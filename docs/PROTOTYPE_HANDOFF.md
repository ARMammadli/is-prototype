# Prototype handoff: switch to "rule ranks, GenAI explains, planner decides"

This brief comes from a design review of the Team 26 AI Strategy Lab project (RSM, Information Strategy, 2026). Read it fully, then explore the repository, then propose a plan **before editing any code**.

## 1. Project context (short)

- Setting: nurse roster *repair* at Erasmus MC (synthetic ward: 37 beds, ~70 nurses, 8 weeks, day/evening/night shifts, 5.33% absence, Dutch Working Hours Act rules).
- Decision: a nurse calls in sick; the planner chooses one of several legal repair options.
- Baseline ("ORTEC-like"): choose the option with the fewest changes, then the nurse with the most contract hours left.
- Burnout is motivation only. The system must **not** predict or diagnose burnout or use any health data. Nurses appear only as codes.
- Outcomes are observable roster measures: quick returns (rest < 11 h), nurses with 3+ quick returns in 28 days, max quick returns per nurse, night shifts, consecutive days, overtime, unfilled shifts, short-notice changes, and the inequality (Gini) of short-notice changes.

## 2. The design decision

The current prototype has GenAI (Qwen3 8B, local) **choose** the repair, with a fixed hospital load formula as fallback. The review found:

- The formula ranks about as well as GenAI (200-ward formula run: 71% fewer heavily exposed nurses vs. 59% for GenAI on 5 wards).
- GenAI-as-chooser conflicts with the rest of the project (planner decides, governance, AI Act exposure).
- GenAI's defensible value is explanation and policy translation, which rules cannot do.

**New architecture:**

| Component | Role |
|---|---|
| Option generator (existing) | Lists legal repair options (stands in for ORTEC). |
| Exposure calculator (rules) | Per-nurse exposure before/after each option. |
| Strain ranker (rules) | Ranks options with the hospital weighted formula. **This is the decider.** Hard constraints checked first. |
| GenAI job 1: explanation | Receives the ranked options and writes 2 to 3 plain sentences: who gets extra work, who gets relief, and the trade-off versus the ORTEC-like choice. |
| GenAI job 2: policy translation | Converts a manager's plain-language fairness policy into proposed formula weights; manager must approve. Keep existing function. |
| Fact check (existing) | Verifies every number in the explanation against the roster: "verified" / "mismatch". Keep. |
| Audit log (existing) | Logs ranking, explanation, fact-check status, planner choice, override reason. Keep. |
| Planner | Accepts the top option in one click or overrides with a short reason. |

**Hard rule: GenAI must never change the ranking or the chosen option.** It only explains the rule's choice. If GenAI fails, the decision still stands; the UI shows the ranked table without a narrative and logs the failure.

## 3. Required changes

1. **Flip the decision flow.** Formula selects the option; GenAI receives the selected option, the runner-up(s) and the ORTEC-like option, and explains. Remove the GenAI selection path from the default mode.
2. **Keep GenAI-as-chooser as an experimental arm** (config flag, e.g. `mode = "genai_chooser"`), so the evaluation can compare it. Do not delete it.
3. **Update the explanation prompt** so it explains a given decision rather than making one. Include the before/after exposure numbers for each affected nurse and the policy text. Ask for: who gains load, who is relieved, why this beats the stable option, any cost (e.g. extra short-notice changes).
4. **Planner UI:** show ORTEC-like choice and the rule-ranked choice side by side, the ranked table, the explanation with its fact-check badge, one-click accept, and override with reason. Rename any label like "GenAI decides" to "Rule ranks, GenAI explains, you decide".
5. **Fact check:** also flag explanations whose stated direction of change is wrong (e.g. "reduces from 2 to 3"). This was the 4B model's main failure.

## 4. Evaluation rerun

Use the same 5 wards, same starting rosters, same sick calls and seeds for every arm.

| Arm | Decider |
|---|---|
| A. ORTEC-like | Fewest changes, most contract hours left |
| B. Rule-ranked (main design) | Hospital formula |
| C. GenAI-chooser (experimental) | Qwen3 8B, as in the current prototype |
| D. Optional: strain-aware base roster + ORTEC-like repair | Tests whether gains come from correcting a weak synthetic base roster rather than from repair |

Report per ward and mean of 5 wards: quick returns, nurses with 3+ quick returns in 28 days, max quick returns for one nurse, unfilled shifts, short-notice changes, changes per repair, Gini of short-notice changes, and "wards better than A (x of 5)".

For explanations in arm B: fact-check pass rate, direction-error rate, valid-output rate, mean latency per decision. If feasible, repeat with the smaller 4B model to keep the model-comparison finding.

Optional sensitivity check: increase the weight of "disturb as few people as possible" and report the trade-off between quick returns and short-notice changes (2 to 3 weight settings is enough).

Output: one CSV with all metrics per arm and ward, and a short markdown summary table that can go on a slide.

## 5. Do not change

- Legal rules (Arbeidstijdenwet, 11 h rest, shortening once per 7 days).
- Synthetic ward parameters, absence rate, random seeds.
- Local model, data minimisation, no health data, nurse codes only.
- The ORTEC-like baseline logic.

## 6. How to work

1. Explore the repo and summarise its structure and where selection, explanation, fact check, UI and evaluation live.
2. Propose a short plan mapped to sections 3 and 4 and wait for approval.
3. Make changes in small steps; keep the old behaviour reachable via the config flag.
4. Run the evaluation and report results and anything that did not match the expectations above (for example, if arm C clearly beats arm B, say so rather than hiding it).

Deadline context: deck due Oct 7 23:59, live demo Oct 8. Prioritise a working demo of arm B and the A/B/C results table; arm D and sensitivity are optional.
