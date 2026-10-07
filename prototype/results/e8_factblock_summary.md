# E8: rule writes the facts, GenAI writes the wording

Same 400 arm-B decisions as E6 (seeds 0-4), model qwen3:8b. The E6 fact check is unchanged and runs on the displayed text (fact block + framing); a new check also flags any number or nurse code in the framing that is not in the fact block. The fact block alone passes the E6 check in 400 of 400 decisions (gate run before any model call). The framing has no claims list, so the claims part of the E6 check is trivially clean here.

| | E6 v2 (GenAI writes facts + wording) | E8 (rule writes facts, GenAI wording) |
|---|---|---|
| Valid output | 100.0% | 100.0% |
| Fact-check pass | 66.2% | 92.5% |
| Pass, same pick as today's software | 93% | 100.0% |
| Pass, different pick | 64% | 91.9% |
| Seconds per explanation | 11.3 | 1.7 |

Share of valid explanations with each error type (one explanation can have several):

| Error type | E8 |
|---|---|
| Number not in the data | 0.0% |
| 'from X to Y' direction | 0.0% |
| Nurse up/down wording | 7.5% |
| Today's software / cost / unknown nurse | 0.0% |
| Number or nurse not in fact block (new) | 0.0% |

Pilot gate: fact-check pass >= 95% NOT met.

Manual reads and scans: results/e8_manual_reads.md
