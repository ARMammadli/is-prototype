from evaluation.e3_faithfulness import collect_payloads, summarize
from sim.ward import load_json

def test_collect_payloads_is_stratified():
    ps = collect_payloads(6, load_json("policy.json"), start_seed=1000, per_seed=3)
    assert len(ps) == 6
    assert sum(p["_stratum"] == "differ" for p in ps) == 3
    assert all(len(p["options"]) >= 2 for p in ps)

def test_summarize_rates():
    rows = [
        {"source": "m", "latency_ms": 100, "claims_total": 2, "claims_false": 0, "n_unsupported": 0,
         "recommendation_correct": True, "tradeoff_correct": True, "verified": True},
        {"source": "template", "latency_ms": 5, "claims_total": 2, "claims_false": 1, "n_unsupported": 1,
         "recommendation_correct": False, "tradeoff_correct": False, "verified": False},
    ]
    s = summarize(rows, "m")
    assert s["n"] == 2 and s["fallback_rate"] == 0.5 and s["json_valid_rate"] == 0.5
    assert s["n_llm"] == 1 and s["claim_accuracy"] == 1.0 and s["pct_flagged"] == 0.0
    assert s["latency_p50_ms"] == 100
