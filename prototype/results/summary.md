# Evaluation summary (auto-generated)

Synthetic ward; ORTEC-like baseline is a proxy built from vendor-described logic. Lower is better for every metric. ★ = large and significant effect (either direction).

## E1 — Policy A/B (paired seeds)

| flag | metric | direction | mean_baseline | mean_strain | mean_diff | ci_low | ci_high | rel_change | wilcoxon_p | effect_dz | win_rate | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ★ | changes_per_repair | strain worse | 1.023 | 1.770 | 0.747 | 0.739 | 0.754 | 0.730 | 0.000 | 14.361 | 0.000 | 200 |
| ★ | qr_base_kept | strain better | 165.955 | 112.230 | -53.725 | -54.355 | -53.115 | -0.324 | 0.000 | -11.776 | 1.000 | 200 |
| ★ | QR_total | strain better | 176.310 | 112.965 | -63.345 | -64.120 | -62.575 | -0.359 | 0.000 | -11.455 | 1.000 | 200 |
| ★ | SN_total | strain worse | 69.360 | 117.540 | 48.180 | 47.535 | 48.845 | 0.695 | 0.000 | 10.416 | 0.000 | 200 |
| ★ | nurses_qr_ge3_28d | strain better | 23.155 | 6.700 | -16.455 | -16.890 | -16.040 | -0.711 | 0.000 | -5.320 | 1.000 | 200 |
| ★ | gini_strain | strain better | 0.236 | 0.192 | -0.044 | -0.046 | -0.042 | -0.186 | 0.000 | -3.591 | 1.000 | 200 |
| ★ | nurses_disturbed | strain worse | 50.795 | 62.605 | 11.810 | 11.325 | 12.270 | 0.233 | 0.000 | 3.449 | 0.000 | 200 |
| ★ | qr_from_repairs | strain better | 10.355 | 0.735 | -9.620 | -9.995 | -9.245 | -0.929 | 0.000 | -3.432 | 1.000 | 200 |
| ★ | repair_share_qr | strain better | 0.059 | 0.007 | -0.052 | -0.054 | -0.050 | -0.888 | 0.000 | -3.220 | 1.000 | 200 |
| ★ | gini_sn | strain better | 0.487 | 0.375 | -0.111 | -0.118 | -0.105 | -0.229 | 0.000 | -2.273 | 0.995 | 200 |
| ★ | max_qr | strain better | 6.000 | 4.495 | -1.505 | -1.605 | -1.405 | -0.251 | 0.000 | -2.102 | 0.935 | 200 |
| ★ | top10_qr_share | strain worse | 0.209 | 0.232 | 0.023 | 0.020 | 0.025 | 0.108 | 0.000 | 1.308 | 0.110 | 200 |
|  | LR_total | strain better | 7.430 | 7.355 | -0.075 | -0.140 | -0.010 | -0.010 | 0.026 | -0.160 | 0.135 | 200 |
|  | unfilled | strain better | 0.995 | 0.965 | -0.030 | -0.055 | -0.005 | -0.030 | 0.034 | -0.151 | 0.035 | 200 |
|  | no_senior_shifts | strain worse | 0.105 | 0.115 | 0.010 | -0.005 | 0.030 | 0.095 | 0.317 | 0.071 | 0.005 | 200 |
|  | OT_total | strain worse | 0.060 | 0.111 | 0.051 | -0.058 | 0.175 | 0.858 | 0.247 | 0.064 | 0.015 | 200 |
|  | N_total | strain worse | 335.735 | 335.740 | 0.005 | -0.025 | 0.035 | 0.000 | 0.739 | 0.024 | 0.020 | 200 |
|  | qr_base_roster | no change | 184.100 | 184.100 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 200 |

**QR decomposition** (mean per run). baseline: base roster 184.1, base QRs kept 166.0, created by repairs 10.4; strain: base roster 184.1, base QRs kept 112.2, created by repairs 0.7. The strain policy's QR reduction comes mostly from moving nurses out of base-roster QRs, which costs extra short-notice changes, and only partly from avoiding QRs created during repair. With no base-roster QRs (E2 `no_base_qr`), strain vs baseline gives gini_strain diff -0.115 and QR_total diff -25.04.

Caveats:
- top10_qr_share worsens under strain because total QR shrinks while the remaining QRs stay concentrated.
- repair_share_qr depends on the calibrated base_qr_pref and should not be used to test Assumption 1.
- The p-values are uncorrected across 15 or more metrics, so small effects such as unfilled and LR_total should not be called significant.

Metric notes: nurses_qr_ge3_28d = nurses with ≥3 quick returns in any 28-day window; the spec's >4 is legally near-impossible under the 1-per-7-days rule.

## E2 — Sensitivity and ablation

| config | metric | mean_diff | ci_low | ci_high | wilcoxon_p |
|---|---|---|---|---|---|
| default | gini_strain | -0.040 | -0.043 | -0.037 | 0.000 |
| default | top10_qr_share | 0.024 | 0.020 | 0.027 | 0.000 |
| default | unfilled | 0.000 | 0.000 | 0.000 | 1.000 |
| w_qr_x0.5 | gini_strain | -0.041 | -0.045 | -0.038 | 0.000 |
| w_qr_x0.5 | top10_qr_share | 0.017 | 0.014 | 0.021 | 0.000 |
| w_qr_x0.5 | unfilled | 0.040 | 0.000 | 0.100 | 0.157 |
| w_qr_x2 | gini_strain | -0.033 | -0.036 | -0.030 | 0.000 |
| w_qr_x2 | top10_qr_share | 0.014 | 0.011 | 0.018 | 0.000 |
| w_qr_x2 | unfilled | -0.020 | -0.060 | 0.000 | 0.317 |
| forward_7d | gini_strain | -0.033 | -0.037 | -0.030 | 0.000 |
| forward_7d | top10_qr_share | 0.026 | 0.021 | 0.031 | 0.000 |
| forward_7d | unfilled | -0.040 | -0.100 | 0.000 | 0.157 |
| forward_14d | gini_strain | -0.036 | -0.040 | -0.032 | 0.000 |
| forward_14d | top10_qr_share | 0.025 | 0.022 | 0.029 | 0.000 |
| forward_14d | unfilled | -0.020 | -0.060 | 0.000 | 0.317 |
| linear_cost | gini_strain | 0.012 | 0.009 | 0.014 | 0.000 |
| linear_cost | top10_qr_share | 0.046 | 0.040 | 0.051 | 0.000 |
| linear_cost | unfilled | 0.000 | -0.060 | 0.060 | 1.000 |
| absence_3pct | gini_strain | -0.026 | -0.029 | -0.023 | 0.000 |
| absence_3pct | top10_qr_share | 0.013 | 0.009 | 0.016 | 0.000 |
| absence_3pct | unfilled | -0.020 | -0.060 | 0.000 | 0.317 |
| absence_8pct | gini_strain | -0.053 | -0.057 | -0.050 | 0.000 |
| absence_8pct | top10_qr_share | 0.046 | 0.040 | 0.052 | 0.000 |
| absence_8pct | unfilled | -0.060 | -0.200 | 0.060 | 0.366 |
| no_base_qr | gini_strain | -0.115 | -0.121 | -0.109 | 0.000 |
| no_base_qr | top10_qr_share | -0.063 | -0.193 | 0.067 | 0.699 |
| no_base_qr | unfilled | 0.000 | 0.000 | 0.000 | 1.000 |

## E3 — Explanation faithfulness

| model | n | n_llm | json_valid_rate | claim_accuracy | pct_flagged | pct_direction_error | recommendation_agreement | tradeoff_correct | latency_p50_ms | latency_p95_ms | fallback_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b | 150 | 150 | 1.000 | 0.999 | 0.027 | 0.433 | 1.000 | 1.000 | 6799.000 | 12843.300 | 0.000 |
| qwen3:4b [differ] | 75 | 75 | 1.000 | 1.000 | 0.027 | 0.160 | 1.000 | 1.000 | 8985.000 | 16015.300 | 0.000 |
| qwen3:4b [same] | 75 | 75 | 1.000 | 0.997 | 0.027 | 0.707 | 1.000 | 1.000 | 4599.000 | 10430.400 | 0.000 |

## E4 — Agentic future

| mode | policy | unfilled | QR_total | gini_strain | max_qr | offers_per_fill |
|---|---|---|---|---|---|---|
| permissive | baseline | 1.050 | 176.880 | 0.236 | 6.030 | 1.111 |
| permissive | strain | 1.040 | 115.560 | 0.196 | 4.580 | 1.203 |
| picky | baseline | 1.630 | 172.000 | 0.228 | 6.020 | 2.054 |
| picky | strain | 1.460 | 134.330 | 0.208 | 5.430 | 2.812 |
| today | baseline | 1.020 | 176.810 | 0.236 | 6.050 | 1.000 |
| today | strain | 1.010 | 113.460 | 0.193 | 4.540 | 1.000 |

Acceptance probabilities (0.9 permissive; picky 0.9 / 0.3) are assumptions.

Note: an offer with a 2-nurse move needs both nurses to accept, and the strain policy uses more 2-nurse moves, so its offers_per_fill is partly mechanical.

## Economics bridge (extrapolation — not a simulation result)

- Quick returns avoided per nurse-month: **0.452**
- Vedaa et al. (2017) anchor: ~3.2% fewer absence days ≈ 22 days per 60-FTE ward-year
- 2025 cluster-RCT anchor: ~31.6% ≈ 221 days
- Value at €250–€550/day: **€5,543 – €121,725** per ward-year (compare with the Economics section's 1–18% assumption)
- Repair-only part (QR from repairs, `qr_from_repairs`) avoided per nurse-month: 0.069 (Vedaa anchor ~0.5%), a lower bound on the benefit; the headline figure uses the strain-vs-baseline QR_total difference.
- Assumes the absence effects transfer from Norwegian settings and scale linearly.
- The RCT anchor linearly scales the trial's halving effect (rel/0.5, capped at 44%).
- The two anchors differ by about 10x, and the RCT anchor exceeds the Economics section's 1–18% range.
- The magnitude depends on the synthetic base-roster QR level (base_qr_pref).

## Run configuration

```json
{
  "ward": {
    "n_nurses": 70,
    "fte_values": [
      1.0,
      0.89,
      0.78,
      0.67
    ],
    "fte_probs": [
      0.3,
      0.3,
      0.25,
      0.15
    ],
    "senior_frac": 0.25,
    "night_exempt_frac": 0.15,
    "days": 56,
    "demand": {
      "D": 11,
      "E": 10,
      "N": 6
    },
    "leave_frac": 0.12,
    "leave_block_days": 7,
    "repair_availability_p": 0.2,
    "absence_rate": 0.0533,
    "spell_lengths": [
      1,
      3,
      4,
      5
    ],
    "spell_probs": [
      0.75,
      0.1,
      0.08,
      0.07
    ],
    "short_notice_frac": 0.7,
    "base_qr_pref": 0.14
  },
  "policy": {
    "weights": {
      "QR": 3.0,
      "N": 1.0,
      "LR": 2.0,
      "OT": 0.5,
      "SN": 1.5
    },
    "back_days": 28,
    "forward_days": 28,
    "squared": true,
    "model": "qwen3:8b",
    "ui_timeout_s": 30,
    "eval_timeout_s": 60
  }
}
```
