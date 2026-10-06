"""Monthly scheduler-manager review report: rules compute every number, GenAI only writes the text.

A "month" is a 28-day roster period (the synthetic horizon of 56 days = months 1 and 2). The facts
compare the hospital rule (arm B) with today's software (ORTEC-like) on the same ward and sick calls,
and add what the planner did (audit log) and how GenAI's explanations scored (E6 run), when available.
The text is fact-checked like an explanation: every number must come from the facts; no narrative is
shown when GenAI fails.
"""
from __future__ import annotations

import json
import re
import time

from llm.checker import DOMAIN_NUMBERS, _ID, _NUM, _SENT, _norm, canon_nurse, direction_errors
from llm.ollama_client import chat_json
from llm.plain import plainify
from sim.engine import run_scenario
from sim.strain import qr_transitions

MONTH_DAYS = 28
REASON_WORDS = {"local_knowledge": "local knowledge", "preference": "nurse preference",
                "skill_mix": "skill mix", "other": "other"}

MONTHLY_SYSTEM_PROMPT = """You write the monthly roster review for a hospital ward's scheduler and manager.
You receive JSON with facts for one 4-week month on one ward. All numbers were computed by the roster
system; the hospital rule (which ranks sick-call repairs by the hospital's fairness formula) is
compared with today's software (fewest changes) on the same sick calls.
Write:
- summary: 4 to 6 short sentences (at most 130 words) for the review meeting: what the rule achieved
  on quick returns (back at work after less than 11 hours' rest) and on nurses with 3 or more quick
  returns, what it cost in last-minute call-ins and shift changes, how the planner used the system
  (accepted or overridden choices, if any are logged), and how reliable GenAI's explanations were
  (if given).
- discussion_points: exactly 3 short, concrete points for the meeting. If quick_returns_in_original_roster
  is high, suggest fixing those quick returns in next month's base roster, because then fewer
  last-minute call-ins are needed. If some nurses carry many last-minute call-ins, suggest spreading them.
Rules:
- Only use numbers that appear in the JSON, exactly as written (percentages are in pct_change).
- rule_vs_todays_software tells you, for every measure, whether the rule's number is lower, higher or
  the same. Use exactly that direction: 'fewer'/'lower' only for lower, 'more'/'higher' only for higher.
  When you compare two numbers, write the rule's number first: "56 vs. 96".
- When you name nurses with a number, use each nurse's own number from the JSON.
- Describe what the planner did only from 'planner'. If it has a note, repeat that nothing was logged;
  never claim the planner accepted or overrode anything that is not counted there.
- Write '%' only after a number taken from pct_change or pass_rate_pct; other numbers are counts.
- Refer to nurses only by their codes as given; never blame individuals.
- Never speculate about health, burnout, sickness causes, motivation or private circumstances.
- Plain words for managers: say 'quick return', 'last-minute call-in', 'shift change'."""

MONTHLY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "discussion_points": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
    },
    "required": ["summary", "discussion_points"],
}


def month_window(month: int, days: int) -> tuple[int, int]:
    lo = (month - 1) * MONTH_DAYS
    return lo, min(days - 1, lo + MONTH_DAYS - 1)


def _side(res, lo: int, hi: int) -> dict:
    ward, final = res.ward, res.final
    qr = {n.id: sum(1 for _, d2 in qr_transitions(final, n.id) if lo <= d2 <= hi) for n in ward.nurses}
    sn = {n.id: sum(1 for d in final.short_notice[n.id] if lo <= d <= hi) for n in ward.nurses}
    recs = [r for r in res.records if lo <= r.day <= hi]
    filled = [r for r in recs if r.chosen is not None]
    return {
        "quick_returns": sum(qr.values()),
        "nurses_3plus_quick_returns": sum(1 for v in qr.values() if v >= 3),
        "max_quick_returns_one_nurse": max(qr.values(), default=0),
        "last_minute_call_ins": sum(sn.values()),
        "shift_changes_per_sick_call": round(sum(len(r.changes) for r in filled) / len(filled), 2) if filled else 0.0,
        "nurses_whose_shifts_changed": len({c.nurse for r in filled for c in r.changes}),
        "unfilled_shifts": len(recs) - len(filled),
        "_qr": qr, "_sn": sn,
    }


def _pct(a: float, b: float) -> int | None:
    return round(100 * (a - b) / b) if b else None


def _top(counts: dict, key: str, k: int = 3) -> list[dict]:
    items = sorted(((v, n) for n, v in counts.items() if v > 0), key=lambda x: (-x[0], x[1]))[:k]
    return [{"nurse": n, key: v} for v, n in items]


def _audit_facts(entries: list[dict], seed: int, lo: int, hi: int) -> dict:
    rows = [e for e in entries if e.get("seed") == seed and e.get("mode") == "strain"
            and isinstance(e.get("day"), int) and lo <= e["day"] <= hi]
    reasons: dict[str, int] = {}
    for e in rows:
        if e.get("override_reason"):
            w = REASON_WORDS.get(e["override_reason"], e["override_reason"])
            reasons[w] = reasons.get(w, 0) + 1
    status = [e.get("explanation_status") for e in rows]
    out = {"decisions_by_planner": len(rows),
            "accepted_rule_choice": sum(1 for e in rows if e.get("rank") == 1),
            "overridden": sum(1 for e in rows if e.get("rank") != 1),
            "override_reasons": reasons,
            "explanations_verified": status.count("verified"),
            "explanations_flagged": status.count("mismatch"),
            "explanations_unavailable": sum(1 for s in status if s in ("unavailable", "not ready", None))}
    if not rows:
        out["note"] = NO_PLANNER_NOTE
    return out


NO_PLANNER_NOTE = ("No planner decisions were logged for this month, so nothing is known about accepts or "
                   "overrides; in the simulation the rule's top choice was applied every time.")


def compute_month_facts(seed: int, month: int, policy: dict, audit_entries: list[dict] | None = None,
                        explanation_rows: list[dict] | None = None) -> dict:
    """Deterministic facts for one ward-month: rule (B) vs today's software (A), same sick calls."""
    rule, ortec = run_scenario(seed, "strain", policy), run_scenario(seed, "baseline", policy)
    lo, hi = month_window(month, rule.ward.days)
    r, o = _side(rule, lo, hi), _side(ortec, lo, hi)
    base_qr = sum(1 for n in rule.ward.nurses for _, d2 in qr_transitions(rule.base, n.id) if lo <= d2 <= hi)
    keys = [k for k in r if not k.startswith("_")]
    facts = {
        "ward": seed + 1, "month": month, "days": f"{lo + 1}-{hi + 1}",
        "sick_calls": sum(1 for x in rule.records if lo <= x.day <= hi),
        "hospital_rule": {k: r[k] for k in keys},
        "todays_software": {k: o[k] for k in keys},
        "rule_vs_todays_software": {k: ("lower" if r[k] < o[k] else "higher" if r[k] > o[k] else "the same")
                                    for k in keys},
        "pct_change": {k: _pct(r[k], o[k]) for k in ("quick_returns", "nurses_3plus_quick_returns",
                                                     "last_minute_call_ins")},
        "quick_returns_in_original_roster": base_qr,
        "most_last_minute_call_ins": _top(r["_sn"], "last_minute_call_ins"),
        "most_quick_returns": _top(r["_qr"], "quick_returns"),
    }
    facts["planner"] = _audit_facts(audit_entries or [], seed, lo, hi)
    if explanation_rows:
        days = {x.event_id: x.day for x in rule.records}
        rows = [e for e in explanation_rows if e.get("seed") == seed and lo <= days.get(e.get("event_id"), -1) <= hi]
        if rows:
            ok = sum(1 for e in rows if e.get("verified"))
            facts["genai_explanations"] = {"explained": len(rows), "passed_fact_check": ok,
                                           "flagged": len(rows) - ok,
                                           "pass_rate_pct": round(100 * ok / len(rows))}
    return facts


def _allowed(facts) -> set:
    out = set(DOMAIN_NUMBERS) | {"3", "4", "1", "2"}

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            n = _norm(abs(x))
            if n is not None:
                out.add(n)
        elif isinstance(x, str):
            out.update(n for n in (_norm(v) for v in _NUM.findall(x)) if n is not None)
    walk(facts)
    return out


_VS = re.compile(r"(?:(\d+(?:\.\d+)?)%?\s*(?:vs\.?|versus|compared (?:with|to)|against)\s*(\d+(?:\.\d+)?)"
                 r"|from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?))", re.I)
_DOWN_W = re.compile(r"\b(fewer|less|lower\w*|reduc\w*|decreas\w*|drop\w*|fell|cut\w*|declin\w*)\b", re.I)
_UP_W = re.compile(r"\b(more|higher|increas\w*|rais\w*|ris\w*|rose|grew|added|extra)\b", re.I)
_NURSE = re.compile(r"\bnurse[ _]?0*\d+\b", re.I)


def versus_errors(text: str) -> list[str]:
    """'fewer call-ins (74 vs. 42)': the nearest direction word before 'X vs. Y' must match X vs Y."""
    text = re.sub(r"\bvs\.", "vs", text, flags=re.I)  # 'vs.' is not a sentence end
    out = []
    start = 0
    for end in [m.end() for m in _SENT.finditer(text)] + [len(text)]:
        sent, start = text[start:end], end
        for m in _VS.finditer(sent):
            a, b = (float(m.group(1)), float(m.group(2))) if m.group(1) else (float(m.group(4)), float(m.group(3)))  # from X to Y: after, before
            if a == b:
                continue
            words = [(w.start(), "down") for w in _DOWN_W.finditer(sent[:m.start()])]
            words += [(w.start(), "up") for w in _UP_W.finditer(sent[:m.start()])]
            if words and (max(words)[1] == "down") != (a < b):
                out.append(m.group(0))
    return out


def nurse_number_errors(text: str, facts: dict) -> list[str]:
    """A sentence naming listed nurses with numbers must use each nurse's own number."""
    vals: dict[str, set] = {}
    for key in ("most_last_minute_call_ins", "most_quick_returns"):
        for row in facts.get(key, []):
            vals.setdefault(row["nurse"], set()).update(_norm(v) for k, v in row.items() if k != "nurse")
    out = []
    start = 0
    for end in [m.end() for m in _SENT.finditer(text)] + [len(text)]:
        sent, start = text[start:end], end
        nums = {_norm(x) for x in _NUM.findall(_NURSE.sub(" ", sent))}
        if not nums:
            continue
        for m in _NURSE.finditer(sent):
            n = canon_nurse(m.group(0))
            if n in vals and not (vals[n] & nums):
                out.append(f"{n}: {sorted(nums)}")
    return out


def check_report(report, facts: dict) -> dict:
    """Every number must be in the facts; 'from X to Y' and 'X vs. Y' wording must match the numbers;
    named nurses must carry their own numbers. Never raises."""
    empty = {"unsupported_numbers": [], "direction_errors": [], "nurse_errors": [], "verified": False}
    if not isinstance(report, dict):
        return {**empty, "status": "unavailable"}
    try:
        text = " ".join([report.get("summary") or ""] + list(report.get("discussion_points") or []))
        allowed = _allowed(facts)
        unsupported = [x for x in _NUM.findall(_ID.sub(" ", text)) if _norm(x) is None or _norm(x) not in allowed]
        dirs = direction_errors(text) + versus_errors(text)
        pcts = {_norm(abs(v)) for v in facts.get("pct_change", {}).values() if v is not None}
        g = facts.get("genai_explanations") or {}
        if "pass_rate_pct" in g:
            pcts.add(_norm(g["pass_rate_pct"]))
        unsupported += [f"{x}%" for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", text) if _norm(x) not in pcts]
        nurses = nurse_number_errors(text, facts)
    except Exception:  # junk model output must never break the endpoint
        return {**empty, "status": "mismatch"}
    ok = not unsupported and not dirs and not nurses
    return {"unsupported_numbers": unsupported, "direction_errors": dirs, "nurse_errors": nurses,
            "verified": ok, "status": "verified" if ok else "mismatch"}


def public_facts(facts: dict) -> dict:
    return {k: v for k, v in facts.items() if not k.startswith("_")}


def write_report(facts: dict, model: str, timeout: float) -> dict:
    t0 = time.perf_counter()
    out, error = chat_json(MONTHLY_SYSTEM_PROMPT, json.dumps(public_facts(facts), separators=(",", ":")),
                           MONTHLY_SCHEMA, model, timeout)
    if out is None and error is None:
        error = "empty output"
    if out is not None and not (isinstance(out, dict) and isinstance(out.get("summary"), str)
                                and isinstance(out.get("discussion_points"), list)
                                and all(isinstance(p, str) for p in out["discussion_points"])):
        error, out = "invalid output shape", None
    report = ({"summary": plainify(out["summary"]), "discussion_points": [plainify(p) for p in out["discussion_points"]]}
              if out else None)
    return {"report": report, "source": model if out else "unavailable", "error": error,
            "latency_ms": round((time.perf_counter() - t0) * 1000), "facts": public_facts(facts),
            "check": check_report(out, facts)}
