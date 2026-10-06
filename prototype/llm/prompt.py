"""LLM payload and prompt (spec §5). Only pseudonymous IDs and computed metrics are sent."""
from __future__ import annotations

from llm.checker import comparison_pair, ground_truth_tradeoff
from sim.compare import plain_change
from sim.policies import rank_options
from sim.strain import METRICS, TRADEOFFS

DEFINITIONS = """For every affected nurse each option lists metrics before and after the repair, counted
over the planning window: QR = quick returns (less than 11 h rest), N = night shifts,
LR = runs of 6+ consecutive working days, OT = overtime hours above contract,
SN = short-notice changes absorbed. Days are numbered from 1."""

DIRECTION_RULE = """Describe every change in the direction its numbers show: say 'reduces'/'lowers' only when
after < before, and 'adds'/'increases' when after > before. When you write 'from X to Y', X must
be the before value and Y the after value."""

STYLE_RULES = """Audience and style (the text is read by hospital managers):
- Write for hospital managers who are not roster experts. Never use the codes QR, N, LR, OT or SN in the text.
- Use these plain phrases: QR = 'quick return (back at work after less than 11 hours' rest)', and just 'quick return' on later mentions; N = 'night shift'; LR = 'long stretch of 6+ working days in a row'; OT = 'overtime hours'; SN = 'last-minute call-in'.
- Write short sentences. Say who gets what, e.g. 'Nurse_68 would get one more quick return and one more last-minute call-in.'
- Talk about 'load', not 'strain'.
- Name people exactly as in the data (e.g. Nurse_68); refer to options by their description, never by their id. Only use numbers from the JSON, only for nurses who appear in it. Never say 'this month' or 'already has' unless that exact before value is in the JSON.
(The claims list keeps using the metric codes; that part is internal. Only the text is plain English.)"""

SYSTEM_PROMPT = f"""You explain nurse roster repair options to a hospital ward planner.
You receive JSON with one absence, the hospital's strain weights, and up to four feasible repair
options. {DEFINITIONS}
Rules:
- recommended_option must equal comparison.recommended, and main_tradeoff must equal
  comparison.main_driver.
- Explain in plain words why comparison.recommended is preferred over comparison.compared_with,
  using comparison.metric_added and comparison.strain_added.
- {DIRECTION_RULE}
- Refer to options by their description, never by their id. Refer to nurses as in the data.
- Only use numbers that appear in the JSON.
- Do not cite weights or ranks; cite only nurse metrics, strain values, days and notice hours.
- Every before/after number you mention about a nurse must also be listed in claims.
- Never speculate about health, burnout, motivation or private circumstances.
- Answer in at most 3 short sentences (about 50 words).
- Mention only your chosen option and at most one alternative — prefer the option ORTEC-like would pick if it is in the list, otherwise the closest alternative. Do not walk through every option.
- Cite at most 4 numbers.
- List at most 6 claims.
{STYLE_RULES}"""

CLAIM_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "nurse": {"type": "string"},
        "metric": {"type": "string", "enum": list(METRICS)},
        "before": {"type": "number"},
        "after": {"type": "number"},
    },
    "required": ["nurse", "metric", "before", "after"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_option": {"type": "string"},
        "main_tradeoff": {"type": "string", "enum": list(TRADEOFFS)},
        "claims": {
            "type": "array",
            "items": CLAIM_ITEM_SCHEMA,
            "maxItems": 6,
        },
        "text": {"type": "string"},
    },
    "required": ["recommended_option", "main_tradeoff", "claims", "text"],
}


def _option_payload(so, is_base_top: bool) -> dict:
    return {
        "id": so.option.id,
        "description": plain_change(so.option),
        "rank_strain": so.rank_strain,
        "rank_baseline": so.rank_baseline,
        "is_baseline_top": is_base_top,
        "kind": so.option.kind,
        "n_changes": so.option.n_changes,
        "delta_strain": so.delta_strain,
        "changes": [{"nurse": c.nurse, "day": c.day + 1, "from": c.old, "to": c.new}
                    for c in so.option.changes],
        "nurses": so.nurses,
    }


def _added(opt, metric):
    if opt is None:
        return None
    return round(sum(nd["after"][metric] - nd["before"][metric] for nd in opt["nurses"]), 2)


def build_comparison(payload: dict) -> dict:
    """Deterministic comparison block: recommended vs. compared-with option."""
    top, other = comparison_pair(payload)
    return {
        "recommended": top["id"],
        "compared_with": other["id"] if other else None,
        "main_driver": ground_truth_tradeoff(payload),
        "strain_added": {"recommended": top["delta_strain"],
                         "compared_with": other["delta_strain"] if other else None},
        "metric_added": {m: {"recommended": _added(top, m), "compared_with": _added(other, m)}
                         for m in METRICS},
    }


def build_payload(ctx, scored, policy: dict, k: int = 3) -> dict:
    by_strain = rank_options(scored, "strain")
    base_top = rank_options(scored, "baseline")[0]
    chosen = list(by_strain[:k])
    if not any(so is base_top for so in chosen):
        chosen.append(base_top)
    payload = {
        "event": {"absent": ctx.absent, "day": ctx.day + 1, "shift": ctx.shift,
                  "notice_h": round(ctx.notice_h, 1)},
        "weights": dict(policy["weights"]),
        "options": [_option_payload(so, so is base_top) for so in chosen],
    }
    payload["comparison"] = build_comparison(payload)
    return payload


# --- Rule ranks, GenAI explains (default mode) -------------------------------------------------
# The hospital formula has already chosen. GenAI only explains that choice; it never picks.

DEFAULT_POLICY_TEXT = ("Spread the extra work fairly: avoid giving any nurse a quick return, and do not add "
                       "load to the nurses who already carry the most.")

PLAIN_METRIC = {"QR": "quick returns", "N": "night shifts", "LR": "long stretches",
                "OT": "overtime hours", "SN": "last-minute call-ins"}

EXPLAIN_SYSTEM_PROMPT = f"""You explain a nurse roster repair decision that the hospital's fairness rule has ALREADY
made. You do not choose and you never suggest a different option.
You receive JSON with one absence, the manager's fairness policy (policy_text), the decision (the option the
rule chose, the runner-up, and the option today's software would pick: fewest changes, most contract hours
left) and those options. {DEFINITIONS}
For every nurse, 'more' lists what goes up for that nurse, 'less' lists what goes down, and load_change is
the load after minus the load before (positive = more load, negative = relieved).
Write 2 to 3 short sentences (about 60 words) that say:
1. who gets extra work in the chosen option, and who is relieved (if anyone);
2. why the chosen option fits the policy better than today's software's choice (if
   decision.same_as_todays_software is true, say both agree and compare with the runner-up instead);
3. the cost, if any, for example more nurses changed or more last-minute call-ins.
Rules:
- {DIRECTION_RULE} A nurse whose item is in 'less' is relieved of it; never say that nurse gets more of it.
- Refer to options by their description, never by their id. Refer to nurses as in the data.
- Only use numbers that appear in the JSON. Do not cite weights or ranks.
- Every before/after number you mention about a nurse must also be listed in claims.
- Never speculate about health, burnout, motivation or private circumstances.
- Cite at most 4 numbers and list at most 6 claims.
{STYLE_RULES}"""

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": CLAIM_ITEM_SCHEMA, "maxItems": 6},
        "text": {"type": "string"},
    },
    "required": ["claims", "text"],
}


def _nurse_view(nd: dict) -> dict:
    up = [PLAIN_METRIC[m] for m in METRICS if nd["after"][m] > nd["before"][m]]
    down = [PLAIN_METRIC[m] for m in METRICS if nd["after"][m] < nd["before"][m]]
    return {**nd, "load_change": round(nd["strain_after"] - nd["strain_before"], 2), "more": up, "less": down}


def build_explain_payload(ctx, scored, policy: dict, policy_text: str | None = None) -> dict:
    """The rule's choice, its runner-up and the ORTEC-like choice, with per-nurse before/after numbers."""
    by_strain = rank_options(scored, "strain")
    top, base_top = by_strain[0], rank_options(scored, "baseline")[0]
    runner = by_strain[1] if len(by_strain) > 1 else None
    chosen = [top]
    for so in (runner, base_top):
        if so is not None and all(so is not c for c in chosen):
            chosen.append(so)
    roles = {id(top): ["chosen by the hospital rule"]}
    if runner is not None:
        roles.setdefault(id(runner), []).append("runner-up")
    roles.setdefault(id(base_top), []).append("today's software would pick this")
    options = []
    for so in chosen:
        o = _option_payload(so, so is base_top)
        o["role"] = " and ".join(roles.get(id(so), []))
        o["nurses"] = [_nurse_view(nd) for nd in so.nurses]
        options.append(o)
    payload = {
        "event": {"absent": ctx.absent, "day": ctx.day + 1, "shift": ctx.shift,
                  "notice_h": round(ctx.notice_h, 1)},
        "policy_text": policy_text or DEFAULT_POLICY_TEXT,
        "weights": dict(policy["weights"]),
        "decision": {"chosen": top.option.id, "runner_up": runner.option.id if runner else None,
                     "todays_software": base_top.option.id,
                     "same_as_todays_software": base_top is top},
        "options": options,
    }
    payload["comparison"] = build_comparison(payload)
    return payload
