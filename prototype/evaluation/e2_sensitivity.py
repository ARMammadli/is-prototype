"""E2 — sensitivity and ablation of the strain-aware effect (spec §6)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.ward import load_json

# (name, policy_overrides, absence_rate, ward_overrides)
CONFIGS = [
    ("default", {}, None, {}),
    ("w_qr_x0.5", {"weights_scale": {"QR": 0.5}}, None, {}),
    ("w_qr_x2", {"weights_scale": {"QR": 2}}, None, {}),
    ("forward_7d", {"forward_days": 7}, None, {}),
    ("forward_14d", {"forward_days": 14}, None, {}),
    ("linear_cost", {"squared": False}, None, {}),
    ("absence_3pct", {}, 0.03, {}),
    ("absence_8pct", {}, 0.08, {}),
    ("no_base_qr", {}, None, {"base_qr_pref": 0.0}),
]
E2_METRICS = ["gini_strain", "top10_qr_share", "QR_total", "max_qr", "nurses_qr_ge3_28d",
              "unfilled", "changes_per_repair"]

def make_policy(overrides: dict) -> dict:
    p = load_json("policy.json")
    scale = overrides.get("weights_scale", {})
    p["weights"] = {k: v * scale.get(k, 1) for k, v in p["weights"].items()}
    for k in ("forward_days", "squared"):
        if k in overrides:
            p[k] = overrides[k]
    return p

def baseline_name(rate, ward_ov: dict) -> str:
    return f"baseline@{rate}|{sorted(ward_ov.items())}"

def run_one(job) -> dict:
    config, policy_name, seed, overrides, rate, ward_ov = job
    ward_cfg = {**load_json("ward.json"), **ward_ov} if ward_ov else None
    res = run_scenario(seed, policy_name, make_policy(overrides), absence_rate=rate, ward_cfg=ward_cfg)
    # Always measure with the default weights so every configuration is comparable.
    row = run_metrics(res, load_json("policy.json")["weights"])
    row.update(config=config, policy=policy_name, seed=seed, rate=rate if rate is not None else -1)
    return row

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    # One baseline per unique (absence rate, ward overrides) key, on the same seeds.
    keys = {}
    for _, _, r, wo in CONFIGS:
        keys.setdefault(baseline_name(r, wo), (r, wo))
    jobs = [(name, "baseline", s, {}, r, wo) for name, (r, wo) in keys.items() for s in range(args.seeds)]
    jobs += [(name, "strain", s, ov, r, wo) for name, ov, r, wo in CONFIGS for s in range(args.seeds)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        runs = pd.DataFrame(list(ex.map(run_one, jobs, chunksize=4)))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs.to_csv(RESULTS_DIR / "e2_runs.csv", index=False)
    tables = []
    for name, _, r, wo in CONFIGS:
        pair = runs[runs.config.isin([name, baseline_name(r, wo)])]
        tables.append(paired_table(pair, E2_METRICS).assign(config=name))
    stats = pd.concat(tables, ignore_index=True)
    stats.to_csv(RESULTS_DIR / "e2_stats.csv", index=False)
    print(stats[stats.metric.isin(["gini_strain", "unfilled"])].to_string(index=False))

if __name__ == "__main__":
    main()
