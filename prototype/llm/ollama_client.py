"""Minimal Ollama chat client with JSON-schema structured output (spec §5).

LLM_MODE selects where answers come from:
- live (default): call Ollama.
- record: call Ollama and store every successful answer in the replay file.
- replay: answer only from the replay file (pre-generated on a machine that can run the model); never
  touches the network. A prompt that was not recorded returns (None, NOT_RECORDED) and callers fall back
  to the rule's facts, as they do when the model is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_MODE = os.environ.get("LLM_MODE", "live")
REPLAY_PATH = Path(os.environ.get("LLM_REPLAY_PATH", Path(__file__).resolve().parent.parent / "config" / "llm_replay.jsonl"))
NOT_RECORDED = "not pre-generated"

_store: dict[str, dict] | None = None
_lock = threading.Lock()

def cache_key(system: str, user: str, schema: dict, model: str) -> str:
    return hashlib.sha256(json.dumps([model, system, user, schema], sort_keys=True).encode()).hexdigest()

def _kind(schema: dict) -> str:
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    return "translate" if "weights" in props else "monthly" if "discussion_points" in props else "explain"

def _load() -> dict[str, dict]:
    global _store
    if _store is None:
        _store = {}
        if REPLAY_PATH.exists():
            for line in REPLAY_PATH.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    _store[row["key"]] = row
    return _store

def _ollama(system: str, user: str, schema: dict, model: str, timeout: float):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0},
    }
    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"]), None
    except (httpx.HTTPError, httpx.InvalidURL, KeyError, TypeError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"

def chat_json(system: str, user: str, schema: dict, model: str, timeout: float):
    if LLM_MODE == "replay":
        row = _load().get(cache_key(system, user, schema, model))
        return (row["answer"], None) if row else (None, NOT_RECORDED)
    if LLM_MODE == "record":
        key = cache_key(system, user, schema, model)
        with _lock:
            row = _load().get(key)
        if row:
            return row["answer"], None
        out, error = _ollama(system, user, schema, model, timeout)
        if out is not None:
            row = {"key": key, "kind": _kind(schema), "model": model, "answer": out,
                   "recorded_at": datetime.now().isoformat(timespec="seconds")}
            with _lock:
                _load()[key] = row
                REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
                with REPLAY_PATH.open("a") as fh:
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        return out, error
    return _ollama(system, user, schema, model, timeout)

def is_available(timeout: float = 2.0) -> bool:
    if LLM_MODE == "replay":
        return bool(_load())
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout).status_code == 200
    except (httpx.HTTPError, httpx.InvalidURL):
        return False

def is_replay() -> bool:
    return LLM_MODE == "replay"
