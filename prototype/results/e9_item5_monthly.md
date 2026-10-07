## Item 5: monthly report, rule writes every number, GenAI writes the words

Same 10 ward-months and identical facts as E7. Before (E7): 7/10 passed. After: 9/10 passed. Median time 4.8 s.

### Ward 1, month 1: verified (E7: mismatch)

The rule reduced quick returns for heavily exposed nurses and achieved fewer quick returns overall. It increased last-minute call-ins and shift changes. The planner had no decisions logged. GenAI explanations were mostly accurate, with some flagged for review.

1. Quick returns already in the original roster should be fixed in next month's base roster to reduce last-minute call-ins.
2. Nurses with many last-minute call-ins, such as Nurse_24 and Nurse_30, should have their call-ins spread across shifts.
3. The rule's impact on shift changes needs further analysis to understand its effect on workflow.

### Ward 1, month 2: mismatch (E7: verified)

The rule reduced quick returns for heavily exposed nurses and achieved fewer quick returns overall. It increased last-minute call-ins and shift changes. The planner had no decisions logged. GenAI's explanations were partially reliable, with half passing fact checks.

1. Quick returns already in the original roster suggest fewer last-minute call-ins are needed next month.
2. Nurses Nurse_31, Nurse_56, and Nurse_59 carried the most last-minute call-ins; consider spreading these across more staff.
3. The rule's impact on shift changes and call-ins highlights the need for further review of its fairness formula.

> Flagged: number not in fact block: 'half'

### Ward 2, month 1: verified (E7: verified)

The hospital rule reduced quick returns for nurses and minimized the number of nurses with multiple quick returns. It increased last-minute call-ins and shift changes. The planner had no decisions logged, so its behavior is unknown. GenAI provided explanations, but some were flagged as unreliable.

1. Quick returns already in the original roster suggest fewer last-minute call-ins are needed next month.
2. Nurses Nurse_45, Nurse_49, and Nurse_50 carried the most last-minute call-ins; consider spreading these across more staff.
3. The rule's impact on shift changes and call-ins highlights a trade-off between fairness and operational stability.

### Ward 2, month 2: verified (E7: verified)

The rule reduced quick returns for nurses and eliminated quick returns entirely for some, but increased last-minute call-ins and shift changes. The planner had no logged decisions, so its behavior remains unknown. GenAI provided explanations for all sick calls, with most passing fact checks.

1. Quick returns already in the original roster suggest the rule may have avoided additional call-ins; consider fixing these in next month's base roster.
2. Nurses Nurse_59, Nurse_02, and Nurse_05 carried the most last-minute call-ins; consider spreading these across more staff.
3. The rule's higher shift changes and call-ins indicate a trade-off between quick returns and operational stability.

### Ward 3, month 1: verified (E7: verified)

The hospital rule reduced quick returns for heavily exposed nurses and achieved fewer quick returns overall. It increased last-minute call-ins and shift changes. The planner had no decisions logged, so its behavior is unknown. GenAI's explanations were mostly accurate, with a pass rate of 74%.

1. Quick returns already in the original roster suggest the rule may have been effective in minimizing last-minute call-ins. Fixing these in next month's base roster could reduce the need for call-ins.
2. Nurses with multiple last-minute call-ins should have their shifts redistributed to spread the workload more evenly.
3. The rule's impact on shift changes and call-ins indicates a trade-off between fairness and operational stability, which should be reviewed for future adjustments.

### Ward 3, month 2: verified (E7: verified)

The hospital rule reduced quick returns for heavily exposed nurses and achieved fewer quick returns overall. It increased last-minute call-ins and shift changes. The planner had no decisions logged, so its behavior is unknown. GenAI's explanations had a pass rate of 60%.

1. Quick returns already in the original roster suggest fewer last-minute call-ins are needed next month.
2. Nurse_15, Nurse_07, and Nurse_13 carried the most last-minute call-ins; consider spreading these across more nurses.
3. The rule's impact on shift changes and call-ins should be reviewed for balance with quick returns.

### Ward 4, month 1: verified (E7: mismatch)

The rule reduced quick returns for nurses and eliminated all quick returns already in the original roster. It increased last-minute call-ins and shift changes. The planner had no decisions logged. GenAI explanations had a pass rate of 72%.

1. Quick returns were already fully covered in the original roster, so next month's base roster should include these to reduce last-minute call-ins.
2. Nurses Nurse_13, Nurse_30, and Nurse_68 had the most last-minute call-ins; these should be spread across more nurses.
3. The rule's impact on shift changes and call-ins needs further review to balance fairness and operational stability.

### Ward 4, month 2: verified (E7: mismatch)

The rule reduced quick returns for nurses and eliminated quick returns for those with 3 or more. It increased last-minute call-ins and shift changes. The planner had no decisions logged. GenAI explanations had a pass rate of 55%.

1. Quick returns already in the original roster this month were high, so next month's base roster should address these to reduce last-minute call-ins.
2. Nurses Nurse_57, Nurse_08, and Nurse_27 carried the most last-minute call-ins, so their load should be spread across more nurses.
3. The rule's impact on shift changes and call-ins suggests a need to balance fairness with operational stability.

### Ward 5, month 1: verified (E7: verified)

The rule reduced quick returns for heavily exposed nurses and achieved fewer quick returns overall. It increased last-minute call-ins and shift changes. The planner had no decisions logged. GenAI explanations had a pass rate of 60%.

1. Quick returns already in the original roster are high; consider fixing them in next month's base roster to reduce last-minute call-ins.
2. Nurses Nurse_08, Nurse_01, and Nurse_03 carry most last-minute call-ins; consider spreading these across more staff.
3. The rule's impact on shift changes and call-ins suggests a need to balance fairness with operational stability.

### Ward 5, month 2: verified (E7: verified)

The rule reduced quick returns for nurses and concentrated them among fewer staff, but increased last-minute call-ins and shift changes. The planner had no decisions logged, so its role remains unclear. GenAI provided explanations, but only two-thirds passed fact checks.

1. Quick returns were already high in the original roster, so next month's base roster should address this to reduce call-ins.
2. Nurses Nurse_14, Nurse_19, and Nurse_23 carried the most last-minute call-ins; their load should be spread across more staff.
3. The rule's impact on shift changes suggests a need to review how it balances workload across the team.
