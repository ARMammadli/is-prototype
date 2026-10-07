"""E10: GenAI may only restate the rule's fact sentences; the planner sees a GenAI summary only if it passes.

Same 400 arm-B decisions (seeds 0-4), qwen3:8b, temperature 0. The 95% gate is unchanged.
Check: check v3 (spared statements accepted, two-nurse roles checked, unbacked load/fairness claims flagged)
plus any mention of policy, fairness or protecting someone, which the fact block never states.
Display rule: if the check flags a summary, the planner sees the rule's facts only.

  python3 -m evaluation.e10_restate explain     # LLM, resumable
  python3 -m evaluation.e10_restate score       # coverage, error types, the 20-case hand-read sample
  python3 -m evaluation.e10_restate monthly     # LLM, 10 reports, rule's table + GenAI narrative
"""
from __future__ import annotations

import argparse
import json
import random

import pandas as pd

from evaluation.e6_arms import _rd
from evaluation.e8_factblock import all_payloads
from llm.factblock import check_v3
from llm.service import explain_decision

OUT = "e10_restate_qwen3-8b.jsonl"
HAND_READ_SEED = 5  # fixed before the run


def _rows(name):
    return [json.loads(x) for x in (_rd() / name).read_text().splitlines() if x.strip()]


def run(model: str, timeout: float) -> None:
    path = _rd() / OUT
    done = {(r["seed"], r["event_id"]) for r in _rows(OUT)} if path.exists() else set()
    items = all_payloads()
    with path.open("a") as fh:
        for i, (sd, eid, p) in enumerate(items):
            if (sd, eid) in done:
                continue
            r = explain_decision(p, model, timeout, variant="restate")
            fh.write(json.dumps({"seed": sd, "event_id": eid, "model": model, "error": r["error"],
                                 "latency_ms": r["latency_ms"], "fact_block": r["fact_block"],
                                 "framing": r["framing"], "text": r["display_text"]}) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(items)} seed {sd} event {eid} {r['latency_ms']}ms", flush=True)


def score() -> str:
    P = {(sd, eid): p for sd, eid, p in all_payloads()}
    rows = []
    for r in _rows(OUT):
        k = (r["seed"], r["event_id"])
        p = P[k]
        c = check_v3(r["text"], r["framing"], p, " ".join(r["fact_block"]), load_fact=False, policy_claims=True)
        rows.append({"seed": k[0], "event_id": k[1], "same_as_ortec": p["decision"]["same_as_todays_software"],
                     "valid": r["framing"] is not None, "shown": bool(c.get("verified_v3")),
                     "old_dir": c.get("nurse_direction_errors_v3", []), "role": c.get("role_errors", []),
                     "load_policy": c.get("load_claim_errors", []),
                     "other": (c.get("unsupported_numbers", []) + c.get("direction_errors", [])
                               + c.get("comparison_errors", []) + c.get("fact_block_errors", [])),
                     "latency_ms": r["latency_ms"], "framing": r["framing"]})
    d = pd.DataFrame(rows)
    d.to_json(_rd() / "e10_restate_scored.jsonl", orient="records", lines=True)
    v = d[d.valid]
    shown = d[d.shown]
    keys = sorted(zip(shown.seed, shown.event_id))
    sample = sorted(random.Random(HAND_READ_SEED).sample(keys, min(20, len(keys))))
    share = lambda col: f"{(v[col].map(len) > 0).mean():.1%}"  # noqa: E731
    md = "\n".join([
        "# E10: GenAI restates the rule's facts only; flagged summaries are hidden", "",
        f"Valid output: {d.valid.mean():.1%}. Coverage (GenAI summary shown): {len(shown)}/{len(d)} = {len(shown) / len(d):.1%} "
        f"(same pick as today's software: {d[d.same_as_ortec].shown.mean():.1%}; different pick: "
        f"{d[~d.same_as_ortec].shown.mean():.1%}). Seconds per explanation: {v.latency_ms.mean() / 1000:.1f}.", "",
        "| Flag type (share of valid summaries) | Share |", "|---|---|",
        f"| Role check (two-nurse sentences included) | {share('role')} |",
        f"| Old up/down wording, after the 'spared' exemption | {share('old_dir')} |",
        f"| Unbacked load / fairness / policy claim | {share('load_policy')} |",
        f"| Numbers, from-to, today's software or cost, not in fact block | {share('other')} |", "",
        f"Hand-read sample (RNG seed {HAND_READ_SEED}, 20 of the shown summaries): {sample}"])
    (_rd() / "e10_summary.md").write_text(md)
    return md


def monthly(model: str) -> str:
    from llm.monthly import write_report_table
    rows = []
    for old in _rows("e7_monthly_reports.jsonl"):  # identical facts to E7 and E9
        r = write_report_table(old["facts"], model, 90)
        rows.append({"seed": old["seed"], "month": old["month"], "model": model, **r})
        print(f"ward {old['seed'] + 1} month {old['month']}: {r['check']['status']} {r['latency_ms']}ms", flush=True)
    (_rd() / "e10_monthly_table.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    ok = sum(r["check"]["verified"] for r in rows)
    lines = ["# E10 monthly: rule's table + GenAI narrative (restate only)", "",
             f"Fact check passed: {ok}/10. Median seconds: {sorted(r['latency_ms'] for r in rows)[5] / 1000:.1f}.", ""]
    for r in rows:
        c = r["check"]
        lines += [f"## Ward {r['seed'] + 1}, month {r['month']}: {c['status']}", ""]
        if r["report"]:
            lines += [r["report"]["summary"], ""] + [f"{i}. {x}" for i, x in enumerate(r["report"]["discussion_points"], 1)]
        issues = (c["unsupported_numbers"] + c["direction_errors"] + c["nurse_errors"] + c.get("fact_block_errors", [])
                  + c.get("policy_claim_errors", []))
        lines += ([""] + [f"> Flagged: {', '.join(map(str, issues))}"] if issues else []) + [""]
    md = "\n".join(lines)
    (_rd() / "e10_monthly_summary.md").write_text(md)
    return md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["explain", "score", "monthly"])
    ap.add_argument("--model", default="qwen3:8b")
    args = ap.parse_args()
    if args.cmd == "explain":
        run(args.model, 60)
    elif args.cmd == "score":
        print(score())
    else:
        print(monthly(args.model))


if __name__ == "__main__":
    main()
