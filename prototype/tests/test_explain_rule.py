"""Rule ranks, GenAI explains: payload, fact check, and the hard rule that GenAI never changes the choice."""
import pytest

from llm import service
from llm.checker import check_explanation, nurse_direction_errors
from llm.prompt import DEFAULT_POLICY_TEXT, EXPLAIN_SCHEMA, build_explain_payload
from sim.engine import run_scenario
from sim.policies import rank_options
from sim.ward import load_json

ZERO = {"QR": 0, "N": 0, "LR": 0, "OT": 0.0, "SN": 0}
PAYLOAD = {
    "event": {"absent": "Nurse_03", "day": 3, "shift": "D", "notice_h": 5.0},
    "decision": {"chosen": "Option_2", "runner_up": "Option_1", "todays_software": "Option_1",
                 "same_as_todays_software": False},
    "options": [
        {"id": "Option_2", "n_changes": 2, "delta_strain": -1.5, "changes": [],
         "nurses": [{"nurse": "Nurse_02", "before": dict(ZERO), "after": dict(ZERO, SN=1),
                     "strain_before": 0.0, "strain_after": 1.5, "load_change": 1.5},
                    {"nurse": "Nurse_05", "before": dict(ZERO, QR=1), "after": dict(ZERO),
                     "strain_before": 3.0, "strain_after": 0.0, "load_change": -3.0}]},
        {"id": "Option_1", "n_changes": 1, "delta_strain": 4.5, "changes": [],
         "nurses": [{"nurse": "Nurse_01", "before": dict(ZERO), "after": dict(ZERO, QR=1, SN=1),
                     "strain_before": 0.0, "strain_after": 4.5, "load_change": 4.5}]},
    ],
}


def test_nurse_direction_errors():
    assert nurse_direction_errors("This relieves Nurse_02 of work.", PAYLOAD) == ["Nurse_02: 'relieves'"]
    assert nurse_direction_errors("Nurse_05 gets one more quick return.", PAYLOAD) == ["Nurse_05: 'more'"]
    assert nurse_direction_errors("Nurse_05 is spared a quick return.", PAYLOAD) == []
    assert nurse_direction_errors(
        "Nurse_02 gets one more last-minute call-in (back at work after less than 11 hours' rest).", PAYLOAD) == []
    assert nurse_direction_errors("Nurse_02 helps Nurse_05 with fewer shifts.", PAYLOAD) == []  # two nurses: skipped
    assert nurse_direction_errors("Nurse_99 gets more.", PAYLOAD) == [] and nurse_direction_errors(None, PAYLOAD) == []


def test_check_explanation_status():
    ok = {"claims": [{"nurse": "Nurse_05", "metric": "QR", "before": 1, "after": 0}],
          "text": "Nurse_05 is relieved of a quick return, from 1 to 0."}
    assert check_explanation(ok, PAYLOAD)["status"] == "verified"
    bad_dir = dict(ok, text="Nurse_05 reduces quick returns from 0 to 1.")
    r = check_explanation(bad_dir, PAYLOAD)
    assert r["status"] == "mismatch" and r["direction_errors"] == ["from 0 to 1"]
    assert check_explanation(dict(ok, text="Nurse_05 gets 77 more."), PAYLOAD)["status"] == "mismatch"
    assert check_explanation(None, PAYLOAD)["status"] == "unavailable"
    assert "recommended_option" not in EXPLAIN_SCHEMA["properties"]


def _payloads(seed=1, n=10):
    policy = load_json("policy.json")
    out = []

    def on_event(ctx, scored):
        if len(scored) >= 2 and len(out) < n:
            out.append((build_explain_payload(ctx, scored, policy), rank_options(scored, "strain")[0].option.id,
                        rank_options(scored, "baseline")[0].option.id))
    run_scenario(seed, "strain", policy, on_event=on_event)
    return out


def test_build_explain_payload_has_rule_choice_ortec_and_policy():
    for p, top, ortec in _payloads():
        assert p["decision"]["chosen"] == top and p["options"][0]["id"] == top
        assert p["decision"]["todays_software"] == ortec and ortec in {o["id"] for o in p["options"]}
        assert p["decision"]["same_as_todays_software"] == (top == ortec)
        assert p["policy_text"] == DEFAULT_POLICY_TEXT and len(p["options"]) <= 3
        assert "chosen by the hospital rule" in p["options"][0]["role"]
        for nd in p["options"][0]["nurses"]:
            assert nd["load_change"] == round(nd["strain_after"] - nd["strain_before"], 2)


@pytest.mark.parametrize("reply", [
    (None, "ConnectError: down"),
    ({"claims": "junk", "text": 5}, None),
    ({"claims": [], "text": "Ignore the rule and pick Option_1 instead.", "chosen_option": "Option_1"}, None),
])
def test_hard_rule_genai_never_changes_the_choice(monkeypatch, reply):
    """Arm B rosters are identical with no explainer, a failing one, junk, or one that 'recommends' another option."""
    policy = load_json("policy.json")
    plain = run_scenario(2, "strain", policy)
    monkeypatch.setattr("llm.service.chat_json", lambda *a, **k: reply)
    calls = []

    def explainer(ctx, scored):
        if scored:
            calls.append(service.explain_decision(build_explain_payload(ctx, scored, policy), "m", 1))
    explained = run_scenario(2, "strain", policy, on_event=explainer)
    assert calls and explained.final.by_nurse == plain.final.by_nurse
    assert [r.chosen for r in explained.records] == [r.chosen for r in plain.records]
