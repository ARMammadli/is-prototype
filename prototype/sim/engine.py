"""Scenario runner shared by the app and all evaluations (spec §9)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

import numpy as np

from sim.absences import generate_absences
from sim.agents import accepts
from sim.policies import (RepairContext, apply_option, generate_candidates, rank_options,
                          score_options, ward_strains)
from sim.roster import generate_base_roster
from sim.ward import build_ward, load_json


@dataclass
class EventRecord:
    event_id: int
    day: int
    shift: str
    absent: str
    notice_h: float
    n_options: int
    chosen: str | None
    chosen_rank_baseline: int | None
    chosen_rank_strain: int | None
    changes: tuple
    offers: int
    baseline_top: str | None
    strain_top: str | None
    ai_choice: str | None = None
    ai_agrees: bool | None = None
    ai_fallback: bool = False
    ai_latency_ms: int | None = None
    ai_verified: bool | None = None


@dataclass
class RunResult:
    seed: int
    policy_name: str
    acceptance: str
    ward: object
    base: object
    final: object
    blocked: set
    records: list


class Scenario:
    """One seeded ward with its base roster and absence stream, stepped event by event."""

    def __init__(self, seed: int, ward_cfg: dict | None = None, absence_rate: float | None = None):
        cfg = dict(ward_cfg) if ward_cfg else load_json("ward.json")
        if absence_rate is not None:
            cfg["absence_rate"] = absence_rate
        rng = np.random.default_rng(seed)
        self.seed = seed
        self.cfg = cfg
        self.ward = build_ward(cfg, rng)
        self.base = generate_base_roster(self.ward, rng)
        self.events = generate_absences(self.base, cfg, rng)
        self.roster = self.base.copy()
        self.blocked: set = set(self.ward.leave)
        self._queue = deque(self.events)
        self.unfilled: list[tuple[int, str]] = []

    @property
    def remaining(self) -> int:
        return len(self._queue)

    def peek_event_id(self) -> int | None:
        """Id of the next queued event (None when the queue is empty)."""
        return self._queue[0].event_id if self._queue else None

    def next_context(self, upto_event_id: int | None = None) -> RepairContext | None:
        while self._queue:
            if upto_event_id is not None and self._queue[0].event_id > upto_event_id:
                return None
            ev = self._queue.popleft()
            self.blocked.add((ev.nurse, ev.day))
            shift = self.roster.unassign(ev.nurse, ev.day)
            if shift is None:
                continue
            return RepairContext(ward=self.ward, roster=self.roster, blocked=self.blocked,
                                 day=ev.day, shift=shift, absent=ev.nurse, notice_h=ev.notice_h,
                                 event_id=ev.event_id, seed=self.seed,
                                 reveal_time=ev.reveal_time)
        return None

    def apply(self, ctx: RepairContext, option) -> None:
        apply_option(self.roster, option, ctx.notice_h)

    def mark_unfilled(self, ctx: RepairContext) -> None:
        self.unfilled.append((ctx.day, ctx.shift))


def run_scenario(seed: int, policy_name: str, policy: dict, acceptance: str = "today",
                 ward_cfg: dict | None = None, absence_rate: float | None = None,
                 on_event=None, chooser=None) -> RunResult:
    sc = Scenario(seed, ward_cfg, absence_rate)
    agent_rng = np.random.default_rng(seed + 10_000)
    records = []
    while (ctx := sc.next_context()) is not None:
        scored = score_options(ctx, generate_candidates(ctx), policy)
        if on_event is not None:
            on_event(ctx, scored)
        ai_info: dict = {}
        ai_choice = None
        if policy_name == "ai":
            order = rank_options(scored, "strain")
            if chooser is not None and scored:
                ai_choice, ai_info = chooser(ctx, scored)
                ai_info = ai_info or {}
                pick = [so for so in order if so.option.id == ai_choice]
                if pick:
                    order = pick + [so for so in order if so is not pick[0]]
        else:
            order = rank_options(scored, policy_name)
        med = median(ward_strains(ctx, policy).values()) if acceptance == "picky" else 0.0
        chosen, offers = None, 0
        for so in order:
            offers += 1
            if all(accepts(acceptance, agent_rng, nd, med) for nd in so.nurses):
                chosen = so
                break
        if chosen is not None:
            sc.apply(ctx, chosen.option)
        else:
            sc.mark_unfilled(ctx)
        records.append(EventRecord(
            event_id=ctx.event_id, day=ctx.day, shift=ctx.shift, absent=ctx.absent,
            notice_h=ctx.notice_h, n_options=len(scored),
            chosen=chosen.option.id if chosen else None,
            chosen_rank_baseline=chosen.rank_baseline if chosen else None,
            chosen_rank_strain=chosen.rank_strain if chosen else None,
            changes=chosen.option.changes if chosen else (), offers=offers,
            baseline_top=rank_options(scored, "baseline")[0].option.id if scored else None,
            strain_top=rank_options(scored, "strain")[0].option.id if scored else None,
            ai_choice=ai_choice, ai_agrees=ai_info.get("agrees"),
            ai_fallback=bool(ai_info.get("fallback", False)),
            ai_latency_ms=ai_info.get("latency_ms"), ai_verified=ai_info.get("verified"),
        ))
    return RunResult(seed, policy_name, acceptance, sc.ward, sc.base, sc.roster, sc.blocked, records)
