from evaluation.e2_sensitivity import CONFIGS, make_policy
from evaluation.e2_sensitivity import run_one as e2_run
from evaluation.e4_agents import run_one as e4_run

def test_make_policy_overrides():
    p = make_policy({"weights_scale": {"QR": 2}, "forward_days": 7, "squared": False})
    assert p["weights"]["QR"] == 6.0 and p["weights"]["N"] == 1.0
    assert p["forward_days"] == 7 and p["squared"] is False
    assert [c[0] for c in CONFIGS][0] == "default" and all(len(c) == 4 for c in CONFIGS)

def test_e4_picky_agents_run():
    row = e4_run((0, "strain", "picky"))
    assert row["mode"] == "picky" and row["policy"] == "strain" and row["offers_per_fill"] >= 1

def test_e2_run_uses_default_weights_for_measurement():
    row = e2_run(("w_qr_x2", "strain", 0, {"weights_scale": {"QR": 2}}, None, {}))
    assert row["config"] == "w_qr_x2" and "gini_strain" in row

def test_e2_no_base_qr_uses_zero_pref_ward():
    row = e2_run(("no_base_qr", "baseline", 0, {}, None, {"base_qr_pref": 0.0}))
    assert row["config"] == "no_base_qr" and "qr_base_roster" in row
