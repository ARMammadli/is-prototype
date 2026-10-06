"""Slide-ready figures (spec §6). Each figure is skipped if its input CSV does not exist yet."""
from __future__ import annotations

import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from evaluation.stats import FIGURES_DIR, RESULTS_DIR  # noqa: E402

COLORS = {"baseline": "#8a8f98", "strain": "#1f6feb"}
LABELS = {"baseline": "ORTEC-like", "strain": "Strain-aware"}
POLICIES = ("baseline", "strain")
plt.rcParams.update({"savefig.dpi": 300, "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False})


def _save(fig, name: str) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / name)
    plt.close(fig)
    print("wrote", FIGURES_DIR / name)


def _boxes(ax, runs, metric, title):
    data = [runs.loc[runs.policy == p, metric] for p in POLICIES]
    bp = ax.boxplot(data, tick_labels=[LABELS[p] for p in POLICIES], patch_artist=True, widths=0.6)
    for patch, p in zip(bp["boxes"], POLICIES):
        patch.set_facecolor(COLORS[p])
        patch.set_alpha(0.85)
    ax.set_title(title, fontsize=12)


def fig_e1_concentration(runs):
    panels = [("gini_strain", "Gini of per-nurse strain"),
              ("top10_qr_share", "Top-10% share of quick returns"),
              ("max_qr", "Max quick returns (one nurse)"),
              ("nurses_qr_ge3_28d", "Nurses with ≥3 QR in 28 days")]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
    for ax, (m, t) in zip(axes, panels):
        _boxes(ax, runs, m, t)
    fig.suptitle("E1 — Concentration of roster strain (lower is better)")
    _save(fig, "e1_concentration.png")


def fig_e1_guardrails(runs):
    panels = [("unfilled", "Unfilled shifts"), ("QR_total", "Total quick returns"),
              ("changes_per_repair", "Changes per repair"), ("nurses_disturbed", "Nurses disturbed")]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
    for ax, (m, t) in zip(axes, panels):
        _boxes(ax, runs, m, t)
    fig.suptitle("E1 — Guardrails and stability trade-off")
    _save(fig, "e1_guardrails.png")


def fig_e1_lorenz(nurses):
    fig, ax = plt.subplots(figsize=(6, 6))
    for p in POLICIES:
        v = np.sort(nurses.loc[nurses.policy == p, "QR"].to_numpy(dtype=float))
        cum = np.concatenate([[0], np.cumsum(v) / v.sum()]) if v.sum() else np.zeros(len(v) + 1)
        ax.plot(np.linspace(0, 1, len(cum)), cum, color=COLORS[p], lw=2.5, label=LABELS[p])
    ax.plot([0, 1], [0, 1], ls="--", color="#bbb", label="Perfect equality")
    ax.set_xlabel("Share of nurses (sorted by quick returns)")
    ax.set_ylabel("Share of all quick returns")
    ax.set_title("E1 — Who absorbs the quick returns?")
    ax.legend()
    _save(fig, "e1_lorenz.png")


def fig_e2(stats):
    sub = stats[stats.metric == "gini_strain"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(sub))
    err = [sub.mean_diff - sub.ci_low, sub.ci_high - sub.mean_diff]
    ax.barh(y, sub.mean_diff, xerr=err, color=COLORS["strain"], alpha=0.85, capsize=4)
    ax.set_yticks(y, sub.config)
    ax.axvline(0, color="#555", lw=1)
    ax.set_xlabel("Δ Gini of strain vs ORTEC-like (negative = more even)")
    ax.set_title("E2 — Sensitivity of the effect")
    _save(fig, "e2_sensitivity.png")


def fig_e3(summary):
    cols = [("json_valid_rate", "Valid JSON"), ("claim_accuracy", "Claim accuracy"),
            ("recommendation_agreement", "Picks top option"), ("tradeoff_correct", "Right trade-off"),
            ("pct_flagged", "Flagged (false/unsupported)")]
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.8 / max(1, len(summary))
    x = np.arange(len(cols))
    for i, (_, row) in enumerate(summary.iterrows()):
        ax.bar(x + i * width, [row[c] for c, _ in cols], width, label=row["model"])
    ax.set_xticks(x + width * (len(summary) - 1) / 2, [label for _, label in cols])
    ax.set_ylim(0, 1)
    ax.set_title("E3 — Explanation faithfulness (local LLM)")
    ax.legend()
    _save(fig, "e3_faithfulness.png")


def fig_e4(summary):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    modes = ["today", "permissive", "picky"]
    x = np.arange(len(modes))
    for ax, (m, t) in zip(axes, [("unfilled", "Unfilled shifts"), ("QR_total", "Total quick returns")]):
        for i, p in enumerate(POLICIES):
            vals = [summary[(summary["mode"] == md) & (summary.policy == p)][m].mean() for md in modes]
            ax.bar(x + i * 0.38, vals, 0.38, color=COLORS[p], label=LABELS[p])
        ax.set_xticks(x + 0.19, ["Planner assigns", "Permissive agents", "Picky agents"])
        ax.set_title(t)
    axes[0].legend()
    fig.suptitle("E4 — Agentic future: nurses' agents accept or decline offers")
    _save(fig, "e4_agents.png")


def main() -> None:
    def read(name):
        path = RESULTS_DIR / name
        return pd.read_csv(path) if path.exists() else None

    if (runs := read("e1_runs.csv")) is not None:
        fig_e1_concentration(runs)
        fig_e1_guardrails(runs)
    if (nurses := read("e1_nurses.csv")) is not None:
        fig_e1_lorenz(nurses)
    if (e2 := read("e2_stats.csv")) is not None:
        fig_e2(e2)
    e3_files = sorted(glob.glob(str(RESULTS_DIR / "e3_summary_*.csv")))
    if e3_files:
        fig_e3(pd.concat([pd.read_csv(f) for f in e3_files], ignore_index=True))
    if (e4 := read("e4_summary.csv")) is not None:
        fig_e4(e4)


if __name__ == "__main__":
    main()
