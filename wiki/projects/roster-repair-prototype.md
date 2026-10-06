# Project: Strain-aware roster repair prototype

**Last updated:** 2026-10-05
**See also:** [evaluation-results.md](evaluation-results.md), [../preferences/workflow.md](../preferences/workflow.md), [../../raw/assignment-brief.md](../../raw/assignment-brief.md)

## What it is
This prototype fills report Components 3 (prototype) and 6 (evaluation), and regenerates the numbers for Component 8.
- **Data:** a synthetic 37-bed ward (~60 FTE, 70 nurses) over 56 days, with D/E/N shifts and absences injected at 5.33%.
- **Comparison:** an ORTEC-like baseline (stability, then contract fit) against strain-aware ranking of the **same** feasible options. A local-LLM explanation sits on top.
- **Documents:**
  - Spec: `docs/superpowers/specs/2026-10-05-roster-repair-prototype-design.md`
  - Plan: `docs/superpowers/plans/2026-10-05-roster-repair-prototype.md`
- **Code:** `prototype/`, with these parts:
  - `sim/`: the simulator.
  - `llm/`: payload, Ollama client, deterministic checker, template fallback.
  - `app/`: FastAPI and a vanilla-JS planner page.
  - `evaluation/`: E1–E4 and the summary.

## Design decisions (agreed with user 2026-10-05)
- **Synthetic data only.** No real Erasmus MC or ORTEC data is accessible.
- **One baseline:** an ORTEC-like scheduler that ranks options as the vendor describes (feasible, limited ripple, best-fit on contract hours). It shows a plain options table.
- **Honest framing:** strain-aware ranking is **Stage 1, deterministic look-ahead** from the report's Economics section. The AI part is the LLM explanation; predictive ranking is Stage 2.
- **Strain score:** a weighted sum of QR, nights, long runs, overtime and short-notice changes. The weights (QR 3, N 1, LR 2, OT 0.5, SN 1.5) are a hospital policy that can be edited in the UI.
  - Option cost is the change in the **squared** strain of each affected nurse, which penalises concentration.
- **LLM:** Ollama `qwen3:4b` with thinking off, temperature 0 and JSON-schema output.
  - A deterministic checker verifies every claim against the computed numbers.
  - A template fallback keeps the demo working without Ollama.
- **Shift times:** D 07:30–16:00, E 15:30–23:00, N 23:00–07:30. These make E→D and N→E the legal 8h quick returns (Arbeidstijdenwet 5:3: one shortened rest per 7 days).

## Deviations and rulings made during the build
- **`base_qr_pref = 0.14`:** a new ward.json knob. The greedy base roster had zero quick returns, which is unrealistic. With the knob it has about 2.7 QR per nurse per 8 weeks. This is a synthetic assumption.
- **`/api/apply` requires `event_id`:** this blocks applying a stale option across events.
- **Tighter number allow-list in the checker:** ids, weights and ranks are excluded. Claims verify "exists in the payload", not "attributed to the right option". Spelled-out numbers are not checked.
- **E3 metrics are computed on LLM rows only.** Template-fallback rows would pass by construction.
- **Metric change:** "> 4 QR in 28 days" was replaced by **≥ 3**, because more than 4 is legally near-impossible.
- **Folder rename:** `eval/` became `evaluation/`.
- **No git repo.** The build used subagent-driven development, with snapshot diffs for review. The review ledger is kept at `.superpowers/sdd/2026-10-05-roster-repair-prototype/progress.md`.

## State (2026-10-05)
- All 13 plan tasks are done and reviewed, and the final whole-project review found no Critical issues. **85 tests pass.**
- E1, E2 and E4 have been run, and the results are in `prototype/results/` (with `summary.md`).
- **Pending, environment only:**
  - **Figures: DONE 2026-10-05.** `brew install expat` is keg-only, so run `DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib python3 -m evaluation.make_figures`. Five PNGs are in `prototype/figures/` (E3 figure pending).
  - **E3 live run:** Ollama is installed and serving, but **no model pulled yet** (`ollama pull qwen3:4b`), then `python3 -m evaluation.e3_faithfulness --n 150`.
  - **Browser demo:** not yet clicked through manually. Run with `python3 -m uvicorn app.server:app --port 8000`.
- **Report still to write:** the Prototype, Evaluation and Recommendation sections, a rewrite of Section 8 with the E4 numbers, and the missing references.

## Gotchas
- Every run is seeded and paired, so the same seed gives the same ward, base roster and absences for both policies. One run takes about 0.1 s, and full E1 takes about 16 s.
- App and batch use identical logic. The final review verified that app == batch rosters on seed 3.
- Demo KPIs use a ±28-day window around the current event, while E1 uses the full 56 days.
