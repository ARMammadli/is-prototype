"""Exogenous, seeded absence stream (spec §3): ~5.33% of rostered shifts, short notice."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.ward import shift_start


@dataclass(frozen=True, order=True)
class AbsenceEvent:
    reveal_time: float
    day: int
    nurse: str
    event_id: int
    notice_h: float


def generate_absences(base, cfg: dict, rng: np.random.Generator) -> list[AbsenceEvent]:
    rostered = sorted((nid, d) for nid, days in base.by_nurse.items() for d in days)
    target = round(cfg["absence_rate"] * len(rostered))
    absent: set[tuple[str, int]] = set()
    raw: list[tuple[float, int, str, float]] = []
    guard = 0
    while len(absent) < target and guard < 100_000:
        guard += 1
        nid, d = rostered[int(rng.integers(len(rostered)))]
        if (nid, d) in absent:
            continue
        length = int(rng.choice(cfg["spell_lengths"], p=cfg["spell_probs"]))
        if rng.random() < cfg["short_notice_frac"]:
            notice = float(rng.uniform(1, 12))
        else:
            notice = float(rng.uniform(12, 48))
        reveal = shift_start(d, base.get(nid, d)) - notice
        for dd in range(d, d + length):
            shift = base.get(nid, dd)
            if shift is None or (nid, dd) in absent:
                continue
            absent.add((nid, dd))
            raw.append((reveal, dd, nid, shift_start(dd, shift) - reveal))
    raw.sort()
    return [AbsenceEvent(r, dd, nid, i, n) for i, (r, dd, nid, n) in enumerate(raw)]
