## Item 1: accuracy accounting for E8 (each explanation counted once)

| Step | Count |
|---|---|
| Explanations | 400 |
| Passed the E8 fact check | 370 |
| - passed, but a nurse's role or direction is wrong | 26 |
| - passed, only error is a false 'load/burden' line | 63 |
| = passed, no known error | 281 |
| Flagged by the E8 check | 30 |
| - flagged and really wrong | 5 |
| = flagged but true | 25 |

(a) Fact-check pass rate (what the 95% gate measures): 370/400 = 92.5%.

(b) Estimated true accuracy, truth-based: (passed with no known error + flagged but true) / all = (281 + 25) / 400 = 76.5%. This is an upper bound: only known errors are subtracted, and 270 of the 'no known error' explanations were never read by a person (only checked by code and the two-nurse scan).

Strict version: also count every unverifiable 'load/burden' line as an error (load is not in the E8 facts): 0 / 400 = 0.0%.

Definitions: a 'load/burden' line is false when, among the nurses whose load rises, the most loaded one before the repair is more loaded in the rule's choice than in today's software's choice. Role errors come from the hand labels (3 flagged, 17 from the two-nurse scan, 1 from the 15-case audit) plus check v3's role check, whose every flag on these 400 was read and confirmed by hand.

The earlier '85-88%' was not computed step by step. It was a rough judgement from the 17 scan errors and the load line, and is withdrawn; the numbers above replace it.