"""Deterministic faithfulness checker for explanations (spec §5)."""
from __future__ import annotations

import math
import re

from sim.strain import METRICS, TRADEOFF_NAMES

OT_TOLERANCE = 0.11
DOMAIN_NUMBERS = {"6", "7", "8", "11", "28", "46", "48"}  # rule constants an explanation may cite
_NUM = re.compile(r"\d+(?:\.\d+)?")
_ID = re.compile(r"\b(?:nurse[ _]?\d+|option[ _]?\d+|N\d+|opt\d+)\b(?!\.\d)", re.I)
_NURSE_REF = re.compile(r"^\s*nurse[ _]?0*(\d+)\s*$", re.I)
_OPTION_REF = re.compile(r"^\s*option[ _]?0*(\d+)\s*$", re.I)


_SENT = re.compile(r"[;!?]|\.(?!\d)")
_FROM_TO = re.compile(r"from (\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)", re.I)
_DIR_VERB = re.compile(r"\b(reduc\w*|lower\w*|decreas\w*|cut\w*|fewer|less|"
                       r"increas\w*|add\w*|rais\w*|more)\b", re.I)
_DOWN = ("reduc", "lower", "decreas", "cut", "fewer", "less")


def direction_errors(text) -> list[str]:
    """Heuristic: the nearest verb can mislead with words like "less" or "more".

    'from A to B' phrases whose nearest preceding verb in the sentence contradicts A vs B."""
    if not isinstance(text, str):
        return []
    out: list[str] = []
    start = 0
    for end in [m.end() for m in _SENT.finditer(text)] + [len(text)]:
        sent = text[start:end]
        start = end
        for m in _FROM_TO.finditer(sent):
            try:
                a, b = float(m.group(1)), float(m.group(2))
            except (ValueError, OverflowError):
                continue
            verbs = _DIR_VERB.findall(sent[:m.start()])
            if not verbs or a == b:
                continue
            down = verbs[-1].lower().startswith(_DOWN)
            if (down and b > a) or (not down and b < a):
                out.append(m.group(0))
    return out


def canon_nurse(value):
    """'Nurse 10' / 'nurse_10' / 'Nurse_010' -> 'Nurse_10'; anything else is returned unchanged."""
    m = _NURSE_REF.match(value) if isinstance(value, str) else None
    if not m:
        return value
    try:
        return f"Nurse_{int(m.group(1)):02d}"
    except (ValueError, OverflowError):
        return value


def canon_option(value):
    """'Option 2' / 'option_2' -> 'Option_2'; anything else is returned unchanged."""
    m = _OPTION_REF.match(value) if isinstance(value, str) else None
    if not m:
        return value
    try:
        return f"Option_{int(m.group(1))}"
    except (ValueError, OverflowError):
        return value


def comparison_pair(payload: dict):
    opts = sorted(payload["options"], key=lambda o: o["rank_strain"])
    top = opts[0]
    base = next((o for o in opts if o["is_baseline_top"]), None)
    if base is not None and base["id"] != top["id"]:
        return top, base
    return top, (opts[1] if len(opts) > 1 else None)


def _increment(opt: dict, metric: str) -> float:
    return sum(nd["after"][metric] - nd["before"][metric] for nd in opt["nurses"])


def ground_truth_tradeoff(payload: dict) -> str:
    top, other = comparison_pair(payload)
    if other is None:
        return "stability"
    w = payload["weights"]
    diffs = {m: w[m] * abs(_increment(other, m) - _increment(top, m)) for m in METRICS}
    best = max(METRICS, key=lambda m: diffs[m])
    if diffs[best] > 0:
        return TRADEOFF_NAMES[best]
    loaded = lambda o: max(nd["strain_before"] for nd in o["nurses"])  # noqa: E731
    return "concentration" if loaded(other) != loaded(top) else "stability"


def _norm(value):
    """Normalise to 2 decimals; None when not a finite number (never raises)."""
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(f):
        return None
    r = round(f, 2)
    return str(int(r)) if r == int(r) else str(r)


def _allowed_numbers(payload: dict) -> set:
    out = set(DOMAIN_NUMBERS)

    def add(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            n = _norm(v)
            if n is not None:
                out.add(n)

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        else:
            add(x)

    walk(payload.get("comparison", {}).get("strain_added", {}) if isinstance(payload.get("comparison"), dict) else {})
    walk(payload.get("comparison", {}).get("metric_added", {}) if isinstance(payload.get("comparison"), dict) else {})
    ev = payload.get("event", {})
    add(ev.get("day"))
    add(ev.get("notice_h"))
    for opt in payload["options"]:
        add(opt.get("delta_strain"))
        add(opt.get("n_changes"))
        for c in opt.get("changes", []):
            add(c.get("day"))
        for nd in opt["nurses"]:
            add(nd.get("strain_before"))
            add(nd.get("strain_after"))
            for side in ("before", "after"):
                for v in nd[side].values():
                    add(v)
    return out


def _matches(record: dict, claim: dict) -> bool:
    metric = claim.get("metric")
    if metric not in METRICS:
        return False
    tol = OT_TOLERANCE if metric == "OT" else 1e-9
    try:
        return (abs(float(record["before"][metric]) - float(claim["before"])) <= tol
                and abs(float(record["after"][metric]) - float(claim["after"])) <= tol)
    except (KeyError, TypeError, ValueError):
        return False


def check_text(text, claims, payload: dict, claim_options=None) -> dict:
    """Claims + numbers + direction check for free text against a payload; never raises."""
    index: dict[str, list[dict]] = {}
    for opt in (payload.get("options", []) if claim_options is None else claim_options):
        for nd in opt.get("nurses", []):
            index.setdefault(nd["nurse"], []).append(nd)
    claims = claims if isinstance(claims, list) else []
    false = 0
    for c in claims:
        if (not isinstance(c, dict) or not isinstance(c.get("nurse"), str)
                or not any(_matches(r, c) for r in index.get(canon_nurse(c["nurse"]), []))):
            false += 1
    allowed = _allowed_numbers(payload)
    text = text if isinstance(text, str) else ""
    unsupported = [x for x in _NUM.findall(_ID.sub(" ", text))
                   if _norm(x) is None or _norm(x) not in allowed]
    return {"claims_total": len(claims), "claims_false": false,
            "unsupported_numbers": unsupported, "direction_errors": direction_errors(text)}


def check(expl: dict, payload: dict) -> dict:
    """Deterministic faithfulness check; never raises on JSON-shaped explanations.

    Limits: a claim is verified if the nurse's before/after metric pair exists in ANY option of
    the payload ("exists in the payload"), not "attributed to the right option". Numbers in text
    must come from an allow-list (nurse metrics, strain values, delta_strain, n_changes, change
    days, event day/notice, domain constants); ids are stripped first. Spelled-out numbers
    ("three") are out of scope.
    """
    base = check_text(expl.get("text"), expl.get("claims"), payload)
    claims_total, false, unsupported = base["claims_total"], base["claims_false"], base["unsupported_numbers"]
    dir_err = base["direction_errors"]
    top, _ = comparison_pair(payload)
    truth = ground_truth_tradeoff(payload)
    rec_ok = canon_option(expl.get("recommended_option")) == top["id"]
    tradeoff_ok = expl.get("main_tradeoff") == truth
    return {
        "claims_total": claims_total,
        "claims_false": false,
        "unsupported_numbers": unsupported,
        "recommendation_correct": rec_ok,
        "tradeoff_correct": tradeoff_ok,
        "direction_errors": dir_err,
        "ground_truth": truth,
        "verified": false == 0 and not unsupported and rec_ok and tradeoff_ok and not dir_err,
    }
