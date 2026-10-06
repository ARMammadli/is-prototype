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


_NURSE_MENTION = re.compile(r"\bnurse[ _]?0*(\d+)\b", re.I)
_UP_WORD = re.compile(r"\b(more|extra|additional|add\w*|increas\w*|rais\w*|ris\w*|gain\w*|takes on|picks up)\b", re.I)
_DOWN_WORD = re.compile(r"\b(reliev\w*|relief|spar\w*|fewer|less|reduc\w*|lower\w*|drop\w*|decreas\w*|cut\w*|free\w*)\b", re.I)
# The style guide's own phrase for a quick return contains "less"; it is not a direction word.
_QR_PHRASE = re.compile(r"less than 11 hours'?(?: rest)?", re.I)


def _nurse_directions(payload: dict) -> dict[str, set]:
    """{nurse: {"up", "down"}} - which directions that nurse's numbers move in any listed option."""
    out: dict[str, set] = {}
    for opt in payload.get("options", []):
        for nd in opt.get("nurses", []):
            dirs = out.setdefault(nd["nurse"], set())
            for m in METRICS:
                a, b = nd["after"].get(m, 0), nd["before"].get(m, 0)
                dirs.update({"up"} if a > b else {"down"} if a < b else set())
            delta = (nd.get("strain_after") or 0) - (nd.get("strain_before") or 0)
            dirs.update({"up"} if delta > 0 else {"down"} if delta < 0 else set())
    return out


def nurse_direction_errors(text, payload: dict) -> list[str]:
    """Heuristic: a sentence about exactly one nurse whose nearest direction word contradicts that
    nurse's numbers (e.g. "relieves Nurse_12" when every number for Nurse_12 goes up).

    Only unambiguous contradictions are flagged: an 'up' word is accepted if anything for that
    nurse goes up, a 'down' word if anything goes down."""
    if not isinstance(text, str):
        return []
    try:
        dirs = _nurse_directions(payload)
    except (KeyError, TypeError, AttributeError):
        return []
    out: list[str] = []
    start = 0
    for end in [m.end() for m in _SENT.finditer(text)] + [len(text)]:
        sent, start = _QR_PHRASE.sub(" ", text[start:end]), end
        mentions = list(_NURSE_MENTION.finditer(sent))
        names = {canon_nurse(m.group(0)) for m in mentions}
        if len(names) != 1:
            continue
        nurse = names.pop()
        if nurse not in dirs or not dirs[nurse]:
            continue
        pos = mentions[0].start()
        words = [(abs(w.start() - pos), "up", w.group(0)) for w in _UP_WORD.finditer(sent)]
        words += [(abs(w.start() - pos), "down", w.group(0)) for w in _DOWN_WORD.finditer(sent)]
        if not words:
            continue
        _, way, word = min(words)
        if way not in dirs[nurse]:
            out.append(f"{nurse}: '{word}'")
    return out


_METRIC_PHRASE = {"QR": r"quick returns?", "SN": r"(?:last-minute )?call-ins?", "N": r"night shifts?",
                  "OT": r"overtime", "LR": r"long stretch(?:es)?"}
_ADD = re.compile(r"\b(adds?|added|adding|gives?|gave|more|extra|another)\b", re.I)


def _added_by(opt: dict) -> dict:
    return {m: sum(nd["after"][m] - nd["before"][m] for nd in opt.get("nurses", [])) for m in METRICS}


_SENT_END = re.compile(r"[!?]|\.(?!\d)")  # option descriptions contain ';', so only real sentence ends
_CLAUSE = re.compile(r",?\s*\b(?:while|whereas|unlike|but)\b", re.I)
_COUNT_BEFORE_MORE = re.compile(r"\b(?:one|two|three|a|an|\d+)\s+more\b", re.I)


def comparison_errors(text, payload: dict) -> list[str]:
    """Heuristic check of claims about today's software's option and about the chosen option's cost.

    Per clause (split at while/whereas/unlike/but):
    - a clause about today's software (named, or its option description) saying it adds an item is flagged
      when that option adds none of it; 'adds more <item>' (a comparison) is flagged when it adds no more
      than the chosen option ('one more' counts as an amount, not a comparison);
    - 'the cost is ... <item>' is flagged when the chosen option adds none of that item.
    Clauses naming both options are skipped; nothing is checked when both picks are the same."""
    if not isinstance(text, str):
        return []
    try:
        dec = payload["decision"]
        if dec.get("same_as_todays_software"):
            return []
        opts = {o["id"]: o for o in payload["options"]}
        chosen, ortec = opts[dec["chosen"]], opts[dec["todays_software"]]
        ca, oa = _added_by(chosen), _added_by(ortec)
    except (KeyError, TypeError, AttributeError):
        return []
    cdesc, odesc = (chosen.get("description") or "").lower(), (ortec.get("description") or "").lower()
    out: list[str] = []
    start = 0
    for end in [m.end() for m in _SENT_END.finditer(text)] + [len(text)]:
        sent, start = text[start:end], end
        for clause in _CLAUSE.split(sent.lower().replace("\u2019", "'")):
            has_chosen = bool(cdesc) and cdesc in clause
            about_ortec = (("today's software" in clause or (bool(odesc) and odesc in clause)) and not has_chosen
                           and not re.search(r"than (?:today's software|“)", clause))  # "X more than today's" is about X
            for m, pat in _METRIC_PHRASE.items():
                hit = re.search(pat, clause)
                if not hit:
                    continue
                before = clause[max(0, hit.start() - 40):hit.start()]
                verbs = [v.lower() for v in _ADD.findall(before)]
                if not verbs:
                    continue
                relative = "more" in verbs and not _COUNT_BEFORE_MORE.search(before)
                if about_ortec and (oa[m] <= 0 or (relative and oa[m] <= ca[m])):
                    out.append(f"today's software: '{clause.strip()[:80]}'")
                elif not about_ortec and "the cost is" in clause and ca[m] <= 0:
                    out.append(f"cost: '{clause.strip()[:80]}'")
    return list(dict.fromkeys(out))


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
            add(nd.get("load_change"))
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


def check_explanation(expl, payload: dict) -> dict:
    """Fact check for 'rule ranks, GenAI explains': numbers, claims and direction only.

    The choice itself is never the model's, so there is no recommendation check. status is
    'verified', 'mismatch', or 'unavailable' (no model output). Never raises."""
    if not isinstance(expl, dict):
        return {"claims_total": 0, "claims_false": 0, "unsupported_numbers": [], "direction_errors": [],
                "nurse_direction_errors": [], "comparison_errors": [], "no_claims": True, "verified": False,
                "status": "unavailable"}
    try:
        r = check_text(expl.get("text"), expl.get("claims"), payload)
        r["nurse_direction_errors"] = nurse_direction_errors(expl.get("text"), payload)
        r["comparison_errors"] = comparison_errors(expl.get("text"), payload)
    except Exception:  # junk model output must never break the endpoint
        r = {"claims_total": 0, "claims_false": 1, "unsupported_numbers": [], "direction_errors": [],
             "nurse_direction_errors": [], "comparison_errors": []}
    r["no_claims"] = r["claims_total"] == 0
    r["verified"] = (r["claims_false"] == 0 and not r["unsupported_numbers"] and not r["direction_errors"]
                     and not r["nurse_direction_errors"] and not r["comparison_errors"])
    r["status"] = "verified" if r["verified"] else "mismatch"
    return r
