"""E1 — paired policy A/B: ORTEC-like baseline vs strain-aware (spec §6)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.strain import nurse_metrics, strain
from sim.ward import load_json

E1_METRICS = ["unfilled", "no_senior_shifts", "QR_total", "N_total", "LR_total", "OT_total",
              "SN_total", "gini_strain", "top10_qr_share", "max_qr", "nurses_qr_ge3_28d", "gini_sn",
              "changes_per_repair", "nurses_disturbed", "repair_share_qr",
              "qr_base_roster", "qr_base_kept", "qr_from_repairs"]


def run_one(job):
    seed, policy_name = job
    policy = load_json("policy.json")
    res = run_scenario(seed, policy_name, policy)
    row = run_metrics(res, policy["weights"])
    row.update(seed=seed, policy=policy_name)
    nurses = []
    for n in res.ward.nurses:
        m = nurse_metrics(res.final, n.id, 0, res.ward.days - 1)
        nurses.append({"seed": seed, "policy": policy_name, "nurse": n.id, "QR": m["QR"],
                       "strain": strain(m, policy["weights"])})
    return row, nurses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    jobs = [(s, p) for s in range(args.seeds) for p in ("baseline", "strain")]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        out = list(ex.map(run_one, jobs, chunksize=4))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs = pd.DataFrame([r for r, _ in out])
    runs.to_csv(RESULTS_DIR / "e1_runs.csv", index=False)
    pd.DataFrame([x for _, ns in out for x in ns]).to_csv(RESULTS_DIR / "e1_nurses.csv", index=False)
    stats = paired_table(runs, E1_METRICS)
    stats.to_csv(RESULTS_DIR / "e1_stats.csv", index=False)
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
