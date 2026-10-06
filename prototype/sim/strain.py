"""Per-nurse strain metrics and the weighted strain score (spec §3)."""
from __future__ import annotations

from sim.rules import QR_REST
from sim.ward import SHIFT_HOURS, shift_end, shift_start

METRICS = ("QR", "N", "LR", "OT", "SN")
TRADEOFF_NAMES = {"QR": "quick_returns", "N": "nights", "LR": "long_runs",
                  "OT": "overtime", "SN": "short_notice"}
TRADEOFFS = tuple(TRADEOFF_NAMES.values()) + ("stability", "concentration")
SHORT_NOTICE_H = 48.0
LONG_RUN = 6


def window(day: int, days: int, back: int = 28, forward: int = 28) -> tuple[int, int]:
    return max(0, day - back), min(days - 1, day + forward)


def expected_hours(ward, nid: str, lo: int, hi: int) -> float:
    leave = sum(1 for d in range(lo, hi + 1) if (nid, d) in ward.leave)
    return ward.nurse(nid).weekly_hours / 7 * (hi - lo + 1 - leave)


def qr_transitions(roster, nid: str) -> list[tuple[int, int]]:
    items = roster.shifts_of(nid)
    return [
        (d1, d2)
        for (d1, s1), (d2, s2) in zip(items, items[1:])
        if shift_start(d2, s2) - shift_end(d1, s1) < QR_REST
    ]


def _runs(days: list[int]) -> list[tuple[int, int]]:
    runs, start, prev = [], None, None
    for d in days:
        if prev is not None and d == prev + 1:
            prev = d
            continue
        if prev is not None:
            runs.append((start, prev))
        start = prev = d
    if prev is not None:
        runs.append((start, prev))
    return runs


def nurse_metrics(roster, nid: str, lo: int, hi: int) -> dict:
    items = roster.shifts_of(nid)
    qr = sum(1 for _, d2 in qr_transitions(roster, nid) if lo <= d2 <= hi)
    nights = sum(1 for d, s in items if lo <= d <= hi and s == "N")
    lr = sum(1 for a, b in _runs([d for d, _ in items]) if b - a + 1 >= LONG_RUN and b >= lo and a <= hi)
    worked = sum(SHIFT_HOURS[s] for d, s in items if lo <= d <= hi)
    ot = max(0.0, worked - expected_hours(roster.ward, nid, lo, hi))
    sn = sum(1 for d in roster.short_notice[nid] if lo <= d <= hi)
    return {"QR": qr, "N": nights, "LR": lr, "OT": round(ot, 1), "SN": sn}


def strain(metrics: dict, weights: dict) -> float:
    return float(sum(weights[k] * metrics[k] for k in METRICS))
