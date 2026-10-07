"""explain(): local LLM with template fallback, always followed by the deterministic check."""
from __future__ import annotations

import json
import time

from llm.checker import check, check_explanation
from llm.factblock import (FRAMING_SCHEMA, check_v3, FRAMING_SYSTEM_PROMPT, FRAMING_SYSTEM_PROMPT_RESTATE, fact_block_errors,
                           render_fact_block)
from llm.ollama_client import chat_json
from llm.plain import option_descriptions, plainify, replace_option_ids, short_text
from llm.prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT
from llm.template import template_explanation


def _valid_shape(expl) -> bool:
    return (isinstance(expl, dict)
            and isinstance(expl.get("recommended_option"), str)
            and isinstance(expl.get("main_tradeoff"), str)
            and isinstance(expl.get("claims"), list)
            and isinstance(expl.get("text"), str))


def explain(payload: dict, model: str, timeout: float, use_llm: bool = True) -> dict:
    t0 = time.perf_counter()
    expl, error, source = None, None, model
    if use_llm:
        expl, error = chat_json(SYSTEM_PROMPT, json.dumps(payload, separators=(",", ":")),
                                OUTPUT_SCHEMA, model, timeout)
        if expl is None and error is None:
            error = "empty output"
        if expl is not None and not _valid_shape(expl):
            error, expl = "invalid output shape", None
    else:
        error = "LLM disabled"
    if expl is None:
        expl, source = template_explanation(payload), "template"
    display_text = replace_option_ids(plainify(expl.get("text")), option_descriptions(payload))
    short, truncated = short_text(display_text)
    return {"explanation": expl, "source": source, "display_text": display_text,
            "display_short": short, "display_truncated": truncated,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "error": error, "check": check(expl, payload)}


def explain_decision(payload: dict, model: str, timeout: float, variant: str = "restate") -> dict:
    """The rule writes the facts, GenAI writes 1-2 sentences around them.

    Default (final design, E10, 'restate'): GenAI sees only the fact block and may only restate it; the summary is
    scored with check v3 (roles, unbacked load/fairness/policy claims) and 'show_summary' is False when flagged, so
    the planner then sees the rule's facts only. Variant 'e8' (E8 framing with the policy text) is kept for
    reproducing E8.

    GenAI sees only the fact block and the policy text. The existing fact check runs unchanged on the
    displayed text (fact block + framing); fact_block_errors also flags any number or nurse code in the
    framing that is not in the fact block. On model failure the fact block is still shown, without
    framing, and the decision (made before this call) is unaffected."""
    t0 = time.perf_counter()
    facts = render_fact_block(payload)
    system = FRAMING_SYSTEM_PROMPT_RESTATE if variant == "restate" else FRAMING_SYSTEM_PROMPT
    fact_text = " ".join(facts)
    user = json.dumps({"fact_block": facts} if variant == "restate"
                      else {"policy_text": payload.get("policy_text", ""), "fact_block": facts})
    expl, error = chat_json(system, user, FRAMING_SCHEMA, model, timeout)
    if expl is None and error is None:
        error = "empty output"
    if expl is not None and not (isinstance(expl, dict) and isinstance(expl.get("text"), str)):
        error, expl = "invalid output shape", None
    framing = plainify(expl["text"]).strip() if expl else None
    display_text = f"{fact_text} {framing}" if framing else None
    short, truncated = short_text(display_text) if display_text else (None, False)
    if variant == "restate":
        check = check_v3(display_text, framing, payload, fact_text, load_fact=False, policy_claims=True)
        check["verified"], check["status"] = bool(check.get("verified_v3")), check.get("status_v3", "unavailable")
    else:
        check = check_explanation({"claims": [], "text": display_text} if expl else None, payload)
        check["fact_block_errors"] = fact_block_errors(framing, fact_text)
        if check["fact_block_errors"]:
            check["verified"], check["status"] = False, "mismatch"
    return {"explanation": expl, "source": model if expl else "unavailable", "display_text": display_text,
            "display_short": short, "display_truncated": truncated, "fact_block": facts, "framing": framing,
            "show_summary": bool(framing) and check["verified"],
            "latency_ms": round((time.perf_counter() - t0) * 1000), "error": error,
            "chosen_option": payload["decision"]["chosen"], "check": check}
