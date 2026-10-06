import copy
import json

from helpers import make_ward, roster_with
from llm import service
from llm.checker import canon_nurse, canon_option, check, direction_errors, ground_truth_tradeoff
from llm.prompt import OUTPUT_SCHEMA, build_comparison, build_payload
from llm.template import template_explanation
from sim.policies import RepairContext, generate_candidates, score_options

ZERO = {"QR": 0, "N": 0, "LR": 0, "OT": 0.0, "SN": 0}
PAYLOAD = {
    "event": {"absent": "Nurse_03", "day": 3, "shift": "D", "notice_h": 5.0},
    "weights": {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5},
    "options": [
        {"id": "Option_2", "rank_strain": 1, "rank_baseline": 2, "is_baseline_top": False, "kind": "direct",
         "n_changes": 1, "delta_strain": 1.5, "changes": [{"nurse": "Nurse_02", "day": 3, "from": None, "to": "D"}],
         "nurses": [{"nurse": "Nurse_02", "before": dict(ZERO), "after": dict(ZERO, SN=1),
                     "strain_before": 0.0, "strain_after": 1.5}]},
        {"id": "Option_1", "rank_strain": 2, "rank_baseline": 1, "is_baseline_top": True, "kind": "direct",
         "n_changes": 1, "delta_strain": 4.5, "changes": [{"nurse": "Nurse_01", "day": 3, "from": None, "to": "D"}],
         "nurses": [{"nurse": "Nurse_01", "before": dict(ZERO), "after": dict(ZERO, QR=1, SN=1),
                     "strain_before": 0.0, "strain_after": 4.5}]},
    ],
}
GOOD = {"recommended_option": "Option_2", "main_tradeoff": "quick_returns",
        "claims": [{"nurse": "Nurse_01", "metric": "QR", "before": 0, "after": 1}],
        "text": "Option_2 avoids giving Nurse_01 a quick return (0 to 1)."}


def test_ground_truth_is_quick_returns():
    assert ground_truth_tradeoff(PAYLOAD) == "quick_returns"


def test_ground_truth_concentration_when_increments_equal():
    p = copy.deepcopy(PAYLOAD)
    for opt in p["options"]:
        opt["nurses"][0]["after"] = dict(ZERO, N=1)
    p["options"][1]["nurses"][0]["strain_before"] = 9.0
    assert ground_truth_tradeoff(p) == "concentration"


def test_ground_truth_single_option_is_stability():
    p = copy.deepcopy(PAYLOAD)
    p["options"] = p["options"][:1]
    assert ground_truth_tradeoff(p) == "stability"


def test_correct_explanation_is_verified():
    r = check(GOOD, PAYLOAD)
    assert r["verified"] and r["claims_false"] == 0 and r["unsupported_numbers"] == []
    assert r["recommendation_correct"] and r["tradeoff_correct"]


def test_wrong_number_unknown_nurse_and_malformed_claims_are_flagged():
    bad = dict(GOOD, claims=[{"nurse": "Nurse_01", "metric": "QR", "before": 0, "after": 2},
                             {"nurse": "Nurse_99", "metric": "QR", "before": 0, "after": 1},
                             "junk", {"nurse": "Nurse_01"}])
    r = check(bad, PAYLOAD)
    assert r["claims_false"] == 4 and not r["verified"]


def test_unsupported_number_in_text_is_flagged():
    r = check(dict(GOOD, text="Option_2 saves 17 hours."), PAYLOAD)
    assert r["unsupported_numbers"] == ["17"] and not r["verified"]


def test_wrong_or_unknown_recommendation_is_flagged():
    assert not check(dict(GOOD, recommended_option="Option_1"), PAYLOAD)["recommendation_correct"]
    assert not check(dict(GOOD, recommended_option="Option_9"), PAYLOAD)["verified"]


def test_template_is_verified_for_two_and_one_options():
    t = template_explanation(PAYLOAD)
    assert t["recommended_option"] == "Option_2" and check(t, PAYLOAD)["verified"]
    single = copy.deepcopy(PAYLOAD)
    single["options"] = single["options"][:1]
    assert check(template_explanation(single), single)["verified"]


def test_service_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: (None, "ConnectError: refused"))
    r = service.explain(PAYLOAD, "qwen3:4b", 1)
    assert r["source"] == "template" and r["check"]["verified"] and "ConnectError" in r["error"]


def test_service_rejects_wrong_shape(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: ({"foo": 1}, None))
    assert service.explain(PAYLOAD, "qwen3:4b", 1)["source"] == "template"


def test_service_uses_model_output(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: (dict(GOOD), None))
    r = service.explain(PAYLOAD, "qwen3:4b", 1)
    assert r["source"] == "qwen3:4b" and r["check"]["verified"]


def test_build_payload_from_real_context():
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"Nurse_01": {1: "E"}, "Nurse_02": {5: "D", 6: "D", 7: "D", 8: "D"}})
    ctx = RepairContext(w, r, {("Nurse_03", 2)}, 2, "D", "Nurse_03", 5.0, 0, 0)
    policy = {"weights": PAYLOAD["weights"], "back_days": 28, "forward_days": 28, "squared": True}
    p = build_payload(ctx, score_options(ctx, generate_candidates(ctx), policy), policy)
    assert p["event"]["day"] == 3
    assert any(o["is_baseline_top"] for o in p["options"])
    assert min(o["rank_strain"] for o in p["options"]) == 1
    json.dumps(p)
    assert set(OUTPUT_SCHEMA["required"]) == {"recommended_option", "main_tradeoff", "claims", "text"}


def test_unhashable_nurse_claims_do_not_raise():
    bad = dict(GOOD, claims=[{"nurse": ["Nurse_01"], "metric": "QR", "before": 0, "after": 1},
                             {"nurse": {}, "metric": "QR", "before": 0, "after": 1}])
    r = check(bad, PAYLOAD)
    assert r["claims_false"] == 2 and not r["verified"]


def test_huge_number_in_text_is_flagged_not_raised():
    r = check(dict(GOOD, text="Option_2 saves " + "9" * 400 + " hours."), PAYLOAD)
    assert r["unsupported_numbers"] == ["9" * 400] and not r["verified"]


def test_weights_do_not_whitelist_numbers():
    r = check(dict(GOOD, text="Option_2 gives Nurse_02 3 quick returns and 2 long runs"), PAYLOAD)
    assert "2" in r["unsupported_numbers"] and not r["verified"]


def test_ot_claim_off_by_04_is_false():
    p = copy.deepcopy(PAYLOAD)
    p["options"][0]["nurses"][0]["after"]["OT"] = 2.0
    ok = dict(GOOD, claims=[{"nurse": "Nurse_02", "metric": "OT", "before": 0, "after": 2.05}])
    bad = dict(GOOD, claims=[{"nurse": "Nurse_02", "metric": "OT", "before": 0, "after": 2.4}])
    assert check(ok, p)["claims_false"] == 0 and check(bad, p)["claims_false"] == 1


def test_service_empty_output_sets_error(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: (None, None))
    assert service.explain(PAYLOAD, "m", 1)["error"] == "empty output"


def test_id_normalisation_helpers():
    assert [canon_nurse(x) for x in ("Nurse 10", "nurse_10", "Nurse_010", "Nurse_10")] == ["Nurse_10"] * 4
    assert canon_nurse("Nurse_01") == "Nurse_01" and canon_nurse("Nurse 1") == "Nurse_01"
    assert canon_option("Option 2") == canon_option("option_2") == "Option_2"
    assert canon_nurse(["x"]) == ["x"] and canon_option(None) is None and canon_nurse("bob") == "bob"


def test_check_accepts_spaced_and_lowercase_ids():
    ex = dict(GOOD, recommended_option="Option 2",
              claims=[{"nurse": "Nurse 01", "metric": "QR", "before": 0, "after": 1}],
              text="Option 2 avoids giving Nurse 01 a quick return (0 to 1); legacy opt2 and N01 too.")
    r = check(ex, PAYLOAD)
    assert r["verified"] and r["unsupported_numbers"] == []
    assert check(dict(ex, recommended_option="option_2"), PAYLOAD)["recommendation_correct"]
    assert check(dict(GOOD, claims=[{"nurse": "nurse_01", "metric": "QR", "before": 0, "after": 1}]),
                 PAYLOAD)["claims_false"] == 0
    assert check(dict(GOOD, recommended_option=5), PAYLOAD)["recommendation_correct"] is False


def test_wrong_tradeoff_is_not_verified():
    r = check(dict(GOOD, main_tradeoff="nights"), PAYLOAD)
    assert not r["tradeoff_correct"] and not r["verified"] and r["ground_truth"] == "quick_returns"


def test_comparison_block_and_allowed_numbers():
    c = build_comparison(PAYLOAD)
    assert c["recommended"] == "Option_2" and c["compared_with"] == "Option_1"
    assert c["main_driver"] == "quick_returns"
    assert c["metric_added"]["QR"] == {"recommended": 0, "compared_with": 1}
    assert c["strain_added"] == {"recommended": 1.5, "compared_with": 4.5}
    p = copy.deepcopy(PAYLOAD)
    p["comparison"] = dict(c, strain_added={"recommended": 7.25, "compared_with": 1.5})
    assert check(dict(GOOD, text="Option_2 adds 7.25 strain."), p)["unsupported_numbers"] == []
    assert ground_truth_tradeoff(p) == "quick_returns"


def test_build_payload_includes_comparison():
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"Nurse_01": {1: "E"}, "Nurse_02": {5: "D", 6: "D", 7: "D", 8: "D"}})
    ctx = RepairContext(w, r, {("Nurse_03", 2)}, 2, "D", "Nurse_03", 5.0, 0, 0)
    policy = {"weights": PAYLOAD["weights"], "back_days": 28, "forward_days": 28, "squared": True}
    p = build_payload(ctx, score_options(ctx, generate_candidates(ctx), policy), policy)
    assert p["comparison"] == build_comparison(p) and p["comparison"]["recommended"].startswith("Option_")
    json.dumps(p)


def test_direction_check():
    assert direction_errors("Option_2 reduces Nurse_01's quick returns from 1 to 0.") == []
    assert direction_errors("Option_2 reduces Nurse_01's quick returns from 1 to 2.") == ["from 1 to 2"]
    assert direction_errors("Option_2 adds quick returns from 2 to 1.") == ["from 2 to 1"]
    assert direction_errors("Nurse_03 reduces QR (from 3 to 2) and Nurse_10's SN (from 1 to 2)") == ["from 1 to 2"]
    assert direction_errors("QR goes from 1 to 2.") == [] and direction_errors("reduces from 2 to 2") == []
    assert direction_errors("It adds 1.5. Then lowers from 3.5 to 2.5") == []
    assert direction_errors(None) == [] and direction_errors(["x"]) == []


def test_direction_error_blocks_verified():
    r = check(dict(GOOD, text="Option_2 reduces Nurse_01 QR from 0 to 1."), PAYLOAD)
    assert r["direction_errors"] == ["from 0 to 1"] and not r["verified"]
    assert check(GOOD, PAYLOAD)["direction_errors"] == []


def test_huge_digit_ids_do_not_raise():
    big = "9" * 5000
    ex = dict(GOOD, recommended_option="Option_" + big,
              claims=[{"nurse": "Nurse_" + big, "metric": "QR", "before": 0, "after": 1}])
    r = check(ex, PAYLOAD)
    assert not r["verified"] and r["claims_false"] == 1 and not r["recommendation_correct"]
    assert canon_nurse("Nurse_" + big) == "Nurse_" + big


def test_decimal_after_id_is_not_left_behind():
    r = check(dict(GOOD, text="Option 1.5 is odd."), PAYLOAD)
    assert r["unsupported_numbers"] == []


def test_checker_strips_display_nurse_ids_from_number_check():
    from llm.checker import check_text
    payload = {"options": [{"id": "Option_1", "n_changes": 1, "delta_strain": 1.5, "changes": [{"day": 2}],
                            "nurses": [{"nurse": "Nurse_08", "before": {"QR": 0}, "after": {"QR": 1},
                                        "strain_before": 1.5, "strain_after": 4.5}]}], "event": {}}
    r = check_text("Call in Nurse 08 (Nurse 8, nurse_08, Option 1) adds 1 quick return.", [], payload)
    assert r["unsupported_numbers"] == []
    assert check_text("Nurse 08 got 77 more.", [], payload)["unsupported_numbers"] == ["77"]
