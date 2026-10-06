"""Run-level evaluation metrics (spec §6, E1)."""
from __future__ import annotations

import math

from sim.strain import nurse_metrics, qr_transitions, strain
from sim.ward import SHIFT_CODES


def gini(values) -> float:
    x = sorted(float(v) for v in values)
    n, total = len(x), sum(x)
    if n == 0 or total == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(x))
    return 2 * cum / (n * total) - (n + 1) / n


def top_share(values, frac: float = 0.1) -> float:
    x = sorted((float(v) for v in values), reverse=True)
    total = sum(x)
    if total == 0:
        return 0.0
    k = max(1, math.ceil(len(x) * frac))
    return sum(x[:k]) / total


def understaffed(roster) -> int:
    ward = roster.ward
    return sum(max(0, ward.demand[s] - len(roster.staff(d, s)))
               for d in range(ward.days) for s in SHIFT_CODES)


def max_qr_in_28d(roster, nid: str) -> int:
    days = [d2 for _, d2 in qr_transitions(roster, nid)]
    return max((sum(1 for e in days[i:] if e < d + 28) for i, d in enumerate(days)), default=0)


def run_metrics(result, weights: dict) -> dict:
    ward, final = result.ward, result.final
    per = {n.id: nurse_metrics(final, n.id, 0, ward.days - 1) for n in ward.nurses}
    strains = [strain(m, weights) for m in per.values()]
    qr = [m["QR"] for m in per.values()]
    sn = [m["SN"] for m in per.values()]
    filled = [r for r in result.records if r.chosen is not None]
    total_qr = repair_qr = 0
    for n in ward.nurses:
        for d1, d2 in qr_transitions(final, n.id):
            total_qr += 1
            if (n.id, d1) in final.added or (n.id, d2) in final.added:
                repair_qr += 1
    qr_base_roster = sum(len(qr_transitions(result.base, n.id)) for n in ward.nurses)
    return {
        "n_events": len(result.records),
        "unfilled": len(result.records) - len(filled),
        "no_senior_shifts": sum(1 for d in range(ward.days) for s in SHIFT_CODES
                                if final.staff(d, s) and not final.has_senior(d, s)),
        "QR_total": sum(qr),
        "N_total": sum(m["N"] for m in per.values()),
        "LR_total": sum(m["LR"] for m in per.values()),
        "OT_total": round(sum(m["OT"] for m in per.values()), 1),
        "SN_total": sum(sn),
        "gini_strain": gini(strains),
        "top10_qr_share": top_share(qr),
        "max_qr": max(qr),
        "nurses_qr_ge3_28d": sum(1 for n in ward.nurses if max_qr_in_28d(final, n.id) >= 3),
        "gini_sn": gini(sn),
        "changes_per_repair": (sum(len(r.changes) for r in filled) / len(filled)) if filled else 0.0,
        "nurses_disturbed": len({c.nurse for r in filled for c in r.changes}),
        "qr_base_roster": qr_base_roster,
        "qr_from_repairs": repair_qr,
        "qr_base_kept": sum(qr) - repair_qr,
        "repair_share_qr": repair_qr / total_qr if total_qr else 0.0,
        "offers_per_fill": (sum(r.offers for r in filled) / len(filled)) if filled else 0.0,
    }


def plan_scoreboard(roster, ward, weights: dict) -> dict:
    """Full-horizon summary of the CURRENT plan (used for the live ours-vs-ORTEC scoreboard)."""
    per = {n.id: nurse_metrics(roster, n.id, 0, ward.days - 1) for n in ward.nurses}
    return {
        "quick_returns": sum(m["QR"] for m in per.values()),
        "nurses_qr_ge3_28d": sum(1 for n in ward.nurses if max_qr_in_28d(roster, n.id) >= 3),
        "max_load": round(max((strain(m, weights) for m in per.values()), default=0.0), 1),
        "short_notice_calls": sum(m["SN"] for m in per.values()),
        "shifts_changed": len(roster.added),
    }
