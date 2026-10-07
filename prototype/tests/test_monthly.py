"""Monthly review report: rule-computed facts, GenAI text, deterministic check."""
from fastapi.testclient import TestClient

import app.server as server
from llm.monthly import check_report, compute_month_facts, versus_errors, write_report
from sim.ward import load_json

POLICY = load_json("policy.json")


def test_facts_are_consistent_and_have_no_health_data():
    f1, f2 = (compute_month_facts(0, m, POLICY) for m in (1, 2))
    for f in (f1, f2):
        r, o = f["hospital_rule"], f["todays_software"]
        assert set(r) == set(o) and f["rule_vs_todays_software"]["quick_returns"] in ("lower", "higher", "the same")
        assert f["planner"]["decisions_by_planner"] == 0 and "note" in f["planner"]
        assert all(set(x) == {"nurse", "last_minute_call_ins"} for x in f["most_last_minute_call_ins"])
    assert (f1["days"], f2["days"]) == ("1-28", "29-56")


def test_check_report_catches_wrong_numbers_directions_and_nurses():
    f = {"q": [56, 96, 74, 42], "pct_change": {"quick_returns": -42},
         "most_last_minute_call_ins": [{"nurse": "Nurse_24", "last_minute_call_ins": 4},
                                       {"nurse": "Nurse_06", "last_minute_call_ins": 3}]}
    good = {"summary": "Fewer quick returns (56 vs. 96), down 42%. More call-ins (74 vs. 42).",
            "discussion_points": ["Nurse_24 had 4 call-ins.", "b", "c"]}
    assert check_report(good, f)["status"] == "verified"
    assert check_report(dict(good, summary="Fewer call-ins (74 vs. 42)."), f)["direction_errors"] == ["74 vs 42"]
    assert check_report(dict(good, summary="Quick returns fell 77%."), f)["unsupported_numbers"] == ["77", "77%"]
    assert check_report(dict(good, summary="Quick returns were 56%."), f)["unsupported_numbers"] == ["56%"]
    assert check_report(dict(good, discussion_points=["Nurse_24 and Nurse_06 each had 4."]), f)["nurse_errors"]
    assert check_report(None, f)["status"] == "unavailable"
    assert versus_errors("dropped from 7 to 1") == [] and versus_errors("rose from 7 to 1") == ["from 7 to 1"]


def test_write_report_without_genai_keeps_facts(monkeypatch):
    monkeypatch.setattr("llm.monthly.chat_json", lambda *a, **k: (None, "ConnectError: down"))
    r = write_report(compute_month_facts(1, 1, POLICY), "m", 1)
    assert r["report"] is None and r["check"]["status"] == "unavailable" and r["facts"]["hospital_rule"]


def test_monthly_endpoint_counts_logged_planner_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(server.STATE, "policy", load_json("policy.json"))
    monkeypatch.setattr("llm.monthly.chat_json", lambda *a, **k: (
        {"summary": "Fewer quick returns.", "discussion_points": ["a", "b", "c"]}, None))
    c = TestClient(server.app)
    c.post("/api/scenario", json={"seed": 1})
    for _ in range(20):
        ev = c.post("/api/next-event").json()["state"]["event"]
        if ev and not ev["unfilled"]:
            break
    opts = c.get("/api/options?mode=strain").json()["options"]
    c.post("/api/apply", json={"event_id": ev["event_id"], "option_id": opts[1]["id"], "mode": "strain",
                               "override_reason": "skill_mix"})
    r = c.post("/api/monthly-report", json={"month": 1 if ev["day"] < 28 else 2}).json()
    p = r["facts"]["planner"]
    assert p["decisions_by_planner"] == 1 and p["overridden"] == 1 and p["override_reasons"] == {"skill mix": 1}
    assert r["check"]["status"] == "verified" and r["report"]["summary"] == "Fewer quick returns."
    assert c.get("/api/audit").json()["entries"][-1]["mode"] == "monthly_report"
    assert c.post("/api/monthly-report", json={"month": 3}).status_code == 422
