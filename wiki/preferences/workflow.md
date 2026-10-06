# Workflow preferences (this repo)

**Last updated:** 2026-10-05

- **Process:** the user chose brainstorming → spec → plan → **subagent-driven development**, approving each section of the design before any build.
- **Synthetic data:** the user prefers synthetic data when real data isn't accessible. The prototype runs entirely on the Mac with a local LLM (Ollama).
- **Metrics:** compute a broad set of metrics, then choose the meaningful ones for the deck. Report the inconvenient results too, e.g. the worse top-10% share.
- **No installs by Claude.** No pip/uv installs and no Homebrew installs. The user runs installs such as `brew install expat` and `brew install ollama` themselves.
- **Wiki location:** for this project, the wiki lives **in this repo** (`is_prototype/wiki/`), not in the PersonalProjects memory wiki.
- **Git:** there is no git repo here. Don't `git init` or commit unless asked.
