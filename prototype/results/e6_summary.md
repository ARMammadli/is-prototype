# E6 — Arms rerun: rule ranks, GenAI explains, planner decides

Synthetic ward, 5 wards (seeds 0-4), same base rosters and sick calls for every arm. Mean of 5 wards; lower is better for every metric. "x/5" = wards where the arm is strictly better than A on that metric.

| Metric | A. ORTEC-like | B. Rule-ranked (main) | C. GenAI-chooser (qwen3:8b) | B with SN weight 3 | B with SN weight 6 |
|---|---|---|---|---|---|
| Quick returns | 182.4 | 115.0 (5/5) | 120.0 (5/5) | 149.2 (5/5) | 161.6 (5/5) |
| Nurses with 3+ QR in 28 d | 24.4 | 6.2 (5/5) | 10.0 (5/5) | 16.2 (5/5) | 21.2 (5/5) |
| Max QR, one nurse | 6.0 | 4.8 (4/5) | 5.0 (4/5) | 5.0 (4/5) | 5.0 (4/5) |
| Unfilled shifts | 1.2 | 1.2 (0/5) | 1.0 (1/5) | 1.2 (0/5) | 1.2 (0/5) |
| Short-notice changes | 71.2 | 123.8 (0/5) | 137.0 (0/5) | 85.8 (0/5) | 74.2 (0/5) |
| Changes per repair | 1.02 | 1.81 (0/5) | 1.97 (0/5) | 1.33 (0/5) | 1.19 (0/5) |
| Gini of short-notice changes | 0.495 | 0.387 (5/5) | 0.343 (5/5) | 0.451 (4/5) | 0.464 (4/5) |

C replays the qwen3:8b choices logged in E5 (`e5_decisions.jsonl`); the replay reproduces E5's rosters exactly.

## Arm B explanations (GenAI explains the rule's choice)

| Model | Decisions | Valid output | Fact-check pass | Direction error | Mean latency (s) |
|---|---|---|---|---|---|
| qwen3:8b | 400 | 100.0% | 96.5% | 0.5% | 9.7 |
