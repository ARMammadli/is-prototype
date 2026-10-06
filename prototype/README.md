# Strain-aware roster repair — prototype

Synthetic 37-bed ward (~60 FTE). **Rule ranks, GenAI explains, the planner decides.**
An ORTEC-like repair (stability + contract fit) is compared with the hospital's weighted fairness rule,
which ranks the same feasible options and decides. A local LLM (qwen3:8b) is used for two things only,
and every number it writes is fact-checked: (1) explaining each repair decision, (2) the monthly
scheduler–manager review report. Policy translation (words → proposed weights) is an extra.
GenAI never changes the ranking or the choice. Spec: `../docs/superpowers/specs/2026-10-05-roster-repair-prototype-design.md`.

## Setup
Python packages are already installed (numpy, pandas, scipy, matplotlib, fastapi, uvicorn, httpx, pytest).
- If `import matplotlib.pyplot` fails with a pyexpat/libexpat "Symbol not found" error, run `brew install expat`
  (keg-only, so it is not picked up automatically), then generate figures with
  `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib python3 -m evaluation.make_figures`.
  A permanent fix is `brew reinstall python@3.14`.

For the LLM (optional — without it the decision still stands; the app shows no narrative):
```bash
brew install ollama
ollama serve            # keep running in a separate terminal
ollama pull qwen3:8b
```

## Run the app (demo)
```bash
cd prototype
python3 -m uvicorn app.server:app --port 8000
```
Open http://localhost:8000 → ▶ Start. Tabs: ① one sick call (today's software vs the rule's choice,
GenAI explanation with fact-check badge, accept or override with a reason), ② results across the 5 wards,
③ monthly report.

## Run the evaluation
```bash
cd prototype
python3 -m evaluation.calibrate                 # sanity check of the synthetic ward
python3 -m evaluation.e1_ab --seeds 200         # policy A/B
python3 -m evaluation.e3_faithfulness --n 150   # needs Ollama
python3 -m evaluation.e4_agents --seeds 100     # agentic future
python3 -m evaluation.e2_sensitivity --seeds 50 # sensitivity
python3 -m evaluation.e6_arms arms              # A (ORTEC-like) vs B (rule) + SN-weight sensitivity, 5 wards
python3 -m evaluation.e6_arms explain           # B explanations with qwen3:8b (~10 s each), then: rescore, summary
python3 -m evaluation.e7_monthly                # 10 monthly reports (5 wards x 2 months), fact-checked
python3 -m evaluation.make_figures && python3 -m evaluation.make_summary
```
Outputs: `results/*.csv`, `results/summary.md`, `figures/*.png`.

## Tests
```bash
cd prototype && python3 -m pytest -q
```

## Limitations
Synthetic data; the baseline is a proxy for ORTEC's vendor-described logic, not its real configuration;
batch runs assume the planner accepts the top option; absences are exogenous; agent acceptance
probabilities and policy weights are assumptions.
- The base roster's quick-return level is calibrated by `base_qr_pref` (a synthetic assumption).
- The fact check verifies numbers, up/down wording, claims about today's software and the stated cost.
  It does not judge reasoning quality, and it does not check spelled-out numbers ("three").
