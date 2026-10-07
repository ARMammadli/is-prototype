# E8 manual reads and scans

Superseded counts: the E9 labels (results/e9_accounting_labels.csv, results/e9_summary.md) put the real errors among the 30 flagged at 3 of 30, not about 4. They also add 8 passing errors found by check v3's role check.

## Manual reads

**15 passing explanations** (fixed random draw, seed 0, from cases where the rule and today's software pick differently: (0,29) (1,8) (1,55) (1,78) (2,10) (2,22) (2,53) (2,74) (3,6) (3,14) (3,50) (3,54) (3,64) (3,67) (4,26)), each read against the full payload:
- Judged by truth against the payload: 1 of 15 contains an error: (3,14) "relieving Nurse_01's absence impact" is a confused phrase (Nurse_01 is the absent nurse) that the facts do not support. Under E6 v2, 7 of 15 had errors.
- Judged by the spec rule (no comparison that is not in the fact block): 15 of 15 break it, because every one says the choice avoids load on "already burdened" nurses, and load is not in the fact block.
- 0 of 15 have a wrong number, a wrong direction or an invented comparison.
- In 15 of 15, the policy sentence is generic ("fits the policy by avoiding extra load on already burdened nurses"). It was true in every case, checked against the load before. But the fact block does not show load, so the planner cannot verify it from the text.
- In 9 of 15, the relieved nurse also gets a last-minute call-in that the framing leaves out. That call-in is stated in the fact block directly above, so the framing is incomplete, not false.

**All 30 flagged explanations:**
- About 4 of 30 contain a real error:
  - (0,2): Nurse_04 is "spared from change" but is called in;
  - (0,9): the same pattern;
  - (1,46): night shifts reversed between two nurses. The heuristic skips sentences with two nurses, so this item failed only on another flag;
  - (4,15): "Nurse_70 who has fewer quick returns" is invented.
- About 26 of 30 are true statements that the unchanged heuristic flags: "Nurse_X is spared", where Nurse_X is the nurse today's software would have called in. Nurse_X's numbers rise only in the other option. The check was not relaxed, so these still count as failures.

Across all 400, 167 framings end with the same sentence: "This fits the policy by avoiding extra load on already burdened nurses". Another 84 use a near-copy.

## Scan 1: passing framings the check cannot test for direction

The nurse up/down check skips any sentence that names 2+ nurses. 229 of the 370 passing framings have such a sentence. A rough model-free scan split those sentences at commas, "while" and "and", and compared each part with the rule's choice. Every hit was then read by hand:
- 17 passing framings contain a real error, so at least 4.6% of passing framings are wrong in a way the check misses. This is a lower bound, because the scan is rough.
- 15 of the 17 name the nurse that today's software would have called in as taking on work in the rule's choice. For example, (1,42): "Nurse_08 takes on more", but Nurse_08 is only in today's software's choice.
- 2 of the 17 reverse a direction: (0,42) "Nurse_28 handles fewer call-ins" when the count goes from 0 to 1; (1,30) "Nurse_57 takes on extra night shifts" when the count goes from 5 to 4.
- Cases: (0,42) (0,61) (1,20) (1,30) (1,32) (1,42) (1,79) (2,17) (2,42) (2,64) (3,30) (3,68) (3,81) (4,8) (4,12) (4,14) (4,53).

## Scan 2: is the "already burdened nurses" sentence true?

362 differ-case framings use a "burdened / those with the most" policy sentence. In 61 of them (17%), the nurse gaining load in the rule's choice started with more load than the nurse in today's software's choice. That makes the sentence false. 59 of those 61 pass the fact check.

## Why most failures happen
The prompt asks who is "relieved or spared". The model then writes "Nurse_X is spared" about today's software's nurse, which is true, but the unchanged heuristic flags it. Rewording the prompt and rerunning on these same 400 decisions would tune the prompt to the check on the test set. Any new prompt should be evaluated on fresh seeds (for example 5-9).
