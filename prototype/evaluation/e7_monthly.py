"""E7 — monthly review reports: 5 wards x 2 months, qwen3:8b writes, the checker verifies.

Rules compute the facts (arm B vs arm A, same sick calls); GenAI only writes the text.
  python3 -m evaluation.e7_monthly [--model qwen3:8b]
Outputs results/e7_monthly_reports.jsonl (facts, text, check) and results/e7_monthly_summary.md.
"""
from __future__ import annotations

import argparse
import json
import sys

from evaluation import stats as _stats
from llm.monthly import compute_month_facts, write_report
from llm.ollama_client import OLLAMA_URL, is_available
from sim.ward import load_json

SEEDS = range(5)
MONTHS = (1, 2)


def _rd():
    return _stats.RESULTS_DIR


def summary_markdown(rows: list[dict]) -> str:
    valid = [r for r in rows if r["report"] is not None]
    ok = [r for r in valid if r["check"]["verified"]]
    lat = sorted(r["latency_ms"] for r in valid)
    lines = ["# E7 — Monthly review reports (rules compute, GenAI writes, checker verifies)", "",
             f"Model: {rows[0]['model']}. {len(rows)} reports (5 wards x 2 months).", "",
             "| Valid output | Fact check passed | Median latency (s) |", "|---|---|---|",
             f"| {len(valid)}/{len(rows)} | {len(ok)}/{len(valid)} | {lat[len(lat) // 2] / 1000:.1f} |" if lat else "| 0 | – | – |",
             "", "The fact check verifies that every number is in the facts, that 'from X to Y' / 'X vs. Y' wording "
             "matches the direction of the numbers, and that named nurses carry their own numbers. It does not "
             "judge whether the discussion points are wise.", ""]
    for r in rows:
        f = r["facts"]
        lines += [f"## Ward {f['ward']}, month {f['month']} — {r['check']['status']}", ""]
        if r["report"] is None:
            lines += [f"_No report: {r['error']}_", ""]
            continue
        lines += [r["report"]["summary"], ""] + [f"{i}. {p}" for i, p in enumerate(r["report"]["discussion_points"], 1)]
        issues = r["check"]["unsupported_numbers"] + r["check"]["direction_errors"] + r["check"]["nurse_errors"]
        lines += ([""] + [f"> Flagged: {', '.join(map(str, issues))}"] if issues else []) + [""]
    return "\n".join(lines)


def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=90)
    args = ap.parse_args()
    if not is_available():
        print(f"Ollama is not reachable at {OLLAMA_URL}.")
        sys.exit(2)
    rd = _rd()
    expl_path = rd / f"e6_explanations_{args.model.replace(':', '-')}.jsonl"
    expl = [json.loads(x) for x in expl_path.read_text().splitlines() if x.strip()] if expl_path.exists() else None
    rows = []
    for seed in SEEDS:
        for month in MONTHS:
            facts = compute_month_facts(seed, month, policy, explanation_rows=expl)
            r = write_report(facts, args.model, args.timeout)
            rows.append({"seed": seed, "month": month, "model": args.model, **r})
            print(f"ward {seed + 1} month {month}: {r['check']['status']} {r['latency_ms']}ms", flush=True)
    with (rd / "e7_monthly_reports.jsonl").open("w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in rows)
    (rd / "e7_monthly_summary.md").write_text(summary_markdown(rows))
    print(summary_markdown(rows)[:600])


if __name__ == "__main__":
    main()
