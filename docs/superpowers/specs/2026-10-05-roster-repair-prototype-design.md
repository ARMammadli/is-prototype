# Strain-Aware Roster Repair — Prototype & Evaluation Design

**Date:** 2026-10-05
**Course:** Information Strategy (RSM), AI Strategy Lab — Track A, Erasmus MC
**Fills report components:** 3 (Working prototype), 6 (Evaluation), 8 (Future-market test — regenerates its numbers)
**Deadline context:** strategy deck due 2026-10-07 23:59; live demo 2026-10-08.

## 1. Purpose and success criteria

The prototype tests the report's central hypothesis: when a published roster is repaired after an absence, ranking the
*same feasible options* by cumulative, person-level strain reduces the concentration of roster strain compared with an
ORTEC-like stability-first repair, without reducing coverage.

The prototype is done when:

1. A locally-run web app lets a user step through absence events on a synthetic ward and repair them in two modes:
   **ORTEC-like baseline** and **strain-aware + AI explanation**, with override and audit log.
2. A batch evaluation produces CSV tables, slide-ready PNG figures and an auto-generated `results/summary.md` for
   experiments E1–E4 (Section 6).
3. The LLM explanation runs on a local Ollama model and is automatically checked for faithfulness; the app works with a
   template fallback if Ollama is unavailable.
4. Unit tests pass, including the invariant that no policy ever produces a roster violating a hard rule.

Framing for the deck: the strain-aware ranking is **Stage 1 (rule-first, deterministic look-ahead)** from the Economics
section. The AI component is the LLM explanation layer. Predictive ranking is Stage 2 and out of scope.

## 2. Constraints

- Runs entirely on the user's Mac (24 GB RAM). No `pip install` / `uv sync` (user rule). Available and used:
  Python 3.14, FastAPI 0.128, uvicorn, pydantic 2, httpx, numpy, pandas, scipy, matplotlib, pytest. Not available:
  streamlit, plotly, OR-tools — not used.
- Ollama is **not installed yet**; the user installs it and pulls the model manually
  (`brew install ollama`, `ollama pull qwen3:4b`, optionally `ollama pull qwen3:1.7b`).
- Chart.js is vendored into `app/static/vendor/` (one-time download) so the demo works offline.
- Synthetic data only. No real Erasmus MC or ORTEC data is available.
- No git repository; files are written in place.

## 3. Synthetic ward and simulator (`sim/`)

All parameters live in `config/ward.json` and every run is seeded.

**Ward.** 37-bed inpatient ward, ~60 FTE ≈ 70 nurses. 1.0 FTE = 36 h/week. Contract mix: 1.0 (30%), 0.89 (30%),
0.78 (25%), 0.67 (15%). ~25% senior. ~15% exempt from night shifts.

**Shifts.**

| Code | Time | Hours |
|---|---|---|
| D | 07:30–16:00 | 8.5 |
| E | 15:30–23:00 | 7.5 |
| N | 23:00–07:30 (+1 day) | 8.5 |

These times make E→D (8.5 h rest) and N→E (8 h rest) the quick-return transitions that the law permits once per
7 days; D→N on the same day or N→D the next morning are impossible. Demand per shift is configurable (starting point
D 11 / E 10 / N 6, each needing ≥1 senior). Demand is calibrated so that a typical absence has roughly 2–8 feasible
direct-fill candidates. This is a calibration acceptance check, so that repairs are under real pressure without being
impossible.

**Horizon.** 8 weeks (56 days). Pre-planned leave blocks remove ~12% of nurse-days before rostering.

**Base roster.** A seeded greedy constructive generator. It fills each shift from eligible nurses, prioritising those
furthest below their contract hours, and respects all hard rules. It is deliberately not optimal, so it carries
realistic baseline strain.

**Hard rules** (`sim/rules.py`, checked for every candidate and on every final roster):

- At most one shift per nurse per calendar start day.
- Rest ≥ 11 h between shifts, except rest ≥ 8 h is allowed at most once in any rolling 7 days (Arbeidstijdenwet 5:3).
- At most 60 h worked in any rolling 7 days.
- At most 6 consecutive working days.
- After a series of ≥ 3 nights, ≥ 46 h rest.
- Night-exempt nurses never work N.
- Every shift keeps ≥ 1 senior.
- The nurse is not absent or on leave.

**Absence stream.** Injected so that ~5.33% of rostered shifts are lost (Erasmus MC 2024). Spells are mostly 1 day,
with some 3–5 day spells. Notice is short: 70% under 12 h, the rest under 48 h. The stream is generated once per seed
from the base roster and is identical for every policy (paired design). Absences are exogenous: strain does not cause
new absences in the model.

**Per-nurse strain metrics** (`sim/strain.py`). They are computed over a window of 28 days back plus 28 days forward
from the event day, on the current planned and realised roster:

- `QR`: quick returns (rest < 11 h)
- `N`: night shifts
- `LR`: runs of ≥ 6 consecutive working days
- `OT`: hours above contract over the window
- `SN`: short-notice changes absorbed (notice < 48 h)

`strain_i = w_qr·QR + w_n·N + w_lr·LR + w_ot·OT + w_sn·SN`

Default weights live in `config/policy.json` and are editable in the UI. They are a hospital policy, not an empirical
fact: `w_qr=3, w_n=1, w_lr=2, w_ot=0.5 (per hour), w_sn=1.5`. Quick returns get the highest weight because the trial
evidence concerns short rest.

## 4. Repair policies (`sim/policies.py`)

**Repair event.** Nurse A is absent for shift *s* on day *d*.

**Candidate generation (shared).** All candidates must pass every hard rule.

1. **Direct fill:** an off-duty nurse takes *s* (1 change).
2. **One-hop move:** nurse X moves from shift *t* on day *d* into *s*. This is allowed only if *t* is above demand or
   *t* is backfilled by an off-duty nurse Y (at most 2 changes). At most 20 one-hop candidates are kept per event.
3. **Run short:** used only when no feasible candidate exists. It is recorded as an unfilled shift.

Both policies rank **the identical feasible set**.

**Baseline — ORTEC-like.** Ranks by:

1. fewest changed assignments (stability, as ORTEC describes "limited ripple effects")
2. best fit on contract hours: largest remaining contract hours this 4-week period
3. senior match when *s* would otherwise lack a senior

The screen shows a plain table: nurse, contract, hours so far, change. No strain metrics, no explanation.

**Strain-aware.**

`cost(option) = Σ_{affected i} (strain_i_after² − strain_i_before²)`

Lowest cost wins. Ties are broken by fewest changes, then by the baseline order. Squaring makes extra load on an
already-loaded nurse more expensive, which penalises concentration. Variants for E2: a linear cost (no square) and
look-ahead windows of 7, 14 or 28 days forward.

**Batch decision rule.** In batch runs the top-ranked option of the active policy is applied. This assumes the planner
accepts the system's first suggestion, and the deck will say so.

## 5. Planner app (`app/`) and LLM layer (`llm/`)

**Server.** FastAPI on `localhost:8000` serving one static page and a JSON API:

- `POST /api/scenario {seed}`
- `GET /api/state`
- `POST /api/next-event`
- `GET /api/options?mode=baseline|strain`
- `POST /api/explain`
- `POST /api/apply {option_id, override_reason?}`
- `GET|PUT /api/policy`
- `GET /api/audit`

The app keeps one in-memory scenario at a time.

**Page.**

- **Top bar:** seed, mode toggle, "Next event" button.
- **Roster grid:** nurses × days with D/E/N cells, the absence highlighted and changed cells marked.
- **Event panel.**
- **Options table:** plain table in baseline mode; ranked table with colour-coded before→after values for QR / N / OT /
  LR and Δstrain in strain mode.
- **Explanation card (strain mode):** source tag (`qwen3:4b` or `template`), latency, and a ✅ verified / ⚠️ mismatch
  badge.
- **Apply button per option.** Choosing anything other than the top option requires an override reason from a
  dropdown: local knowledge / preference / skill mix / other. Every decision is appended to `app/data/audit.jsonl`.
- **Ward strain panel:** per-nurse strain bars plus live Gini, top-10% QR share and max QR per nurse.
- **Policy panel:** weight sliders.

**LLM.**

- **Model call:** Ollama `/api/chat`, model `qwen3:4b` (configurable; `qwen3:1.7b` as the light option), `think: false`,
  temperature 0, structured output enforced with the `format` JSON schema. Timeouts: 20 s in the UI, 60 s in
  evaluation.
- **Input:** the top 3 strain-aware options plus the baseline's top option, as JSON with pseudonymous IDs (`N01`…),
  per-nurse before/after metrics, Δstrain, change count and policy weights. No names and no health data. Nothing leaves
  the machine.
- **Output schema:**

  ```json
  {"recommended_option": "opt_id",
   "main_tradeoff": "quick_returns|nights|overtime|long_runs|short_notice|stability",
   "claims": [{"nurse": "N07", "metric": "QR", "before": 2, "after": 3}],
   "text": "≤ 80 words"}
  ```

- **Checker** (`llm/checker.py`, deterministic):
  - Every claim must match the computed numbers exactly. OT uses a ±0.5 h tolerance.
  - A claim about a nurse not in the input counts as false.
  - Any number in `text` that is not supported by the claims or input is flagged.
  - `recommended_option` is compared with the policy's top option.
  - `main_tradeoff` is compared with the ground-truth driver. The ground truth is the weighted metric with the largest
    strain difference between the strain-aware top option and the baseline top option, or rank 2 if they are the same
    option.
- **Fallback** (`llm/template.py`): if Ollama is unreachable, times out, or returns invalid JSON, a template
  explanation is generated from the same input. The UI labels it "template".

## 6. Evaluation (`eval/`)

All experiments use paired seeds. Results go to `results/` and figures to `figures/` (PNG, 300 dpi, 16:9-friendly).
`eval/make_summary.py` writes `results/summary.md` with the key numbers, every metric ranked by standardised effect
size, and the run configs and seeds. The team selects which metrics are meaningful for the deck from this ranking.

**E1 — Policy A/B** (200 seeds × {baseline, strain}). Metrics are computed on the realised 8-week roster.

- **Coverage guardrail:** unfilled shifts; shifts without a senior.
- **Exposure totals:** QR, N, LR, OT hours.
- **Concentration (hypothesis):**
  - Gini of per-nurse strain
  - top-10% share of QR
  - max QR per nurse
  - nurses with > 4 QR in any 28 days
  - Gini of short-notice changes
- **Stability (where the baseline should win):** changes per repair, distinct nurses disturbed.
- **Repair share of exposure:** the share of total QR and strain created by repairs rather than the base roster. This
  tests Assumption 1.
- **Statistics:** mean paired difference, 95% bootstrap CI, Wilcoxon signed-rank, per-seed win rate.

**E2 — Sensitivity and ablation** (50 seeds each):

- `w_qr` × {0.5, 1, 2}
- forward look-ahead {7, 14, 28} days
- squared vs linear cost
- absence rate {3%, 5.33%, 8%}

**E3 — Explanation faithfulness** (150 events sampled from E1, stratified so that half have different baseline and
strain-aware top options):

- valid-JSON rate
- claim accuracy
- % of explanations with ≥ 1 false claim or unsupported number
- recommendation agreement
- trade-off correctness
- latency p50 / p95
- fallback rate

`qwen3:1.7b` vs `qwen3:4b` is run if time allows.

**E4 — Agentic future (Section 8)** (100 seeds). Offers are made in the policy's rank order until one is accepted, or
the list is exhausted, in which case the shift is unfilled.

- **Today:** the planner assigns and the nurse accepts (p = 1).
- **Permissive agents:** each nurse agent accepts with p = 0.9.
- **Picky agents:** accept with p = 0.9 if the offer adds no QR and the nurse's strain is at or below the ward median;
  otherwise p = 0.3.

Crossed with {baseline, strain}. Metrics: unfilled shifts, QR, concentration, offers per filled shift.

**Economics bridge** (post-hoc, labelled as extrapolation). The reduction in QR per nurse-month is converted into
estimated avoided absence days. Two anchors give the range: Vedaa et al. (2017), about +21% absence days per 3 QR per
month, and the 2025 cluster RCT (IRR 0.56 for halving short rest). The result is compared with the Economics section's
1–18% assumption.

**Limitations to state:**

- The data is synthetic.
- The ORTEC-like baseline is a proxy based on vendor-described logic, not ORTEC's actual configuration.
- Batch runs assume the planner accepts the top option.
- Absences are exogenous.
- The agent acceptance probabilities are assumptions.

## 7. Error handling

- Hard-rule violations in any candidate raise an error in tests. At runtime an infeasible candidate is dropped, never
  shown.
- No feasible candidate leads to run-short, which is recorded and shown in the UI as an unfilled shift.
- Ollama errors, timeouts and invalid JSON fall back to the template explanation. Every fallback is logged and counted
  in E3.
- `PUT /api/policy` validates that weights are numeric and ≥ 0.

## 8. Testing (`tests/`, pytest)

- `rules`: each hard rule has passing and violating fixtures, including the "8 h once per 7 days" exception.
- `strain`: hand-computed metrics on a small fixed roster.
- `policies`: both policies rank the identical feasible set, and the baseline ordering is correct on a fixture.
- **Invariant:** over 20 random seeds × both policies, the final roster passes every hard rule.
- `checker`: correct claims pass, wrong numbers fail, an unknown nurse fails, an unsupported number in the text is
  flagged.
- `template`: produces valid output for any option set.

## 9. Layout

```
prototype/
  config/   ward.json  policy.json
  sim/      ward.py roster.py rules.py absences.py strain.py policies.py agents.py engine.py
  llm/      ollama_client.py prompt.py checker.py template.py
  app/      server.py  data/audit.jsonl  static/{index.html, app.js, style.css, vendor/chart.umd.min.js}
  eval/     e1_ab.py e2_sensitivity.py e3_faithfulness.py e4_agents.py make_figures.py make_summary.py
  tests/
  results/  figures/
  README.md   (how to run: app, eval, tests; Ollama setup)
```

`sim/engine.py` runs a scenario: build the ward, generate the base roster and absence stream, then repair each event in
time order with a given policy and acceptance mode. The app and all evaluation scripts share it.

## 10. Build order

1. `sim/` and its tests
2. E1 plus figures (earliest evidence for the deck)
3. App with the baseline and strain modes
4. LLM layer, checker and E3
5. E4 and E2
6. Summary, README and demo rehearsal

Steps 1–2 produce deck evidence even if later steps slip.

## 11. Out of scope

- Explanations aimed at nurses
- Dutch-language output
- Authentication
- Free-form roster editing
- Predictive (Stage 2) ranking
- Integration with real ORTEC or HiX
- Absences that respond to strain
