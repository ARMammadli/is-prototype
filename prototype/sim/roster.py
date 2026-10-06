"""Roster container and greedy base-roster generator (spec §3)."""
from __future__ import annotations

from collections import Counter

import numpy as np

from sim.rules import nurse_violations
from sim.ward import SHIFT_CODES, SHIFT_HOURS, Ward


class Roster:
    """Assignments nurse -> day -> shift, plus repair bookkeeping."""

    def __init__(self, ward: Ward) -> None:
        self.ward = ward
        self.by_nurse: dict[str, dict[int, str]] = {n.id: {} for n in ward.nurses}
        self.by_slot: dict[tuple[int, str], set[str]] = {
            (d, s): set() for d in range(ward.days) for s in SHIFT_CODES
        }
        self.short_notice: dict[str, list[int]] = {n.id: [] for n in ward.nurses}
        self.added: set[tuple[str, int]] = set()

    def get(self, nid: str, day: int) -> str | None:
        return self.by_nurse[nid].get(day)

    def assign(self, nid: str, day: int, shift: str) -> None:
        old = self.by_nurse[nid].get(day)
        if old is not None:
            self.by_slot[(day, old)].discard(nid)
        self.by_nurse[nid][day] = shift
        self.by_slot[(day, shift)].add(nid)

    def unassign(self, nid: str, day: int) -> str | None:
        old = self.by_nurse[nid].pop(day, None)
        if old is not None:
            self.by_slot[(day, old)].discard(nid)
        return old

    def staff(self, day: int, shift: str) -> set[str]:
        return self.by_slot[(day, shift)]

    def has_senior(self, day: int, shift: str) -> bool:
        return any(self.ward.nurse(n).senior for n in self.by_slot[(day, shift)])

    def shifts_of(self, nid: str) -> list[tuple[int, str]]:
        return sorted(self.by_nurse[nid].items())

    def copy(self) -> "Roster":
        r = Roster.__new__(Roster)
        r.ward = self.ward
        r.by_nurse = {k: dict(v) for k, v in self.by_nurse.items()}
        r.by_slot = {k: set(v) for k, v in self.by_slot.items()}
        r.short_notice = {k: list(v) for k, v in self.short_notice.items()}
        r.added = set(self.added)
        return r


def generate_base_roster(ward: Ward, rng: np.random.Generator) -> Roster:
    """Greedy, seeded, rule-respecting base roster; prioritises nurses furthest below contract."""
    roster = Roster(ward)
    leave_days = Counter(nid for nid, _ in ward.leave)
    target = {n.id: n.weekly_hours / 7 * (ward.days - leave_days[n.id]) for n in ward.nurses}
    worked = {n.id: 0.0 for n in ward.nurses}
    for day in range(ward.days):
        progress = (day + 1) / ward.days
        for shift in SHIFT_CODES:
            while len(roster.staff(day, shift)) < ward.demand[shift]:
                nid = _pick(roster, day, shift, target, worked, progress, rng)
                if nid is None:
                    break
                roster.assign(nid, day, shift)
                worked[nid] += SHIFT_HOURS[shift]
    return roster


def _pick(roster, day, shift, target, worked, progress, rng):
    ward = roster.ward
    pool = [
        n for n in ward.nurses
        if roster.get(n.id, day) is None
        and (n.id, day) not in ward.leave
        and (shift != "N" or n.night_ok)
    ]
    noise = rng.random(len(pool))
    def creates_qr(nid):
        prev = roster.get(nid, day - 1)
        return (shift == "D" and prev == "E") or (shift == "E" and prev == "N")

    order = sorted(
        range(len(pool)),
        key=lambda i: -(target[pool[i].id] * progress - worked[pool[i].id] + noise[i]
                        + (ward.base_qr_pref * 36.0 if creates_qr(pool[i].id) else 0.0)),
    )
    passes = [True, False] if not roster.has_senior(day, shift) else [False]
    for senior_only in passes:
        for i in order:
            n = pool[i]
            if senior_only and not n.senior:
                continue
            roster.assign(n.id, day, shift)
            ok = not nurse_violations(roster, n.id, ward.leave, day - 8, day + 1)
            roster.unassign(n.id, day)
            if ok:
                return n.id
    return None
