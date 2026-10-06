import pytest
from fastapi.testclient import TestClient

import app.server as server
from sim.ward import load_json


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(server.STATE, "policy", load_json("policy.json"))
    monkeypatch.setattr("llm.service.chat_json", lambda *a, **k: (None, "ConnectError: down"))
    c = TestClient(server.app)
    c.post("/api/scenario", json={"seed": 1})
    return c


def _open_event(client):
    for _ in range(20):
        r = client.post("/api/next-event").json()
        if r["state"]["event"] and not r["state"]["event"]["unfilled"]:
            return r["state"]["event"]
    pytest.fail("no fillable event found")


def test_state_and_index(client):
    s = client.get("/api/state").json()
    assert s["seed"] == 1 and len(s["nurses"]) == 70 and s["event"] is None
    assert client.get("/").status_code == 200


def test_full_repair_flow_and_audit(client):
    ev = _open_event(client)
    base = client.get("/api/options?mode=baseline").json()["options"]
    strain = client.get("/api/options?mode=strain").json()["options"]
    assert base[0]["rank"] == 1 and "contract_h" in base[0]
    assert strain[0]["rank"] == 1 and "nurses" in strain[0]
    assert {o["id"] for o in base} <= {o["id"] for o in client.get("/api/options?mode=strain&limit=100").json()["options"]}
    ex = client.post("/api/explain").json()  # LLM down: no narrative, the rule's choice stands
    assert ex["source"] == "unavailable" and ex["explanation"] is None and ex["display_text"] is None
    assert ex["check"]["status"] == "unavailable" and ex["chosen_option"] == strain[0]["id"]
    assert ex["event_id"] == ev["event_id"]
    r = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": strain[0]["id"], "mode": "strain"})
    assert r.status_code == 200 and r.json()["state"]["event"] is None
    e = client.get("/api/audit").json()["entries"][-1]
    assert e["option_id"] == strain[0]["id"] and e["explanation_source"] == "unavailable"
    assert e["explanation_status"] == "unavailable" and "ConnectError" in e["explanation_error"]
    assert e["ranking"][0] == strain[0]["id"] and e["accepted_top"] is True and e["ortec_choice"].startswith("Option_")


def test_non_top_without_reason_is_rejected_then_accepted_with_reason(client):
    ev = _open_event(client)
    opts = client.get("/api/options?mode=baseline").json()["options"]
    if len(opts) < 2:
        pytest.skip("event has a single option")
    bad = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": opts[1]["id"], "mode": "baseline"})
    assert bad.status_code == 422
    assert client.get("/api/state").json()["event"] is not None
    ok = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": opts[1]["id"], "mode": "baseline",
                                         "override_reason": "local_knowledge"})
    assert ok.status_code == 200
    assert client.get("/api/audit").json()["entries"][-1]["override_reason"] == "local_knowledge"


def test_stale_option_and_no_event_return_409(client):
    ev = _open_event(client)
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    body = {"event_id": ev["event_id"], "option_id": top["id"], "mode": "baseline"}
    client.post("/api/apply", json=body)
    assert client.post("/api/apply", json=body).status_code == 409
    assert client.get("/api/options?mode=strain").status_code == 409
    assert client.post("/api/explain").status_code == 409


def test_next_event_while_open_returns_409(client):
    _open_event(client)
    assert client.post("/api/next-event").status_code == 409


def test_invalid_policy_is_rejected_and_unchanged(client):
    before = client.get("/api/policy").json()
    bad = {"weights": {"QR": -1, "N": 1, "LR": 2, "OT": 0.5, "SN": 1.5}, "forward_days": 28, "squared": True}
    assert client.put("/api/policy", json=bad).status_code == 422
    missing = {"weights": {"QR": 1}, "forward_days": 28, "squared": True}
    assert client.put("/api/policy", json=missing).status_code == 422
    assert client.get("/api/policy").json() == before


def test_valid_policy_rescores_open_event(client):
    _open_event(client)
    zero = {"weights": {k: 0 for k in ("QR", "N", "LR", "OT", "SN")}, "forward_days": 14, "squared": False}
    assert client.put("/api/policy", json=zero).status_code == 200
    b = [o["id"] for o in client.get("/api/options?mode=baseline&limit=100").json()["options"]]
    s = [o["id"] for o in client.get("/api/options?mode=strain&limit=100").json()["options"]]
    assert b == s


def test_option_id_from_resolved_event_is_stale_for_later_event(client):
    a = _open_event(client)
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    body = {"event_id": a["event_id"], "option_id": top["id"], "mode": "baseline"}
    assert client.post("/api/apply", json=body).status_code == 200
    b = _open_event(client)
    assert b["event_id"] != a["event_id"]
    before = client.get("/api/state").json()
    assert client.post("/api/apply", json=body).status_code == 409
    assert client.get("/api/state").json() == before
    assert before["event"] == b


def test_unknown_option_and_bad_reason(client):
    ev = _open_event(client)
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    r = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": "Option_9999", "mode": "baseline"})
    assert r.status_code == 409
    r = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top["id"],
                                        "mode": "baseline", "override_reason": "bogus"})
    assert r.status_code == 422
    assert client.post("/api/apply", json={"option_id": top["id"], "mode": "baseline"}).status_code == 422


def test_response_shapes(client):
    ev = _open_event(client)
    s = client.get("/api/state").json()
    assert s["app_mode"] == "rule_explains" and s["default_mode"] == "strain"
    assert set(s) == {"seed", "app_mode", "default_mode", "days", "nurses", "grid", "changed", "absent", "leave", "event",
                      "remaining_events", "unfilled", "strain", "kpis", "preview", "headline", "scoreboard", "since_takeover", "autoplay_running"}
    assert set(s["event"]) == {"event_id", "absent", "day", "shift", "notice_h", "unfilled"}
    assert set(s["kpis"]) == {"gini", "top10_qr_share", "max_qr"}
    base = client.get("/api/options?mode=baseline").json()["options"][0]
    assert set(base) == {"id", "rank", "kind", "change_text", "description", "nurse", "contract_h", "hours_period", "n_changes"}
    st = client.get("/api/options?mode=strain").json()["options"][0]
    assert set(st) == {"id", "rank", "rank_baseline", "kind", "change_text", "description", "n_changes", "delta_strain", "nurses"}


def _fake_decide(choice_index):
    def fake(system, user, schema, model, timeout):
        ids = schema["properties"]["chosen_option"]["enum"]
        return {"chosen_option": ids[choice_index], "main_tradeoff": "stability", "claims": [],
                "reasoning": "Fewer changes."}, None
    return fake

def test_decide_requires_event(client):
    assert client.post("/api/decide").status_code == 409

def test_decide_and_ai_options(client, monkeypatch):
    monkeypatch.setattr("llm.decide.chat_json", _fake_decide(0))
    ev = _open_event(client)
    ai = client.get("/api/options?mode=ai").json()
    st = client.get("/api/options?mode=strain").json()
    assert ai["mode"] == "ai" and ai["options"][0] == st["options"][0]
    r = client.post("/api/decide").json()
    assert r["event_id"] == ev["event_id"] and r["decision"]["chosen_option"].startswith("Option_")
    assert r["formula_top"] == st["options"][0]["id"] and "check" in r

def test_apply_ai_mode_override_and_audit(client, monkeypatch):
    monkeypatch.setattr("llm.decide.chat_json", _fake_decide(0))
    ev = _open_event(client)
    r = client.post("/api/decide").json()
    pick = r["decision"]["chosen_option"]
    others = [o["id"] for o in client.get("/api/options?mode=ai&limit=100").json()["options"] if o["id"] != pick]
    if not others:
        pytest.skip("single option")
    body = {"event_id": ev["event_id"], "option_id": others[0], "mode": "ai"}
    assert client.post("/api/apply", json=body).status_code == 422
    assert client.post("/api/apply", json={**body, "override_reason": "preference"}).status_code == 200
    e = client.get("/api/audit").json()["entries"][-1]
    assert e["ai_choice"] == pick and e["formula_top"] == r["formula_top"]
    assert e["ai_agrees"] == (pick == r["formula_top"]) and e["mode"] == "ai" and e["top_option"] == pick
    assert e["explanation_source"] == r["source"] and e["rank"] >= 2

def test_apply_ai_pick_needs_no_reason(client, monkeypatch):
    monkeypatch.setattr("llm.decide.chat_json", _fake_decide(1))
    ev = _open_event(client)
    r = client.post("/api/decide").json()
    ok = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": r["decision"]["chosen_option"], "mode": "ai"})
    assert ok.status_code == 200
    assert client.get("/api/audit").json()["entries"][-1]["rank"] == 1

def test_ai_options_cover_candidate_set(client):
    from llm.decide import build_decision_payload
    _open_event(client)
    ids = {o["id"] for o in build_decision_payload(server.STATE.ctx, server.STATE.scored, server.STATE.policy)["options"]}
    shown = client.get("/api/options?mode=ai&limit=1").json()["options"]
    assert ids == {o["id"] for o in shown}
    ranks = [o["rank"] for o in shown]
    assert ranks == sorted(ranks)

def test_ai_apply_without_decision_logs_verified_none(client):
    ev = _open_event(client)
    top = client.get("/api/options?mode=ai").json()["options"][0]
    assert client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top["id"], "mode": "ai"}).status_code == 200
    assert client.get("/api/audit").json()["entries"][-1]["verified"] is None


PREVIEW_KEYS = {"QR_total", "nurses_qr_ge3_28d", "max_qr", "gini_strain", "unfilled", "SN_total", "changes_per_repair"}

def test_preview_has_both_policies(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)  # no e5 file -> no GenAI column
    client.post("/api/scenario", json={"seed": 1})
    pv = client.get("/api/state").json()["preview"]
    assert set(pv) == {"baseline", "strain"} and set(pv["baseline"]) == PREVIEW_KEYS == set(pv["strain"])

def test_scoreboard_shadow_and_history(client):
    sb = client.get("/api/state").json()["scoreboard"]
    assert set(sb) == {"ours", "ortec", "history", "start"} and sb["history"] == []
    assert set(sb["ours"]) == {"quick_returns", "nurses_qr_ge3_28d", "max_load", "short_notice_calls", "shifts_changed"}
    assert sb["ours"] == sb["ortec"]
    ev = _open_event(client)
    done = server.STATE.shadow.remaining
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top["id"], "mode": "baseline"})
    assert server.STATE.shadow.remaining < done or done == 0
    assert (server.STATE.shadow.peek_event_id() or 10**9) > ev["event_id"]
    sb = client.get("/api/state").json()["scoreboard"]
    assert len(sb["history"]) == 1 and set(sb["history"][0]) == {"n", "ours_qr", "ortec_qr", "ours_ge3", "ortec_ge3", "ours_avoided", "ortec_avoided",
                                                                  "ours_extra_calls", "ortec_extra_calls", "ours_ge3_change", "ortec_ge3_change"}
    assert sb["ours"]["shifts_changed"] >= 1 and sb["ortec"]["shifts_changed"] >= 1
    assert sb["ours"] == sb["ortec"]  # baseline top applied on both sides

def test_fast_forward_to_day(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM must not be called")
    monkeypatch.setattr("llm.service.chat_json", boom)
    monkeypatch.setattr("llm.decide.chat_json", boom)
    r = client.post("/api/fast-forward", json={"to_day": 15, "mode": "ai"}).json()
    assert r["resolved"] > 0 and r["resolved_open"] == 0
    st = r["state"]
    assert st["event"] is not None or st["remaining_events"] == 0
    if st["event"] is not None:
        assert server.STATE.ctx.reveal_time >= 14 * 24
    assert len(st["scoreboard"]["history"]) >= r["resolved"]
    last = client.get("/api/audit").json()["entries"][-1]
    assert last["mode"] == "auto" and last["explanation_source"] is None
    nxt = server.STATE.shadow.peek_event_id()
    assert nxt is None or nxt > last["event_id"]

def test_fast_forward_events_and_open_event(client):
    ev = _open_event(client)
    r = client.post("/api/fast-forward", json={"events": 3, "mode": "baseline"}).json()
    assert r["resolved"] >= 3 and r["resolved_open"] == 1
    assert r["state"]["event"] is None or r["state"]["event"]["event_id"] != ev["event_id"]

def test_fast_forward_requires_exactly_one_field(client):
    assert client.post("/api/fast-forward", json={"to_day": 10, "events": 5}).status_code == 422
    assert client.post("/api/fast-forward", json={}).status_code == 422

def test_options_include_comparison_in_all_modes(client):
    _open_event(client)
    for mode in ("baseline", "strain", "ai"):
        c = client.get(f"/api/options?mode={mode}").json()["comparison"]
        assert set(c) == {"ours", "ortec", "plain_words", "difference", "who_words", "card_lines", "rest_lines"} and c["plain_words"] and "Option_" not in c["who_words"]
        assert {"id", "change_text", "description", "new_quick_returns", "heaviest_before", "heaviest_after",
                "people_disturbed", "load_added", "extra_work", "relief", "involved"} == set(c["ours"])


def test_reset_clears_shadow_and_history_and_policy_put_refreshes_preview(client):
    client.post("/api/fast-forward", json={"events": 3})
    assert client.get("/api/state").json()["scoreboard"]["history"]
    client.post("/api/scenario", json={"seed": 1})
    sb = client.get("/api/state").json()["scoreboard"]
    assert sb["history"] == [] and sb["ours"] == sb["ortec"]
    before = client.get("/api/state").json()["preview"]["strain"]
    zero = {"weights": {k: 0 for k in ("QR", "N", "LR", "OT", "SN")}, "forward_days": 14, "squared": False}
    assert client.put("/api/policy", json=zero).status_code == 200
    after = client.get("/api/state").json()["preview"]["strain"]
    assert after != before


# ---- GenAI labels / policy translator / E5 column ----
_GOOD_PROPOSAL = {"weights": {"QR": 9, "N": 2, "LR": 2, "OT": 0.5, "SN": 7}, "rationale": "quick returns above all"}


def test_translate_returns_proposal_and_does_not_change_policy(client, monkeypatch):
    monkeypatch.setattr("llm.policy_translate.chat_json", lambda *a, **k: (_GOOD_PROPOSAL, None))
    before = client.get("/api/policy").json()
    r = client.post("/api/policy/translate", json={"text": "protect quick returns"}).json()
    assert r["proposal"]["weights"]["QR"] == 9 and r["current"] == before["weights"] and r["source"] != "unavailable"
    assert client.get("/api/policy").json() == before
    assert not server.AUDIT_PATH.exists()


def test_translate_unavailable_when_llm_down(client, monkeypatch):
    monkeypatch.setattr("llm.policy_translate.chat_json", lambda *a, **k: (None, "down"))
    r = client.post("/api/policy/translate", json={"text": "x"}).json()
    assert r["proposal"] is None and r["source"] == "unavailable"


def test_translate_text_validation(client):
    assert client.post("/api/policy/translate", json={"text": ""}).status_code == 422
    assert client.post("/api/policy/translate", json={"text": "a" * 1001}).status_code == 422
    assert client.post("/api/policy/translate", json={}).status_code == 422


def test_put_policy_genai_writes_policy_audit_entry(client):
    body = {"weights": _GOOD_PROPOSAL["weights"], "forward_days": 14, "squared": False,
            "source": "genai", "policy_text": "protect quick returns"}
    assert client.put("/api/policy", json=body).status_code == 200
    e = client.get("/api/audit").json()["entries"][-1]
    assert e["mode"] == "policy" and e["source"] == "genai" and e["policy_text"] == "protect quick returns"
    assert e["weights"]["QR"] == 9 and e["forward_days"] == 14 and e["squared"] is False


def test_put_policy_defaults_to_manual_and_validates_source(client):
    base = {"weights": _GOOD_PROPOSAL["weights"], "forward_days": 14, "squared": True}
    assert client.put("/api/policy", json=base).status_code == 200
    assert client.get("/api/audit").json()["entries"][-1]["source"] == "manual"
    assert client.put("/api/policy", json={**base, "source": "robot"}).status_code == 422
    assert client.put("/api/policy", json={**base, "policy_text": "a" * 1001}).status_code == 422


def test_decide_includes_comparison(client, monkeypatch):
    monkeypatch.setattr("llm.decide.chat_json", _fake_decide(1))
    _open_event(client)
    r = client.post("/api/decide").json()
    c = r["comparison"]
    assert set(c) == {"ours", "ortec", "plain_words", "difference", "who_words", "card_lines", "rest_lines", "formula_top"}
    assert c["ours"]["id"] == r["decision"]["chosen_option"] and c["formula_top"] == r["formula_top"]
    assert c["ortec"]["id"] == client.get("/api/options?mode=baseline").json()["comparison"]["ortec"]["id"]
    assert c["plain_words"]


def test_decide_without_decision_has_no_comparison(client, monkeypatch):
    monkeypatch.setattr("llm.decide.chat_json", lambda *a, **k: (None, "ConnectError: down"))
    _open_event(client)
    r = client.post("/api/decide").json()
    assert r["decision"] is None and "comparison" not in r


def _write_e5(tmp_path, seed, rows=1):
    cols = ["seed", "policy", *server.PREVIEW_KEYS]
    lines = [",".join(cols)]
    for _ in range(rows):
        lines.append(",".join([str(seed), "ai", "5", "3", "1", "0.2", "0", "2", "1.5"]))
    lines.append(",".join([str(seed), "baseline"] + ["9"] * len(server.PREVIEW_KEYS)))
    (tmp_path / "e5_runs.csv").write_text("\n".join(lines) + "\n")


def test_preview_includes_genai_column_when_e5_present(client, monkeypatch, tmp_path):
    _write_e5(tmp_path, 1)
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    pv = client.post("/api/scenario", json={"seed": 1}).json()["preview"]
    assert set(pv) == {"baseline", "strain", "ai"} and set(pv["ai"]) == PREVIEW_KEYS
    assert pv["ai"]["QR_total"] == 5 and pv["ai"]["changes_per_repair"] == 1.5


def test_preview_without_genai_for_other_seed_missing_or_bad_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    assert "ai" not in client.post("/api/scenario", json={"seed": 1}).json()["preview"]  # no file
    _write_e5(tmp_path, 4)
    assert "ai" not in client.post("/api/scenario", json={"seed": 1}).json()["preview"]  # other seed
    (tmp_path / "e5_runs.csv").write_bytes(b"\xff\xfe garbage\n1,2")
    assert "ai" not in client.post("/api/scenario", json={"seed": 1}).json()["preview"]  # unreadable


def _e5_text(tmp_path, body):
    cols = ["seed", "policy", *server.PREVIEW_KEYS]
    (tmp_path / "e5_runs.csv").write_text(",".join(cols) + "\n" + body)


def test_e5_nan_row_is_skipped_not_500(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    _e5_text(tmp_path, "1,ai,5,3,1,nan,0,2,1.5\n")
    r = client.post("/api/scenario", json={"seed": 1})
    assert r.status_code == 200 and "ai" not in r.json()["preview"]
    assert client.get("/api/state").status_code == 200
    body = {"weights": {"QR": 1, "N": 1, "LR": 1, "OT": 1, "SN": 1}, "forward_days": 14, "squared": True}
    assert client.put("/api/policy", json=body).status_code == 200
    _e5_text(tmp_path, "1,ai,5,3,1,inf,0,2,1.5\n1,ai,4,3,1,0.2,0,2,1.0\n")  # good row still used
    assert client.post("/api/scenario", json={"seed": 1}).json()["preview"]["ai"]["QR_total"] == 4


def test_e5_missing_seed_and_truncated_row(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    _e5_text(tmp_path, "7,ai,5,3,1,0.2,0,2,1.5\n")
    assert "ai" not in client.post("/api/scenario", json={"seed": 1}).json()["preview"]
    _e5_text(tmp_path, "1,ai,5,3\n")
    assert "ai" not in client.post("/api/scenario", json={"seed": 1}).json()["preview"]


# ---- plain-English display fields and GenAI autoplay --------------------------------------------
import time


def _coded_decide(system, user, schema, model, timeout):
    ids = schema["properties"]["chosen_option"]["enum"]
    return {"chosen_option": ids[0], "main_tradeoff": "stability", "claims": [],
            "reasoning": "adds 1 to QR and 1 to SN; strain up. Second sentence."}, None


def test_explain_and_decide_add_display_text(client, monkeypatch):
    def coded_explain(system, user, schema, model, timeout):
        import json
        pl = json.loads(user)
        return {"recommended_option": pl["comparison"]["recommended"], "main_tradeoff": pl["comparison"]["main_driver"],
                "claims": [], "text": "It adds 1 to QR for Nurse_68."}, None
    monkeypatch.setattr("llm.service.chat_json", coded_explain)
    monkeypatch.setattr("llm.decide.chat_json", _coded_decide)
    _open_event(client)
    ex = client.post("/api/explain").json()
    assert ex["explanation"]["text"] == "It adds 1 to QR for Nurse_68."  # raw text untouched
    assert ex["display_text"] == "It adds 1 to quick returns for Nurse_68."
    d = client.post("/api/decide").json()
    assert d["decision"]["reasoning"].startswith("adds 1 to QR and 1 to SN; strain up")
    assert d["display_text"] == "adds 1 to quick returns and 1 to last-minute call-ins; load up. Second sentence."
    for r in (ex, d):
        assert r["display_short"] == r["display_text"] and r["display_truncated"] is False


def test_display_short_truncates_long_text(client, monkeypatch):
    long = "First point. Second point. Third point. Fourth point."
    monkeypatch.setattr("llm.decide.chat_json", lambda s, u, sc, m, t: (
        {"chosen_option": sc["properties"]["chosen_option"]["enum"][0], "main_tradeoff": "stability",
         "claims": [], "reasoning": long}, None))
    _open_event(client)
    d = client.post("/api/decide").json()
    assert d["display_short"] == "First point. Second point." and d["display_truncated"] is True
    assert d["display_text"] == long and d["decision"]["reasoning"] == long


def test_explain_gets_rule_choice_and_policy_text_and_never_picks(client, monkeypatch):
    import json
    seen = {}

    def fake(system, user, schema, model, timeout):
        seen["payload"], seen["schema"] = json.loads(user), schema
        return {"claims": [], "text": "Pick another option instead."}, None
    monkeypatch.setattr("llm.service.chat_json", fake)
    ev = _open_event(client)
    client.put("/api/policy", json={"weights": load_json("policy.json")["weights"], "forward_days": 28,
                                    "squared": True, "source": "genai", "policy_text": "Protect night workers."})
    top = client.get("/api/options?mode=strain").json()["options"][0]["id"]
    ex = client.post("/api/explain").json()
    assert "chosen_option" not in seen["schema"]["properties"] and "recommended_option" not in seen["schema"]["properties"]
    assert seen["payload"]["decision"]["chosen"] == top == ex["chosen_option"]
    assert seen["payload"]["policy_text"] == "Protect night workers."
    r = client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top, "mode": "strain"})
    assert r.status_code == 200  # the model's words cannot move the choice


def _first_id(system, user, schema, model, timeout):
    return {"chosen_option": schema["properties"]["chosen_option"]["enum"][0], "main_tradeoff": "stability",
            "claims": [], "reasoning": "Fewer changes. More text."}, None


def _slow(delay=0.3):
    def f(*a, **k):
        time.sleep(delay)
        return _first_id(*a, **k)
    return f


def _wait_auto(client, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get("/api/autoplay/status").json()
        if not s["running"]:
            return s
        time.sleep(0.05)
    pytest.fail("autoplay did not finish")


@pytest.fixture
def auto_client(client):
    server._auto_reset()
    yield client
    client.post("/api/autoplay/stop")
    _wait_auto(client)


def test_autoplay_ai_runs_events_and_leaves_event_open(auto_client, monkeypatch):
    client = auto_client
    monkeypatch.setattr("llm.decide.chat_json", _first_id)
    _open_event(client)  # an open event is resolved first and counts as the first of the three
    n_hist = len(client.get("/api/state").json()["scoreboard"]["history"])
    r = client.post("/api/autoplay", json={"events": 3, "mode": "ai"})
    assert r.status_code == 200 and r.json() == {"started": True}
    s = _wait_auto(client)
    assert s["error"] is None and s["done"] == 3 and s["total"] == 3 and len(s["log"]) == 3
    it = s["log"][0]
    assert {"event_id", "absent", "day", "shift", "chosen", "chosen_change_text", "by", "agrees_with_formula",
            "verified", "display_text", "plain_words", "description"} <= set(it)
    assert it["description"] and "Option_" not in it["description"]
    assert it["shift"] in ("Day", "Evening", "Night") and it["day"] >= 1 and it["by"] == "GenAI"
    assert it["display_text"] == "Fewer changes."
    entries = [e for e in client.get("/api/audit").json()["entries"] if e["mode"] == "auto-ai"]
    assert len(entries) == 3
    assert {"ai_choice", "formula_top", "ai_agrees", "ai_verified"} <= set(entries[0])
    st = client.get("/api/state").json()
    assert st["event"] is not None and st["autoplay_running"] is False
    assert len(st["scoreboard"]["history"]) == n_hist + 3
    # shadow synced: ORTEC scoreboard covers the same events
    assert st["scoreboard"]["history"][-1]["n"] == n_hist + 3


@pytest.mark.parametrize("mode,by", [("strain", "Formula"), ("baseline", "ORTEC-like")])
def test_autoplay_non_llm_modes(auto_client, monkeypatch, mode, by):
    client = auto_client
    monkeypatch.setattr("llm.decide.chat_json", lambda *a, **k: pytest.fail("LLM must not be called"))
    client.post("/api/autoplay", json={"events": 2, "mode": mode})
    s = _wait_auto(client)
    assert s["done"] == 2 and s["error"] is None and all(i["by"] == by for i in s["log"])
    assert len([e for e in client.get("/api/audit").json()["entries"] if e["mode"] == f"auto-{mode}"]) == 2


def test_autoplay_blocks_other_mutations_and_rejects_second_start(auto_client, monkeypatch):
    client = auto_client
    monkeypatch.setattr("llm.decide.chat_json", _slow())
    assert client.post("/api/autoplay", json={"events": 2, "mode": "ai"}).status_code == 200
    assert client.get("/api/state").json()["autoplay_running"] is True
    assert client.get("/api/autoplay/status").json()["running"] is True
    assert client.post("/api/autoplay", json={"events": 2, "mode": "ai"}).status_code == 409
    for path, body in [("/api/next-event", None), ("/api/scenario", {"seed": 2}), ("/api/fast-forward", {"events": 1}),
                       ("/api/decide", None), ("/api/explain", None),
                       ("/api/apply", {"event_id": 0, "option_id": "Option_1", "mode": "strain"})]:
        r = client.post(path, json=body) if body is not None else client.post(path)
        assert r.status_code == 409 and r.json()["detail"] == "GenAI autoplay running", path
    pol = client.get("/api/policy").json()
    assert client.put("/api/policy", json={"weights": pol["weights"], "forward_days": 14, "squared": True}).status_code == 409
    s = _wait_auto(client)
    assert s["done"] == 2 and s["error"] is None
    assert client.post("/api/fast-forward", json={"events": 1}).status_code == 200


def test_autoplay_stop_ends_early(auto_client, monkeypatch):
    client = auto_client
    monkeypatch.setattr("llm.decide.chat_json", _slow())
    client.post("/api/autoplay", json={"events": 10, "mode": "ai"})
    time.sleep(0.1)
    assert client.post("/api/autoplay/stop").status_code == 200
    s = _wait_auto(client)
    assert 1 <= s["done"] < 10 and s["error"] is None
    assert client.get("/api/state").json()["event"] is not None


def test_autoplay_fallback_applies_formula_top(auto_client, monkeypatch):
    client = auto_client
    monkeypatch.setattr("llm.decide.chat_json", lambda *a, **k: (None, "ConnectError: down"))
    client.post("/api/autoplay", json={"events": 2, "mode": "ai"})
    s = _wait_auto(client)
    assert s["done"] == 2 and all(i["by"] == "Formula (fallback)" and i["chosen"] == i["formula_top"] for i in s["log"])
    entries = [e for e in client.get("/api/audit").json()["entries"] if e["mode"] == "auto-ai"]
    assert all(e["fallback"] and e["option_id"] == e["formula_top"] and e["ai_choice"] is None for e in entries)


def test_autoplay_unknown_ai_option_falls_back(auto_client, monkeypatch):
    client = auto_client
    monkeypatch.setattr(server, "decide", lambda payload, top, model, timeout: {
        "decision": {"chosen_option": "Option_999", "main_tradeoff": "stability", "claims": [], "reasoning": "x."},
        "source": "m", "display_text": "x.", "check": {"verified": True}})
    client.post("/api/autoplay", json={"events": 2, "mode": "ai"})
    s = _wait_auto(client)
    assert s["error"] is None and s["done"] == 2
    assert all(i["by"] == "Formula (fallback)" and i["chosen"] == i["formula_top"] and i["verified"] is None for i in s["log"])


def test_autoplay_validates_input(auto_client):
    assert auto_client.post("/api/autoplay", json={"events": 0}).status_code == 422
    assert auto_client.post("/api/autoplay", json={"events": 31}).status_code == 422
    assert auto_client.post("/api/autoplay", json={"events": 2, "mode": "x"}).status_code == 422


def test_first_sentence():
    assert server._first_sentence("One. Two.") == "One."
    assert server._first_sentence("No stop") == "No stop"
    assert server._first_sentence("Nurse_1 gets 1.5 more hours. Next.") == "Nurse_1 gets 1.5 more hours."


# ---- headline, fair start, option-id backstop ---------------------------------------------------
def _e5_files(tmp_path, ai_qr="133.2", ai_unf="1.2", seeds=(0, 1, 2)):
    cols = "policy,QR_total,nurses_qr_ge3_28d,unfilled"
    (tmp_path / "e5_summary.csv").write_text(f"{cols}\nbaseline,200,20,1.2\nstrain,100,5,1.2\nai,{ai_qr},10,{ai_unf}\n")
    runs = ["seed,policy"] + [f"{s},ai" for s in seeds] + [f"{s},baseline" for s in seeds]
    (tmp_path / "e5_runs.csv").write_text("\n".join(runs) + "\n")


def test_headline_values_and_unfilled_flag(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    _e5_files(tmp_path, ai_qr="150")
    h = client.get("/api/state").json()["headline"]
    assert h["qr_pct"] == 25 and h["ge3_pct"] == 50 and h["unfilled_same"] is True and h["n_wards"] == 3
    _e5_files(tmp_path, ai_unf="2.0")
    h = client.get("/api/state").json()["headline"]
    assert h["unfilled_same"] is False and h["unfilled_ai"] == 2.0 and h["unfilled_baseline"] == 1.2


def test_headline_real_results_and_bad_files(client, monkeypatch, tmp_path):
    h = client.get("/api/state").json()["headline"]
    assert h is not None and h["qr_pct"] > 0 and h["n_wards"] >= 1
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    assert client.get("/api/state").json()["headline"] is None  # missing
    (tmp_path / "e5_summary.csv").write_bytes(b"\xff\xfe junk")
    (tmp_path / "e5_runs.csv").write_text("seed,policy\n0,ai\n")
    assert client.get("/api/state").json()["headline"] is None
    (tmp_path / "e5_summary.csv").write_text("policy,QR_total,nurses_qr_ge3_28d,unfilled\nbaseline,0,0,1\nai,1,1,1\n")
    assert client.get("/api/state").json()["headline"] is None  # no division by zero
    (tmp_path / "e5_summary.csv").write_text("policy,QR_total,nurses_qr_ge3_28d,unfilled\nbaseline,5,5,1\nai,x,1,1\n")
    assert client.get("/api/state").json()["headline"] is None


def test_fast_forward_reset_history_gives_identical_start(client):
    r = client.post("/api/fast-forward", json={"to_day": 29, "mode": "baseline", "reset_history": True}).json()
    sb = r["state"]["scoreboard"]
    assert r["resolved"] > 0 and sb["history"] == []
    assert sb["ours"] == sb["ortec"]
    assert sb["start"]["qr"] == sb["ours"]["quick_returns"]
    ev = r["state"]["event"]
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top["id"], "mode": "baseline"})
    sb = client.get("/api/state").json()["scoreboard"]
    assert len(sb["history"]) == 1 and sb["ours"] == sb["ortec"]
    assert sb["history"][0]["ours_qr"] == sb["history"][0]["ortec_qr"]


def test_fast_forward_keeps_history_by_default(client):
    client.post("/api/fast-forward", json={"events": 3, "mode": "baseline"})
    assert len(client.get("/api/state").json()["scoreboard"]["history"]) >= 3


def test_option_ids_replaced_in_display_text_only(client, monkeypatch):
    def chatty(system, user, schema, model, timeout):
        ids = schema["properties"]["chosen_option"]["enum"]
        return {"chosen_option": ids[0], "main_tradeoff": "stability", "claims": [],
                "reasoning": f"{ids[0]} is fairest. Option_999 is worse."}, None
    monkeypatch.setattr("llm.decide.chat_json", chatty)
    _open_event(client)
    d = client.post("/api/decide").json()
    chosen = d["decision"]["chosen_option"]
    assert chosen in d["decision"]["reasoning"]  # raw text untouched
    desc = next(o["description"] for o in client.get("/api/options?mode=ai").json()["options"] if o["id"] == chosen)
    assert "Option_" not in d["display_text"] and "Option_" not in d["display_short"]
    assert d["display_text"].startswith(f"\u201c{desc}\u201d is fairest. another option is worse.")


ZERO = {"quick_returns_avoided": 0, "quick_returns_change": 0, "extra_late_calls": 0, "nurses_3plus_change": 0}


def test_since_takeover_zero_then_counts(client):
    st = client.get("/api/state").json()["since_takeover"]
    assert st == {"ours": ZERO, "ortec": ZERO, "calls_handled": 0}
    r = client.post("/api/fast-forward", json={"to_day": 29, "mode": "baseline", "reset_history": True}).json()
    assert r["state"]["since_takeover"] == {"ours": ZERO, "ortec": ZERO, "calls_handled": 0}
    ev = r["state"]["event"]
    top = client.get("/api/options?mode=strain").json()["options"][0]
    client.post("/api/apply", json={"event_id": ev["event_id"], "option_id": top["id"], "mode": "strain"})
    s = client.get("/api/state").json()
    st, h = s["since_takeover"], s["scoreboard"]["history"][-1]
    assert st["calls_handled"] == 1
    tk, sb = server.STATE.takeover, s["scoreboard"]
    assert st["ours"]["quick_returns_avoided"] == tk["ours"]["quick_returns"] - sb["ours"]["quick_returns"]
    assert st["ortec"]["extra_late_calls"] == sb["ortec"]["short_notice_calls"] - tk["ortec"]["short_notice_calls"]
    assert st["ours"]["quick_returns_change"] == -st["ours"]["quick_returns_avoided"]
    assert st["ortec"]["quick_returns_change"] == sb["ortec"]["quick_returns"] - tk["ortec"]["quick_returns"]
    assert h["ours_avoided"] == st["ours"]["quick_returns_avoided"] and h["ortec_extra_calls"] == st["ortec"]["extra_late_calls"]


def test_reset_history_forces_baseline_policy(client):
    client.post("/api/fast-forward", json={"to_day": 29, "mode": "strain", "reset_history": True})
    sb = client.get("/api/state").json()["scoreboard"]
    assert sb["ours"] == sb["ortec"]  # a client cannot break the fair start


def test_comparison_card_lines_in_options(client):
    _open_event(client)
    cl = client.get("/api/options?mode=ai").json()["comparison"]["card_lines"]
    assert set(cl) == {"ours", "ortec", "rest_lines"} and len(cl["ours"]) >= 2 and len(cl["ortec"]) >= 2
    assert all(cl["rest_lines"][k] for k in ("ours", "ortec"))
    assert cl["ortec"][1].startswith("Result:") and cl["ours"][1].startswith("Result:")


# ---- /api/results ---------------------------------------------------------------------------------
RES_COLS = "arm,seed,QR_total,nurses_qr_ge3_28d,max_qr,unfilled,SN_total,changes_per_repair"


def _res_files(tmp_path, b_rows=None, expl=None):
    b_rows = b_rows if b_rows is not None else ["B,0,100,10,5,1,80,1.5", "B,1,90,8,4,0,70,1.6"]
    rows = ["A,0,200,20,6,1,50,1.0", "A,1,100,10,3,0,60,1.0", "A,2,5,5,5,5,5,1", "C,0,120,12,5,1,90,1.9"] + b_rows
    (tmp_path / "e6_runs.csv").write_text("\n".join([RES_COLS] + rows) + "\n")
    if expl:
        (tmp_path / "e6_explanations_summary.csv").write_text(
            "model,n_decisions,valid_output_rate,fact_check_pass_rate,direction_error_rate,mean_latency_s\n" + expl + "\n")


def test_results_values(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    _res_files(tmp_path, expl="qwen3:8b,400,1.0,0.9,0.05,10.2")
    r = client.get("/api/results").json()
    assert r["available"] and r["n_wards"] == 2 and r["n_exp_wards"] == 1  # seed 2 has no B row
    qr = next(m for m in r["metrics"] if m["key"] == "QR_total")
    assert qr["baseline"] == {"mean": 150.0, "min": 100.0, "max": 200.0}
    assert qr["ours"] == {"mean": 95.0, "min": 90.0, "max": 100.0} and qr["wins"] == 2 and qr["cost"] is False
    assert qr["exp"] == {"mean": 120.0, "min": 120.0, "max": 120.0} and qr["exp_wins"] == 1
    assert round(qr["change_pct"], 1) == -36.7
    mx = next(m for m in r["metrics"] if m["key"] == "max_qr")
    assert mx["wins"] == 1 and mx["ties"] == 0  # ward 2: 4 vs 3 is worse
    sn = next(m for m in r["metrics"] if m["key"] == "SN_total")
    assert sn["cost"] is True and sn["wins"] == 0
    assert [w["ward"] for w in r["wards"]] == [1, 2]
    assert r["wards"][0]["values"]["QR_total"] == {"baseline": 200.0, "ours": 100.0, "exp": 120.0}
    assert r["explanations"]["fact_check_pass_rate"] == 0.9 and r["explanations"]["model"] == "qwen3:8b"


def test_results_without_explanations(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    _res_files(tmp_path)
    r = client.get("/api/results").json()
    assert r["available"] and r["explanations"] is None


def test_results_missing_or_bad_files(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS_DIR", tmp_path)
    assert client.get("/api/results").json() == {"available": False}  # nothing there
    _res_files(tmp_path, b_rows=["B,0,nan,10,5,1,80,1.5", "B,1,,8,4,0,70,1.6"])
    assert client.get("/api/results").json() == {"available": False}  # non-finite / blank rows are skipped
    (tmp_path / "e6_runs.csv").write_text("garbage\n")
    assert client.get("/api/results").json() == {"available": False}


def test_results_real_files(client):
    r = client.get("/api/results").json()
    assert r["available"] and r["n_wards"] >= 1 and len(r["metrics"]) == 6 and len(r["wards"]) == r["n_wards"]
    assert [m["cost"] for m in r["metrics"]] == [False, False, False, False, True, True]


def test_rest_lines_in_options_and_decide(client, monkeypatch):
    _open_event(client)
    rl = client.get("/api/options?mode=ai").json()["comparison"]["rest_lines"]
    assert rl["ours"] and rl["ortec"] and all(isinstance(x, str) for x in rl["ours"] + rl["ortec"])
    roster_before = {k: dict(v) for k, v in server.STATE.ctx.roster.by_nurse.items()}
    client.get("/api/options?mode=ai")
    assert server.STATE.ctx.roster.by_nurse == roster_before  # temporary changes are always reverted
