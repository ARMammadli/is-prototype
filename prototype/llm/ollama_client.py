"""Minimal Ollama chat client with JSON-schema structured output (spec §5)."""
from __future__ import annotations

import json
import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def chat_json(system: str, user: str, schema: dict, model: str, timeout: float):
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


def is_available(timeout: float = 2.0) -> bool:
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout).status_code == 200
    except (httpx.HTTPError, httpx.InvalidURL):
        return False
