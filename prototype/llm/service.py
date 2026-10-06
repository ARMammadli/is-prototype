"""explain(): local LLM with template fallback, always followed by the deterministic check."""
from __future__ import annotations

import json
import time

from llm.checker import check
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
