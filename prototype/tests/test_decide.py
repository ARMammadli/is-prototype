import pytest

from helpers import make_ward, roster_with  # noqa: F401  (ensures tests dir on path)
from llm import decide as dec
from llm.decide import build_decision_payload, decide, decision_schema
from sim.engine import Scenario
from sim.policies import generate_candidates, score_options
from sim.ward import load_json

FORBIDDEN = {"rank_strain", "rank_baseline", "is_baseline_top", "delta_strain", "cost", "comparison"}


@pytest.fixture(scope="module")
def payload():
    policy = load_json("policy.json")
    sc = Scenario(1)
    while True:
        ctx = sc.next_context()
        opts = generate_candidates(ctx)
        if len(opts) >= 3:
            break
        if opts:
            sc.apply(ctx, opts[0])
        else:
            sc.mark_unfilled(ctx)
    return build_decision_payload(ctx, score_options(ctx, opts, policy), policy)


def test_payload_has_no_rank_or_delta_keys(payload):
    assert set(payload) == {"event", "goal", "options"}
    assert "weights" not in payload
    assert "ortec_pick" not in payload
    assert set(payload["event"]) == {"absent", "day", "shift", "notice_h"}
    for o in payload["options"]:
        assert not (set(o) & FORBIDDEN)
        assert set(o) == {"id", "description", "kind", "n_changes", "changes", "nurses"}
        assert "Option_" not in o["description"] and "_" not in o["description"]
        for n in o["nurses"]:
            assert "load_before" in n and "load_after" in n
            assert "strain_before" not in n and "strain_after" not in n


def test_options_ordered_by_index(payload):
    idx = [int(o["id"].split("_")[1]) for o in payload["options"]]
    assert idx == sorted(idx) and len(set(idx)) == len(idx)


def test_schema_enum_equals_ids(payload):
    ids = [o["id"] for o in payload["options"]]
    schema = decision_schema(ids)
    assert schema["properties"]["chosen_option"]["enum"] == ids
    assert set(schema["required"]) == {"chosen_option", "main_tradeoff", "claims", "reasoning"}


def _reply(choice):
    return {"chosen_option": choice, "main_tradeoff": "stability", "claims": [], "reasoning": "Fewer changes."}


def test_agrees_true_and_false(payload, monkeypatch):
    ids = [o["id"] for o in payload["options"]]
    monkeypatch.setattr(dec, "chat_json", lambda *a, **k: (_reply(ids[0]), None))
    r = decide(payload, ids[0], "m", 1)
    assert r["agrees"] is True and r["source"] == "m" and r["check"]["no_claims"]
    r = decide(payload, ids[1], "m", 1)
    assert r["agrees"] is False and r["formula_top"] == ids[1]


def test_invalid_choice_is_unavailable(payload, monkeypatch):
    monkeypatch.setattr(dec, "chat_json", lambda *a, **k: (_reply("Option_99999"), None))
    r = decide(payload, "Option_1", "m", 1)
    assert r["decision"] is None and r["source"] == "unavailable" and r["error"] and r["agrees"] is False


def test_llm_down_is_unavailable(payload, monkeypatch):
    monkeypatch.setattr(dec, "chat_json", lambda *a, **k: (None, "ConnectError: down"))
    r = decide(payload, "Option_1", "m", 1)
    assert r["decision"] is None and r["source"] == "unavailable" and "down" in r["error"]


@pytest.mark.parametrize("junk", [{}, {"reasoning": 5, "claims": "x"}, {"reasoning": "from 1 to", "claims": [1, None, {"nurse": 3}]},
                                  {"reasoning": "Reduces from 2 to 9 and 99.5", "claims": [{"nurse": "Nurse_01"}]}])
def test_check_never_raises_on_junk(payload, junk):
    r = dec._check(junk, payload)
    assert "verified" in r
    assert dec._check(None, payload)["verified"] in (True, False)


def test_check_unverified_without_decision(payload):
    r = dec._check(None, payload)
    assert r["verified"] is False and r["claims_total"] == 0


def test_no_claims_not_verified_and_claims_match_chosen_only(payload):
    ids = [o["id"] for o in payload["options"]]
    assert dec._check({"chosen_option": ids[0], "reasoning": "x", "claims": []}, payload)["no_claims"]
    # a claim true only for another option's nurse must be false
    other = next(o for o in payload["options"] if o["id"] != ids[0])
    nd = next(n for n in other["nurses"] if n["nurse"] not in {m["nurse"] for m in payload["options"][0]["nurses"]})
    claim = {"nurse": nd["nurse"], "metric": "QR", "before": nd["before"]["QR"], "after": nd["after"]["QR"]}
    r = dec._check({"chosen_option": ids[0], "reasoning": "x", "claims": [claim]}, payload)
    assert r["claims_false"] == 1


def test_audit_path_env(monkeypatch):
    import importlib
    import app.server as server
    monkeypatch.setenv("ROSTER_AUDIT_PATH", "/tmp/claude-x/audit.jsonl")
    try:
        importlib.reload(server)
        assert str(server.AUDIT_PATH) == "/tmp/claude-x/audit.jsonl"
    finally:
        monkeypatch.delenv("ROSTER_AUDIT_PATH")
        importlib.reload(server)


def test_goal_is_plain_principles_without_formula(payload):
    g = payload["goal"]
    assert g.startswith("Every option covers the shift.")
    assert "quick return" in g and "load_before" in g and "disturb fewer people" in g
    for banned in ("weight", "point", "squar", "formula"):
        assert banned not in g.lower()
        assert banned not in dec.DECIDE_SYSTEM_PROMPT.lower().replace("do not use any formula or points", "")


def test_prompt_keeps_short_answer_rules():
    p = dec.DECIDE_SYSTEM_PROMPT
    assert "at most 3 short sentences" in p and "at most one alternative" in p and "at most 6 claims" in p
    assert "'reduces'" in p and "(1) avoid giving anyone a new quick return" in p


def test_goal_load_before_wording(payload):
    g = payload["goal"]
    assert "HIGHEST load_before" in g and "high load_before" in g
    assert "strain_" not in dec.DECIDE_SYSTEM_PROMPT


def test_check_reads_load_fields(payload, monkeypatch):
    o = payload["options"][0]
    n = o["nurses"][0]
    claim = {"nurse": n["nurse"], "metric": "QR", "before": n["before"]["QR"], "after": n["after"]["QR"]}
    reply = {"chosen_option": o["id"], "main_tradeoff": "stability", "claims": [claim],
             "reasoning": f"{n['nurse']} load goes from {n['load_before']} to {n['load_after']}."}
    monkeypatch.setattr(dec, "chat_json", lambda *a, **k: (reply, None))
    c = decide(payload, o["id"], "m", 1)["check"]
    assert c["claims_false"] == 0 and c["unsupported_numbers"] == [] and c["verified"]
