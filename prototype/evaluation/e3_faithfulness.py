"""E3 — faithfulness of local-LLM explanations, checked against computed numbers (spec §6)."""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from evaluation.stats import RESULTS_DIR
from llm.ollama_client import OLLAMA_URL, is_available
from llm.prompt import build_payload
from llm.service import explain
from sim.engine import run_scenario
from sim.policies import rank_options
from sim.ward import load_json

def collect_payloads(n: int, policy: dict, start_seed: int = 1000, per_seed: int = 5) -> list[dict]:
    want = {"differ": n // 2, "same": n - n // 2}
    got: dict[str, list[dict]] = {"differ": [], "same": []}
    seed = start_seed
    while any(len(got[k]) < want[k] for k in want) and seed < start_seed + 300:
        bucket: dict[str, list[dict]] = {"differ": [], "same": []}

        def on_event(ctx, scored):
            if len(scored) < 2:
                return
            same = rank_options(scored, "baseline")[0] is rank_options(scored, "strain")[0]
            payload = build_payload(ctx, scored, policy)
            payload["_stratum"] = "same" if same else "differ"
            bucket[payload["_stratum"]].append(payload)

        run_scenario(seed, "strain", policy, on_event=on_event)
        rng = np.random.default_rng(seed)
        for k in want:
            items = bucket[k]
            take = min(per_seed, len(items), want[k] - len(got[k]))
            if take > 0:
                got[k].extend(items[i] for i in rng.choice(len(items), size=take, replace=False))
        seed += 1
    return got["differ"] + got["same"]

def summarize(rows: list[dict], model: str) -> dict:
    df = pd.DataFrame(rows)
    llm = df[df.source != "template"]
    nan = float("nan")
    claims = llm.claims_total.sum()
    flagged = (llm.claims_false > 0) | (llm.n_unsupported > 0)
    return {
        "model": model, "n": len(df), "n_llm": len(llm),
        "json_valid_rate": float((df.source != "template").mean()),
        # LLM-only: template fallbacks are verified by construction and would inflate these.
        "claim_accuracy": (float(1 - llm.claims_false.sum() / claims) if claims else 1.0) if len(llm) else nan,
        "pct_flagged": float(flagged.mean()) if len(llm) else nan,
        "pct_direction_error": float((llm["n_direction_errors"] > 0).mean()) if len(llm) and "n_direction_errors" in llm else nan,
        "recommendation_agreement": float(llm.recommendation_correct.mean()) if len(llm) else nan,
        "tradeoff_correct": float(llm.tradeoff_correct.mean()) if len(llm) else nan,
        "latency_p50_ms": float(llm.latency_ms.median()) if len(llm) else float("nan"),
        "latency_p95_ms": float(llm.latency_ms.quantile(0.95)) if len(llm) else float("nan"),
        "fallback_rate": float((df.source == "template").mean()),
    }

def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=policy["eval_timeout_s"])
    args = ap.parse_args()
    if not is_available():
        print(f"Ollama is not reachable at {OLLAMA_URL}. Start it with `ollama serve` and run "
              f"`ollama pull {args.model}` first.")
        sys.exit(2)
    payloads = collect_payloads(args.n, policy)
    tag = args.model.replace(":", "-")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"e3_explanations_{tag}.jsonl"
    rows = []
    with out.open("w") as fh:
        for i, p in enumerate(payloads):
            stratum = p.pop("_stratum")
            r = explain(p, args.model, args.timeout)
            c = r["check"]
            row = {"i": i, "stratum": stratum, "model": args.model, "source": r["source"],
                   "latency_ms": r["latency_ms"], "error": r["error"],
                   "claims_total": c["claims_total"], "claims_false": c["claims_false"],
                   "n_unsupported": len(c["unsupported_numbers"]),
                   "n_direction_errors": len(c["direction_errors"]),
                   "recommendation_correct": c["recommendation_correct"],
                   "tradeoff_correct": c["tradeoff_correct"], "verified": c["verified"],
                   "ground_truth": c["ground_truth"],
                   "main_tradeoff": r["explanation"].get("main_tradeoff")}
            rows.append(row)
            fh.write(json.dumps({**row, "text": r["explanation"].get("text"), "payload": p}) + "\n")
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{len(payloads)} done")
    summary = pd.DataFrame([summarize(rows, args.model)] +
                           [dict(summarize([r for r in rows if r["stratum"] == s], args.model), model=f"{args.model} [{s}]")
                            for s in ("differ", "same")])
    summary.to_csv(RESULTS_DIR / f"e3_summary_{tag}.csv", index=False)
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
