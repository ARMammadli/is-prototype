# E6 — Arms rerun: rule ranks, GenAI explains, planner decides

Synthetic ward, 5 wards (seeds 0-4), same base rosters and sick calls for every arm. Mean of 5 wards; lower is better for every metric. "x/5" = wards where the arm is strictly better than A on that metric.

| Metric | A. ORTEC-like | B. Rule-ranked (main) | B with SN weight 3 | B with SN weight 6 |
|---|---|---|---|---|
| Quick returns | 182.4 | 115.0 (5/5) | 149.2 (5/5) | 161.6 (5/5) |
| Nurses with 3+ QR in 28 d | 24.4 | 6.2 (5/5) | 16.2 (5/5) | 21.2 (5/5) |
| Max QR, one nurse | 6.0 | 4.8 (4/5) | 5.0 (4/5) | 5.0 (4/5) |
| Unfilled shifts | 1.2 | 1.2 (0/5) | 1.2 (0/5) | 1.2 (0/5) |
| Short-notice changes | 71.2 | 123.8 (0/5) | 85.8 (0/5) | 74.2 (0/5) |
| Changes per repair | 1.02 | 1.81 (0/5) | 1.33 (0/5) | 1.19 (0/5) |
| Gini of short-notice changes | 0.495 | 0.387 (5/5) | 0.451 (4/5) | 0.464 (4/5) |

## Arm B explanations (GenAI explains the rule's choice)

| Model | Decisions | Valid output | Fact-check pass | Direction error | Wrong comparison | Mean latency (s) |
|---|---|---|---|---|---|---|
| qwen3:8b | 400 | 100.0% | 66.2% | 0.2% | 31.0% | 11.3 |

Fact-check pass = numbers, claims, up/down wording, nurse codes, and claims about today's software and the stated cost all match the data. Two prompts were run on the same 400 decisions and re-scored with the same final check: v1 (results/archive_e6_prompt_v1/) 66.2%, v2 (this run, with per-option totals and more/fewer/same labels) 66.2%; the prompt change did not raise accuracy. When the rule and today's software pick the same option, 93% pass; when they differ, 64%. Manual reads: 9 of 25 v1 explanations had errors the first check missed; 7 of 15 passing v2 explanations (differ cases) had errors, 3 of which the final check now catches. The check is a safety net, not a guarantee: the planner still reads the explanation.
