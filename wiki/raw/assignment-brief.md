# Raw: Assignment brief + report status (distilled)

Sources:
- `docs/ai_strategy_assigment.txt`
- `docs/AI Strategy Lab informal document.docx`

Read on 2026-10-05.

## Assignment (RSM Information Strategy, AI Strategy Lab)
- Teams of four do one integrated project. Track A: transform an existing organisation's workflow with an emerging technology.
- Required components:
  1. Problem/opportunity
  2. Business model
  3. Working prototype
  4. Economics
  5. Competitive/ecosystem analysis
  6. Evaluation against a baseline
  7. Governance/failure analysis
  8. Future-market test (agents on all sides)
  9. Final recommendation
- **Deliverables:**
  - Final strategy deck: at most 15 slides plus appendix, submitted together with the prototype/workflow. Due **2026-10-07 23:59**.
  - Mandatory Demo Day, **2026-10-08 16:00–18:45**. It is not graded.
- **Grading:** only the deck is graded. The focus is strategic reasoning, design choices, course concepts, evidence and critical evaluation, not technical sophistication. A simulation or mock-up is acceptable if it tests the main assumptions.

## Team report as of 2026-10-05
- **Case:** Erasmus MC inpatient nurse roster *repair*. ORTEC is the incumbent scheduler.
- **Hypothesis:** repairs under coverage pressure optimise feasibility and stability, so cumulative strain concentrates on flexible nurses. Strain here means quick returns (rest under 11h), nights, consecutive shifts and overtime.
- **Proposal:** an "Existing+" layer owned by the hospital.
  - Deterministic exposure counting.
  - ORTEC generates the feasible options.
  - AI ranks them by forward-looking cumulative strain and explains the trade-offs.
  - The planner decides, and overrides are logged.
  - A monthly scheduler–manager review feeds results into the next base roster.
  - The proposal explicitly does not predict burnout.
- **Component status:**
  - Complete: Components 1, 2, 4, 5 and 7.
  - Component 8 was short and cited simulation numbers (49→~1 QR, +26% unfilled) that had **no source**.
  - Empty: Components 3 (prototype), 6 (evaluation) and 9 (recommendation).
- **Reference list gaps:** it covers Components 1, 2 and 5 only. Citations in Economics, Governance and Future-market are missing. The same RCT is cited both as "Shift schedule with fewer short daily rest periods" (2025) and as Djupedal et al. (2025).
- **Key numbers used in the report:**
  - absence rate 5.33% (Erasmus MC 2024)
  - about 700 absence days per 60-FTE ward per year
  - €250–€550 per absence day
  - Vedaa 2017: about 3 QR/month ↔ +21% absence days
  - RCT 2025: IRR 0.56 for absence days
