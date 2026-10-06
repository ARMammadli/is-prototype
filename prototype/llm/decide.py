"""AI-decides mode: the LLM sees unranked options, picks one and explains why."""
from __future__ import annotations

import json
import time

from llm.checker import check_text
from llm.plain import option_descriptions, plainify, replace_option_ids, short_text
from llm.ollama_client import chat_json
from llm.prompt import CLAIM_ITEM_SCHEMA, DEFINITIONS, DIRECTION_RULE, STYLE_RULES
from sim.compare import plain_change
from sim.policies import rank_options
from sim.strain import TRADEOFFS

GOAL = ("Every option covers the shift. Choose the option that is fairest to the nurses, using these "
        "principles in order: (1) avoid giving anyone a new quick return; (2) do not add load to a nurse "
        "who is already heavily loaded (high load_before); (3) when possible, relieve the "
        "most worn-down nurse involved \u2014 that is the nurse with the HIGHEST load_before; (4) avoid overtime and long stretches of working days; (5) if "
        "options are otherwise similar, disturb fewer people.")

DECIDE_SYSTEM_PROMPT = f"""You help a hospital ward planner choose one nurse roster repair option.
You receive JSON with one absence, a goal, and several feasible repair options in no particular
order. {DEFINITIONS}
load_before / load_after are each nurse's accumulated load before / after the repair (higher =
more loaded).
Rules:
- Every option covers the shift. Choose the fairest option for the nurses, applying the principles
  of the goal in order: (1) avoid giving anyone a new quick return; (2) do not add load to a nurse
  who is already heavily loaded (high load_before); (3) when possible, relieve the most worn-down
  nurse involved, that is the nurse with the HIGHEST load_before;
  (4) avoid overtime and long stretches of working days; (5) if options are otherwise similar,
  disturb fewer people. Do not use any formula or points.
- Choose exactly one option id from the list.
- Explain your choice in reasoning (plain words, see the writing style below).
- {DIRECTION_RULE}
- Refer to options by their description, never by their id. Refer to nurses as in the data.
- Only use numbers that appear in the JSON.
- Every before/after number you mention about a nurse must also be listed in claims.
- Never speculate about health, burnout, motivation or private circumstances.
- Answer in at most 3 short sentences (about 50 words).
- Mention only your chosen option and at most one alternative (the closest one). Do not walk through every option.
- Cite at most 4 numbers.
- List at most 6 claims.
{STYLE_RULES}"""


def decision_candidates(scored, k: int = 8) -> list:
    """Union of the top-k strain-ranked and top-k baseline-ranked options, ordered by strain rank."""
    chosen = {so.option.id: so for so in rank_options(scored, "strain")[:k]}
    chosen.update({so.option.id: so for so in rank_options(scored, "baseline")[:k]})
    return sorted(chosen.values(), key=lambda so: so.rank_strain)


def _rename(n: dict) -> dict:
    """Decision payload speaks of plain 'load', not the internal strain_* field names."""
    out = {k: v for k, v in n.items() if k not in ("strain_before", "strain_after")}
    out["load_before"], out["load_after"] = n["strain_before"], n["strain_after"]
    return out

def _unrename(n: dict) -> dict:
    out = {k: v for k, v in n.items() if k not in ("load_before", "load_after")}
    out["strain_before"], out["strain_after"] = n.get("load_before"), n.get("load_after")
    return out

def build_decision_payload(ctx, scored, policy: dict, k: int = 8) -> dict:
    ordered = sorted(decision_candidates(scored, k), key=lambda so: so.option.index)
    return {
        "event": {"absent": ctx.absent, "day": ctx.day + 1, "shift": ctx.shift,
                  "notice_h": round(ctx.notice_h, 1)},
        "goal": GOAL,
        "options": [{
            "id": so.option.id,
            "description": plain_change(so.option),
            "kind": so.option.kind,
            "n_changes": so.option.n_changes,
            "changes": [{"nurse": c.nurse, "day": c.day + 1, "from": c.old, "to": c.new}
                        for c in so.option.changes],
            "nurses": [_rename(n) for n in so.nurses],
        } for so in ordered],
    }


def decision_schema(option_ids) -> dict:
    return {
        "type": "object",
        "properties": {
            "chosen_option": {"type": "string", "enum": list(option_ids)},
            "main_tradeoff": {"type": "string", "enum": list(TRADEOFFS)},
            "claims": {"type": "array", "items": CLAIM_ITEM_SCHEMA, "maxItems": 6},
            "reasoning": {"type": "string"},
        },
        "required": ["chosen_option", "main_tradeoff", "claims", "reasoning"],
    }


def _check(decision, payload: dict) -> dict:
    empty = {"claims_total": 0, "claims_false": 0, "unsupported_numbers": [], "direction_errors": [],
             "no_claims": False, "verified": False}
    if not isinstance(decision, dict):
        return empty
    try:
        legacy = {**payload, "options": [{**o, "nurses": [_unrename(n) for n in o["nurses"]]}
                                         for o in payload["options"]]}
        chosen = [o for o in legacy["options"] if o["id"] == decision.get("chosen_option")]
        r = check_text(decision.get("reasoning"), decision.get("claims"), legacy, claim_options=chosen)
    except Exception:  # junk model output must never break the endpoint
        return empty
    r["no_claims"] = r["claims_total"] == 0
    r["verified"] = (r["claims_false"] == 0 and not r["unsupported_numbers"]
                     and not r["direction_errors"] and not r["no_claims"])
    return r


def decide(payload: dict, formula_top_id: str, model: str, timeout: float) -> dict:
    t0 = time.perf_counter()
    ids = [o["id"] for o in payload["options"]]
    decision, error = chat_json(DECIDE_SYSTEM_PROMPT, json.dumps(payload, separators=(",", ":")),
                                decision_schema(ids), model, timeout)
    if decision is None and error is None:
        error = "empty output"
    if decision is not None and not (
            isinstance(decision, dict) and decision.get("chosen_option") in ids
            and isinstance(decision.get("reasoning"), str)
            and isinstance(decision.get("claims"), list)
            and isinstance(decision.get("main_tradeoff"), str)):
        error, decision = "invalid output shape", None
    source = model if decision is not None else "unavailable"
    display_text = (replace_option_ids(plainify(decision["reasoning"]), option_descriptions(payload))
                    if decision else None)
    short, truncated = short_text(display_text) if display_text else (None, False)
    return {"decision": decision, "source": source,
            "display_text": display_text, "display_short": short, "display_truncated": truncated,
            "latency_ms": round((time.perf_counter() - t0) * 1000), "error": error,
            "formula_top": formula_top_id,
            "agrees": decision is not None and decision["chosen_option"] == formula_top_id,
            "check": _check(decision, payload)}
