"""GenAI policy translator: manager's words -> PROPOSED load-score weights. Never applies anything."""
from __future__ import annotations

import json
import math
import time

from llm.ollama_client import chat_json

KEYS = ("QR", "N", "LR", "OT", "SN")

POLICY_SYSTEM_PROMPT = """You help a hospital manager turn a fairness policy written in words into numeric weights.
You receive JSON with the manager's policy text and the current weights for five roster items:
QR = quick returns, N = night shifts, LR = long runs of 6 or more working days in a row,
OT = overtime hours, SN = short-notice changes.
Return new weights from 0 to 10 for all five items. A higher weight means the hospital wants that item
avoided more. Keep the current weight for an item the policy does not mention.
Return a rationale of at most 80 words that names which words of the policy caused each change.
Do not invent constraints that are not in the text. Do not mention anything else."""


def policy_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "weights": {
                "type": "object",
                "properties": {k: {"type": "number", "minimum": 0, "maximum": 10} for k in KEYS},
                "required": list(KEYS),
            },
            "rationale": {"type": "string"},
        },
        "required": ["weights", "rationale"],
    }


def _valid(out) -> bool:
    if not isinstance(out, dict) or not isinstance(out.get("rationale"), str):
        return False
    w = out.get("weights")
    if not isinstance(w, dict):
        return False
    for k in KEYS:
        v = w.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 10:
            return False
    return True


def translate_policy(text: str, current_weights: dict, model: str, timeout: float) -> dict:
    t0 = time.perf_counter()
    proposal, error = None, None
    try:
        user = json.dumps({"policy_text": text, "current_weights": {k: current_weights.get(k) for k in KEYS}},
                          separators=(",", ":"))
        out, error = chat_json(POLICY_SYSTEM_PROMPT, user, policy_schema(), model, timeout)
        if out is None and error is None:
            error = "empty output"
        if out is not None:
            if _valid(out):
                proposal = {"weights": {k: float(out["weights"][k]) for k in KEYS},
                            "rationale": out["rationale"]}
            else:
                error = "invalid output shape or weights out of range"
    except Exception as exc:  # junk model output must never break the endpoint
        proposal, error = None, f"{type(exc).__name__}: {exc}"
    return {"proposal": proposal, "source": model if proposal else "unavailable", "error": error,
            "latency_ms": round((time.perf_counter() - t0) * 1000)}
