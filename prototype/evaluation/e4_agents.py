"""E4 — agentic future: nurse agents accept or decline offers (spec §6, Section 8 numbers)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.ward import load_json

MODES = ("today", "permissive", "picky")
E4_METRICS = ["unfilled", "QR_total", "gini_strain", "top10_qr_share", "max_qr", "offers_per_fill"]

def run_one(job) -> dict:
    seed, policy_name, mode = job
    policy = load_json("policy.json")
    row = run_metrics(run_scenario(seed, policy_name, policy, acceptance=mode), policy["weights"])
    row.update(seed=seed, policy=policy_name, mode=mode)
    return row

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    jobs = [(s, p, m) for s in range(args.seeds) for p in ("baseline", "strain") for m in MODES]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        runs = pd.DataFrame(list(ex.map(run_one, jobs, chunksize=4)))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs.to_csv(RESULTS_DIR / "e4_runs.csv", index=False)
    summary = runs.groupby(["mode", "policy"], as_index=False)[E4_METRICS].mean()
    summary.to_csv(RESULTS_DIR / "e4_summary.csv", index=False)
    stats = pd.concat([paired_table(runs[runs["mode"] == m], E4_METRICS).assign(mode=m) for m in MODES],
                      ignore_index=True)
    stats.to_csv(RESULTS_DIR / "e4_stats.csv", index=False)
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
