import pytest

from llm.policy_translate import POLICY_SYSTEM_PROMPT, policy_schema, translate_policy

CUR = {"QR": 3, "N": 1, "LR": 2, "OT": 0.5, "SN": 1.5}
GOOD = {"weights": {"QR": 9, "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "quick returns above all"}


def _patch(monkeypatch, out, err=None):
    monkeypatch.setattr("llm.policy_translate.chat_json", lambda *a, **k: (out, err))


def test_schema_shape():
    sch = policy_schema()
    w = sch["properties"]["weights"]
    assert set(w["required"]) == {"QR", "N", "LR", "OT", "SN"}
    assert all(p["minimum"] == 0 and p["maximum"] == 10 for p in w["properties"].values())
    assert sch["properties"]["rationale"]["type"] == "string"
    assert "80 words" in POLICY_SYSTEM_PROMPT


def test_valid_proposal(monkeypatch):
    _patch(monkeypatch, GOOD)
    r = translate_policy("protect QR", CUR, "m", 5)
    assert r["source"] == "m" and r["error"] is None and r["proposal"]["weights"]["QR"] == 9
    assert r["proposal"]["rationale"] == "quick returns above all" and "latency_ms" in r


@pytest.mark.parametrize("bad", [
    {"weights": {"QR": 11, "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "x"},
    {"weights": {"QR": -1, "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "x"},
    {"weights": {"QR": 9, "N": 2, "LR": 2, "OT": 0.5}, "rationale": "x"},
    {"weights": {"QR": "9", "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "x"},
    {"weights": {"QR": True, "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "x"},
    {"weights": GOOD["weights"]},
])
def test_invalid_is_unavailable(monkeypatch, bad):
    _patch(monkeypatch, bad)
    r = translate_policy("t", CUR, "m", 5)
    assert r["proposal"] is None and r["source"] == "unavailable" and r["error"]


def test_llm_down(monkeypatch):
    _patch(monkeypatch, None, "ConnectError: down")
    r = translate_policy("t", CUR, "m", 5)
    assert r["proposal"] is None and r["source"] == "unavailable" and "down" in r["error"]


@pytest.mark.parametrize("junk", ["text", 5, [], [1], {}, {"weights": None}, {"weights": [], "rationale": 3}, None])
def test_never_raises_on_junk(monkeypatch, junk):
    _patch(monkeypatch, junk)
    assert translate_policy("t", CUR, "m", 5)["proposal"] is None


def test_chat_json_raising_is_contained(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr("llm.policy_translate.chat_json", boom)
    assert translate_policy("t", CUR, "m", 5)["source"] == "unavailable"
