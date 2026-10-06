# E7 — Monthly review reports (rules compute, GenAI writes, checker verifies)

Model: qwen3:8b. 10 reports (5 wards x 2 months).

| Valid output | Fact check passed | Median latency (s) |
|---|---|---|
| 10/10 | 7/10 | 6.5 |

The fact check verifies that every number is in the facts, that 'from X to Y' / 'X vs. Y' wording matches the direction of the numbers, and that named nurses carry their own numbers. It does not judge whether the discussion points are wise.

## Ward 1, month 1 — mismatch

The hospital rule reduced quick returns to 56 (lower than today's 96) but increased last-minute call-ins to 74 (higher than 42). Two nurses had 3+ quick returns, fewer than the 8 under today's software. The planner made no decisions, and GenAI explained 53 sick calls, with 70% passing fact checks.

1. Quick returns in the original roster were 103, suggesting potential for reducing last-minute call-ins by adjusting the base roster.
2. Nurses Nurse_24, Nurse_30, and Nurse_06 each had 4 last-minute call-ins, indicating a need to spread these more evenly.
3. The rule led to more shift changes per sick call (1.81 vs. 1.0) and more nurses with changed shifts (50 vs. 36).

> Flagged: Nurse_06: ['4']

## Ward 1, month 2 — verified

The hospital rule reduced quick returns to 57 (lower than today's 81) and cut nurses with 3+ quick returns to 1 (lower than 7). It increased last-minute call-ins to 49 (higher) and shift changes to 1.82 (higher). The planner made no decisions, and no overrides were logged. GenAI explained 28 sick calls, with 61% passing fact checks.

1. Quick returns in the original roster were high at 86; consider reducing them in next month's base roster to lower last-minute call-ins.
2. Nurses Nurse_31, Nurse_56, and Nurse_59 each had 3 last-minute call-ins; consider spreading these across more staff to reduce load.
3. The rule increased shift changes per sick call to 1.82; monitor if this impacts nurse workload or patient care.

## Ward 2, month 1 — verified

The hospital rule reduced quick returns to 62 vs. 97, with fewer nurses having 3+ quick returns (4 vs. 13). It increased last-minute call-ins to 63 vs. 38 and shift changes per sick call to 1.73 vs. 1.02. The planner made no decisions, and no overrides were logged. GenAI explanations passed fact checks for 68% of sick calls.

1. Quick returns in the original roster were high (94), suggesting potential for improvement in next month's base roster to reduce last-minute call-ins.
2. Nurses Nurse_45, Nurse_49, and Nurse_50 each had 3 last-minute call-ins; consider spreading these across more staff.
3. The rule increased shift changes per sick call, which may impact nurse workload and should be monitored.

## Ward 2, month 2 — verified

The hospital rule reduced quick returns to 56 (lower than today's 94) and eliminated nurses with 3+ quick returns. It increased last-minute call-ins to 60 (higher than today's 34) and raised shift changes per sick call to 1.9 (higher than today's 1.05). No planner overrides were logged, and GenAI explanations passed fact checks for 66% of sick calls. Quick returns in the original roster were high at 96, suggesting potential for improvement.

1. Quick returns in the original roster were 96, which is higher than the rule's 56; consider reducing these in next month's base roster to lower last-minute call-ins.
2. Nurse_59 had the most last-minute call-ins (3), suggesting a need to spread these more evenly across the team.
3. The rule increased shift changes per sick call to 1.9, which may impact nurse workload and should be monitored.

## Ward 3, month 1 — verified

The hospital rule reduced quick returns to 63 vs. 97, with fewer nurses having 3+ quick returns (3 vs. 11). It increased last-minute call-ins to 59 vs. 33 and shift changes per sick call to 1.86 vs. 1.03. The planner made no decisions, and GenAI explanations had a 71% pass rate. Quick returns in the original roster were high (98), suggesting potential for improvement.

1. Quick returns in the original roster were 98, which may contribute to higher last-minute call-ins; consider reducing these in next month's base roster.
2. Nurses Nurse_02, Nurse_12, and Nurse_46 each had 3 last-minute call-ins; consider spreading these more evenly across the team.
3. The rule increased shift changes per sick call to 1.86, which may impact workflow efficiency.

## Ward 3, month 2 — verified

The hospital rule reduced quick returns to 54 (lower than today's 80) but increased last-minute call-ins to 58 (higher than 35). Only 1 nurse had 3+ quick returns, down from 9. Shift changes per sick call rose to 1.71 (higher than 1.0), and 47 nurses had shifts changed (higher than 31). The planner made no decisions, and GenAI explanations had a 57% pass rate. Quick returns in the original roster were high at 85, suggesting potential for improvement.

1. Quick returns in the original roster were high at 85, which may have contributed to the higher last-minute call-ins under the rule.
2. Nurses Nurse_15, Nurse_07, and Nurse_13 carried the most last-minute call-ins, suggesting a need to spread these more evenly.
3. The rule's shift changes per sick call were higher than today's software, indicating a trade-off between fairness and operational flexibility.

## Ward 4, month 1 — mismatch

The hospital rule reduced quick returns to 62 vs. 95, with no nurses having 3+ quick returns. It increased last-minute call-ins to 58 vs. 33 and shift changes per sick call to 1.83 vs. 1.03. The planner made no decisions, and no overrides were logged. GenAI explained 36 sick calls, with 69% passing fact checks.

1. Quick returns in the original roster were 100, suggesting the rule could reduce them further by adjusting the base roster.
2. Nurses Nurse_13, Nurse_30, and Nurse_68 each had 3 last-minute call-ins; spreading these could reduce load.
3. The rule increased shift changes per sick call by 83%, which may impact nurse workload and scheduling efficiency.

> Flagged: 83, 83%

## Ward 4, month 2 — mismatch

The hospital rule reduced quick returns to 44 vs. 96, with no nurses having 3+ quick returns. Last-minute call-ins increased to 75 vs. 40, and shift changes rose to 1.93 vs. 1.02. The planner made no decisions, and GenAI's explanations had a 64% pass rate. Quick returns in the original roster were high at 92, suggesting potential for improvement.

1. Quick returns in the original roster were high at 92, which may have contributed to the higher last-minute call-ins under the rule.
2. Nurses Nurse_57, Nurse_08, and Nurse_27 carried the most last-minute call-ins, suggesting a need to spread these more evenly.
3. The rule's approach led to more shift changes, which may require closer monitoring to ensure staff stability.

> Flagged: 96

## Ward 5, month 1 — verified

The hospital rule reduced quick returns to 58 vs. 89, with fewer nurses having 3+ quick returns (2 vs. 9). It increased last-minute call-ins to 63 vs. 36 and shift changes per sick call to 1.77 vs. 1.0, affecting 48 vs. 28 nurses. The planner made no decisions, and GenAI explained 40 sick calls, with 68% passing fact checks.

1. Quick returns in the original roster were 98, suggesting fixing these could reduce last-minute call-ins.
2. Nurse_08 had the most last-minute call-ins (3), and Nurse_01 and Nurse_03 each had 2; consider spreading these responsibilities.
3. The rule increased shift changes per sick call to 1.77, which may impact nurse workload and scheduling efficiency.

## Ward 5, month 2 — verified

The hospital rule reduced quick returns to 63 (lower than today's 97) and cut nurses with 3+ quick returns to 4 (lower than 13). It increased last-minute call-ins to 60 (higher than 38) and shift changes per sick call to 1.71 (higher than 1.05). The planner made no decisions, and no overrides were logged. GenAI explained 41 sick calls, with 68% passing fact checks.

1. Quick returns in the original roster were 96, suggesting fixing these could reduce last-minute call-ins.
2. Nurses Nurse_14, Nurse_19, and Nurse_23 each had 3 last-minute call-ins; spreading these could improve reliability.
3. The rule increased shift changes per sick call to 1.71, which may impact staff planning.
