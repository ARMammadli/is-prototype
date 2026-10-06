import pandas as pd
import pytest

from evaluation.stats import paired_stats


def _df(base, strain):
    rows = [{"seed": i, "policy": "baseline", "m": b} for i, b in enumerate(base)]
    rows += [{"seed": i, "policy": "strain", "m": s} for i, s in enumerate(strain)]
    return pd.DataFrame(rows)


def test_consistent_improvement():
    r = paired_stats(_df([5, 6, 7, 8], [4, 5, 6, 7]), "m")
    assert r["mean_diff"] == pytest.approx(-1.0)
    assert r["ci_low"] == pytest.approx(-1.0) and r["ci_high"] == pytest.approx(-1.0)
    assert r["win_rate"] == 1.0 and r["n"] == 4


def test_no_difference():
    r = paired_stats(_df([1, 2, 3], [1, 2, 3]), "m")
    assert r["mean_diff"] == 0 and r["wilcoxon_p"] == 1.0 and r["effect_dz"] == 0.0
    assert r["tie_rate"] == 1.0
