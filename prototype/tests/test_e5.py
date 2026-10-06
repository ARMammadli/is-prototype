import json

import pandas as pd
import pytest

from evaluation import e5_ai_decides as e5
from evaluation import make_summary
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.policies import rank_options
from sim.rules import roster_violations
from sim.ward import load_json

POLICY = load_json("policy.json")

def _metrics(res):
    return run_metrics(res, POLICY["weights"])

def test_strain_top_chooser_reproduces_strain():
    ref = _metrics(run_scenario(0, "strain", POLICY))
    chooser = lambda ctx, scored: (rank_options(scored, "strain")[0].option.id, {"agrees": True})
    res = run_scenario(0, "ai", POLICY, chooser=chooser)
    assert _metrics(res) == ref
    assert all(r.ai_agrees for r in res.records)

def test_baseline_top_chooser_is_legal():
    chooser = lambda ctx, scored: (rank_options(scored, "baseline")[0].option.id, {"agrees": False})
    res = run_scenario(0, "ai", POLICY, chooser=chooser)
    assert roster_violations(res.final, res.blocked) == []
    assert res.records
    for r in res.records:
        assert r.ai_choice == r.baseline_top

def test_unknown_id_falls_back_and_info_propagates():
    ref = _metrics(run_scenario(0, "strain", POLICY))
    info = {"agrees": False, "fallback": False, "latency_ms": 7, "verified": True}
    res = run_scenario(0, "ai", POLICY, chooser=lambda ctx, scored: ("Option_nope", dict(info)))
    assert _metrics(res) == ref
    for r in res.records:
        assert r.ai_choice == "Option_nope" and r.ai_fallback is False
        assert r.ai_agrees is False and r.ai_latency_ms == 7 and r.ai_verified is True
    res = run_scenario(0, "ai", POLICY, chooser=lambda ctx, scored: (None, {"fallback": True}))
    assert _metrics(res) == ref and all(r.ai_fallback for r in res.records)

def test_no_chooser_defaults_unchanged():
    res = run_scenario(0, "strain", POLICY)
    assert all(r.ai_choice is None and r.ai_fallback is False for r in res.records)

def test_make_chooser_skips_small_and_logs(monkeypatch):
    monkeypatch.setattr(e5, "decide", lambda payload, top, model, timeout: {
        "decision": {"chosen_option": top, "main_tradeoff": "x"}, "agrees": True, "latency_ms": 5,
        "check": {"verified": True}})
    counters = {}
    ch = e5.make_chooser(POLICY, "m", 1, seed=3, counters=counters)
    res = run_scenario(0, "ai", POLICY, chooser=ch)
    lines = [json.loads(x) for x in ch.lines]
    n_ai = sum(1 for r in res.records if r.ai_agrees is not None)
    assert len(lines) == n_ai and counters["skipped"] == len(res.records) - n_ai
    assert all(x["seed"] == 3 and x["agrees"] for x in lines)

def _fake_results(tmp_path):
    e1 = []
    for seed in (0, 1, 2):
        for pol, k in (("baseline", 3.0), ("strain", 1.0)):
            e1.append({"seed": seed, "policy": pol, **{m: k + seed for m in e5.E5_METRICS}})
    e1.append({"seed": 9, "policy": "baseline", **{m: 50.0 for m in e5.E5_METRICS}})
    pd.DataFrame(e1).to_csv(tmp_path / "e1_runs.csv", index=False)
    ai = [{"seed": s, "policy": "ai", **{m: 2.0 + s + 0.1 * s * s for m in e5.E5_METRICS},
           "model": "qwen-test", "agreement_rate": 0.5, "fallback_rate": 0.1, "verified_rate": 0.4, "latency_p50_ms": 900.0,
           "n_ai_decisions": 10} for s in (0, 1, 2)]
    pd.DataFrame(ai).to_csv(tmp_path / "e5_runs.csv", index=False)

def test_summary_building(tmp_path, monkeypatch):
    monkeypatch.setattr(e5._stats, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(make_summary, "RESULTS_DIR", tmp_path)
    _fake_results(tmp_path)
    summary = e5.write_outputs()
    assert list(summary.policy) == ["baseline", "strain", "ai"]
    assert summary.set_index("policy").loc["baseline", "QR_total"] == pytest.approx(4.0)  # seed 9 excluded
    stats = pd.read_csv(tmp_path / "e5_stats.csv")
    assert set(stats.comparison) == {"ai vs strain", "ai vs baseline"}
    md = make_summary.build_summary()
    assert "E5 — AI as decision-maker" in md and "n seeds = 3 (qwen-test; small sample)" in md
    assert summary.set_index("policy").loc["ai", "latency_p50_ms"] == 900.0

def test_missing_e1_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(e5._stats, "RESULTS_DIR", tmp_path)
    pd.DataFrame([{"seed": 0, "policy": "ai"}]).to_csv(tmp_path / "e5_runs.csv", index=False)
    with pytest.raises(FileNotFoundError, match="e1_runs.csv"):
        e5.write_outputs()

def _fake_decide(fail):
    def f(payload, top, model, timeout):
        if fail:
            return {"decision": None, "agrees": False, "latency_ms": 1, "check": {"verified": False}}
        return {"decision": {"chosen_option": top, "main_tradeoff": "x"}, "agrees": True, "latency_ms": 5,
                "check": {"verified": True}}
    return f

def test_all_fallback_seed_aborts_and_is_not_persisted(monkeypatch):
    monkeypatch.setattr(e5, "decide", _fake_decide(True))
    with pytest.raises(e5.FallbackAbort):
        e5.run_seed(0, POLICY, "m", 1)

def test_run_seed_ok_and_persist_prune(tmp_path, monkeypatch):
    monkeypatch.setattr(e5, "decide", _fake_decide(False))
    row, lines, skipped = e5.run_seed(0, POLICY, "m", 1)
    assert row["fallback_rate"] == 0 and row["model"] == "m" and lines
    e5.persist_seed(tmp_path, row, lines)
    # simulate a crashed seed 1: decision lines written, no CSV row
    with open(tmp_path / "e5_decisions.jsonl", "a") as fh:
        fh.write(json.dumps({"seed": 1, "event_id": 0}) + "\n")
    e5.prune_decisions(tmp_path, {0})
    kept = [json.loads(x) for x in (tmp_path / "e5_decisions.jsonl").read_text().splitlines()]
    assert len(kept) == len(lines) and all(x["seed"] == 0 for x in kept)
    assert list(pd.read_csv(tmp_path / "e5_runs.csv").seed) == [0]
