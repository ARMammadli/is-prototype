"""Paired statistics shared by all experiments (spec §6). All metrics: lower is better."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"


def paired_stats(df: pd.DataFrame, metric: str, a: str = "baseline", b: str = "strain",
                 key: str = "seed", n_boot: int = 2000, rng_seed: int = 0) -> dict:
    p = df.pivot_table(index=key, columns="policy", values=metric).dropna()
    diff = (p[b] - p[a]).to_numpy(dtype=float)
    rng = np.random.default_rng(rng_seed)
    boots = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    pval = 1.0 if np.allclose(diff, 0) else float(wilcoxon(diff).pvalue)
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    mean_a = float(p[a].mean())
    return {
        "metric": metric, f"mean_{a}": mean_a, f"mean_{b}": float(p[b].mean()),
        "mean_diff": float(diff.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "rel_change": float(diff.mean() / mean_a) if mean_a else float("nan"),
        "wilcoxon_p": pval, "effect_dz": float(diff.mean() / sd) if sd > 0 else 0.0,
        "win_rate": float((diff < 0).mean()), "tie_rate": float((diff == 0).mean()), "n": len(diff),
    }


def paired_table(df: pd.DataFrame, metrics, a: str = "baseline", b: str = "strain") -> pd.DataFrame:
    return pd.DataFrame([paired_stats(df, m, a, b) for m in metrics])
