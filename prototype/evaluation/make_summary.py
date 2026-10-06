"""Auto-generated evaluation summary for the deck (spec §6), incl. the economics bridge."""
from __future__ import annotations

import glob
import json

import pandas as pd

from evaluation.stats import RESULTS_DIR
from sim.ward import load_json

WARD_ABSENCE_DAYS = 700           # report Component 1/4: 60-FTE ward at 5.33% absence
DAY_VALUE_EUR = (250, 550)        # report Component 4 range per absence day
VEDAA_PER_QR_MONTH = 0.21 / 3     # Vedaa et al. 2017: ~3 QR/month ~ +21% absence days
RCT_MAX = 0.44                    # 2025 cluster RCT: IRR 0.56 when short rest roughly halved


def md_table(df: pd.DataFrame, cols: list[str]) -> str:
    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join(lines)


def direction(diff: float) -> str:
    return "strain better" if diff < 0 else "strain worse" if diff > 0 else "no change"


def qr_decomposition(runs: pd.DataFrame, e2: pd.DataFrame | None = None) -> str:
    cols = ["qr_base_roster", "qr_base_kept", "qr_from_repairs"]
    if not all(c in runs.columns for c in cols):
        return ""
    m = runs.groupby("policy")[cols].mean()
    f = lambda pol, c: f"{m.loc[pol, c]:.1f}" if pol in m.index else "n/a"
    txt = ("**QR decomposition** (mean per run). "
           + "; ".join(f"{pol}: base roster {f(pol, 'qr_base_roster')}, base QRs kept {f(pol, 'qr_base_kept')}, "
                       f"created by repairs {f(pol, 'qr_from_repairs')}" for pol in ("baseline", "strain"))
           + ". The strain policy's QR reduction comes mostly from moving nurses out of base-roster QRs, "
             "which costs extra short-notice changes, and only partly from avoiding QRs created during repair.")
    if e2 is not None and "no_base_qr" in set(e2.config):
        g = e2[e2.config == "no_base_qr"].set_index("metric")
        txt += (f" With no base-roster QRs (E2 `no_base_qr`), strain vs baseline gives gini_strain diff "
                f"{g.loc['gini_strain', 'mean_diff']:.3f} and QR_total diff {g.loc['QR_total', 'mean_diff']:.2f}.")
    return txt


def economics_bridge(runs: pd.DataFrame, ward_cfg: dict) -> dict:
    qb = runs.loc[runs.policy == "baseline", "QR_total"].mean()
    qs = runs.loc[runs.policy == "strain", "QR_total"].mean()
    if "qr_from_repairs" in runs.columns:
        rb = runs.loc[runs.policy == "baseline", "qr_from_repairs"].mean()
        rs = runs.loc[runs.policy == "strain", "qr_from_repairs"].mean()
    else:
        rb = rs = float("nan")
    nurse_months = ward_cfg["n_nurses"] * ward_cfg["days"] / 28
    dqr = (qb - qs) / nurse_months
    vedaa = max(0.0, dqr * VEDAA_PER_QR_MONTH)
    rel = (qb - qs) / qb if qb else 0.0
    rct = min(RCT_MAX, max(0.0, RCT_MAX * rel / 0.5))
    lo, hi = sorted([vedaa, rct])
    rdqr = (rb - rs) / nurse_months
    return {"dqr_per_nurse_month": dqr, "repair_only_dqr_per_nurse_month": rdqr,
            "repair_only_vedaa_pct": max(0.0, rdqr * VEDAA_PER_QR_MONTH) if rdqr == rdqr else float("nan"), "vedaa_pct": vedaa, "rct_pct": rct,
            "vedaa_days": WARD_ABSENCE_DAYS * vedaa, "rct_days": WARD_ABSENCE_DAYS * rct,
            "value_low_eur": WARD_ABSENCE_DAYS * lo * DAY_VALUE_EUR[0],
            "value_high_eur": WARD_ABSENCE_DAYS * hi * DAY_VALUE_EUR[1]}


def _read(name):
    path = RESULTS_DIR / name
    return pd.read_csv(path) if path.exists() else None


def build_summary() -> str:
    ward_cfg, policy = load_json("ward.json"), load_json("policy.json")
    out = ["# Evaluation summary (auto-generated)", "",
           "Synthetic ward; ORTEC-like baseline is a proxy built from vendor-described logic. "
           "Lower is better for every metric. ★ = large and significant effect (either direction).", ""]
    if (e1 := _read("e1_stats.csv")) is not None:
        e1 = e1.assign(abs_dz=e1.effect_dz.abs()).sort_values("abs_dz", ascending=False)
        e1["direction"] = [direction(d) for d in e1.mean_diff]
        e1["flag"] = ["★" if (abs(d) >= 0.5 and p < 0.01) else "" for d, p in zip(e1.effect_dz, e1.wilcoxon_p)]
        out += ["## E1 — Policy A/B (paired seeds)", "",
                md_table(e1, ["flag", "metric", "direction", "mean_baseline", "mean_strain", "mean_diff", "ci_low",
                              "ci_high", "rel_change", "wilcoxon_p", "effect_dz", "win_rate", "n"]), ""]
        e2_ = _read("e2_stats.csv")
        if (runs1 := _read("e1_runs.csv")) is not None and (q := qr_decomposition(runs1, e2_)):
            out += [q, ""]
        out += ["Caveats:",
                "- top10_qr_share worsens under strain because total QR shrinks while the remaining QRs stay concentrated.",
                "- repair_share_qr depends on the calibrated base_qr_pref and should not be used to test Assumption 1.",
                "- The p-values are uncorrected across 15 or more metrics, so small effects such as unfilled and "
                "LR_total should not be called significant.",
                "",
                "Metric notes: nurses_qr_ge3_28d = nurses with ≥3 quick returns in any 28-day window; the spec's >4 "
                "is legally near-impossible under the 1-per-7-days rule.", ""]
    if (e2 := _read("e2_stats.csv")) is not None:
        sub = e2[e2.metric.isin(["gini_strain", "top10_qr_share", "unfilled"])]
        out += ["## E2 — Sensitivity and ablation", "",
                md_table(sub, ["config", "metric", "mean_diff", "ci_low", "ci_high", "wilcoxon_p"]), ""]
    e3_files = sorted(glob.glob(str(RESULTS_DIR / "e3_summary_*.csv")))
    if e3_files:
        e3 = pd.concat([pd.read_csv(f) for f in e3_files], ignore_index=True)
        out += ["## E3 — Explanation faithfulness", "",
                md_table(e3, ["model", "n", "n_llm", "json_valid_rate", "claim_accuracy", "pct_flagged", "pct_direction_error",
                              "recommendation_agreement", "tradeoff_correct", "latency_p50_ms",
                              "latency_p95_ms", "fallback_rate"]), ""]
    else:
        out += ["## E3 — Explanation faithfulness", "", "_Not run yet (requires Ollama)._", ""]
    if (e4 := _read("e4_summary.csv")) is not None:
        out += ["## E4 — Agentic future", "",
                md_table(e4, ["mode", "policy", "unfilled", "QR_total", "gini_strain", "max_qr",
                              "offers_per_fill"]), "",
                "Acceptance probabilities (0.9 permissive; picky 0.9 / 0.3) are assumptions.",
                "",
                "Note: an offer with a 2-nurse move needs both nurses to accept, and the strain policy uses more "
                "2-nurse moves, so its offers_per_fill is partly mechanical.", ""]
    if (e5 := _read("e5_summary.csv")) is not None:
        ai = e5[e5.policy == "ai"].iloc[0]
        runs5 = _read("e5_runs.csv")
        model5 = str(runs5["model"].iloc[0]) if runs5 is not None and "model" in runs5.columns else "local LLM"
        n_seeds = len(runs5) if runs5 is not None else 0
        out += ["## E5 — AI as decision-maker", "",
                md_table(e5, ["policy", "QR_total", "gini_strain", "max_qr", "nurses_qr_ge3_28d",
                              "top10_qr_share", "unfilled", "changes_per_repair", "SN_total", "n_events"]), "",
                f"AI agreement with the formula: {ai['agreement_rate']:.1%}; fallback rate: "
                f"{ai['fallback_rate']:.1%}; verified rate: {ai['verified_rate']:.1%}; "
                f"agreement/fallback/verified pooled by decision count; "
                f"latency = median of per-seed medians ({ai['latency_p50_ms']:.0f} ms).", ""]
        if (e5s := _read("e5_stats.csv")) is not None:
            n_seeds = int(e5s["n"].iloc[0])
            for other in ("strain", "baseline"):
                out += [md_table(e5s[e5s.comparison == f"ai vs {other}"].assign(mean_other=lambda d, o=other: d[f"mean_{o}"]),
                                 ["comparison", "metric", "mean_other", "mean_ai", "mean_diff", "ci_low", "ci_high",
                                  "wilcoxon_p", "effect_dz", "n"]), ""]
        out += [f"Caveat: n seeds = {n_seeds} ({model5}; small sample).", ""]
    if (runs := _read("e1_runs.csv")) is not None:
        e = economics_bridge(runs, ward_cfg)
        out += ["## Economics bridge (extrapolation — not a simulation result)", "",
                f"- Quick returns avoided per nurse-month: **{e['dqr_per_nurse_month']:.3f}**",
                f"- Vedaa et al. (2017) anchor: ~{e['vedaa_pct'] * 100:.1f}% fewer absence days "
                f"≈ {e['vedaa_days']:.0f} days per 60-FTE ward-year",
                f"- 2025 cluster-RCT anchor: ~{e['rct_pct'] * 100:.1f}% ≈ {e['rct_days']:.0f} days",
                f"- Value at €250–€550/day: **€{e['value_low_eur']:,.0f} – €{e['value_high_eur']:,.0f}** "
                "per ward-year (compare with the Economics section's 1–18% assumption)",
                f"- Repair-only part (QR from repairs, `qr_from_repairs`) avoided per nurse-month: "
                f"{e['repair_only_dqr_per_nurse_month']:.3f} (Vedaa anchor ~{e['repair_only_vedaa_pct'] * 100:.1f}%), "
                "a lower bound on the benefit; the headline figure uses the strain-vs-baseline QR_total difference.",
                "- Assumes the absence effects transfer from Norwegian settings and scale linearly.",
                "- The RCT anchor linearly scales the trial's halving effect (rel/0.5, capped at 44%).",
                "- The two anchors differ by about 10x, and the RCT anchor exceeds the Economics section's 1–18% range.",
                "- The magnitude depends on the synthetic base-roster QR level (base_qr_pref).", ""]
    out += ["## Run configuration", "", "```json", json.dumps({"ward": ward_cfg, "policy": policy}, indent=2),
            "```", ""]
    return "\n".join(out)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "summary.md").write_text(build_summary())
    print("wrote", RESULTS_DIR / "summary.md")


if __name__ == "__main__":
    main()
