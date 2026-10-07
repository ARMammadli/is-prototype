"""Rule writes the facts, GenAI writes the wording."""
from llm import service
from llm.checker import check_explanation
from llm.factblock import fact_block_errors, fact_block_text, render_fact_block
from test_explain_rule import PAYLOAD, _payloads

FACTS = "In the rule's choice, Nurse_05: quick returns from 1 to 0. The rule's choice changes the shifts of 2 nurses."


def test_fact_block_passes_the_existing_check():
    for p, _, _ in _payloads(n=20):
        t = fact_block_text(p)
        assert check_explanation({"claims": [], "text": t}, p)["verified"], t
        assert fact_block_errors(t, t) == []


def test_fact_block_covers_both_options_and_cost():
    p = dict(PAYLOAD, options=[dict(o, description=d) for o, d in zip(PAYLOAD["options"], ["Plan two", "Plan one"])])
    s = " ".join(render_fact_block(p))
    assert "Nurse_05: quick returns from 1 to 0" in s and "Nurse_01: quick returns from 0 to 1" in s
    assert "changes the shifts of 2 nurses; today's software's choice changes the shifts of 1 nurse." in s


def test_fact_block_errors_flags_planted_number_and_nurse():
    assert fact_block_errors("Nurse_05 is relieved, which fits the policy.", FACTS) == []
    assert fact_block_errors("Nurse_05 is relieved of 3 quick returns.", FACTS) == ["number not in fact block: 3"]
    assert fact_block_errors("Nurse_05 gets three fewer.", FACTS) == ["number not in fact block: 'three'"]
    assert fact_block_errors("Two nurses change; no one else.", FACTS) == []
    assert fact_block_errors("Nurse_77 takes the shift.", FACTS) == ["nurse not in fact block: Nurse_77"]


def test_explain_decision_framing_only(monkeypatch):
    p, _, _ = _payloads(n=1)[0]
    seen = {}

    def fake(system, user, schema, model, timeout):
        seen["user"] = user
        return {"text": "Nurse_99 is spared 7 call-ins."}, None
    monkeypatch.setattr("llm.service.chat_json", fake)
    r = service.explain_decision(p, "m", 1)
    assert '"options"' not in seen["user"] and "fact_block" in seen["user"]  # GenAI never sees the raw payload
    assert r["display_text"].startswith(" ".join(r["fact_block"])) and r["check"]["status"] == "mismatch"
    assert "nurse not in fact block: Nurse_99" in r["check"]["fact_block_errors"]
    monkeypatch.setattr("llm.service.chat_json", lambda *a, **k: (None, "down"))
    r = service.explain_decision(p, "m", 1)
    assert r["fact_block"] and r["framing"] is None and r["check"]["status"] == "unavailable"


# --- check v3 (follow-up) ---------------------------------------------------------------------------
from llm.factblock import check_v3, load_claim_errors, render_load_fact, role_errors  # noqa: E402


def _differ_payload():
    for p, top, ortec in _payloads(n=40):
        o = {x["id"]: x for x in p["options"]}
        ch, ot = o[p["decision"]["chosen"]], o[p["decision"]["todays_software"]]
        only_ortec = [nd for nd in ot["nurses"] if nd["nurse"] not in {x["nurse"] for x in ch["nurses"]}
                      and nd["strain_after"] > nd["strain_before"]]
        gainer = [nd for nd in ch["nurses"] if nd["after"]["SN"] > nd["before"]["SN"]]
        if not p["decision"]["same_as_todays_software"] and only_ortec and gainer:
            return p, gainer[0]["nurse"], only_ortec[0]["nurse"]
    raise AssertionError("no suitable payload")


def test_role_check_both_directions():
    p, gainer, ortec_nurse = _differ_payload()
    assert role_errors(f"{gainer} takes on a last-minute call-in, while {ortec_nurse} is spared.", p) == []
    assert role_errors(f"{gainer} takes on a last-minute call-in and {ortec_nurse} takes on extra work.", p)
    assert role_errors(f"{gainer} is relieved of last-minute call-ins.", p)


def test_load_claims_need_a_backing_fact():
    p, gainer, _ = _differ_payload()
    claim = "This fits the policy by avoiding extra load on already burdened nurses."
    assert load_claim_errors(claim, p, load_fact=False)
    assert load_claim_errors("This fits the fairness policy.", p, load_fact=False) == []
    from llm.factblock import load_comparison
    assert bool(load_claim_errors(claim, p, load_fact=True)) == (load_comparison(p)["verdict"] != "rule_lower")


def test_load_fact_and_template_pass_check_v3():
    from evaluation.e9_followup import template_text
    for p, _, _ in _payloads(n=20):
        f = " ".join(render_fact_block(p) + render_load_fact(p))
        t = template_text(p)
        assert check_v3(f + " " + t, t, p, f, load_fact=True)["verified_v3"], t
