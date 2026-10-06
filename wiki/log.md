# Wiki Log — is_prototype

[INGEST] 2026-10-05 — Assignment brief + team report (docs/) → raw/assignment-brief.md

[UPDATE] 2026-10-05 — Created the local wiki. Covers the brainstorm, spec and plan for the strain-aware roster-repair prototype, and its subagent-driven build: 13 tasks plus a final review, 85 tests passing. Added:
- projects/roster-repair-prototype.md: decisions, rulings, state, pending environment steps.
- projects/evaluation-results.md: E1/E2/E4 numbers, the QR decomposition framing, economics caveats, citation rules.
- preferences/workflow.md.

[UPDATE] 2026-10-05 — Figures generated using the DYLD_LIBRARY_PATH expat workaround. Ollama is serving but has no model pulled. The user's demo trial is in audit.jsonl: 2 baseline-mode applies, one a non-top option with reason 'preference'.

[UPDATE] 2026-10-05 — DECISION: comparison is baseline (ORTEC-like) vs our solution (GenAI). GenAI decides is the main product; the rule formula is the safety net and benchmark. No ML training, GenAI functions only. E5 becomes the headline experiment.

[UPDATE] 2026-10-05 — E5 stopped at the user's request after 5 wards (seeds 0–4); resumable for seeds 5–9. GenAI decides vs ORTEC: QR −49 (−27%), nurses with 3+ QR −11.4 (−47%), same coverage. GenAI vs the formula: worse (QR +18, nurses with 3+ QR +6.8, Gini +0.05) but 12 fewer short-notice calls. GenAI agreed with the formula 26% of the time, fell back 0.7%, was verified 53%, p50 12.3 s.

[UPDATE] 2026-10-05 — Demo-ready: plain-language GenAI text (plainify backstop), no abbreviations on screen, "Let GenAI handle the next N sick calls" background autoplay with a live feed. 193 tests.

[UPDATE] 2026-10-05 — Presenter view is the default: Ward and start week, sick call, ORTEC vs GenAI side by side (who gets extra work / who gets relief), Hospital rule check line, Apply, GenAI autoplay, 3-row scoreboard. The formula is renamed "Hospital rule check". "Show details" opens the expert view.

[UPDATE] 2026-10-05 — GenAI prompts shortened (max 3 sentences, ~50 words; display shows 2 sentences + "Show full reasoning"). The decide payload stays unanchored (no ORTEC pick). NOTE: E5 (seeds 0–4) was measured with the older long prompt; re-run E5 with the new prompt, or disclose this in the appendix.

[UPDATE] 2026-10-05 — Model switched to qwen3:8b (config/policy.json). On 8 identical sick calls it beat 4b: median choice rank 2 vs 5, top-3 picks 5/8 vs 3/8, 12 s vs 8 s. qwen3:4b with thinking mode: 98 s and still a poor pick. MLX: Ollama 0.35 has an MLX runner, but the only qwen MLX build is 27b (18 GB), too big for 24 GB, so it stays on GGUF/Metal.

[UPDATE] 2026-10-06 — Two-page presenter: (1) one sick call with rest hours, tiredness words and a symmetric counter; (2) results across wards from E5 (27% fewer QR, 5/5 wards; costs +57% call-ins, +61% changes). Page 2 still shows qwen3:4b E5 numbers until the re-run.

[UPDATE] 2026-10-06 — E5 re-run started (qwen3:8b, short prompt, 5 wards). The old 4b long-prompt results are archived in results/archive_e5_qwen3-4b_longprompt/ for the appendix.

[UPDATE] 2026-10-06 — E5 re-run (qwen3:8b, short prompt, 5 wards) done: QR 182.4→120.0 (−34%), nurses with 3+ QR 24.4→10.0 (−59%), unfilled 1.2→1.0, Gini 0.218→0.199; facts verified 94.5% (was 53% for 4b); costs: call-ins 71→137, changes per call 1.02→1.97. Agreement with the formula 32%.
