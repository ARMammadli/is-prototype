"""Record/replay of GenAI answers (LLM_MODE) for a server that cannot run the model."""
import json

import pytest

from llm import ollama_client as oc

SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}}


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "replay.jsonl"
    monkeypatch.setattr(oc, "REPLAY_PATH", path)
    monkeypatch.setattr(oc, "_store", None)
    return path


def no_network(*a, **k):
    raise AssertionError("replay must not touch the network")


def test_key_is_stable_and_prompt_specific():
    k = oc.cache_key("sys", "user", SCHEMA, "qwen3:8b")
    assert k == oc.cache_key("sys", "user", dict(reversed(list(SCHEMA.items()))), "qwen3:8b")
    assert k != oc.cache_key("sys", "user2", SCHEMA, "qwen3:8b")
    assert k != oc.cache_key("sys", "user", SCHEMA, "qwen3:4b")


def test_record_appends_once(store, monkeypatch):
    monkeypatch.setattr(oc, "LLM_MODE", "record")
    calls = []
    monkeypatch.setattr(oc, "_ollama", lambda *a: calls.append(a) or ({"text": "hi"}, None))
    assert oc.chat_json("s", "u", SCHEMA, "m", 5) == ({"text": "hi"}, None)
    assert oc.chat_json("s", "u", SCHEMA, "m", 5) == ({"text": "hi"}, None)
    rows = [json.loads(x) for x in store.read_text().splitlines()]
    assert len(calls) == 1 and len(rows) == 1
    assert rows[0]["kind"] == "explain" and rows[0]["answer"] == {"text": "hi"}


def test_record_skips_failures(store, monkeypatch):
    monkeypatch.setattr(oc, "LLM_MODE", "record")
    monkeypatch.setattr(oc, "_ollama", lambda *a: (None, "down"))
    assert oc.chat_json("s", "u", SCHEMA, "m", 5) == (None, "down")
    assert not store.exists()


def test_replay_hit_and_miss_without_network(store, monkeypatch):
    store.write_text(json.dumps({"key": oc.cache_key("s", "u", SCHEMA, "m"), "answer": {"text": "hi"}}) + "\n")
    monkeypatch.setattr(oc, "LLM_MODE", "replay")
    monkeypatch.setattr(oc.httpx, "post", no_network)
    monkeypatch.setattr(oc.httpx, "get", no_network)
    assert oc.chat_json("s", "u", SCHEMA, "m", 5) == ({"text": "hi"}, None)
    assert oc.chat_json("s", "other", SCHEMA, "m", 5) == (None, oc.NOT_RECORDED)
    assert oc.is_available() is True


def test_replay_empty_store_is_unavailable(store, monkeypatch):
    monkeypatch.setattr(oc, "LLM_MODE", "replay")
    assert oc.is_available() is False


def test_server_marks_replayed_and_missing_text(store, monkeypatch):
    from fastapi.testclient import TestClient

    from app import server
    from llm.factblock import FRAMING_SCHEMA, FRAMING_SYSTEM_PROMPT_RESTATE

    monkeypatch.setattr(oc, "LLM_MODE", "replay")
    monkeypatch.setattr(server, "LLM_MODE", "replay")
    monkeypatch.setattr(server, "is_replay", lambda: True)
    monkeypatch.setattr(oc.httpx, "post", no_network)
    c = TestClient(server.app)
    c.post("/api/demo")
    miss = c.post("/api/explain").json()
    assert miss["not_recorded"] is True and miss["framing"] is None and miss["fact_block"]
    user = json.dumps({"fact_block": miss["fact_block"]})
    key = oc.cache_key(FRAMING_SYSTEM_PROMPT_RESTATE, user, FRAMING_SCHEMA, "qwen3:8b")
    store.write_text(json.dumps({"key": key, "answer": {"text": "Nurse 03 moves to the day shift."}}) + "\n")
    monkeypatch.setattr(oc, "_store", None)
    hit = c.post("/api/explain").json()
    assert hit["source"] == "qwen3:8b (pre-generated)" and hit["not_recorded"] is False
    assert c.get("/api/llm-status").json()["mode"] == "replay"
