# E9: follow-up on the explanation evaluation

Same 400 arm-B decisions (seeds 0-4) and the same 10 ward-months throughout. No threshold, seed, ward
parameter or the 95% gate was changed. Model: qwen3:8b via Ollama, temperature 0. The 400 decisions are the
same ones the checks were built on, so every pass rate below is an in-sample number. Code:
`evaluation/e9_followup.py`, `llm/factblock.py`, `llm/monthly.py`. Per-item files: `results/e9_item*.md`.

## 1. Accuracy accounting for E8 (rule writes facts, GenAI writes wording)

Each explanation is counted once (labels: `results/e9_accounting_labels.csv`).

| Step | Count |
|---|---|
| Explanations | 400 |
| Passed the E8 fact check | 370 |
| minus: passed, but a nurse's role or direction is wrong | 26 |
| minus: passed, only error is a false "load/burden" line | 63 |
| = passed, no known error | 281 |
| Flagged by the E8 check | 30 |
| minus: flagged and really wrong | 5 |
| = flagged but true | 25 |

- (a) Fact-check pass rate (what the 95% gate measures): 370 / 400 = **92.5%**.
- (b) Estimated true accuracy (truth-based): (281 + 25) / 400 = **76.5%**.
  - This is an upper bound. Only known errors are subtracted, and 270 of the 281 "no known error" explanations were never read by a person.
  - The 26 role errors are: 17 from the two-nurse scan, 1 from the 15-case hand audit, and 8 found later by check v3's role check (each read and confirmed).
- Strict version: count every "load/burden" line as an error, because load was not in the E8 facts. Every one of the 400 framings has such a line, so strict accuracy is **0%**.
- A "load/burden" line is **false** when, among the nurses whose load rises, the most loaded one before the repair is more loaded in the rule's choice than in today's software's choice.
- The earlier "85-88%" was **not** computed step by step. It was a rough judgement and is withdrawn.

## 2. Check v3 (changed in both directions), E8 outputs rescored

Prompt, model and temperature (0) are unchanged. So the saved 400 outputs were rescored instead of regenerated; regenerating would give the same text.

What changed in the check (everything else is unchanged):
1. **Narrow exemption.** The old up/down wording check no longer flags a relief word ("spared", "relieved", ...) about a nurse whom today's software's choice loads more than the rule's choice does.
2. **New role check.** This covers sentences naming two or more nurses, which the old check skipped:
   - each named nurse's role (takes on work / relieved or spared / no extra) must match the rule's facts for that nurse;
   - where an item is named, the check uses that item ("more night shifts" needs night shifts to rise);
   - "spared from change" about a nurse whose shift changes is an error;
   - a nurse who appears only in today's software's choice may not be described as taking on work in the rule's choice;
   - clauses with "today's software", "would" or "instead of" are judged against today's software's choice.
3. **New load check.** Any sentence about load, burden, overload, "those with the most", spreading or fairness is flagged unless a fact sentence states a load comparison that favours the rule. The policy name itself ("the fairness policy") is not a claim.

Agreement with the hand-labelled cases (role part): check v3 catches **20 of 20** known-wrong cases and passes **41 of 41** known-true cases. This is in-sample: check bugs were fixed while looking at these same cases and at the flags on the 400, so it is not an independent validation.

| | E8 check | Check v3 |
|---|---|---|
| Pass rate on E8 outputs | 92.5% | **0.0%** |
| Without the new load check | | 93.0% |
| Role errors (new) | | 7.0% |
| Load claim not backed by a fact (new) | | 100% |

Every E8 framing ends with a load/fairness line, and the E8 facts contain no load, so nothing passes. No new audit of passing cases was possible, because none pass.

## 3. Fixing the policy line at the source: the rule adds a load fact

**Choice: the rule adds load facts.** For every nurse named, the rule states the load score before the repair (the rule's weighted count). For each option, it names the most loaded nurse before the repair among those whose load rises, and says whether the rule's choice puts the extra load on a less loaded, a more loaded or an equally loaded nurse than today's software's choice.

Why this option:
- The manager's policy is about load ("do not add load to the nurses who already carry the most").
- Only a load fact makes a policy-fit claim checkable.
- Simply banning claims would leave GenAI with nothing beyond what the template in item 4 already says.

The prompt gained one rule: claim policy fit on load only when the fact says "a less loaded nurse".

Decided before the run:
- Ties count as "equal", and any load claim there is flagged.
- In the 29 same-pick cases there is no comparison, so any load claim there is flagged.
- When the fact is unfavourable, a sentence may repeat the fact's direction ("more loaded", "same load") if it claims no policy fit.

The new fact block alone passes the frozen check in 400 of 400 decisions. The prompt and check were frozen before this single run, and nothing was tuned afterwards.

| | E8 (E8 check) | Load fact (check v3) |
|---|---|---|
| Fact-check pass | 92.5% | **32.5%** (130/400) |
| Same pick as today's software | 100% | 0% |
| Different pick | 91.9% | 35.0% |
| Load fact favours the rule (200 cases) | | 65% |
| Load fact equal / unfavourable / same pick (200 cases) | | 0% |
| Role errors | 7.0% (under v3) | 21.8% |
| Load claim not backed by a fact | 100% (under v3) | 49.5% |
| Seconds per explanation | 1.7 | 2.0 |
| Same outputs scored with the old E8 check | | 98.2% |

What happened:
- **The model ignored the load rule.** In the 200 cases where the load fact does not favour the rule, it still claimed policy fit on load 97-100% of the time.
- **Direction errors went up.** Role errors rose from 9% to 35% in the favourable cases, mostly "takes on more quick returns" for a nurse whose quick returns fall.
- **The old check would have missed nearly all of this:** it passes 98.2% of these outputs.

Hand checks:
- 15 passing explanations (RNG seed 2, different-pick cases): **0 of 15 contain an error**. Several leave out that the relieved nurse also takes a call-in; that is incomplete, not false.
- 20 random flagged explanations (RNG seed 3): **20 of 20 are real errors**.

Estimated true accuracy, using the same standard as item 1 (wrong = a wrong role or direction, or a false load line; an unbacked but true load line is not counted): at most **63.5%**, down from 76.5% for E8.

Under the stricter "every load claim must be backed" standard used by check v3 and by the 20-case read, it is about 32.5%. If up to 20% of the passing ones were wrong and up to 15% of the flagged ones were true (the limits our small reads allow), the range is roughly 26% to 43%.

Summary across designs, one standard each:

| Design | Original (E8) check | Check v3 | True accuracy, item-1 standard (upper bound) |
|---|---|---|---|
| E8: rule writes facts, GenAI wording | 92.5% | 0% | 76.5% |
| Item 3: plus load facts | 98.2% | 32.5% | 63.5% |
| Item 4: template, no GenAI | 100% | 100% | 100% |

Limitation of the load fact: "equal" covers 99 cases, often where the same nurse gains load in both options, so it hides real differences. In example (1,50) below, today's software would also give Nurse_10 a quick return. The fact sentence also reads awkwardly when nobody's load rises.

## 4. Template only (no GenAI)

A deterministic template built from the rule's facts. For each nurse in the rule's choice it says what the nurse avoids and takes on. It then says what today's software's choice would do instead and how many nurses each option changes. It uses no numbers except the change counts.

- Pass rate under check v3, with the load fact: **100% (400/400)**.
  - The first version scored 99.8%. Its one failure was a false positive in the existing today's-software check: night shifts net to zero across two nurses, but the per-nurse sentence was true.
  - The contrast sentence was then made complete (it also states the relief); the checker was not changed.
- Time: about **0.02 ms** per explanation to render the facts and template (the check is not timed), against 1.7-2.0 s for GenAI.

Three random different-pick cases (RNG seed 4, pool of 371):

**Case (0,58)**
- **Rule facts:** Nurse_60: quick returns from 4 to 3; Nurse_69: no count changes. Today's software: call in Nurse_23 (no count changes). 2 vs 1 nurses changed. Load: nobody's load rises in either choice ("equal").
- **Template:** "Nurse_60 avoids a quick return. Nurse_69's counts do not change. With today's software's choice, Nurse_23 would instead have no count changes. Nurses changed: 2 with the rule's choice, 1 with today's software's."
- **GenAI (item 3):** "The rule's choice moves Nurse 60 to a lighter load and keeps Nurse 69 unaffected. This fits the policy by avoiding extra load on already burdened nurses." **Flagged:** load claim not backed.

**Case (1,50)**
- **Rule facts:** Nurse_12: quick returns from 1 to 0, call-ins from 0 to 1; Nurse_10: call-ins from 0 to 1. Today's software: Nurse_10 gets a quick return and a call-in. 2 vs 1 nurses changed. Load: equal (Nurse_10 gains in both).
- **Template:** "Nurse_12 avoids a quick return and takes on a last-minute call-in. Nurse_10 takes on a last-minute call-in. With today's software's choice, Nurse_10 would instead take on a quick return and a last-minute call-in. Nurses changed: 2 with the rule's choice, 1 with today's software's."
- **GenAI (item 3):** "Nurse_12 is relieved of quick returns. Nurse_10 takes on a last-minute call-in. The rule's choice fits the policy by avoiding adding load to already loaded nurses." **Flagged:** load claim not backed.

**Case (2,5)**
- **Rule facts:** Nurse_12: quick returns from 4 to 3, nights from 4 to 3, call-ins from 0 to 1; Nurse_14: nights from 2 to 3, call-ins from 0 to 1. Today's software: Nurse_60 gets a call-in. 2 vs 1 nurses changed. Load: the rule loads a less loaded nurse (5 vs 11).
- **Template:** "Nurse_12 avoids a quick return and a night shift and takes on a last-minute call-in. Nurse_14 takes on a night shift and a last-minute call-in. With today's software's choice, Nurse_60 would instead take on a last-minute call-in. Nurses changed: 2 with the rule's choice, 1 with today's software's."
- **GenAI (item 3):** "Nurse_12 and Nurse_14 take on extra work. The rule's choice puts the extra load on a less loaded nurse than today's software's choice." **Passes** the check, but is misleading: Nurse_12 is relieved overall.

**What GenAI wording adds over the template.** On this evidence, very little:
- The template is complete, always correct under the check, and instant.
- GenAI's text is shorter and sounds more natural. But it leaves facts out, often adds a policy claim the facts do not support, and reverses directions in a fifth of cases.
- The only thing GenAI adds is a sentence linking the choice to the manager's policy. That sentence is reliable only when the rule itself states the load comparison, at which point the template could state it too.

## 5. Monthly report: rule writes every number, GenAI writes the words

The 10 ward-months use the exact facts saved from the E7 run. The rule renders every number as fixed sentences, and these alone pass the unchanged check in 10 of 10. GenAI writes the summary and 3 discussion points with no numbers. The unchanged report check runs on facts plus words, plus the check for numbers and nurse codes not in the facts.

| | Before (E7, GenAI writes numbers) | After (rule writes numbers) |
|---|---|---|
| Fact-check pass | 7/10 | **9/10** |
| Median seconds per report | 7.0 | 4.8 |

Hand read of all 10 "after" reports:
- **4 of the 9 passing reports contain a false or misleading claim** that the check cannot see, because it has no numbers:
  - W3M1 says the rule "may have been effective in minimizing last-minute call-ins" (they rose).
  - W4M1 says it "eliminated all quick returns already in the original roster" (invented).
  - W5M2 says quick returns were "concentrated among fewer staff".
  - W2M2 says the rule "may have avoided additional call-ins".
- **The 1 flagged report is actually correct.** It says "half passing", and the facts say 50%: a false positive of the number-word check.
- Correct after the split: **6/10**. Before: 2/10 if the planner misstatement counts, 7/10 if not; so on the lenient count, correctness went from 7/10 to 6/10.

Hand read of the 7 "before" passes, for comparison:
- All numbers are correct.
- 5 of the 7 say "the planner made no decisions", while the facts say only that none were logged. That is a misstatement.
- Correct before: 2/10 if that misstatement counts, 7/10 if it does not.

Ten reports are too few for conclusions. The split removes number errors, but the model then makes vaguer, sometimes false, qualitative claims.

## 6. Small fixes

- **GenAI-chooser arm (arm C, qwen3:8b chose the repair).** Taken from git history (commit c3385cf). It ran on the same 5 seeds, with base rosters and sick calls identical to the ORTEC-like arm, and its A rows match the current run exactly. Mean of 5 wards, with wards better than ORTEC-like in brackets:
  - quick returns 120.0 (5/5);
  - nurses with 3+ quick returns 10.0 (5/5);
  - max quick returns 5.0 (4/5, 1 tie);
  - unfilled shifts 1.0 (better in 1 ward, equal in 4);
  - short-notice changes 137.0 (0/5);
  - changes per repair 1.97;
  - Gini of short-notice changes 0.343 (5/5).
- **Unfilled shifts** wording is now "equal in 5 of 5" for the rule.
- **200-ward robustness run (E1).** All 200 wards × 2 policies were re-run with the current rule (squared score on, `policy.json`), and all 400 rows match the saved E1 results exactly. It used the same squared-score rule.

## 7. Quick returns created by repairs vs already in the base roster (E2 robustness runs, 50 wards per row)

| Absence | Policy | Quick returns | Kept from base roster | Created by repairs | Share created by repairs |
|---|---|---|---|---|---|
| 3% | ORTEC-like | 182.1 | 175.7 | 6.4 | 3.5% |
| 3% | Rule | 142.7 | 142.3 | 0.4 | 0.3% |
| 8% | ORTEC-like | 173.9 | 158.7 | 15.1 | 8.7% |
| 8% | Rule | 87.3 | 86.2 | 1.0 | 1.2% |

Quick returns total = kept + created in every row.
- At both absence rates, almost all remaining quick returns were already in the base roster.
- The ORTEC-like logic creates more of them as absence rises.
- The rule's gain grows with absence (−22% at 3%, −50% at 8%), because more sick calls give it more chances to move nurses out of base-roster quick returns.

## Not yet in the app

- The app's explanation badge still uses the E8 check, not check v3.
- The monthly endpoint still uses the first-version report, where GenAI writes the numbers.
- Wiring either in is a team decision. With check v3, the badge would show "mismatch" on almost every current explanation.
