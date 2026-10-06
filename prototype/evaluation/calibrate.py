"""Calibration report: base roster fully staffed, ~2-8 direct-fill candidates per absence (spec §3)."""
from __future__ import annotations

import time

from sim.engine import Scenario, run_scenario
from sim.metrics import understaffed
from sim.policies import generate_candidates
from sim.strain import nurse_metrics
from sim.ward import load_json


def calibration_rows(seeds) -> list[dict]:
    rows = []
    for seed in seeds:
        sc = Scenario(seed)
        gaps = understaffed(sc.base)
        qr = sum(nurse_metrics(sc.base, n.id, 0, sc.ward.days - 1)["QR"] for n in sc.ward.nurses)
        direct, total, events = [], [], 0
        while (ctx := sc.next_context()) is not None:
            events += 1
            opts = generate_candidates(ctx)
            direct.append(sum(o.kind == "direct" for o in opts))
            total.append(len(opts))
            if opts:
                sc.apply(ctx, opts[0])
            else:
                sc.mark_unfilled(ctx)
        rows.append({"seed": seed, "base_gaps": gaps, "events": events,
                     "mean_direct": sum(direct) / max(1, len(direct)),
                     "mean_options": sum(total) / max(1, len(total)),
                     "base_qr_per_nurse": qr / len(sc.ward.nurses)})
    return rows


def main() -> None:
    rows = calibration_rows(range(10))
    for r in rows:
        print(r)
    t0 = time.perf_counter()
    run_scenario(0, "strain", load_json("policy.json"))
    print(f"one strain-aware run: {time.perf_counter() - t0:.1f}s")
    md = sum(r["mean_direct"] for r in rows) / len(rows)
    print("base gaps zero:", all(r["base_gaps"] == 0 for r in rows), "| mean direct:", round(md, 2))


if __name__ == "__main__":
    main()
