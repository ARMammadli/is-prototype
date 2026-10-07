# E10 monthly: rule's table + GenAI narrative (restate only)

Fact check passed: 10/10. Median seconds: 6.0.

## Ward 1, month 1: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had 53 sick calls. The planner note indicates no decisions were logged. A GenAI row shows some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 56 compared to 96.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 74 compared to 42.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.81 compared to 1.

## Ward 1, month 2: verified

The table shows the simulated month for Ward 1, with the hospital rule's numbers lower than today's software for quick returns and nurses with 3 or more quick returns. Last-minute call-ins and shift changes are higher. The planner note is empty. GenAI explanations for 14 of 28 sick calls were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 57 compared to 81.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 49 compared to 27.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.82 compared to 1.

## Ward 2, month 1: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had no planner decisions logged. The GenAI row indicates that 70% of explanations passed the fact check. The planner note is empty.

1. Quick returns: The hospital rule's number is lower than today's software, with 62 quick returns compared to 97.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 63 call-ins compared to 38.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.73 changes compared to 1.02.

## Ward 2, month 2: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had 41 sick calls. The planner note states no decisions were logged. A GenAI row indicates some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 56 quick returns compared to 94.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 60 call-ins compared to 34.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.9 changes compared to 1.05.

## Ward 3, month 1: verified

The table shows that for the simulated month, the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The planner note indicates no decisions were made. The GenAI row shows some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 3 nurses having 3 or more quick returns.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with Nurse_02, Nurse_12, and Nurse_46 having the most.
3. Shift changes: The hospital rule's number is higher than today's software, with 43 nurses having shifts that changed.

## Ward 3, month 2: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had 45 sick calls. The planner note states no decisions were logged. A GenAI row indicates some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 54 compared to 80.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 58 compared to 35.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.71 compared to 1.

## Ward 4, month 1: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had no planner decisions logged. The GenAI row indicates that 26 of 36 explanations passed the fact check. The planner note is empty.

1. Quick returns: The hospital rule's number is lower than today's software, with 62 compared to 95.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 58 compared to 33.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.83 compared to 1.03.

## Ward 4, month 2: verified

The table shows that for the simulated month, the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. There were no quick returns already in the original roster. The planner note indicates no decisions were logged. Some explanations in the GenAI row were flagged as passing the fact check.

1. Quick returns: The hospital rule's number is lower than today's software, with 44 quick returns compared to 86.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 75 call-ins compared to 40.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.93 changes compared to 1.02.

## Ward 5, month 1: verified

The table shows that the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The simulated month had 40 sick calls. The planner note states no decisions were logged. A GenAI row indicates some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 58 compared to 89.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 63 compared to 36.
3. Nurses whose shifts changed: The hospital rule's number is higher than today's software, with 48 compared to 28.

## Ward 5, month 2: verified

The table shows that for the simulated 4-week month, the hospital rule's number is lower for quick returns and nurses with 3 or more quick returns, but higher for last-minute call-ins and shift changes. The planner note indicates no decisions were logged for this month. The GenAI row shows some explanations were flagged.

1. Quick returns: The hospital rule's number is lower than today's software, with 63 quick returns compared to 97.
2. Last-minute call-ins: The hospital rule's number is higher than today's software, with 60 call-ins compared to 38.
3. Shift changes per sick call: The hospital rule's number is higher than today's software, with 1.71 changes compared to 1.05.

## Hand read of all 10

- Correct: W1M1, W2M2, W3M2, W5M1, W5M2 (5).
- Errors:
  - W1M2, W2M1, W4M1 say "the planner note is empty"; the note says no decisions were logged. W2M1 contradicts its own previous sentence.
  - W4M2 says "there were no quick returns already in the original roster"; there were 92. It also says explanations were "flagged as passing".
  - W3M1 says "no decisions were made"; the note says none were logged. This is the same slip as in E7.
- **Correct: 5 of 10 strictly, 6 of 10 if the W3M1 slip is not counted.** The check passed 10 of 10, so it misses all of these.
- The model wrote numbers in every report despite the instruction. The check allows them because they come from the table.
- The "discussion points" restate table rows ("Quick returns: lower, 56 compared to 96") instead of raising points for the meeting.
