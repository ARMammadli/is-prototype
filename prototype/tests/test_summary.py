import pandas as pd
import pytest

from evaluation.make_summary import build_summary, direction, economics_bridge, md_table


def test_md_table():
    out = md_table(pd.DataFrame([{"a": 1.23456, "b": "x"}]), ["a", "b"])
    assert out.splitlines()[0] == "| a | b |" and "1.235" in out


def test_economics_bridge():
    runs = pd.DataFrame([{"policy": "baseline", "QR_total": 140}, {"policy": "strain", "QR_total": 100}])
    e = economics_bridge(runs, {"n_nurses": 70, "days": 56})
    assert e["dqr_per_nurse_month"] == pytest.approx(40 / 140)
    assert e["vedaa_pct"] == pytest.approx(40 / 140 * 0.07)
    assert e["rct_pct"] == pytest.approx(min(0.44, 0.44 * (40 / 140) / 0.5))
    assert e["vedaa_days"] == pytest.approx(700 * e["vedaa_pct"])


def test_direction_labels():
    assert direction(-1.0) == "strain better" and direction(2.0) == "strain worse" and direction(0.0) == "no change"


def test_summary_has_direction_column():
    assert "| direction |" in build_summary()
