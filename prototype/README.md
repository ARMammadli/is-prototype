# Prototype code

See the README at the repository root for what the prototype does, how to run it, how to reproduce the
evaluation and the main results.

- `app/`: web app (FastAPI server and the planner, results and monthly-report pages)
- `sim/`: synthetic ward, sick calls, repair options and the hospital rule
- `llm/`: local-model client, fact block, fact checks, monthly report
- `evaluation/`: scripts that produce everything in `results/` and `figures/`
- `config/`: ward parameters and the hospital's default weights (`policy.json`)
- `tests/`: `python3 -m pytest -q`
