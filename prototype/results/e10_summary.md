# E10: GenAI restates the rule's facts only; flagged summaries are hidden

Valid output: 100.0%. Coverage (GenAI summary shown): 383/400 = 95.8% (same pick as today's software: 100.0%; different pick: 95.4%). Seconds per explanation: 1.6.

| Flag type (share of valid summaries) | Share |
|---|---|
| Role check (two-nurse sentences included) | 4.2% |
| Old up/down wording, after the 'spared' exemption | 1.0% |
| Unbacked load / fairness / policy claim | 0.0% |
| Numbers, from-to, today's software or cost, not in fact block | 0.0% |

Hand-read sample (RNG seed 5, 20 of the shown summaries): [(0, 14), (0, 27), (0, 58), (1, 1), (1, 50), (1, 51), (1, 54), (2, 28), (2, 36), (2, 41), (3, 10), (3, 12), (3, 48), (3, 55), (4, 13), (4, 27), (4, 28), (4, 51), (4, 76), (4, 77)]
## Independent hand read of 20 shown summaries

Check v3 was tuned on the 61 hand-labelled E8 cases. This read is the independent check: 20 summaries drawn at random (RNG seed 5, fixed before the run) from the 383 shown, each read against the rule's facts.

- **Substantive errors: 2 of 20.**
  - (0,27) says Nurse_13 comes in "with 1 last-minute call-in"; Nurse_13's call-ins go from 1 to 2.
  - (1,1) "Nurse_07 takes 1 hour of last-minute call-ins": the hour is invented.
- **Imprecise wording: 8 of 20.** They say a nurse is "moved" when the facts say the nurse is called in: (0,58) (1,50) (1,54) (3,48) (3,55) (4,13) (4,28) (4,77). For a planner this matters, because a call-in is a last-minute change from a day off.
- **Strict count (any error): 10 of 20 contain an error.** Substantive only: 2 of 20.
- **Content.**
  - 0 of the 383 shown summaries mention quick returns, and only 2 mention anyone being relieved.
  - 323 of 383 use "moves". The summaries mostly paraphrase the option description ("moves Nurse X to day shift, calls in Nurse Y") that the planner already sees.
  - 24 of 383 contain digits despite the instruction. The check allows them because the numbers are in the facts.

## Hand-read breakdown after the vocabulary fix (same 20 summaries, no rerun)

- **Factual errors: 2.**
  - (0,27) "with 1 last-minute call-in": the count goes from 1 to 2.
  - (1,1) "1 hour" of call-ins: invented.
- **Wording errors: 8.** Each says a nurse is "moved" when the facts say the nurse is called in: (0,58) (1,50) (1,54) (3,48) (3,55) (4,13) (4,28) (4,77). **None of the 8 is actually correct.** Each fact block's description line says "call in".
- **Any error: 10 of 20.**
- The old fact label called every change made with less than 48 hours' notice a "last-minute call-in", including moves (271 of 400 fact blocks). That may explain 5 of the 8, but the summary shown to the planner was still wrong.
- An earlier version of this note counted only "5 of 20 GenAI errors" by removing those 5. That figure is withdrawn.
