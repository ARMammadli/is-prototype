## Item 2: E8 outputs rescored with check v3 (no LLM call; same prompt, temperature 0)

| | E8 check | Check v3 |
|---|---|---|
| Fact-check pass, all | 92.5% | 0.0% |
| Same pick as today's software | | 0.0% |
| Different pick | | 0.0% |

Errors per type (share of valid explanations; one explanation can have several):

| Error type | Share |
|---|---|
| Old up/down wording check, after the narrow exemption | 0.2% |
| Role check (new) | 7.0% |
| Load/burden claim not backed by a fact (new) | 100.0% |
| Any other existing check (numbers, from-to, today's software/cost, not in fact block) | 0.0% |

Seconds per explanation: 1.7.

Gold set from the hand labels: check v3 catches 20 of 20 known-wrong cases and passes 41 of 41 known-true cases (role part).

New audit sample (RNG seed 1, passing under v3, different pick): []