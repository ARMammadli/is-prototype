# E7 — Monthly review reports (rules compute, GenAI writes, checker verifies)

Model: qwen3:8b. 10 reports (5 wards x 2 months).

| Valid output | Fact check passed | Median latency (s) |
|---|---|---|
| 10/10 | 9/10 | 6.6 |

The fact check verifies that every number is in the facts, that 'from X to Y' / 'X vs. Y' wording matches the direction of the numbers, and that named nurses carry their own numbers. It does not judge whether the discussion points are wise.

## Ward 1, month 1 — mismatch

The hospital rule reduced quick returns to 56 (lower than today's 96) but increased last-minute call-ins to 74 (higher than 42). Two nurses had 3+ quick returns, fewer than the 8 under today's software. The planner made no decisions, so no overrides were logged. GenAI's explanations were reliable, with 98% passing fact checks.

1. Quick returns in the original roster were 103, suggesting potential for reducing last-minute call-ins by adjusting the base roster.
2. Nurses Nurse_24, Nurse_30, and Nurse_06 each had 4 last-minute call-ins, indicating a need to spread these more evenly.
3. The rule increased shift changes per sick call to 1.81 (higher than 1.0), which may impact nurse workload consistency.

> Flagged: Nurse_06: ['4']

## Ward 1, month 2 — verified

The hospital rule reduced quick returns to 57 (lower than today's 81) but increased last-minute call-ins to 49 (higher). Only 1 nurse had 3+ quick returns, lower than today's 7. Shift changes per sick call rose to 1.82 (higher), affecting 34 nurses. The planner made no decisions, so no overrides were logged. GenAI explained 28 sick calls, with 96% passing fact checks.

1. Quick returns in the original roster were high at 86; consider reducing these in next month's base roster to lower last-minute call-ins.
2. Nurses Nurse_31, Nurse_56, and Nurse_59 each had 3 last-minute call-ins; consider spreading these more evenly across the team.
3. The rule increased shift changes per sick call to 1.82, which may impact nurse workload; monitor if this affects shift stability.

## Ward 2, month 1 — verified

The hospital rule reduced quick returns to 62 vs. 97, with fewer nurses having 3+ quick returns (4 vs. 13). It increased last-minute call-ins to 63 vs. 38 and shift changes per sick call to 1.73 vs. 1.02. The planner made no decisions, applying the rule's top choice. GenAI explanations passed fact checks at 95%, with 2 flagged for review.

1. Quick returns in the original roster were high at 94, suggesting next month's base roster should address these to reduce last-minute call-ins.
2. Nurses 45, 49, and 50 each had 3 last-minute call-ins; consider spreading these across more staff to reduce individual burdens.
3. The rule's higher shift changes per sick call (1.73) compared to today's software (1.02) may require closer monitoring for operational impact.

## Ward 2, month 2 — verified

The hospital rule reduced quick returns to 56 (lower than today's 94) and eliminated nurses with 3+ quick returns. It increased last-minute call-ins to 60 (higher than today's 34) and shift changes per sick call to 1.9 (higher than today's 1.05). The planner made no decisions, so no overrides were logged. GenAI explanations passed fact checks for 39 out of 41 sick calls (95% pass rate).

1. Quick returns in the original roster were 96, suggesting next month's base roster could reduce last-minute call-ins by fixing these.
2. Nurse_59 had the most last-minute call-ins (3), and Nurse_02 and Nurse_05 each had 2—consider spreading these across more nurses.
3. The rule's shift changes per sick call were higher than today's software, which may impact nurse workload consistency.

## Ward 3, month 1 — verified

The hospital rule reduced quick returns to 63 vs. 97, with fewer nurses having 3+ quick returns (3 vs. 11). It increased last-minute call-ins to 59 vs. 33 and shift changes per sick call to 1.86 vs. 1.03. The planner made no decisions, applying the rule's top choice. GenAI explanations were fully verified, with 100% pass rate.

1. Quick returns in the original roster were high (98), suggesting next month's base roster should address these to reduce last-minute call-ins.
2. Nurses Nurse_02, Nurse_12, and Nurse_46 each had 3 last-minute call-ins; spreading these could improve reliability.
3. The rule's higher shift changes per sick call (1.86) may require closer monitoring to ensure operational efficiency.

## Ward 3, month 2 — verified

The hospital rule reduced quick returns to 54 (lower than today's 80) but increased last-minute call-ins to 58 (higher than 35). Only 1 nurse had 3+ quick returns, down from 9. Shift changes per sick call rose to 1.71 (higher than 1.0). The planner made no decisions, so no overrides were logged. GenAI explanations passed fact checks at 93%.

1. Quick returns in the original roster were high at 85; consider reducing these in next month's base roster to lower last-minute call-ins.
2. Nurse_15 had the most last-minute call-ins (3), suggesting a need to spread these more evenly across the team.
3. The rule increased shift changes per sick call to 1.71, which may impact nurse workload and should be monitored.

## Ward 4, month 1 — verified

The hospital rule reduced quick returns to 62 vs. 95, with no nurses having 3+ quick returns. It increased last-minute call-ins to 58 vs. 33 and shift changes per sick call to 1.83 vs. 1.03. The planner made no decisions, applying the rule's top choice. GenAI explanations were fully verified, with 100% pass rate.

1. Quick returns in the original roster were 100%, suggesting a need to adjust next month's base roster to reduce last-minute call-ins.
2. Nurses Nurse_13, Nurse_30, and Nurse_68 each had 3 last-minute call-ins, indicating a need to spread these responsibilities.
3. The rule's higher shift changes per sick call (1.83) compared to today's software (1.03) may require further review for efficiency.

## Ward 4, month 2 — verified

The hospital rule reduced quick returns to 44 (lower than today's 86) and eliminated nurses with 3+ quick returns. It increased last-minute call-ins to 75 (higher than 40) and shift changes per sick call to 1.93 (higher than 1.02). The planner made no decisions, so no overrides were logged. GenAI's explanations were reliable, with 95% passing fact checks.

1. Quick returns in the original roster were high at 92; consider reducing these in next month's base roster to lower last-minute call-ins.
2. Nurses 57, 08, and 27 carried the most last-minute call-ins; consider spreading these more evenly across the team.
3. The rule increased shift changes per sick call, which may impact staff workload; monitor for consistency.

## Ward 5, month 1 — verified

The hospital rule reduced quick returns to 58 vs. 89, with fewer nurses having 3+ quick returns (2 vs. 9). However, it increased last-minute call-ins to 63 vs. 36 and shift changes per sick call to 1.77 vs. 1.0. The planner made no decisions, and GenAI explanations were fully verified with a 100% pass rate. Quick returns in the original roster were very high at 98, suggesting potential for improvement.

1. Fix high quick returns in the original roster (98) to reduce last-minute call-ins.
2. Nurse_08 had the most last-minute call-ins (3), suggesting a need to spread these more evenly.
3. The rule increased shift changes per sick call, which may impact nurse workload.

## Ward 5, month 2 — verified

The hospital rule reduced quick returns to 63 vs. 97, with fewer nurses having 3+ quick returns (4 vs. 13). It increased last-minute call-ins to 60 vs. 38 and shift changes per sick call to 1.71 vs. 1.05. The planner made no decisions, applying the rule's top choice. GenAI explanations passed fact checks for 93% of sick calls.

1. Quick returns in the original roster were high (96), suggesting next month's base roster should address these to reduce last-minute call-ins.
2. Nurses Nurse_14, Nurse_19, and Nurse_23 each had 3 last-minute call-ins; consider spreading these across more staff.
3. The rule's shift changes per sick call (1.71) were higher than today's software (1.05), indicating potential for further optimization.
