"""E6 — arms rerun for "rule ranks, GenAI explains, planner decides" (handoff §4).

Same 5 wards (seeds 0-4), same base rosters, sick calls and seeds for every arm:
  A  ORTEC-like       fewest changes, most contract hours left
  B  rule-ranked      hospital formula (main design); GenAI only explains, never changes the choice
  B_sn3 / B_sn6       sensitivity: weight on short-notice changes ("disturb as few people") 1.5 -> 3 -> 6

Subcommands:
  python3 -m evaluation.e6_arms arms                       # A/B/C + sensitivity (seconds)
  python3 -m evaluation.e6_arms explain --model qwen3:8b   # B explanations, resumable (~10 s per decision)
  python3 -m evaluation.e6_arms summary                    # CSV + markdown table from the above
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from evaluation import stats as _stats
from llm.ollama_client import OLLAMA_URL, is_available
from llm.prompt import build_explain_payload
from llm.service import explain_decision
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.ward import load_json

SEEDS = range(5)
METRICS = ["QR_total", "nurses_qr_ge3_28d", "max_qr", "unfilled", "SN_total", "changes_per_repair", "gini_sn"]
LABELS = {"QR_total": "Quick returns", "nurses_qr_ge3_28d": "Nurses with 3+ QR in 28 d",
          "max_qr": "Max QR, one nurse", "unfilled": "Unfilled shifts", "SN_total": "Short-notice changes",
          "changes_per_repair": "Changes per repair", "gini_sn": "Gini of short-notice changes"}
ARM_NAMES = {"A": "A. ORTEC-like", "B": "B. Rule-ranked (main)",
             "B_sn3": "B with SN weight 3", "B_sn6": "B with SN weight 6"}


def _rd():
    return _stats.RESULTS_DIR  # looked up at call time so tests can monkeypatch it


def run_arms(seeds=SEEDS) -> pd.DataFrame:
    policy = load_json("policy.json")
    rows = []
    for seed in seeds:
        for arm, name, pol in [
            ("A", "baseline", policy),
            ("B", "strain", policy),
            ("B_sn3", "strain", {**policy, "weights": {**policy["weights"], "SN": 3.0}}),
            ("B_sn6", "strain", {**policy, "weights": {**policy["weights"], "SN": 6.0}}),
        ]:
            res = run_scenario(seed, name, pol)
            row = run_metrics(res, policy["weights"])  # same weights for every arm's metrics
            row.update(seed=seed, arm=arm)
            rows.append(row)
    return pd.DataFrame(rows)


# --- B explanations ---------------------------------------------------------------------------

def collect_b_payloads(seed: int, policy: dict) -> list[tuple[int, dict]]:
    """Explain-payloads along arm B's own trajectory (events with >=2 options)."""
    out = []

    def on_event(ctx, scored):
        if len(scored) >= 2:
            out.append((ctx.event_id, build_explain_payload(ctx, scored, policy)))
    run_scenario(seed, "strain", policy, on_event=on_event)
    return out


def run_explanations(model: str, timeout: float, seeds=SEEDS) -> None:
    policy = load_json("policy.json")
    tag = model.replace(":", "-")
    path = _rd() / f"e6_explanations_{tag}.jsonl"
    done = set()
    if path.exists():
        done = {(r["seed"], r["event_id"]) for r in map(json.loads, path.read_text().splitlines()) if r}
    with path.open("a") as fh:
        for seed in seeds:
            items = collect_b_payloads(seed, policy)
            for i, (eid, p) in enumerate(items):
                if (seed, eid) in done:
                    continue
                r = explain_decision(p, model, timeout)
                c = r["check"]
                fh.write(json.dumps({
                    "seed": seed, "event_id": eid, "model": model, "source": r["source"], "error": r["error"],
                    "latency_ms": r["latency_ms"], "valid": r["explanation"] is not None,
                    "status": c["status"], "verified": c["verified"], "claims_total": c["claims_total"],
                    "claims_false": c["claims_false"], "n_unsupported": len(c["unsupported_numbers"]),
                    "n_direction_errors": len(c["direction_errors"]) + len(c["nurse_direction_errors"]),
                    "direction_errors": c["direction_errors"] + c["nurse_direction_errors"],
                    "same_as_ortec": p["decision"]["same_as_todays_software"],
                    "chosen": p["decision"]["chosen"], "text": r["display_text"]}) + "\n")
                fh.flush()
                print(f"seed {seed} {i + 1}/{len(items)} {c['status']} {r['latency_ms']}ms", flush=True)


def rescore(model: str) -> None:
    """Re-run the (newer) comparison check on saved explanation texts; no LLM calls.

    Keeps the first-pass result as verified_v1 and adds n_comparison_errors."""
    from llm.checker import comparison_errors
    policy = load_json("policy.json")
    path = _rd() / f"e6_explanations_{model.replace(':', '-')}.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    pay = {(sd, eid): p for sd in SEEDS for eid, p in collect_b_payloads(sd, policy)}
    for r in rows:
        r.setdefault("verified_v1", r["verified"])
        errs = comparison_errors(r["text"], pay[(r["seed"], r["event_id"])]) if r["valid"] else []
        r["comparison_errors"], r["n_comparison_errors"] = errs, len(errs)
        r["verified"] = bool(r["verified_v1"] and not errs)
        r["status"] = "verified" if r["verified"] else ("mismatch" if r["valid"] else "unavailable")
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def explanation_summary(rows: pd.DataFrame) -> dict:
    valid = rows[rows.valid]
    return {"model": rows.model.iloc[0], "n_decisions": len(rows),
            "valid_output_rate": float(rows.valid.mean()),
            "fact_check_pass_rate": float(valid.verified.mean()) if len(valid) else float("nan"),
            "direction_error_rate": float((valid.n_direction_errors > 0).mean()) if len(valid) else float("nan"),
            "comparison_error_rate": (float((valid.n_comparison_errors > 0).mean())
                                      if len(valid) and "n_comparison_errors" in valid else float("nan")),
            "fact_check_pass_rate_v1": (float(valid.verified_v1.mean())
                                        if len(valid) and "verified_v1" in valid else float("nan")),
            "unsupported_number_rate": float((valid.n_unsupported > 0).mean()) if len(valid) else float("nan"),
            "false_claim_rate": float((valid.claims_false > 0).mean()) if len(valid) else float("nan"),
            "mean_latency_s": float(valid.latency_ms.mean() / 1000) if len(valid) else float("nan")}


# --- Summary ----------------------------------------------------------------------------------

def _fmt(v, metric):
    return f"{v:.3f}" if metric == "gini_sn" else f"{v:.2f}" if metric == "changes_per_repair" else f"{v:.1f}"


def summary_markdown(runs: pd.DataFrame, expl: list[dict]) -> str:
    arms = [a for a in ARM_NAMES if a in set(runs.arm)]
    mean = runs.groupby("arm")[METRICS].mean()
    a = runs[runs.arm == "A"].set_index("seed")
    lines = ["# E6 — Arms rerun: rule ranks, GenAI explains, planner decides", "",
             "Synthetic ward, 5 wards (seeds 0-4), same base rosters and sick calls for every arm. "
             "Mean of 5 wards; lower is better for every metric. "
             "\"x/5\" = wards where the arm is strictly better than A on that metric.", "",
             "| Metric | " + " | ".join(ARM_NAMES[x] for x in arms) + " |",
             "|---|" + "---|" * len(arms)]
    for m in METRICS:
        cells = []
        for arm in arms:
            cell = _fmt(mean.loc[arm, m], m)
            if arm != "A":
                r = runs[runs.arm == arm].set_index("seed")
                cell += f" ({int((r[m] < a.loc[r.index, m]).sum())}/5)"
            cells.append(cell)
        lines.append(f"| {LABELS[m]} | " + " | ".join(cells) + " |")
    lines += [""]
    if expl:
        lines += ["## Arm B explanations (GenAI explains the rule's choice)", "",
                  "| Model | Decisions | Valid output | Fact-check pass | Direction error | Wrong comparison | Mean latency (s) |",
                  "|---|---|---|---|---|---|---|"]
        for e in expl:
            lines.append(f"| {e['model']} | {e['n_decisions']} | {e['valid_output_rate']:.1%} | "
                         f"{e['fact_check_pass_rate']:.1%} | {e['direction_error_rate']:.1%} | "
                         f"{e['comparison_error_rate']:.1%} | {e['mean_latency_s']:.1f} |")
        lines += ["", "Fact-check pass = numbers, claims, up/down wording, nurse codes, and claims about today's "
                  "software and the stated cost all match the data. Two prompts were run on the same 400 decisions and "
                  "re-scored with the same final check: v1 (results/archive_e6_prompt_v1/) 66.2%, v2 (this run, with "
                  "per-option totals and more/fewer/same labels) 66.2%; the prompt change did not raise accuracy. "
                  "When the rule and today's software pick the same option, 93% pass; when they differ, 64%. "
                  "Manual reads: 9 of 25 v1 explanations had errors the first check missed; 7 of 15 passing v2 "
                  "explanations (differ cases) had errors, 3 of which the final check now catches. The check is a "
                  "safety net, not a guarantee: the planner still reads the explanation.", ""]
    return "\n".join(lines)


def write_combined_csv(rd, runs: pd.DataFrame) -> None:
    """One CSV, one row per arm x ward: roster metrics plus (arm B only) explanation metrics per model."""
    out = runs.copy()
    for f in sorted(rd.glob("e6_explanations_*.jsonl")):
        rows = pd.DataFrame([json.loads(x) for x in f.read_text().splitlines() if x.strip()])
        if not len(rows):
            continue
        tag = rows.model.iloc[0].replace(":", "_").replace(".", "_")
        per = {sd: explanation_summary(g) for sd, g in rows.groupby("seed")}
        for k in ("n_decisions", "valid_output_rate", "fact_check_pass_rate", "direction_error_rate", "mean_latency_s"):
            out[f"{tag}_{k}"] = [per[sd][k] if arm == "B" and sd in per else None
                                 for arm, sd in zip(out.arm, out.seed)]
    out.to_csv(rd / "e6_arms_by_ward.csv", index=False)


def write_summary() -> str:
    rd = _rd()
    runs = pd.read_csv(rd / "e6_runs.csv")
    expl = []
    for f in sorted(rd.glob("e6_explanations_*.jsonl")):
        rows = pd.DataFrame([json.loads(x) for x in f.read_text().splitlines() if x.strip()])
        if len(rows):
            expl.append(explanation_summary(rows))
    if expl:
        pd.DataFrame(expl).to_csv(rd / "e6_explanations_summary.csv", index=False)
    write_combined_csv(rd, runs)
    md = summary_markdown(runs, expl)
    (rd / "e6_summary.md").write_text(md)
    return md


def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["arms", "explain", "rescore", "summary"])
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=policy["eval_timeout_s"])
    args = ap.parse_args()
    _rd().mkdir(exist_ok=True)
    if args.cmd == "arms":
        df = run_arms()
        cols = ["arm", "seed"] + [c for c in df.columns if c not in ("arm", "seed")]
        df[cols].to_csv(_rd() / "e6_runs.csv", index=False)
        print(df.groupby("arm")[METRICS].mean().to_string())
    elif args.cmd == "explain":
        if not is_available():
            print(f"Ollama is not reachable at {OLLAMA_URL}.")
            sys.exit(2)
        run_explanations(args.model, args.timeout)
    elif args.cmd == "rescore":
        rescore(args.model)
        print(write_summary())
    else:
        print(write_summary())


if __name__ == "__main__":
    main()
