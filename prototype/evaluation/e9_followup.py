"""E9: follow-up on E8 (accuracy accounting, check v3, load fact, template, small fixes).

Same 400 arm-B decisions (seeds 0-4). Nothing here changes thresholds, seeds, ward data or the 95% gate.

  python3 -m evaluation.e9_followup accounting      # item 1: one label per E8 explanation
  python3 -m evaluation.e9_followup rescore         # item 2: check v3 on the saved E8 outputs (no LLM call)
  python3 -m evaluation.e9_followup score-load      # item 3: score the saved load-fact run (variant removed in E10)
  python3 -m evaluation.e9_followup template        # item 4: deterministic template, no GenAI
  python3 -m evaluation.e9_followup small           # items 6 and 7
  python3 -m evaluation.e9_followup run-monthly     # item 5: same 10 month facts as E7, split rule/GenAI (LLM)
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from io import StringIO

import pandas as pd

from evaluation.e6_arms import _rd
from evaluation.e8_factblock import all_payloads
from llm.factblock import (LOAD_CLAIM, check_v3, fact_block_text, load_comparison, render_fact_block,
                           render_load_fact, role_errors)

# Hand labels from the E8 manual reads (results/e8_manual_reads.md), fixed before check v3 was written.
FLAGGED_WRONG = {(0, 2), (1, 46), (4, 15)}  # of the 30 E8 failures; the other 27 are true statements
SCAN_WRONG = {(0, 42), (0, 61), (1, 20), (1, 30), (1, 32), (1, 42), (1, 79), (2, 17), (2, 42), (2, 64), (3, 30),
              (3, 68), (3, 81), (4, 8), (4, 12), (4, 14), (4, 53)}
AUDIT_1 = [(0, 29), (1, 8), (1, 55), (1, 78), (2, 10), (2, 22), (2, 53), (2, 74), (3, 6), (3, 14), (3, 50),
           (3, 54), (3, 64), (3, 67), (4, 26)]
AUDIT_1_WRONG = {(3, 14)}


def _rows(name: str) -> list[dict]:
    return [json.loads(x) for x in (_rd() / name).read_text().splitlines() if x.strip()]


def _payloads() -> dict:
    return {(sd, eid): p for sd, eid, p in all_payloads()}


# --- item 1 ---------------------------------------------------------------------------------------

def accounting() -> pd.DataFrame:
    P = _payloads()
    out = []
    for r in _rows("e8_factblock_qwen3-8b.jsonl"):
        k = (r["seed"], r["event_id"])
        p, fr = P[k], r["framing"] or ""
        role_check = role_errors(fr, p)  # check v3's role part; every flag it raises on E8 was read by hand
        role_wrong = k in FLAGGED_WRONG | SCAN_WRONG | AUDIT_1_WRONG or bool(role_check)
        has_load = bool(LOAD_CLAIM.search(fr.replace("fairness policy", "policy")))
        verdict = load_comparison(p)["verdict"]
        load_false = has_load and verdict == "rule_higher"
        if r["verified"]:
            label = ("pass_wrong_role" if role_wrong else "pass_false_load_line" if load_false
                     else "pass_no_known_error")
        else:
            label = "flagged_wrong" if (role_wrong or load_false) else "flagged_true"
        out.append({"seed": k[0], "event_id": k[1], "e8_pass": r["verified"], "label": label,
                    "role_wrong": role_wrong, "role_found_by": ("hand" if k in FLAGGED_WRONG | SCAN_WRONG | AUDIT_1_WRONG
                                                               else "check_v3" if role_check else ""),
                    "has_load_line": has_load, "load_verdict": verdict, "load_false": load_false,
                    "audited": k in AUDIT_1})
    df = pd.DataFrame(out)
    df.to_csv(_rd() / "e9_accounting_labels.csv", index=False)
    return df


def accounting_md(df: pd.DataFrame) -> str:
    c = df.label.value_counts().to_dict()
    g = lambda k: c.get(k, 0)  # noqa: E731
    n = len(df)
    ok_truth = g("pass_no_known_error") + g("flagged_true")
    strict = int(((df.label.isin(["pass_no_known_error", "flagged_true"])) & ~df.has_load_line).sum())
    unaudited = int(((df.label == "pass_no_known_error") & ~df.audited).sum())
    lines = [
        "## Item 1: accuracy accounting for E8 (each explanation counted once)", "",
        "| Step | Count |", "|---|---|",
        f"| Explanations | {n} |",
        f"| Passed the E8 fact check | {int(df.e8_pass.sum())} |",
        f"| - passed, but a nurse's role or direction is wrong | {g('pass_wrong_role')} |",
        f"| - passed, only error is a false 'load/burden' line | {g('pass_false_load_line')} |",
        f"| = passed, no known error | {g('pass_no_known_error')} |",
        f"| Flagged by the E8 check | {int((~df.e8_pass).sum())} |",
        f"| - flagged and really wrong | {g('flagged_wrong')} |",
        f"| = flagged but true | {g('flagged_true')} |", "",
        f"(a) Fact-check pass rate (what the 95% gate measures): {df.e8_pass.sum()}/{n} = {df.e8_pass.mean():.1%}.", "",
        f"(b) Estimated true accuracy, truth-based: (passed with no known error + flagged but true) / all = "
        f"({g('pass_no_known_error')} + {g('flagged_true')}) / {n} = {ok_truth / n:.1%}. This is an upper bound: "
        f"only known errors are subtracted, and {unaudited} of the 'no known error' explanations were never read "
        "by a person (only checked by code and the two-nurse scan).", "",
        f"Strict version: also count every unverifiable 'load/burden' line as an error (load is not in the E8 "
        f"facts): {strict} / {n} = {strict / n:.1%}.", "",
        "Definitions: a 'load/burden' line is false when, among the nurses whose load rises, the most loaded one "
        "before the repair is more loaded in the rule's choice than in today's software's choice. Role errors come "
        "from the hand labels (3 flagged, 17 from the two-nurse scan, 1 from the 15-case audit) plus check v3's "
        "role check, whose every flag on these 400 was read and confirmed by hand.", "",
        "The earlier '85-88%' was not computed step by step. It was a rough judgement from the 17 scan errors and "
        "the load line, and is withdrawn; the numbers above replace it."]
    return "\n".join(lines)


# --- item 2 ---------------------------------------------------------------------------------------

def rescore(src: str, dst: str, load_fact: bool) -> pd.DataFrame:
    P = _payloads()
    rows = []
    for r in _rows(src):
        k = (r["seed"], r["event_id"])
        p = P[k]
        facts = r["fact_block"]
        c = check_v3(r["text"], r["framing"], p, " ".join(facts), load_fact=load_fact)
        rows.append({"seed": k[0], "event_id": k[1], "same_as_ortec": p["decision"]["same_as_todays_software"],
                     "valid": r["framing"] is not None, "pass_e8_check": bool(c.get("verified_v2")),
                     "pass_v3": bool(c["verified_v3"]),
                     "n_old_nurse_dir": len(c.get("nurse_direction_errors", [])),
                     "n_old_nurse_dir_after_exemption": len(c.get("nurse_direction_errors_v3", [])),
                     "role_errors": c.get("role_errors", []), "load_claim_errors": c.get("load_claim_errors", []),
                     "other_errors": (c.get("unsupported_numbers", []) + c.get("direction_errors", [])
                                      + c.get("comparison_errors", []) + c.get("fact_block_errors", [])),
                     "latency_ms": r.get("latency_ms"), "framing": r["framing"]})
    df = pd.DataFrame(rows)
    df.to_json(_rd() / dst, orient="records", lines=True)
    return df


def gold_eval(df: pd.DataFrame) -> dict:
    """Known-wrong vs known-true cases from the hand labels (role part only)."""
    flagged_true = {(r["seed"], r["event_id"]) for r in _rows("e8_factblock_qwen3-8b.jsonl")
                    if not r["verified"]} - FLAGGED_WRONG
    known_true = flagged_true | (set(AUDIT_1) - AUDIT_1_WRONG)
    known_wrong = FLAGGED_WRONG | SCAN_WRONG
    idx = df.set_index(["seed", "event_id"])
    roleflag = lambda k: bool(idx.loc[k, "role_errors"]) or idx.loc[k, "n_old_nurse_dir_after_exemption"] > 0  # noqa: E731
    return {"known_wrong": len(known_wrong), "caught": sum(roleflag(k) for k in known_wrong),
            "known_true": len(known_true), "passed": sum(not roleflag(k) for k in known_true)}


def audit_sample(df: pd.DataFrame, seed: int, n: int = 15, pool_filter=None) -> list[tuple]:
    pool = df[df.pass_v3 & ~df.same_as_ortec] if pool_filter is None else df[pool_filter]
    keys = sorted(zip(pool.seed, pool.event_id))
    return sorted(random.Random(seed).sample(keys, min(n, len(keys))))


def v3_md(df: pd.DataFrame, title: str, old_label: str, old_rate: float) -> str:
    v = df[df.valid]
    rate = lambda m: f"{m.mean():.1%}" if len(m) else "n/a"  # noqa: E731
    lines = [title, "", f"| | {old_label} | Check v3 |", "|---|---|---|",
             f"| Fact-check pass, all | {old_rate:.1%} | {rate(v.pass_v3)} |",
             f"| Same pick as today's software | | {rate(v[v.same_as_ortec].pass_v3)} |",
             f"| Different pick | | {rate(v[~v.same_as_ortec].pass_v3)} |", "",
             "Errors per type (share of valid explanations; one explanation can have several):", "",
             "| Error type | Share |", "|---|---|",
             f"| Old up/down wording check, after the narrow exemption | {(v.n_old_nurse_dir_after_exemption > 0).mean():.1%} |",
             f"| Role check (new) | {(v.role_errors.map(len) > 0).mean():.1%} |",
             f"| Load/burden claim not backed by a fact (new) | {(v.load_claim_errors.map(len) > 0).mean():.1%} |",
             f"| Any other existing check (numbers, from-to, today's software/cost, not in fact block) | "
             f"{(v.other_errors.map(len) > 0).mean():.1%} |"]
    if v.latency_ms.notna().any():
        lines += ["", f"Seconds per explanation: {v.latency_ms.mean() / 1000:.1f}."]
    return "\n".join(lines)


# --- item 3 ---------------------------------------------------------------------------------------

# --- item 4 ---------------------------------------------------------------------------------------

_TPL = {"QR": "a quick return", "N": "a night shift", "LR": "a long run", "OT": "overtime",
        "SN": "a short-notice change"}
_TPL_PL = {"QR": "quick returns", "N": "night shifts", "LR": "long runs", "OT": "overtime",
           "SN": "short-notice changes"}


def _items(d: dict, sign: int) -> str:
    ms = [m for m in d if (d[m] > 0 if sign > 0 else d[m] < 0)]
    return " and ".join(_TPL[m] if abs(d[m]) == 1 or m == "OT" else _TPL_PL[m] for m in ms)


def template_text(p: dict) -> str:
    """Deterministic explanation from the rule's facts only. No numbers except the change counts."""
    o = {x["id"]: x for x in p["options"]}
    dec = p["decision"]
    ch, ot = o[dec["chosen"]], o[dec["todays_software"]]
    s = []
    for nd in ch["nurses"]:
        d = {m: nd["after"][m] - nd["before"][m] for m in nd["before"]}
        up, down = _items(d, 1), _items(d, -1)
        if down and up:
            s.append(f"{nd['nurse']} avoids {down} and takes on {up}.")
        elif down:
            s.append(f"{nd['nurse']} avoids {down}.")
        elif up:
            s.append(f"{nd['nurse']} takes on {up}.")
        else:
            s.append(f"{nd['nurse']}'s counts do not change.")
    if dec["same_as_todays_software"]:
        s.append("Today's software would pick the same option.")
        return " ".join(s)
    in_rule = {nd["nurse"]: {m: nd["after"][m] - nd["before"][m] for m in nd["before"]} for nd in ch["nurses"]}
    for nd in ot["nurses"]:
        d = {m: nd["after"][m] - nd["before"][m] for m in nd["before"]}
        if in_rule.get(nd["nurse"]) == d:
            continue  # same for this nurse in both choices: nothing to contrast
        up, down = _items(d, 1), _items(d, -1)
        what = (f"avoid {down} and take on {up}" if up and down else f"take on {up}" if up
                else f"avoid {down}" if down else "have no count changes")
        s.append(f"With today's software's choice, {nd['nurse']} would instead {what}.")
    s.append(f"Nurses changed: {ch['n_changes']} with the rule's choice, {ot['n_changes']} with today's software's.")
    return " ".join(s)


def run_template() -> pd.DataFrame:
    rows = []
    for sd, eid, p in all_payloads():
        t0 = time.perf_counter()
        facts = render_fact_block(p) + render_load_fact(p)
        txt = template_text(p)
        ms = (time.perf_counter() - t0) * 1000
        c = check_v3(" ".join(facts) + " " + txt, txt, p, " ".join(facts), load_fact=True)
        rows.append({"seed": sd, "event_id": eid, "same_as_ortec": p["decision"]["same_as_todays_software"],
                     "pass_v3": bool(c["verified_v3"]), "ms": ms, "template": txt,
                     "errors": c.get("role_errors", []) + c.get("load_claim_errors", [])
                     + c.get("nurse_direction_errors_v3", []) + c.get("comparison_errors", [])
                     + c.get("unsupported_numbers", []) + c.get("direction_errors", [])
                     + c.get("fact_block_errors", [])})
    df = pd.DataFrame(rows)
    df.to_json(_rd() / "e9_template.jsonl", orient="records", lines=True)
    return df


# --- items 6 and 7 --------------------------------------------------------------------------------

def small_fixes() -> str:
    old = pd.read_csv(StringIO(subprocess.run(["git", "show", "c3385cf:prototype/results/e6_runs.csv"],
                                              capture_output=True, text=True, check=True).stdout))
    now = pd.read_csv(_rd() / "e6_runs.csv")
    a_old = old[old.arm == "A"].reset_index(drop=True)
    a_now = now[now.arm == "A"].reset_index(drop=True)
    same = a_old[a_now.columns].equals(a_now) and sorted(old[old.arm == "C"].seed) == sorted(a_now.seed)
    c = old[old.arm == "C"].set_index("seed")
    a = a_now.set_index("seed")
    ms = ["QR_total", "nurses_qr_ge3_28d", "max_qr", "unfilled", "SN_total", "changes_per_repair", "gini_sn"]
    lines = ["## Item 6: GenAI-chooser arm (arm C, from git history c3385cf)", "",
             f"Seeds and A rows identical to the current E6 run: {same}.", "", "| Measure | Arm C mean | C better than A (wards) | equal |",
             "|---|---|---|---|"]
    for m in ms:
        lines.append(f"| {m} | {c[m].mean():.3f} | {int((c[m] < a.loc[c.index, m]).sum())} | "
                     f"{int((c[m] == a.loc[c.index, m]).sum())} |")
    e2 = pd.read_csv(_rd() / "e2_runs.csv")
    lines += ["", "## Item 7: quick returns created by repairs vs already in the base roster (E2 robustness runs, 50 wards per row)", "",
              "| Absence | Policy | QR total | Kept from base roster | Created by repairs | Share created by repairs | QR_total = kept + created |",
              "|---|---|---|---|---|---|---|"]
    for cfg, label in (("absence_3pct", "3%"), ("absence_8pct", "8%")):
        for pol in ("baseline", "strain"):
            if pol == "baseline":
                d = e2[e2.config == f"baseline@{0.03 if label == '3%' else 0.08}|[]"]
            else:
                d = e2[(e2.config == cfg) & (e2.policy == "strain")]
            if not len(d):
                continue
            ok = bool((d.QR_total == d.qr_base_kept + d.qr_from_repairs).all())
            lines.append(f"| {label} | {'ORTEC-like' if pol == 'baseline' else 'Rule'} | {d.QR_total.mean():.1f} | "
                         f"{d.qr_base_kept.mean():.1f} | {d.qr_from_repairs.mean():.1f} | "
                         f"{(d.qr_from_repairs.sum() / d.QR_total.sum()):.1%} | {ok} (n={len(d)}) |")
    return "\n".join(lines)


def run_monthly(model: str, timeout: float) -> str:
    """Item 5: the facts are the exact saved facts of the E7 run (7/10), so before/after compare the same input."""
    from llm.monthly import write_report_split
    rows = []
    for old in _rows("e7_monthly_reports.jsonl"):
        r = write_report_split(old["facts"], model, timeout)
        rows.append({"seed": old["seed"], "month": old["month"], "model": model, "e7_status": old["check"]["status"], **r})
        print(f"ward {old['seed'] + 1} month {old['month']}: {r['check']['status']} {r['latency_ms']}ms", flush=True)
    (_rd() / "e9_monthly_split.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    ok = sum(r["check"]["verified"] for r in rows)
    lines = ["## Item 5: monthly report, rule writes every number, GenAI writes the words", "",
             f"Same 10 ward-months and identical facts as E7. Before (E7): 7/10 passed. After: {ok}/10 passed. "
             f"Median time {sorted(r['latency_ms'] for r in rows)[5] / 1000:.1f} s.", ""]
    for r in rows:
        lines += [f"### Ward {r['seed'] + 1}, month {r['month']}: {r['check']['status']} (E7: {r['e7_status']})", ""]
        if r["report"]:
            lines += [r["report"]["summary"], ""] + [f"{i}. {x}" for i, x in enumerate(r["report"]["discussion_points"], 1)]
        issues = (r["check"]["unsupported_numbers"] + r["check"]["direction_errors"] + r["check"]["nurse_errors"]
                  + r["check"].get("fact_block_errors", []))
        lines += ([""] + [f"> Flagged: {', '.join(map(str, issues))}"] if issues else []) + [""]
    md = "\n".join(lines)
    (_rd() / "e9_item5_monthly.md").write_text(md)
    return md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["accounting", "rescore", "score-load", "template", "small", "run-monthly"])
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--timeout", type=float, default=60)
    args = ap.parse_args()
    rd = _rd()
    if args.cmd == "accounting":
        md = accounting_md(accounting())
        (rd / "e9_item1_accounting.md").write_text(md)
        print(md)
    elif args.cmd == "rescore":
        df = rescore("e8_factblock_qwen3-8b.jsonl", "e9_rescored_v3.jsonl", load_fact=False)
        g = gold_eval(df)
        md = v3_md(df, "## Item 2: E8 outputs rescored with check v3 (no LLM call; same prompt, temperature 0)",
                   "E8 check", 0.925)
        md += (f"\n\nGold set from the hand labels: check v3 catches {g['caught']} of {g['known_wrong']} known-wrong "
               f"cases and passes {g['passed']} of {g['known_true']} known-true cases (role part).")
        md += f"\n\nNew audit sample (RNG seed 1, passing under v3, different pick): {audit_sample(df, 1)}"
        (rd / "e9_item2_rescore.md").write_text(md)
        print(md)
    elif args.cmd == "score-load":
        df = rescore("e9_loadfact_qwen3-8b.jsonl", "e9_loadfact_scored.jsonl", load_fact=True)
        md = v3_md(df, "## Item 3: rule adds a load fact; GenAI wording; check v3", "E8 (E8 check)", 0.925)
        md += f"\n\nAudit sample (RNG seed 2, passing, different pick): {audit_sample(df, 2)}"
        (rd / "e9_item3_loadfact.md").write_text(md)
        print(md)
    elif args.cmd == "template":
        df = run_template()
        md = (f"## Item 4: template only (no GenAI)\n\nPass rate with check v3 (load fact included): "
              f"{df.pass_v3.mean():.1%} ({int(df.pass_v3.sum())}/{len(df)}). Mean time per explanation: "
              f"{df.ms.mean():.3f} ms (fact block + template rendering; the check is not timed).")
        (rd / "e9_item4_template.md").write_text(md)
        print(md)
        print(df[~df.pass_v3][["seed", "event_id", "errors", "template"]].head(10).to_string())
    elif args.cmd == "run-monthly":
        print(run_monthly(args.model, 90))
    else:
        md = small_fixes()
        (rd / "e9_item6_7_small.md").write_text(md)
        print(md)


if __name__ == "__main__":
    main()
