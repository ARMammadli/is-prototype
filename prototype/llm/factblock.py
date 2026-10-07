"""Rule writes the facts, GenAI writes the wording.

The fact block is a set of fixed sentences rendered from the explain payload (no model involved).
GenAI only receives the fact block and the policy text and writes 1-2 framing sentences.
The framing may not contain any number or nurse code that is not in the fact block.
"""
from __future__ import annotations

import re

from llm.checker import _ID, _NUM, _NURSE_MENTION, _norm, canon_nurse
from sim.strain import METRICS

# Neutral wording only ('from X to Y', no direction verbs), so the existing heuristic checks
# never fire on the rule's own sentences.
FACT_METRIC = {"QR": "quick returns", "N": "night shifts", "LR": "long runs of 6+ working days",
               "OT": "overtime hours", "SN": "short-notice changes"}
SHIFT = {"D": "day", "E": "evening", "N": "night"}


def _fmt(v) -> str:
    return _norm(v) or str(v)


def _nurse_sentences(opt: dict, label: str) -> list[str]:
    out = []
    for nd in opt["nurses"]:
        parts = [f"{FACT_METRIC[m]} from {_fmt(nd['before'][m])} to {_fmt(nd['after'][m])}"
                 for m in METRICS if nd["after"][m] != nd["before"][m]]
        body = "; ".join(parts) if parts else "no count changes"
        out.append(f"{label}, {nd['nurse']}: {body}.")
    return out


def render_fact_block(payload: dict) -> list[str]:
    """Fixed sentences for the chosen option, today's software's option and the cost."""
    ev, dec = payload["event"], payload["decision"]
    opts = {o["id"]: o for o in payload["options"]}
    chosen, ortec = opts[dec["chosen"]], opts[dec["todays_software"]]
    s = [f"{ev['absent']} is absent for the {SHIFT.get(ev['shift'], ev['shift'])} shift on day {_fmt(ev['day'])}, "
         f"with {_fmt(ev['notice_h'])} hours' notice.",
         "Counts below are per nurse, before and after the repair, in the past and next 28 days. A short-notice "
         "change is any shift change, a move or a call-in, made with less than 48 hours' notice.",
         f"The hospital rule's choice: {chosen['description']}."]
    s += _nurse_sentences(chosen, "In the rule's choice")
    if dec["same_as_todays_software"]:
        s.append("Today's software would pick the same option.")
        s.append(f"The rule's choice changes the shifts of {_fmt(chosen['n_changes'])} "
                 f"nurse{'s' if chosen['n_changes'] != 1 else ''}.")
    else:
        s.append(f"Today's software would pick: {ortec['description']}.")
        s += _nurse_sentences(ortec, "In today's software's choice")
        s.append(f"The rule's choice changes the shifts of {_fmt(chosen['n_changes'])} "
                 f"nurse{'s' if chosen['n_changes'] != 1 else ''}; today's software's choice changes the shifts of "
                 f"{_fmt(ortec['n_changes'])} nurse{'s' if ortec['n_changes'] != 1 else ''}.")
    return s


def fact_block_text(payload: dict) -> str:
    return " ".join(render_fact_block(payload))


FRAMING_SYSTEM_PROMPT = """You help a hospital ward planner read a roster repair decision that the hospital's fairness rule
has ALREADY made. You do not choose and you never suggest a different option.
You receive only two things: the manager's fairness policy (policy_text) and a fact block. The fact block was
written by the rule from the data and is shown to the planner directly above your text.
Write 1 or 2 short sentences (at most 45 words) that frame the decision:
- who is relieved or spared by the rule's choice, if anyone, and who takes on the extra work;
- why this fits the manager's policy.
Rules:
- Do not write any digits or number words (one, two, ...). The numbers are already in the fact block.
- Name only nurses that appear in the fact block, written exactly as there (e.g. Nurse_03).
- Do not compare the options in any way the fact block does not state. Do not invent totals or reasons.
- A count going from a higher to a lower number means that nurse is relieved of it; from lower to higher means
  that nurse gets more of it. Never reverse this.
- Do not use the codes QR, N, LR, OT or SN. Say 'load', not 'strain'.
- Never speculate about health, burnout, motivation or private circumstances.
Return JSON: {"text": "..."}"""

# E10: GenAI may only restate the fact sentences; no claim about policy fit, load, burden or fairness.
FRAMING_SYSTEM_PROMPT_RESTATE = """You help a hospital ward planner read a roster repair decision that the hospital's fairness rule
has ALREADY made. You do not choose and you never suggest a different option.
You receive a fact block written by the rule from the data. It is shown to the planner directly above your text.
Write 1 or 2 short sentences (at most 40 words) that restate, in plain words, what the fact block says about the
rule's choice: which nurse is relieved of what, and which nurse takes on what. You may also restate what today's
software's choice would do instead, exactly as the fact block says.
Rules:
- Only restate what the fact sentences say. Add nothing else: no reasons, no conclusions, no comparisons the
  fact block does not state.
- Do not say that the choice fits or follows any policy, reduces load or burden, protects anyone, spreads the work,
  or is fair. The fact block never states these.
- Do not write any digits or number words (one, two, ...). The numbers are already in the fact block.
- Name only nurses that appear in the fact block, written exactly as there (e.g. Nurse_03).
- A count going from a higher to a lower number means that nurse is relieved of it; from lower to higher means
  that nurse gets more of it. Never reverse this. A nurse whose counts both rise and fall is not simply 'relieved'.
- Do not use the codes QR, N, LR, OT or SN.
- Never speculate about health, burnout, motivation or private circumstances.
Return JSON: {"text": "..."}"""

FRAMING_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                 "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "once": "1",
                 "twice": "2", "single": "1", "double": "2", "half": "0.5"}
_WORD_RX = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", re.I)
_NOT_A_NUMBER = re.compile(r"\b(?:no|any|every|some)\s?one\b|\bone of (?:them|the)\b", re.I)


def _numbers(text: str) -> set:
    return {_norm(x) for x in _NUM.findall(_ID.sub(" ", text))} - {None}


def fact_block_errors(framing, fact_text: str) -> list[str]:
    """Numbers (digits or number words) and nurse codes in the framing that are not in the fact block."""
    if not isinstance(framing, str):
        return []
    allowed = _numbers(fact_text)
    nurses = {canon_nurse(m.group(0)) for m in _NURSE_MENTION.finditer(fact_text)}
    out = [f"number not in fact block: {x}" for x in _NUM.findall(_ID.sub(" ", framing))
           if _norm(x) not in allowed]
    for m in _WORD_RX.finditer(_NOT_A_NUMBER.sub(" ", framing)):
        if _NUMBER_WORDS[m.group(1).lower()] not in allowed:
            out.append(f"number not in fact block: '{m.group(1)}'")
    for m in _NURSE_MENTION.finditer(framing):
        n = canon_nurse(m.group(0))
        if n not in nurses:
            out.append(f"nurse not in fact block: {n}")
    return list(dict.fromkeys(out))


# --- Check v3 (follow-up): role check, load-claim check, narrow 'spared' exemption ----------------

def _opts(payload: dict):
    o = {x["id"]: x for x in payload["options"]}
    d = payload["decision"]
    return o[d["chosen"]], o[d["todays_software"]]


def _delta(nd: dict) -> dict:
    return {m: nd["after"][m] - nd["before"][m] for m in METRICS}


def load_comparison(payload: dict) -> dict:
    """Policy terms: among nurses whose load rises, the highest load before the repair, per option.

    verdict: 'rule_lower' (rule adds load to a less loaded nurse), 'rule_higher', 'equal', or 'same_pick'."""
    chosen, ortec = _opts(payload)

    def top(opt):
        g = [(nd["strain_before"], nd["nurse"]) for nd in opt["nurses"] if nd["strain_after"] > nd["strain_before"]]
        return max(g) if g else None
    c, o = top(chosen), top(ortec)
    if payload["decision"]["same_as_todays_software"]:
        verdict = "same_pick"
    else:
        cv, ov = (c[0] if c else -1), (o[0] if o else -1)
        verdict = "rule_lower" if cv < ov else "rule_higher" if cv > ov else "equal"
    return {"rule": c, "todays_software": o, "verdict": verdict}


def render_load_fact(payload: dict) -> list[str]:
    """Item 3: the rule states the load facts the policy is about (load = the rule's weighted count)."""
    chosen, ortec = _opts(payload)
    seen, parts = set(), []
    for opt in (chosen, ortec):
        for nd in opt["nurses"]:
            if nd["nurse"] not in seen:
                seen.add(nd["nurse"])
                parts.append(f"{nd['nurse']} {_fmt(nd['strain_before'])}")
    lc = load_comparison(payload)
    s = [f"Load score before the repair (the rule's weighted count of each nurse's quick returns, nights, long stretches, overtime and call-ins): {', '.join(parts)}."]
    who = lambda t: f"{t[1]} (load score {_fmt(t[0])})" if t else "nobody"  # noqa: E731
    if lc["verdict"] == "same_pick":
        s.append(f"Of the nurses whose load rises, the most loaded before the repair is {who(lc['rule'])}.")
        return s
    s.append(f"Of the nurses whose load rises, the most loaded before the repair is {who(lc['rule'])} in the rule's "
             f"choice and {who(lc['todays_software'])} in today's software's choice.")
    s.append({"rule_lower": "So the rule's choice puts the extra load on a less loaded nurse than today's software's choice does.",
              "rule_higher": "So the rule's choice puts the extra load on a more loaded nurse than today's software's choice does.",
              "equal": "So both choices put the extra load on nurses with the same load score."}[lc["verdict"]])
    return s


_SENTS = re.compile(r"(?<=[.!?])\s+")
_UP_CUE = re.compile(r"\b(takes? on|taking(?: on)?|takes|take|gets?|getting|handles?|covers?|picks? up|absorbs?|more|extra|additional|"
                     r"adds?|added|increas\w*|gains?|another|assigned)\b", re.I)
_DOWN_CUE = re.compile(r"\b(reliev\w*|relief|spared?|spares|avoids?|fewer|less|reduc\w*|lower\w*|drops?|"
                       r"freed|free of|loses?)\b", re.I)
_NONE_CUE = re.compile(r"\b(unaffected|unchanged|not affected|remains? the same|no change)\b", re.I)
_NEG = re.compile(r"\b(?:no|not|without|never)\s+(?:\w+\s+)?$", re.I)
_METRIC_RX = {"QR": r"quick returns?", "N": r"night(?: shift)?s?\b", "SN": r"(?:last-minute )?call[- ]ins?|short[- ]notice changes?",
              "OT": r"overtime", "LR": r"long stretch(?:es)?|long runs?|days in a row"}
_CHANGE_RX = re.compile(r"\b(?:change|changes|changed|called in|being called|moved|the shift)\b", re.I)
_COUNTERFACTUAL = re.compile(r"today'?s software|\bwould\b|\binstead of\b|\bortec", re.I)
_GROUP_JOIN = re.compile(r"^\s*(?:,|and|,\s*and)\s*$", re.I)
LOAD_CLAIM = re.compile(r"\b(load\w*|burden\w*|overload\w*|heav(?:y|ier|iest)|carr(?:y|ies|ying) the most|"
                        r"those with the most|the most (?:shifts|work)|already (?:busy|stretched|working)|"
                        r"spread\w*|fair(?:ly|er|est)?)\b", re.I)


def _cues(text: str):
    out = []
    for rx, way in ((_UP_CUE, "up"), (_DOWN_CUE, "down"), (_NONE_CUE, "none")):
        for m in rx.finditer(text):
            negated = _NEG.search(text[:m.start()]) or re.match(r"\s+(?:no|nothing)\b", text[m.end():], re.I)
            w = "none" if (way == "up" and negated) else way
            out.append((m.start(), w, m.group(0)))
    return sorted(out)


def _judge(nurse, way, metric, seg, payload) -> str | None:
    """None if the statement fits the rule's facts, else a short error."""
    chosen, ortec = _opts(payload)
    cf = bool(_COUNTERFACTUAL.search(seg))
    target, other = (ortec, chosen) if cf else (chosen, ortec)
    tn = {nd["nurse"]: _delta(nd) for nd in target["nurses"]}
    on = {nd["nurse"]: _delta(nd) for nd in other["nurses"]}
    changed = {c["nurse"] for c in target.get("changes", [])}
    ms = [metric] if metric else list(METRICS)
    if nurse in tn:
        d = tn[nurse]
        if way == "up" and not any(d[m] > 0 for m in ms):
            return f"{nurse}: '{'more ' + metric if metric else 'takes on'}' but nothing rises"
        if way == "none" and any(d[m] > 0 for m in ms):
            return f"{nurse}: 'no extra' but counts rise"
        if way == "down":
            if not metric and _CHANGE_RX.search(seg) and nurse in changed:
                return f"{nurse}: 'spared' but this nurse's shift changes"
            relative = nurse in on and sum(on[nurse][m] for m in ms) > sum(d[m] for m in ms)
            if not any(d[m] < 0 for m in ms) and not relative:
                return f"{nurse}: 'relieved/fewer' but nothing falls"
        return None
    if nurse in on:  # named nurse is only in the other option
        if way == "up":
            return f"{nurse}: described as taking on work in the {'today' if cf else 'rule'}'s choice but is not in it"
        if way == "down" and not any(on[nurse][m] > 0 for m in ms):
            return f"{nurse}: 'spared' but the other option adds nothing to this nurse"
    return None


def role_errors(framing, payload: dict) -> list[str]:
    """Every nurse named in the framing, also in sentences naming several nurses: the role it is given
    (takes on work / relieved or spared / no extra) must match the rule's facts for that nurse, for the
    named item where one is named. Clauses saying 'today's software' / 'would' / 'instead of' are judged
    against today's software's choice."""
    if not isinstance(framing, str):
        return []
    absent = canon_nurse(payload["event"]["absent"])
    out = []
    for sent in _SENTS.split(framing):
        ms = list(_NURSE_MENTION.finditer(sent))
        groups, cur = [], []
        for i, m in enumerate(ms):
            if cur and not _GROUP_JOIN.match(sent[ms[i - 1].end():m.start()]):
                groups.append(cur)
                cur = []
            cur.append(m)
        if cur:
            groups.append(cur)
        for gi, g in enumerate(groups):
            end = groups[gi + 1][0].start() if gi + 1 < len(groups) else len(sent)
            start = groups[gi - 1][-1].end() if gi else 0
            seg = sent[g[-1].end():end]
            cues = _cues(seg)
            if not cues:  # 'relieving Nurse_43 from ...': the cue comes before the nurse
                lead = " ".join(sent[start:g[0].start()].split()[-3:])  # only the words right before the nurse
                seg = lead + " " + sent[g[-1].end():end]
                cues = _cues(lead)
                if not cues:
                    continue
            hits = []
            for mk, rx in _METRIC_RX.items():
                for mm in re.finditer(rx, seg, re.I):
                    before = [c for c in _cues(seg[:mm.start()])]
                    if re.search(r"\bno\s+(?:\w+\s+)?$", seg[:mm.start()], re.I):
                        hits.append((mk, "none"))  # 'but no quick returns'
                    elif before:
                        hits.append((mk, before[-1][1]))
            if not hits:
                hits = [(None, cues[0][1])]  # no item named: the main verb (first cue) sets the role
            for nm in g:
                n = canon_nurse(nm.group(0))
                if n == absent:
                    continue
                for metric, way in hits:
                    e = _judge(n, way, metric, seg, payload)
                    if e:
                        out.append(e)
    return list(dict.fromkeys(out))


def load_claim_errors(framing, payload: dict, load_fact: bool) -> list[str]:
    """A sentence about load / burden / fairness is backed only if the fact block states a load comparison
    and that comparison favours the rule's choice (rule puts the extra load on a less loaded nurse)."""
    if not isinstance(framing, str):
        return []
    text = re.sub(r"fairness (?:policy|rule)", "policy", framing, flags=re.I)
    verdict = load_comparison(payload)["verdict"] if load_fact else None
    out = []
    for sent in _SENTS.split(text):
        m = LOAD_CLAIM.search(sent)
        # Decided before the item-3 run: when the load fact does not favour the rule, a load sentence is
        # accepted only if it repeats the fact's direction ('more loaded' / 'same load') and claims no policy fit.
        echoes = (verdict in ("rule_higher", "equal") and re.search(r"more loaded|same load", sent, re.I)
                  and not re.search(r"\b(avoid\w*|protect\w*|fits?|align\w*|spar\w*|fair\w*|spread\w*)\b", sent, re.I))
        if m and verdict != "rule_lower" and not echoes:
            out.append(f"load claim not backed by a fact ({verdict or 'no load fact'}): '{sent.strip()[:70]}'")
    return out


def _exempt(err: str, payload: dict) -> bool:
    """Narrow exemption for the old up/down heuristic: a relief word ('spared', 'relieved', ...) about a nurse
    whom today's software's choice loads more than the rule's choice does."""
    nurse, word = err.split(": ", 1)
    if not _DOWN_CUE.fullmatch(word.strip("'")):
        return False
    chosen, ortec = _opts(payload)
    load = lambda opt: next((nd["strain_after"] - nd["strain_before"] for nd in opt["nurses"] if nd["nurse"] == nurse), 0)  # noqa: E731
    in_ortec = any(nd["nurse"] == nurse for nd in ortec["nurses"])
    return in_ortec and load(ortec) > 0 and load(ortec) > load(chosen)


POLICY_CLAIM = re.compile(r"\bpolic(?:y|ies)\b|\bfair\w*|\bprotect\w*", re.I)


def policy_claim_errors(framing) -> list[str]:
    """E10: the fact block never mentions the policy or fairness, so any such sentence is unbacked."""
    if not isinstance(framing, str):
        return []
    return [f"policy/fairness claim not backed by a fact: '{x.strip()[:70]}'"
            for x in _SENTS.split(framing) if POLICY_CLAIM.search(x)]


def check_v3(display_text, framing, payload: dict, fact_text: str, load_fact: bool = False,
             policy_claims: bool = False) -> dict:
    """Old check (unchanged) + the three follow-up changes. Returns old and new results side by side."""
    from llm.checker import check_explanation
    old = check_explanation({"claims": [], "text": display_text} if framing is not None else None, payload)
    if framing is None:
        return {**old, "status_v3": "unavailable", "verified_v3": False}
    old["fact_block_errors"] = fact_block_errors(framing, fact_text)
    old["verified_v2"] = old["verified"] and not old["fact_block_errors"]
    kept = [e for e in old["nurse_direction_errors"] if not _exempt(e, payload)]
    old["nurse_direction_errors_v3"] = kept
    old["role_errors"] = role_errors(framing, payload)
    old["load_claim_errors"] = load_claim_errors(framing, payload, load_fact)
    if policy_claims:
        old["load_claim_errors"] += policy_claim_errors(framing)
    old["verified_v3"] = (old["claims_false"] == 0 and not old["unsupported_numbers"] and not old["direction_errors"]
                          and not kept and not old["comparison_errors"] and not old["fact_block_errors"]
                          and not old["role_errors"] and not old["load_claim_errors"])
    old["status_v3"] = "verified" if old["verified_v3"] else "mismatch"
    return old
