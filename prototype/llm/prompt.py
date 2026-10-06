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
