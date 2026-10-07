"""E8: the rule writes the facts, GenAI writes the wording.

Same 400 arm-B decisions as E6 (seeds 0-4, events with >=2 options). For each, a deterministic fact block
is rendered from the data and GenAI writes 1-2 framing sentences from only the fact block and the policy
text. The E6 fact check runs unchanged on the displayed text (fact block + framing), plus a new check that
flags any number or nurse code in the framing that is not in the fact block.

  python3 -m evaluation.e8_factblock gate                      # fact block alone must pass the E6 check
  python3 -m evaluation.e8_factblock explain --model qwen3:8b  # resumable
  python3 -m evaluation.e8_factblock summary
"""
from __future__ import annotations

import argparse
import json
import random
import sys

import pandas as pd

from evaluation.e6_arms import SEEDS, _rd, collect_b_payloads
from llm.checker import check_explanation
from llm.factblock import fact_block_errors, fact_block_text
from llm.ollama_client import OLLAMA_URL, is_available
from llm.service import explain_decision
from sim.ward import load_json

ERROR_TYPES = {
    "unsupported_numbers": "Number not in the data",
    "direction_errors": "'from X to Y' direction",
    "nurse_direction_errors": "Nurse up/down wording",
    "comparison_errors": "Today's software / cost / unknown nurse",
    "fact_block_errors": "Number or nurse not in fact block (new)",
}


def _path(model: str):
    return _rd() / f"e8_factblock_{model.replace(':', '-')}.jsonl"


def all_payloads() -> list[tuple[int, int, dict]]:
    policy = load_json("policy.json")
    return [(sd, eid, p) for sd in SEEDS for eid, p in collect_b_payloads(sd, policy)]


def gate() -> int:
    """Number of decisions whose fact block alone fails the unchanged E6 check (must be 0)."""
    bad = 0
    for _, _, p in all_payloads():
        t = fact_block_text(p)
        if not check_explanation({"claims": [], "text": t}, p)["verified"] or fact_block_errors(t, t):
            bad += 1
    return bad


def run(model: str, timeout: float) -> None:
    path = _path(model)
    done = set()
    if path.exists():
        done = {(r["seed"], r["event_id"]) for r in map(json.loads, path.read_text().splitlines()) if r}
    items = all_payloads()
    with path.open("a") as fh:
        for i, (sd, eid, p) in enumerate(items):
            if (sd, eid) in done:
                continue
            r = explain_decision(p, model, timeout, variant="e8")
            c = r["check"]
            fh.write(json.dumps({
                "seed": sd, "event_id": eid, "model": model, "error": r["error"], "latency_ms": r["latency_ms"],
                "valid": r["explanation"] is not None, "status": c["status"], "verified": c["verified"],
                **{k: c.get(k, []) for k in ERROR_TYPES},
                "same_as_ortec": p["decision"]["same_as_todays_software"], "chosen": p["decision"]["chosen"],
                "fact_block": r["fact_block"], "framing": r["framing"], "text": r["display_text"]}) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(items)} seed {sd} event {eid} {c['status']} {r['latency_ms']}ms", flush=True)


def summarise(rows: pd.DataFrame) -> dict:
    v = rows[rows.valid]
    out = {"model": rows.model.iloc[0], "n_decisions": len(rows), "valid_output_rate": float(rows.valid.mean()),
           "fact_check_pass_rate": float(v.verified.mean()),
           "pass_same_as_ortec": float(v[v.same_as_ortec].verified.mean()),
           "pass_differs": float(v[~v.same_as_ortec].verified.mean()),
           "mean_latency_s": float(v.latency_ms.mean() / 1000)}
    for k in ERROR_TYPES:
        out[f"rate_{k}"] = float((v[k].map(len) > 0).mean())
    return out


def hand_check_sample(rows: pd.DataFrame, n: int = 15, seed: int = 0) -> pd.DataFrame:
    """Fixed random draw of passing explanations where the rule and today's software differ."""
    pool = rows[rows.verified & ~rows.same_as_ortec].sort_values(["seed", "event_id"])
    idx = sorted(random.Random(seed).sample(list(pool.index), min(n, len(pool))))
    return pool.loc[idx]


def write_summary(model: str) -> str:
    rows = pd.DataFrame([json.loads(x) for x in _path(model).read_text().splitlines() if x.strip()])
    s = summarise(rows)
    pd.DataFrame([s]).to_csv(_rd() / "e8_factblock_summary.csv", index=False)
    old = pd.read_csv(_rd() / "e6_explanations_summary.csv").iloc[0]
    lines = ["# E8: rule writes the facts, GenAI writes the wording", "",
             f"Same {s['n_decisions']} arm-B decisions as E6 (seeds 0-4), model {s['model']}. The E6 fact check is "
             "unchanged and runs on the displayed text (fact block + framing); a new check also flags any number "
             "or nurse code in the framing that is not in the fact block. The fact block alone passes the E6 "
             "check in 400 of 400 decisions (gate run before any model call). The framing has no claims list, so "
             "the claims part of the E6 check is trivially clean here.", "",
             "| | E6 v2 (GenAI writes facts + wording) | E8 (rule writes facts, GenAI wording) |", "|---|---|---|",
             f"| Valid output | {old.valid_output_rate:.1%} | {s['valid_output_rate']:.1%} |",
             f"| Fact-check pass | {old.fact_check_pass_rate:.1%} | {s['fact_check_pass_rate']:.1%} |",
             f"| Pass, same pick as today's software | 93% | {s['pass_same_as_ortec']:.1%} |",
             f"| Pass, different pick | 64% | {s['pass_differs']:.1%} |",
             f"| Seconds per explanation | {old.mean_latency_s:.1f} | {s['mean_latency_s']:.1f} |", "",
             "Share of valid explanations with each error type (one explanation can have several):", "",
             "| Error type | E8 |", "|---|---|"]
    lines += [f"| {lab} | {s['rate_' + k]:.1%} |" for k, lab in ERROR_TYPES.items()]
    lines += ["", "Pilot gate: fact-check pass >= 95% " + ("met." if s["fact_check_pass_rate"] >= 0.95 else "NOT met."), ""]
    md = "\n".join(lines)
    (_rd() / "e8_factblock_summary.md").write_text(md)
    return md


def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gate", "explain", "summary", "sample"])
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=policy["eval_timeout_s"])
    args = ap.parse_args()
    if args.cmd == "gate":
        bad = gate()
        print(f"fact block fails the E6 check in {bad} of 400 decisions")
        sys.exit(1 if bad else 0)
    elif args.cmd == "explain":
        if not is_available():
            print(f"Ollama is not reachable at {OLLAMA_URL}.")
            sys.exit(2)
        run(args.model, args.timeout)
    elif args.cmd == "sample":
        rows = pd.DataFrame([json.loads(x) for x in _path(args.model).read_text().splitlines() if x.strip()])
        for _, r in hand_check_sample(rows).iterrows():
            print(f"--- seed {r.seed} event {r.event_id}\nFACTS: {' '.join(r.fact_block)}\nGENAI: {r.framing}\n")
    else:
        print(write_summary(args.model))


if __name__ == "__main__":
    main()
