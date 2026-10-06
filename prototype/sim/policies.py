"""Repair candidates (shared) and the two ranking policies (spec §4)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim.rules import nurse_violations
from sim.strain import (METRICS, SHORT_NOTICE_H, expected_hours, nurse_metrics, strain,
                        window)
from sim.ward import SHIFT_CODES, SHIFT_HOURS

MAX_MOVES = 20
CHECK_RADIUS = 8  # every hard rule is local to +-8 days around a change


@dataclass(frozen=True)
class Change:
    nurse: str
    day: int
    old: str | None
    new: str | None


@dataclass
class Option:
    id: str
    kind: str
    changes: tuple[Change, ...]

    @property
    def n_changes(self) -> int:
        return len(self.changes)

    @property
    def nurses(self) -> list[str]:
        return list(dict.fromkeys(c.nurse for c in self.changes))

    @property
    def extra_nurse(self) -> str:
        """The nurse whose workload increases (direct filler, backfiller, or the mover)."""
        for c in self.changes:
            if c.old is None and c.new is not None:
                return c.nurse
        return self.changes[0].nurse

    @property
    def index(self) -> int:
        return int(self.id.rsplit("_", 1)[1])


@dataclass
class RepairContext:
    ward: object
    roster: object
    blocked: set
    day: int
    shift: str
    absent: str
    notice_h: float
    event_id: int
    seed: int
    reveal_time: float | None = None


@dataclass
class ScoredOption:
    option: Option
    baseline_key: tuple
    cost: float
    nurses: list[dict]
    delta_strain: float
    remaining_h: float
    rank_baseline: int = field(default=0)
    rank_strain: int = field(default=0)


def apply_changes(roster, changes) -> None:
    for c in changes:
        if c.new is None:
            roster.unassign(c.nurse, c.day)
        else:
            roster.assign(c.nurse, c.day, c.new)


def revert_changes(roster, changes) -> None:
    for c in reversed(changes):
        if c.old is None:
            roster.unassign(c.nurse, c.day)
        else:
            roster.assign(c.nurse, c.day, c.old)


def apply_option(roster, option: Option, notice_h: float) -> None:
    apply_changes(roster, option.changes)
    for c in option.changes:
        if c.new is not None:
            roster.added.add((c.nurse, c.day))
            if notice_h < SHORT_NOTICE_H:
                roster.short_notice[c.nurse].append(c.day)


def describe(option: Option) -> str:
    return "; ".join(f"{c.nurse}: {c.old or 'off'} → {c.new or 'off'}" for c in option.changes)


def _feasible(ctx: RepairContext, changes) -> bool:
    apply_changes(ctx.roster, changes)
    try:
        return all(
            not nurse_violations(ctx.roster, c.nurse, ctx.blocked,
                                 ctx.day - CHECK_RADIUS, ctx.day + CHECK_RADIUS)
            for c in changes
        )
    finally:
        revert_changes(ctx.roster, changes)


def _off_duty_ok(ctx: RepairContext, nid: str, shift: str) -> bool:
    ward = ctx.ward
    return (ctx.roster.get(nid, ctx.day) is None
            and (nid, ctx.day) not in ctx.blocked
            and (nid, ctx.day) in ward.available
            and (shift != "N" or ward.nurse(nid).night_ok))


def generate_candidates(ctx: RepairContext, max_moves: int = MAX_MOVES) -> list[Option]:
    """All feasible direct fills plus up to max_moves one-hop moves; identical for both policies."""
    ward, roster, d, s = ctx.ward, ctx.roster, ctx.day, ctx.shift
    direct = []
    for n in ward.nurses:
        if _off_duty_ok(ctx, n.id, s):
            ch = (Change(n.id, d, None, s),)
            if _feasible(ctx, ch):
                direct.append(ch)
    backfill: dict[str, list[str]] = {}
    moves = []
    for t in SHIFT_CODES:
        if t == s:
            continue
        staff_t = roster.staff(d, t)
        for x in sorted(staff_t):
            if s == "N" and not ward.nurse(x).night_ok:
                continue
            move = Change(x, d, t, s)
            if not _feasible(ctx, (move,)):
                continue
            remaining = staff_t - {x}
            keeps_senior = (not ward.nurse(x).senior) or any(ward.nurse(r).senior for r in remaining)
            if len(remaining) >= ward.demand[t] and keeps_senior:
                moves.append((move,))
                continue
            if t not in backfill:
                backfill[t] = [
                    n.id for n in ward.nurses
                    if _off_duty_ok(ctx, n.id, t) and _feasible(ctx, (Change(n.id, d, None, t),))
                ]
            for y in backfill[t]:
                if not keeps_senior and not ward.nurse(y).senior:
                    continue
                moves.append((move, Change(y, d, None, t)))
    if not roster.has_senior(d, s):
        sen_direct = [ch for ch in direct if ward.nurse(ch[0].nurse).senior]
        sen_moves = [ch for ch in moves if ward.nurse(ch[0].nurse).senior]
        if sen_direct or sen_moves:
            direct, moves = sen_direct, sen_moves
    if len(moves) > max_moves:
        rng = np.random.default_rng([ctx.seed, ctx.event_id])
        keep = sorted(rng.choice(len(moves), size=max_moves, replace=False).tolist())
        moves = [moves[i] for i in keep]
    combos = [("direct", ch) for ch in direct] + [("move", ch) for ch in moves]
    if not roster.has_senior(d, s):
        senior_only = [(k, ch) for k, ch in combos if ward.nurse(ch[0].nurse).senior]
        if senior_only:
            combos = senior_only
    return [Option(f"Option_{i + 1}", kind, ch) for i, (kind, ch) in enumerate(combos)]


def _period(day: int, days: int) -> tuple[int, int]:
    lo = (day // 28) * 28
    return lo, min(days - 1, lo + 27)


def period_hours(roster, nid: str, day: int) -> float:
    lo, hi = _period(day, roster.ward.days)
    return sum(SHIFT_HOURS[s] for d, s in roster.shifts_of(nid) if lo <= d <= hi)


def remaining_hours(roster, nid: str, day: int) -> float:
    lo, hi = _period(day, roster.ward.days)
    return expected_hours(roster.ward, nid, lo, hi) - period_hours(roster, nid, day)


def score_options(ctx: RepairContext, options: list[Option], policy: dict) -> list[ScoredOption]:
    weights = policy["weights"]
    squared = policy.get("squared", True)
    lo, hi = window(ctx.day, ctx.ward.days, policy.get("back_days", 28), policy.get("forward_days", 28))
    short = ctx.notice_h < SHORT_NOTICE_H
    lacks_senior = not ctx.roster.has_senior(ctx.day, ctx.shift)
    scored = []
    for opt in options:
        nids = opt.nurses
        before = {n: nurse_metrics(ctx.roster, n, lo, hi) for n in nids}
        rem = remaining_hours(ctx.roster, opt.extra_nurse, ctx.day)
        apply_changes(ctx.roster, opt.changes)
        try:
            after = {n: nurse_metrics(ctx.roster, n, lo, hi) for n in nids}
        finally:
            revert_changes(ctx.roster, opt.changes)
        details, cost, delta = [], 0.0, 0.0
        for n in nids:
            a = dict(after[n])
            if short:
                a["SN"] += 1
            sb, sa = strain(before[n], weights), strain(a, weights)
            cost += (sa * sa - sb * sb) if squared else (sa - sb)
            delta += sa - sb
            details.append({"nurse": n, "before": before[n], "after": a,
                            "strain_before": round(sb, 2), "strain_after": round(sa, 2)})
        senior_flag = 1 if lacks_senior and not ctx.ward.nurse(opt.changes[0].nurse).senior else 0
        key = (opt.n_changes, -round(rem, 2), senior_flag)
        scored.append(ScoredOption(opt, key, cost, details, round(delta, 2), round(rem, 1)))
    for rank, so in enumerate(sorted(scored, key=lambda x: (x.baseline_key, x.option.index)), 1):
        so.rank_baseline = rank
    for rank, so in enumerate(sorted(scored, key=lambda x: (round(x.cost, 6), x.baseline_key,
                                                           x.option.index)), 1):
        so.rank_strain = rank
    return scored


def rank_options(scored: list[ScoredOption], policy_name: str) -> list[ScoredOption]:
    if policy_name == "baseline":
        return sorted(scored, key=lambda s: s.rank_baseline)
    if policy_name == "strain":
        return sorted(scored, key=lambda s: s.rank_strain)
    raise ValueError(f"unknown policy {policy_name!r}")


def ward_strains(ctx: RepairContext, policy: dict) -> dict[str, float]:
    lo, hi = window(ctx.day, ctx.ward.days, policy.get("back_days", 28), policy.get("forward_days", 28))
    return {n.id: strain(nurse_metrics(ctx.roster, n.id, lo, hi), policy["weights"])
            for n in ctx.ward.nurses}
