# Evaluation results and how to cite them

**Last updated:** 2026-10-05
**Source of truth:** `prototype/results/summary.md` (auto-generated). Re-run `python3 -m evaluation.make_summary` after any new run.
**See also:** [roster-repair-prototype.md](roster-repair-prototype.md)

## E1: Policy A/B (200 paired seeds)
| Metric | ORTEC-like | Strain-aware | Note |
|---|---|---|---|
| Nurses with ≥3 QR in 28 days | 23.2 | 6.7 (−71%) | strongest deck claim |
| Max QR, one nurse | 6.0 | 4.5 | |
| Gini of per-nurse strain | 0.236 | 0.192 | partly circular (close to the policy objective) |
| Gini of short-notice changes | 0.487 | 0.375 | |
| Total QR | 176 | 113 (−36%) | see the decomposition below |
| Unfilled shifts | ~1.0 | ~1.0 | coverage guardrail holds |
| Changes per repair | 1.02 | 1.77 | **cost**: less stability |
| Short-notice changes absorbed | 69 | 118 | **cost** |
| Top-10% QR share | 0.209 | 0.232 | **worse**: fewer QRs, but the remainder stays concentrated |

**QR decomposition (important framing).** Each policy's QR total splits into base-roster QRs kept and QRs created by repairs:

| Policy | Base-roster QRs kept | QRs created by repairs |
|---|---|---|
| ORTEC-like | 166 | 10.4 |
| Strain-aware | 112 | 0.7 |

So most of the reduction comes from **moving nurses out of already-rostered QRs** at the cost of extra short-notice changes. Only about 10 QRs come from avoiding new ones during repair. Do not say "avoids creating QRs during repair".

**Robustness without base QRs** (E2 `no_base_qr`): Gini diff −0.115 and QR −25 per run, so the effect does not depend on the calibration knob.

## E2: Sensitivity
- The Gini improvement holds for QR weight ×0.5 and ×2, look-ahead of 7 and 14 days, and absence rates of 3% and 8%. The effect is larger at 8%.
- **Linear cost (no square): Gini gets worse (+0.012).** The squared concentration penalty is what drives the result.

## E4: Agentic future (replaces the unsupported Section 8 numbers)
| Mode | Unfilled (base / strain) | QR (base / strain) |
|---|---|---|
| Planner assigns | 1.02 / 1.01 | 177 / 113 |
| Permissive agents (p = 0.9) | 1.05 / 1.04 | 177 / 116 |
| Picky agents | 1.63 / 1.46 | 172 / 134 |

- **Takeaway:** agents don't remove scarcity. Picky agents raise unfilled shifts by about 50–60% and erode the QR gain.
- The acceptance probabilities are assumptions. The strain policy's higher offers-per-fill is partly mechanical, because a 2-nurse move needs both nurses to accept.

## E3: Explanation faithfulness
Not run yet (needs Ollama). Report its metrics alongside `fallback_rate` and `n_llm`. Recommendation agreement is largely a reading test, because the prompt tells the model the answer is the option with `rank_strain` 1.

## Economics bridge (extrapolation, not simulation)
- **Range:** €5.5k–€122k per ward-year.
- **The two anchors differ about 10×:**
  - Vedaa gives about 3.2% fewer absence days.
  - The RCT anchor gives about 31.6%, a linear scaling of the trial's halving effect. That is above the report's 1–18% assumption.
- **Repair-only lower bound:** about 0.5%.
- **Magnitude depends on `base_qr_pref`.** Present the range as conditional and lead with the Vedaa anchor.

## Citation discipline for the deck
- Lead with concentration: ≥3 QR in 28 days, max QR and Gini, shown next to the stability costs.
- Don't call `unfilled` or `LR_total` significant (15+ uncorrected tests).
- Don't use `repair_share_qr` to test Assumption 1; it depends on the calibration.
- Quote `rel_change` and the CI, not `effect_dz`. The effect size is inflated for low-variance metrics.
- **Limitations to state:**
  - synthetic data;
  - the baseline is a proxy for ORTEC, not ORTEC itself;
  - batch runs assume the planner accepts the top option;
  - absences are exogenous;
  - weights, acceptance probabilities and `base_qr_pref` are assumptions.
