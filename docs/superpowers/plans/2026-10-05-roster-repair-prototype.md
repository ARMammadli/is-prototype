# Strain-Aware Roster Repair Prototype — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally-run synthetic-ward roster-repair simulator, a planner web app (ORTEC-like baseline versus strain-aware + local-LLM explanation), and a batch evaluation (E1–E4) that produces deck-ready CSVs, figures and a summary.

**Architecture:** A pure-Python simulation core (`sim/`) generates a seeded ward, a base roster and an absence stream. It produces the feasible repair options for each absence and scores them under both policies. An `llm/` layer turns the scored options into a JSON payload, calls Ollama (`qwen3:4b`), checks every claim deterministically, and falls back to a template. A FastAPI server (`app/`) exposes the core to a single static HTML/JS page. The scripts in `evaluation/` reuse the same core for the experiments.

**Tech Stack:** Python 3.14, numpy, pandas, scipy, matplotlib, FastAPI 0.128 + uvicorn, pydantic 2, httpx, pytest 9. Vanilla JS with a vendored Chart.js 4. Ollama runs locally.

**Spec:** `docs/superpowers/specs/2026-10-05-roster-repair-prototype-design.md`

**Deviations from spec (deliberate, minor):**
- The `eval/` directory is named `evaluation/`. A package called `eval` shadows the builtin and is confusing.
- Added files: `sim/metrics.py`, `llm/service.py`, `evaluation/stats.py`, `evaluation/calibrate.py`.
- The `main_tradeoff` enum gains a `concentration` value: the load falls on an already-loaded nurse while the metric increments are identical.
- `ward.json` gains `repair_availability_p`, the share of off-duty nurse-days reachable for a short-notice repair. It is needed for the spec's "2–8 direct-fill candidates" calibration.
- The concentration metric "nurses with > 4 QR in any 28 days" is replaced by **≥ 3 QR in 28 days**. The legal cap of one QR per 7 days makes > 4 impossible, and 3 per month is the exposure level Vedaa et al. (2017) link to +21% absence.
- The LLM payload and the UI use **1-based day numbers**. The core uses 0-based days internally.

## Global Constraints

- Everything runs on the user's Mac. **Never run `pip install`, `uv sync` or `pip3 install`.** Use only: numpy, pandas, scipy, matplotlib, fastapi, uvicorn, pydantic, httpx, pytest (all verified installed).
- All commands run from `/Users/abdulrahmanmammadli/Documents/PersonalProjects/is_prototype/prototype` (abbreviated `prototype/`). Run tests with `python3 -m pytest`.
- No git repository exists. **There are no commit steps.** Each task ends with a green test checkpoint instead.
- Ollama is not installed. The user installs it manually (`brew install ollama`, `ollama serve`, `ollama pull qwen3:4b`). Code must work without it, using the template fallback.
- Shift times are fixed: D 07:30–16:00 (8.5 h), E 15:30–23:00 (7.5 h), N 23:00–07:30 (+1 day, 8.5 h). 1.0 FTE = 36 h/week.
- Hard rules:
  - rest ≥ 11 h, except ≥ 8 h is allowed at most once per rolling 7 days (QR gaps < 168 h violate)
  - ≤ 60 h in any rolling 7 days
  - ≤ 6 consecutive working days
  - ≥ 46 h rest after ≥ 3 consecutive nights
  - night-exempt nurses never work N
  - no work on blocked (leave/absence) days
  - at most one shift per nurse per day
- Default policy weights: `QR=3, N=1, LR=2, OT=0.5, SN=1.5`, window 28 days back + 28 days forward, squared cost.
- Short notice = notice < 48 h.
- LLM: model `qwen3:4b`, `think: false`, temperature 0, JSON-schema `format`, UI timeout 20 s, eval timeout 60 s. Only pseudonymous IDs (`N01`…) are sent.
- Figures: PNG, 300 dpi, saved to `prototype/figures/`. Tables go to `prototype/results/`.

## Review Focus

1. **The absent nurse was the only senior on the shift.**
   - Only senior candidates are offered when one exists.
   - If none exists, non-senior candidates are offered and the shift is counted in `no_senior_shifts`. It is not dropped as infeasible. Pinned in Task 4.
2. **An absence is revealed for a nurse-day whose assignment was already moved or cleared by an earlier repair.** The event is skipped silently, the day is still blocked, and nothing crashes. Pinned in Task 5.
3. **Events on the first or last day of the horizon.** Strain windows are clipped to `[0, days-1]` with no `IndexError`, and scoring still works. Pinned in Task 4.
4. **The LLM returns well-formed JSON that references a non-existent option or nurse, or has malformed `claims` entries.**
   - The checker flags it and never raises.
   - The UI shows ⚠️ instead of breaking. Pinned in Task 8.
5. **Invalid API input.** This covers a stale `option_id` after the event was resolved, choosing a non-top option without a reason, and negative or missing policy weights.
   - These return 409/422.
   - Scenario and policy state are unchanged. Pinned in Task 9.

---

## File Structure

```
prototype/
  pytest.ini
  README.md
  config/ward.json, policy.json        ward + hospital policy parameters
  sim/__init__.py
  sim/ward.py        Nurse/Ward dataclasses, shift constants, build_ward, load_json
  sim/rules.py       hard-rule checker (nurse_violations, roster_violations)
  sim/roster.py      Roster container + greedy base-roster generator
  sim/absences.py    AbsenceEvent + absence-stream generator
  sim/strain.py      per-nurse strain metrics, window, strain score
  sim/policies.py    Change/Option/RepairContext, candidate generation, scoring/ranking, apply
  sim/agents.py      acceptance models for E4
  sim/engine.py      Scenario (stepwise) + run_scenario (batch) + records
  sim/metrics.py     run-level evaluation metrics (gini, concentration, coverage, stability)
  llm/__init__.py
  llm/prompt.py      SYSTEM_PROMPT, OUTPUT_SCHEMA, build_payload
  llm/checker.py     comparison_pair, ground_truth_tradeoff, check
  llm/template.py    template_explanation (fallback)
  llm/ollama_client.py  chat_json, is_available
  llm/service.py     explain() = LLM call + fallback + check
  app/__init__.py
  app/server.py      FastAPI API + static mount
  app/static/index.html, style.css, app.js, vendor/chart.umd.min.js
  evaluation/__init__.py
  evaluation/stats.py      paired stats, paths
  evaluation/calibrate.py  ward calibration report
  evaluation/e1_ab.py, e2_sensitivity.py, e3_faithfulness.py, e4_agents.py
  evaluation/make_figures.py, make_summary.py
  tests/helpers.py + test_*.py
  results/  figures/   (created at runtime)
```

---

### Task 1: Scaffolding, ward model and hard rules

**Files:**
- Create: `prototype/pytest.ini`, `prototype/config/ward.json`, `prototype/config/policy.json`
- Create: `prototype/sim/__init__.py` (empty), `prototype/sim/ward.py`, `prototype/sim/rules.py`
- Create: `prototype/sim/roster.py` (the `Roster` class only, because rules tests need it; the generator comes in Task 2)
- Test: `prototype/tests/helpers.py`, `prototype/tests/test_rules.py`

**Interfaces:**
- Produces:
  - `sim.ward`:
    - constants `SHIFT_CODES=("D","E","N")`, `SHIFT_TIMES`, `SHIFT_HOURS`, `HOURS_PER_FTE=36.0`, `CONFIG_DIR`
    - `shift_start(day:int, shift:str)->float`, `shift_end(day,shift)->float`
    - `Nurse(id, fte, senior, night_ok)` with `.weekly_hours`
    - `Ward(nurses, days, demand, leave:set[(nid,day)], available:set[(nid,day)])` with `.nurse(nid)`
    - `load_json(name)->dict`, `build_ward(cfg, rng)->Ward`
  - `sim.roster.Roster(ward)`:
    - attributes `by_nurse`, `by_slot`, `short_notice:dict[nid,list[int]]`, `added:set[(nid,day)]`
    - methods `get`, `assign`, `unassign`, `staff`, `has_senior`, `shifts_of`, `copy`
  - `sim.rules`: `nurse_violations(roster, nid, blocked=frozenset(), lo=None, hi=None)->list[str]`, `roster_violations(roster, blocked=frozenset())->list[str]`, constant `QR_REST=11.0`

- [ ] **Step 1: Create the scaffolding and config files**

`prototype/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

`prototype/config/ward.json`:
```json
{
  "n_nurses": 70,
  "fte_values": [1.0, 0.89, 0.78, 0.67],
  "fte_probs": [0.30, 0.30, 0.25, 0.15],
  "senior_frac": 0.25,
  "night_exempt_frac": 0.15,
  "days": 56,
  "demand": {"D": 11, "E": 10, "N": 6},
  "leave_frac": 0.12,
  "leave_block_days": 7,
  "repair_availability_p": 0.2,
  "absence_rate": 0.0533,
  "spell_lengths": [1, 3, 4, 5],
  "spell_probs": [0.75, 0.10, 0.08, 0.07],
  "short_notice_frac": 0.7
}
```

`prototype/config/policy.json`:
```json
{
  "weights": {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5},
  "back_days": 28,
  "forward_days": 28,
  "squared": true,
  "model": "qwen3:4b",
  "ui_timeout_s": 20,
  "eval_timeout_s": 60
}
```

Create an empty `prototype/sim/__init__.py`.

- [ ] **Step 2: Write `sim/ward.py`**

```python
"""Ward model: nurses, shifts, demand, leave and repair availability (spec §3)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SHIFT_CODES = ("D", "E", "N")
# Hours from the start of the shift's calendar day; N ends the next morning.
SHIFT_TIMES = {"D": (7.5, 16.0), "E": (15.5, 23.0), "N": (23.0, 31.5)}
SHIFT_HOURS = {s: end - start for s, (start, end) in SHIFT_TIMES.items()}
HOURS_PER_FTE = 36.0


def shift_start(day: int, shift: str) -> float:
    return day * 24 + SHIFT_TIMES[shift][0]


def shift_end(day: int, shift: str) -> float:
    return day * 24 + SHIFT_TIMES[shift][1]


@dataclass(frozen=True)
class Nurse:
    id: str
    fte: float
    senior: bool
    night_ok: bool

    @property
    def weekly_hours(self) -> float:
        return HOURS_PER_FTE * self.fte


@dataclass
class Ward:
    nurses: list[Nurse]
    days: int
    demand: dict[str, int]
    leave: set[tuple[str, int]]
    available: set[tuple[str, int]]  # off-duty nurse-days reachable for a short-notice repair
    _index: dict[str, Nurse] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._index = {n.id: n for n in self.nurses}

    def nurse(self, nid: str) -> Nurse:
        return self._index[nid]


def load_json(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text())


def build_ward(cfg: dict, rng: np.random.Generator) -> Ward:
    n = cfg["n_nurses"]
    days = cfg["days"]
    ftes = rng.choice(cfg["fte_values"], size=n, p=cfg["fte_probs"])
    senior_idx = set(rng.choice(n, size=round(cfg["senior_frac"] * n), replace=False).tolist())
    exempt_idx = set(rng.choice(n, size=round(cfg["night_exempt_frac"] * n), replace=False).tolist())
    nurses = [
        Nurse(f"N{i + 1:02d}", float(ftes[i]), i in senior_idx, i not in exempt_idx)
        for i in range(n)
    ]
    leave: set[tuple[str, int]] = set()
    block = cfg["leave_block_days"]
    target = cfg["leave_frac"] * n * days
    while len(leave) < target:
        nurse = nurses[int(rng.integers(n))]
        start = int(rng.integers(0, days - block + 1))
        leave.update((nurse.id, d) for d in range(start, start + block))
    available = {
        (nu.id, d)
        for nu in nurses
        for d in range(days)
        if rng.random() < cfg["repair_availability_p"]
    }
    return Ward(nurses, days, dict(cfg["demand"]), leave, available)
```

- [ ] **Step 3: Write the `Roster` class in `sim/roster.py`**

```python
"""Roster container and greedy base-roster generator (spec §3)."""
from __future__ import annotations

from sim.ward import SHIFT_CODES, Ward


class Roster:
    """Assignments nurse -> day -> shift, plus repair bookkeeping."""

    def __init__(self, ward: Ward) -> None:
        self.ward = ward
        self.by_nurse: dict[str, dict[int, str]] = {n.id: {} for n in ward.nurses}
        self.by_slot: dict[tuple[int, str], set[str]] = {
            (d, s): set() for d in range(ward.days) for s in SHIFT_CODES
        }
        self.short_notice: dict[str, list[int]] = {n.id: [] for n in ward.nurses}
        self.added: set[tuple[str, int]] = set()

    def get(self, nid: str, day: int) -> str | None:
        return self.by_nurse[nid].get(day)

    def assign(self, nid: str, day: int, shift: str) -> None:
        old = self.by_nurse[nid].get(day)
        if old is not None:
            self.by_slot[(day, old)].discard(nid)
        self.by_nurse[nid][day] = shift
        self.by_slot[(day, shift)].add(nid)

    def unassign(self, nid: str, day: int) -> str | None:
        old = self.by_nurse[nid].pop(day, None)
        if old is not None:
            self.by_slot[(day, old)].discard(nid)
        return old

    def staff(self, day: int, shift: str) -> set[str]:
        return self.by_slot[(day, shift)]

    def has_senior(self, day: int, shift: str) -> bool:
        return any(self.ward.nurse(n).senior for n in self.by_slot[(day, shift)])

    def shifts_of(self, nid: str) -> list[tuple[int, str]]:
        return sorted(self.by_nurse[nid].items())

    def copy(self) -> "Roster":
        r = Roster.__new__(Roster)
        r.ward = self.ward
        r.by_nurse = {k: dict(v) for k, v in self.by_nurse.items()}
        r.by_slot = {k: set(v) for k, v in self.by_slot.items()}
        r.short_notice = {k: list(v) for k, v in self.short_notice.items()}
        r.added = set(self.added)
        return r
```

- [ ] **Step 4: Write the test helpers and failing rules tests**

`prototype/tests/helpers.py`:
```python
from sim.roster import Roster
from sim.ward import Nurse, Ward


def make_ward(n=4, days=14, seniors=None, night_ok=None, demand=None, fte=1.0):
    seniors = seniors if seniors is not None else [True] * n
    night_ok = night_ok if night_ok is not None else [True] * n
    nurses = [Nurse(f"N{i + 1:02d}", fte, seniors[i], night_ok[i]) for i in range(n)]
    available = {(x.id, d) for x in nurses for d in range(days)}
    return Ward(nurses, days, demand or {"D": 1, "E": 1, "N": 1}, set(), available)


def roster_with(ward, assignments):
    r = Roster(ward)
    for nid, items in assignments.items():
        for d, s in items.items():
            r.assign(nid, d, s)
    return r
```

`prototype/tests/test_rules.py`:
```python
from helpers import make_ward, roster_with
from sim.rules import nurse_violations


def test_single_quick_return_is_legal():
    r = roster_with(make_ward(), {"N01": {0: "E", 1: "D"}})
    assert nurse_violations(r, "N01") == []


def test_two_quick_returns_within_seven_days_violate():
    r = roster_with(make_ward(), {"N01": {0: "E", 1: "D", 3: "E", 4: "D"}})
    assert any("quick returns" in v for v in nurse_violations(r, "N01"))


def test_quick_returns_exactly_seven_days_apart_are_legal():
    r = roster_with(make_ward(), {"N01": {0: "E", 1: "D", 7: "E", 8: "D"}})
    assert nurse_violations(r, "N01") == []


def test_night_then_evening_is_a_legal_quick_return():
    r = roster_with(make_ward(), {"N01": {0: "N", 1: "E"}})
    assert nurse_violations(r, "N01") == []


def test_night_then_day_violates_minimum_rest():
    r = roster_with(make_ward(), {"N01": {0: "N", 1: "D"}})
    assert any("rest" in v for v in nurse_violations(r, "N01"))


def test_six_consecutive_days_are_legal():
    r = roster_with(make_ward(), {"N01": {d: "D" for d in range(6)}})
    assert nurse_violations(r, "N01") == []


def test_seven_consecutive_days_violate():
    r = roster_with(make_ward(), {"N01": {d: "D" for d in range(7)}})
    assert any("consecutive" in v for v in nurse_violations(r, "N01"))


def test_short_rest_after_three_nights_violates():
    r = roster_with(make_ward(), {"N01": {0: "N", 1: "N", 2: "N", 4: "D"}})
    assert any("46" in v for v in nurse_violations(r, "N01"))


def test_enough_rest_after_three_nights_is_legal():
    r = roster_with(make_ward(), {"N01": {0: "N", 1: "N", 2: "N", 5: "E"}})
    assert nurse_violations(r, "N01") == []


def test_night_exempt_nurse_cannot_work_nights():
    w = make_ward(night_ok=[False, True, True, True])
    r = roster_with(w, {"N01": {0: "N"}})
    assert any("night" in v for v in nurse_violations(r, "N01"))


def test_work_on_blocked_day_violates():
    r = roster_with(make_ward(), {"N01": {2: "D"}})
    assert any("blocked" in v for v in nurse_violations(r, "N01", blocked={("N01", 2)}))


def test_window_restricts_the_check():
    r = roster_with(make_ward(), {"N01": {0: "N", 1: "D"}})
    assert nurse_violations(r, "N01", lo=5, hi=10) == []


def test_roster_copy_is_independent():
    r = roster_with(make_ward(), {"N01": {0: "D"}})
    c = r.copy()
    c.assign("N01", 1, "E")
    c.short_notice["N01"].append(1)
    assert r.get("N01", 1) is None and r.short_notice["N01"] == []
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.rules'`

- [ ] **Step 6: Write `sim/rules.py`**

```python
"""Hard scheduling rules (spec §3). Every candidate and every final roster must pass these."""
from __future__ import annotations

from sim.ward import SHIFT_HOURS, shift_end, shift_start

MIN_REST = 8.0
QR_REST = 11.0
QR_GAP = 168.0  # at most one shortened rest per rolling 7 days (Arbeidstijdenwet 5:3)
MAX_CONSEC = 6
MAX_7D_HOURS = 60.0
NIGHT_SERIES = 3
NIGHT_REST = 46.0


def nurse_violations(roster, nid: str, blocked=frozenset(), lo: int | None = None,
                     hi: int | None = None) -> list[str]:
    """Return human-readable violations for one nurse; optionally only shifts with lo <= day <= hi."""
    nurse = roster.ward.nurse(nid)
    items = roster.shifts_of(nid)
    if lo is not None:
        items = [(d, s) for d, s in items if lo <= d <= hi]
    out: list[str] = []
    for d, s in items:
        if (nid, d) in blocked:
            out.append(f"{nid} d{d}: works on a blocked day")
        if s == "N" and not nurse.night_ok:
            out.append(f"{nid} d{d}: night-exempt nurse on a night shift")
    qr_times: list[float] = []
    for (d1, s1), (d2, s2) in zip(items, items[1:]):
        rest = shift_start(d2, s2) - shift_end(d1, s1)
        if rest < MIN_REST:
            out.append(f"{nid} d{d2}: rest {rest:.1f}h below 8h")
        elif rest < QR_REST:
            qr_times.append(shift_start(d2, s2))
    for t1, t2 in zip(qr_times, qr_times[1:]):
        if t2 - t1 < QR_GAP:
            out.append(f"{nid}: two quick returns within 7 days")
    hours = {d: SHIFT_HOURS[s] for d, s in items}
    for d in hours:
        if sum(h for dd, h in hours.items() if d <= dd < d + 7) > MAX_7D_HOURS:
            out.append(f"{nid} d{d}: more than 60h in 7 days")
    run, prev = 0, None
    for d, _ in items:
        run = run + 1 if prev is not None and d == prev + 1 else 1
        prev = d
        if run > MAX_CONSEC:
            out.append(f"{nid} d{d}: more than 6 consecutive days")
    i = 0
    while i < len(items):
        if items[i][1] != "N":
            i += 1
            continue
        j = i
        while j + 1 < len(items) and items[j + 1][1] == "N" and items[j + 1][0] == items[j][0] + 1:
            j += 1
        if j - i + 1 >= NIGHT_SERIES and j + 1 < len(items):
            rest = shift_start(*items[j + 1]) - shift_end(*items[j])
            if rest < NIGHT_REST:
                out.append(f"{nid} d{items[j + 1][0]}: rest {rest:.1f}h after night series below 46h")
        i = j + 1
    return out


def roster_violations(roster, blocked=frozenset()) -> list[str]:
    return [v for n in roster.ward.nurses for v in nurse_violations(roster, n.id, blocked)]
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_rules.py -v`
Expected: 13 passed

---

### Task 2: Base-roster generator and absence stream

**Files:**
- Modify: `prototype/sim/roster.py` (append the generator)
- Create: `prototype/sim/absences.py`
- Test: `prototype/tests/test_roster_absences.py`

**Interfaces:**
- Consumes: `Roster`, `nurse_violations`, `roster_violations`, `build_ward`, `load_json`, `shift_start`, `SHIFT_HOURS`.
- Produces:
  - `sim.roster.generate_base_roster(ward, rng) -> Roster`
  - `sim.absences.AbsenceEvent(reveal_time: float, day: int, nurse: str, event_id: int, notice_h: float)`, frozen and ordered
  - `sim.absences.generate_absences(base: Roster, cfg: dict, rng) -> list[AbsenceEvent]`, sorted by `(reveal_time, day, nurse)` with `event_id` assigned in that order

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_roster_absences.py`:
```python
import numpy as np
import pytest

from sim.absences import generate_absences
from sim.roster import generate_base_roster
from sim.rules import roster_violations
from sim.ward import build_ward, load_json, shift_start


def _build(seed):
    cfg = load_json("ward.json")
    rng = np.random.default_rng(seed)
    ward = build_ward(cfg, rng)
    base = generate_base_roster(ward, rng)
    return cfg, ward, base, rng


@pytest.mark.parametrize("seed", [0, 1])
def test_base_roster_is_legal(seed):
    _, ward, base, _ = _build(seed)
    assert roster_violations(base, ward.leave) == []


def test_base_roster_is_deterministic():
    _, _, a, _ = _build(5)
    _, _, b, _ = _build(5)
    assert a.by_nurse == b.by_nurse


def test_absence_rate_matches_target():
    cfg, _, base, rng = _build(0)
    events = generate_absences(base, cfg, rng)
    rostered = sum(len(v) for v in base.by_nurse.values())
    target = round(cfg["absence_rate"] * rostered)
    assert target <= len(events) <= target + 5


def test_absence_events_are_sorted_and_consistent():
    cfg, _, base, rng = _build(1)
    events = generate_absences(base, cfg, rng)
    assert events == sorted(events)
    assert [e.event_id for e in events] == list(range(len(events)))
    for e in events:
        shift = base.get(e.nurse, e.day)
        assert shift is not None
        assert e.notice_h > 0
        assert abs(shift_start(e.day, shift) - e.notice_h - e.reveal_time) < 1e-9
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_roster_absences.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.absences'` (or `ImportError` for `generate_base_roster`)

- [ ] **Step 3: Append the generator to `sim/roster.py`**

Add these imports at the top of `sim/roster.py`, below the existing imports:
```python
from collections import Counter

import numpy as np

from sim.rules import nurse_violations
from sim.ward import SHIFT_HOURS
```
Then append:
```python
def generate_base_roster(ward: Ward, rng: np.random.Generator) -> Roster:
    """Greedy, seeded, rule-respecting base roster; prioritises nurses furthest below contract."""
    roster = Roster(ward)
    leave_days = Counter(nid for nid, _ in ward.leave)
    target = {n.id: n.weekly_hours / 7 * (ward.days - leave_days[n.id]) for n in ward.nurses}
    worked = {n.id: 0.0 for n in ward.nurses}
    for day in range(ward.days):
        progress = (day + 1) / ward.days
        for shift in SHIFT_CODES:
            while len(roster.staff(day, shift)) < ward.demand[shift]:
                nid = _pick(roster, day, shift, target, worked, progress, rng)
                if nid is None:
                    break
                roster.assign(nid, day, shift)
                worked[nid] += SHIFT_HOURS[shift]
    return roster


def _pick(roster, day, shift, target, worked, progress, rng):
    ward = roster.ward
    pool = [
        n for n in ward.nurses
        if roster.get(n.id, day) is None
        and (n.id, day) not in ward.leave
        and (shift != "N" or n.night_ok)
    ]
    noise = rng.random(len(pool))
    order = sorted(
        range(len(pool)),
        key=lambda i: -(target[pool[i].id] * progress - worked[pool[i].id] + noise[i]),
    )
    passes = [True, False] if not roster.has_senior(day, shift) else [False]
    for senior_only in passes:
        for i in order:
            n = pool[i]
            if senior_only and not n.senior:
                continue
            roster.assign(n.id, day, shift)
            ok = not nurse_violations(roster, n.id, ward.leave, day - 8, day + 1)
            roster.unassign(n.id, day)
            if ok:
                return n.id
    return None
```

- [ ] **Step 4: Write `sim/absences.py`**

```python
"""Exogenous, seeded absence stream (spec §3): ~5.33% of rostered shifts, short notice."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.ward import shift_start


@dataclass(frozen=True, order=True)
class AbsenceEvent:
    reveal_time: float
    day: int
    nurse: str
    event_id: int
    notice_h: float


def generate_absences(base, cfg: dict, rng: np.random.Generator) -> list[AbsenceEvent]:
    rostered = sorted((nid, d) for nid, days in base.by_nurse.items() for d in days)
    target = round(cfg["absence_rate"] * len(rostered))
    absent: set[tuple[str, int]] = set()
    raw: list[tuple[float, int, str, float]] = []
    guard = 0
    while len(absent) < target and guard < 100_000:
        guard += 1
        nid, d = rostered[int(rng.integers(len(rostered)))]
        if (nid, d) in absent:
            continue
        length = int(rng.choice(cfg["spell_lengths"], p=cfg["spell_probs"]))
        if rng.random() < cfg["short_notice_frac"]:
            notice = float(rng.uniform(1, 12))
        else:
            notice = float(rng.uniform(12, 48))
        reveal = shift_start(d, base.get(nid, d)) - notice
        for dd in range(d, d + length):
            shift = base.get(nid, dd)
            if shift is None or (nid, dd) in absent:
                continue
            absent.add((nid, dd))
            raw.append((reveal, dd, nid, shift_start(dd, shift) - reveal))
    raw.sort()
    return [AbsenceEvent(r, dd, nid, i, n) for i, (r, dd, nid, n) in enumerate(raw)]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_roster_absences.py tests/test_rules.py -v`
Expected: all passed (18)

---

### Task 3: Strain metrics

**Files:**
- Create: `prototype/sim/strain.py`
- Test: `prototype/tests/test_strain.py`

**Interfaces:**
- Consumes: `Roster`, `shift_start`, `shift_end`, `SHIFT_HOURS`, `QR_REST`.
- Produces (`sim.strain`):
  - constants `METRICS=("QR","N","LR","OT","SN")`, `TRADEOFF_NAMES={"QR":"quick_returns","N":"nights","LR":"long_runs","OT":"overtime","SN":"short_notice"}`, `TRADEOFFS` (names + `"stability"`, `"concentration"`), `SHORT_NOTICE_H=48.0`, `LONG_RUN=6`
  - `window(day, days, back=28, forward=28) -> (lo, hi)`
  - `expected_hours(ward, nid, lo, hi) -> float`
  - `qr_transitions(roster, nid) -> list[(d_prev, d_next)]`
  - `nurse_metrics(roster, nid, lo, hi) -> dict` with keys `METRICS` (OT rounded to 0.1)
  - `strain(metrics, weights) -> float`

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_strain.py`:
```python
from helpers import make_ward, roster_with
from sim.strain import nurse_metrics, qr_transitions, strain, window

W = {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5}


def test_metrics_on_fixed_roster():
    w = make_ward(days=28)
    r = roster_with(w, {"N01": {0: "E", 1: "D", 3: "N", 4: "N",
                                10: "D", 11: "D", 12: "D", 13: "D", 14: "D", 15: "D"}})
    r.short_notice["N01"].extend([11, 30])
    assert nurse_metrics(r, "N01", 0, 27) == {"QR": 1, "N": 2, "LR": 1, "OT": 0.0, "SN": 1}


def test_overtime_above_contract():
    w = make_ward(days=7, fte=0.25)  # 9 h/week
    r = roster_with(w, {"N01": {0: "D", 1: "D"}})
    assert nurse_metrics(r, "N01", 0, 6)["OT"] == 8.0


def test_window_is_clipped_to_horizon():
    assert window(2, 56) == (0, 30)
    assert window(50, 56) == (22, 55)
    assert window(10, 56, back=28, forward=7) == (0, 17)


def test_qr_transitions():
    r = roster_with(make_ward(), {"N01": {0: "E", 1: "D", 2: "D", 3: "N", 4: "E"}})
    assert qr_transitions(r, "N01") == [(0, 1), (3, 4)]


def test_strain_weighted_sum():
    assert strain({"QR": 1, "N": 2, "LR": 1, "OT": 0.0, "SN": 1}, W) == 8.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_strain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.strain'`

- [ ] **Step 3: Write `sim/strain.py`**

```python
"""Per-nurse strain metrics and the weighted strain score (spec §3)."""
from __future__ import annotations

from sim.rules import QR_REST
from sim.ward import SHIFT_HOURS, shift_end, shift_start

METRICS = ("QR", "N", "LR", "OT", "SN")
TRADEOFF_NAMES = {"QR": "quick_returns", "N": "nights", "LR": "long_runs",
                  "OT": "overtime", "SN": "short_notice"}
TRADEOFFS = tuple(TRADEOFF_NAMES.values()) + ("stability", "concentration")
SHORT_NOTICE_H = 48.0
LONG_RUN = 6


def window(day: int, days: int, back: int = 28, forward: int = 28) -> tuple[int, int]:
    return max(0, day - back), min(days - 1, day + forward)


def expected_hours(ward, nid: str, lo: int, hi: int) -> float:
    leave = sum(1 for d in range(lo, hi + 1) if (nid, d) in ward.leave)
    return ward.nurse(nid).weekly_hours / 7 * (hi - lo + 1 - leave)


def qr_transitions(roster, nid: str) -> list[tuple[int, int]]:
    items = roster.shifts_of(nid)
    return [
        (d1, d2)
        for (d1, s1), (d2, s2) in zip(items, items[1:])
        if shift_start(d2, s2) - shift_end(d1, s1) < QR_REST
    ]


def _runs(days: list[int]) -> list[tuple[int, int]]:
    runs, start, prev = [], None, None
    for d in days:
        if prev is not None and d == prev + 1:
            prev = d
            continue
        if prev is not None:
            runs.append((start, prev))
        start = prev = d
    if prev is not None:
        runs.append((start, prev))
    return runs


def nurse_metrics(roster, nid: str, lo: int, hi: int) -> dict:
    items = roster.shifts_of(nid)
    qr = sum(1 for _, d2 in qr_transitions(roster, nid) if lo <= d2 <= hi)
    nights = sum(1 for d, s in items if lo <= d <= hi and s == "N")
    lr = sum(1 for a, b in _runs([d for d, _ in items]) if b - a + 1 >= LONG_RUN and b >= lo and a <= hi)
    worked = sum(SHIFT_HOURS[s] for d, s in items if lo <= d <= hi)
    ot = max(0.0, worked - expected_hours(roster.ward, nid, lo, hi))
    sn = sum(1 for d in roster.short_notice[nid] if lo <= d <= hi)
    return {"QR": qr, "N": nights, "LR": lr, "OT": round(ot, 1), "SN": sn}


def strain(metrics: dict, weights: dict) -> float:
    return float(sum(weights[k] * metrics[k] for k in METRICS))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_strain.py -v`
Expected: 5 passed

---

### Task 4: Candidate generation, scoring and ranking

**Files:**
- Create: `prototype/sim/policies.py`
- Test: `prototype/tests/test_policies.py`

**Interfaces:**
- Consumes: `Roster`, `nurse_violations`, `SHIFT_CODES`, `SHIFT_HOURS`, `Ward`, and `METRICS`, `SHORT_NOTICE_H`, `window`, `expected_hours`, `nurse_metrics`, `strain`.
- Produces (`sim.policies`):
  - `Change(nurse, day, old: str|None, new: str|None)` (frozen)
  - `Option(id, kind: "direct"|"move", changes: tuple[Change,...])` with `.n_changes`, `.nurses`, `.extra_nurse`, `.index`
  - `RepairContext(ward, roster, blocked, day, shift, absent, notice_h, event_id, seed)`
  - `apply_changes(roster, changes)`, `revert_changes(roster, changes)`
  - `apply_option(roster, option, notice_h)`, which records `roster.added` and `roster.short_notice`
  - `generate_candidates(ctx, max_moves=20) -> list[Option]`
  - `ScoredOption(option, baseline_key, cost, nurses: list[dict], delta_strain, remaining_h, rank_baseline, rank_strain)`
    - each entry in `nurses` is `{"nurse", "before": metrics, "after": metrics, "strain_before", "strain_after"}`
  - `score_options(ctx, options, policy) -> list[ScoredOption]`
  - `rank_options(scored, policy_name: "baseline"|"strain") -> list[ScoredOption]`
  - `period_hours(roster, nid, day)`, `remaining_hours(roster, nid, day)`
  - `ward_strains(ctx, policy) -> dict[nid, float]`
  - `describe(option) -> str`

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_policies.py`:
```python
from helpers import make_ward, roster_with
from sim.policies import (RepairContext, generate_candidates, rank_options, score_options)

POLICY = {"weights": {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5},
          "back_days": 28, "forward_days": 28, "squared": True}


def _ctx(ward, roster, day, shift, absent="N03", notice_h=5.0):
    return RepairContext(ward=ward, roster=roster, blocked={(absent, day)}, day=day, shift=shift,
                         absent=absent, notice_h=notice_h, event_id=0, seed=0)


def _qr_setup():
    # N01 worked E on day 1 (taking D on day 2 creates a quick return) and has the most
    # remaining contract hours; N02 has fewer remaining hours but no quick return.
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"N01": {1: "E"}, "N02": {5: "D", 6: "D", 7: "D", 8: "D"}})
    return w, r, _ctx(w, r, 2, "D")


def test_baseline_prefers_contract_fit_strain_prefers_no_quick_return():
    _, _, ctx = _qr_setup()
    scored = score_options(ctx, generate_candidates(ctx), POLICY)
    base_top = rank_options(scored, "baseline")[0].option
    strain_top = rank_options(scored, "strain")[0].option
    assert base_top.changes[0].nurse == "N01"
    assert strain_top.changes[0].nurse == "N02"


def test_both_policies_rank_the_identical_feasible_set():
    _, _, ctx = _qr_setup()
    scored = score_options(ctx, generate_candidates(ctx), POLICY)
    ids_b = [s.option.id for s in rank_options(scored, "baseline")]
    ids_s = [s.option.id for s in rank_options(scored, "strain")]
    assert sorted(ids_b) == sorted(ids_s)
    assert sorted(s.rank_baseline for s in scored) == list(range(1, len(scored) + 1))
    assert sorted(s.rank_strain for s in scored) == list(range(1, len(scored) + 1))


def test_zero_weights_make_strain_order_equal_baseline_order():
    _, _, ctx = _qr_setup()
    zero = dict(POLICY, weights={k: 0.0 for k in POLICY["weights"]})
    scored = score_options(ctx, generate_candidates(ctx), zero)
    assert [s.option.id for s in rank_options(scored, "strain")] == \
           [s.option.id for s in rank_options(scored, "baseline")]


def test_infeasible_and_unavailable_nurses_are_excluded():
    w = make_ward(n=4, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"N01": {1: "N"}})  # N on day 1 ends 07:30 on day 2 -> cannot take D on day 2
    w.available.discard(("N02", 2))
    ctx = _ctx(w, r, 2, "D", absent="N04")
    nurses = {o.changes[0].nurse for o in generate_candidates(ctx)}
    assert nurses == {"N03"}


def test_move_with_backfill_is_generated_and_ranked_after_direct_by_baseline():
    w = make_ward(n=4, days=14, demand={"D": 1, "E": 1, "N": 0})
    r = roster_with(w, {"N01": {2: "E"}})
    ctx = _ctx(w, r, 2, "D", absent="N04")
    options = generate_candidates(ctx)
    kinds = sorted(o.kind for o in options)
    assert kinds == ["direct", "direct", "move", "move"]
    scored = score_options(ctx, options, POLICY)
    ranked = rank_options(scored, "baseline")
    assert [s.option.kind for s in ranked[:2]] == ["direct", "direct"]
    move = next(o for o in options if o.kind == "move")
    assert move.n_changes == 2 and move.extra_nurse in {"N02", "N03"}


def test_only_senior_candidates_when_shift_lost_its_senior():
    w = make_ward(n=3, days=14, seniors=[False, True, True], demand={"D": 1, "E": 0, "N": 0})
    ctx = _ctx(w, roster_with(w, {}), 2, "D")  # N03 (senior) is absent
    assert {o.changes[0].nurse for o in generate_candidates(ctx)} == {"N02"}


def test_non_senior_fallback_when_no_senior_is_available():
    w = make_ward(n=3, days=14, seniors=[False, False, True], demand={"D": 1, "E": 0, "N": 0})
    ctx = _ctx(w, roster_with(w, {}), 2, "D")
    assert {o.changes[0].nurse for o in generate_candidates(ctx)} == {"N01", "N02"}


def test_scoring_works_on_horizon_edges():
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    for day in (0, 13):
        ctx = _ctx(w, roster_with(w, {}), day, "D")
        scored = score_options(ctx, generate_candidates(ctx), POLICY)
        assert len(scored) == 2


def test_scoring_leaves_roster_unchanged():
    w, r, ctx = _qr_setup()
    before = {k: dict(v) for k, v in r.by_nurse.items()}
    score_options(ctx, generate_candidates(ctx), POLICY)
    assert r.by_nurse == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_policies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.policies'`

- [ ] **Step 3: Write `sim/policies.py`**

```python
"""Repair candidates (shared) and the two ranking policies (spec §4)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim.rules import nurse_violations
from sim.strain import (METRICS, SHORT_NOTICE_H, expected_hours, nurse_metrics, strain,
                        window)
from sim.ward import SHIFT_CODES, SHIFT_HOURS

MAX_MOVES = 20
CHECK_RADIUS = 8  # every hard rule is local to +-8 days around a change


@dataclass(frozen=True)
class Change:
    nurse: str
    day: int
    old: str | None
    new: str | None


@dataclass
class Option:
    id: str
    kind: str
    changes: tuple[Change, ...]

    @property
    def n_changes(self) -> int:
        return len(self.changes)

    @property
    def nurses(self) -> list[str]:
        return list(dict.fromkeys(c.nurse for c in self.changes))

    @property
    def extra_nurse(self) -> str:
        """The nurse whose workload increases (direct filler, backfiller, or the mover)."""
        for c in self.changes:
            if c.old is None and c.new is not None:
                return c.nurse
        return self.changes[0].nurse

    @property
    def index(self) -> int:
        return int(self.id[3:])


@dataclass
class RepairContext:
    ward: object
    roster: object
    blocked: set
    day: int
    shift: str
    absent: str
    notice_h: float
    event_id: int
    seed: int


@dataclass
class ScoredOption:
    option: Option
    baseline_key: tuple
    cost: float
    nurses: list[dict]
    delta_strain: float
    remaining_h: float
    rank_baseline: int = field(default=0)
    rank_strain: int = field(default=0)


def apply_changes(roster, changes) -> None:
    for c in changes:
        if c.new is None:
            roster.unassign(c.nurse, c.day)
        else:
            roster.assign(c.nurse, c.day, c.new)


def revert_changes(roster, changes) -> None:
    for c in reversed(changes):
        if c.old is None:
            roster.unassign(c.nurse, c.day)
        else:
            roster.assign(c.nurse, c.day, c.old)


def apply_option(roster, option: Option, notice_h: float) -> None:
    apply_changes(roster, option.changes)
    for c in option.changes:
        if c.new is not None:
            roster.added.add((c.nurse, c.day))
            if notice_h < SHORT_NOTICE_H:
                roster.short_notice[c.nurse].append(c.day)


def describe(option: Option) -> str:
    return "; ".join(f"{c.nurse}: {c.old or 'off'} → {c.new or 'off'}" for c in option.changes)


def _feasible(ctx: RepairContext, changes) -> bool:
    apply_changes(ctx.roster, changes)
    try:
        return all(
            not nurse_violations(ctx.roster, c.nurse, ctx.blocked,
                                 ctx.day - CHECK_RADIUS, ctx.day + CHECK_RADIUS)
            for c in changes
        )
    finally:
        revert_changes(ctx.roster, changes)


def _off_duty_ok(ctx: RepairContext, nid: str, shift: str) -> bool:
    ward = ctx.ward
    return (ctx.roster.get(nid, ctx.day) is None
            and (nid, ctx.day) not in ctx.blocked
            and (nid, ctx.day) in ward.available
            and (shift != "N" or ward.nurse(nid).night_ok))


def generate_candidates(ctx: RepairContext, max_moves: int = MAX_MOVES) -> list[Option]:
    """All feasible direct fills plus up to max_moves one-hop moves; identical for both policies."""
    ward, roster, d, s = ctx.ward, ctx.roster, ctx.day, ctx.shift
    direct = []
    for n in ward.nurses:
        if _off_duty_ok(ctx, n.id, s):
            ch = (Change(n.id, d, None, s),)
            if _feasible(ctx, ch):
                direct.append(ch)
    backfill: dict[str, list[str]] = {}
    moves = []
    for t in SHIFT_CODES:
        if t == s:
            continue
        staff_t = roster.staff(d, t)
        for x in sorted(staff_t):
            if s == "N" and not ward.nurse(x).night_ok:
                continue
            move = Change(x, d, t, s)
            if not _feasible(ctx, (move,)):
                continue
            remaining = staff_t - {x}
            keeps_senior = (not ward.nurse(x).senior) or any(ward.nurse(r).senior for r in remaining)
            if len(remaining) >= ward.demand[t] and keeps_senior:
                moves.append((move,))
                continue
            if t not in backfill:
                backfill[t] = [
                    n.id for n in ward.nurses
                    if _off_duty_ok(ctx, n.id, t) and _feasible(ctx, (Change(n.id, d, None, t),))
                ]
            for y in backfill[t]:
                if not keeps_senior and not ward.nurse(y).senior:
                    continue
                moves.append((move, Change(y, d, None, t)))
    if len(moves) > max_moves:
        rng = np.random.default_rng([ctx.seed, ctx.event_id])
        keep = sorted(rng.choice(len(moves), size=max_moves, replace=False).tolist())
        moves = [moves[i] for i in keep]
    combos = [("direct", ch) for ch in direct] + [("move", ch) for ch in moves]
    if not roster.has_senior(d, s):
        senior_only = [(k, ch) for k, ch in combos if ward.nurse(ch[0].nurse).senior]
        if senior_only:
            combos = senior_only
    return [Option(f"opt{i + 1}", kind, ch) for i, (kind, ch) in enumerate(combos)]


def _period(day: int, days: int) -> tuple[int, int]:
    lo = (day // 28) * 28
    return lo, min(days - 1, lo + 27)


def period_hours(roster, nid: str, day: int) -> float:
    lo, hi = _period(day, roster.ward.days)
    return sum(SHIFT_HOURS[s] for d, s in roster.shifts_of(nid) if lo <= d <= hi)


def remaining_hours(roster, nid: str, day: int) -> float:
    lo, hi = _period(day, roster.ward.days)
    return expected_hours(roster.ward, nid, lo, hi) - period_hours(roster, nid, day)


def score_options(ctx: RepairContext, options: list[Option], policy: dict) -> list[ScoredOption]:
    weights = policy["weights"]
    squared = policy.get("squared", True)
    lo, hi = window(ctx.day, ctx.ward.days, policy.get("back_days", 28), policy.get("forward_days", 28))
    short = ctx.notice_h < SHORT_NOTICE_H
    lacks_senior = not ctx.roster.has_senior(ctx.day, ctx.shift)
    scored = []
    for opt in options:
        nids = opt.nurses
        before = {n: nurse_metrics(ctx.roster, n, lo, hi) for n in nids}
        rem = remaining_hours(ctx.roster, opt.extra_nurse, ctx.day)
        apply_changes(ctx.roster, opt.changes)
        try:
            after = {n: nurse_metrics(ctx.roster, n, lo, hi) for n in nids}
        finally:
            revert_changes(ctx.roster, opt.changes)
        details, cost, delta = [], 0.0, 0.0
        for n in nids:
            a = dict(after[n])
            if short:
                a["SN"] += 1
            sb, sa = strain(before[n], weights), strain(a, weights)
            cost += (sa * sa - sb * sb) if squared else (sa - sb)
            delta += sa - sb
            details.append({"nurse": n, "before": before[n], "after": a,
                            "strain_before": round(sb, 2), "strain_after": round(sa, 2)})
        senior_flag = 1 if lacks_senior and not ctx.ward.nurse(opt.changes[0].nurse).senior else 0
        key = (opt.n_changes, -round(rem, 2), senior_flag)
        scored.append(ScoredOption(opt, key, cost, details, round(delta, 2), round(rem, 1)))
    for rank, so in enumerate(sorted(scored, key=lambda x: (x.baseline_key, x.option.index)), 1):
        so.rank_baseline = rank
    for rank, so in enumerate(sorted(scored, key=lambda x: (round(x.cost, 6), x.baseline_key,
                                                           x.option.index)), 1):
        so.rank_strain = rank
    return scored


def rank_options(scored: list[ScoredOption], policy_name: str) -> list[ScoredOption]:
    if policy_name == "baseline":
        return sorted(scored, key=lambda s: s.rank_baseline)
    if policy_name == "strain":
        return sorted(scored, key=lambda s: s.rank_strain)
    raise ValueError(f"unknown policy {policy_name!r}")


def ward_strains(ctx: RepairContext, policy: dict) -> dict[str, float]:
    lo, hi = window(ctx.day, ctx.ward.days, policy.get("back_days", 28), policy.get("forward_days", 28))
    return {n.id: strain(nurse_metrics(ctx.roster, n.id, lo, hi), policy["weights"])
            for n in ctx.ward.nurses}
```

`METRICS` is imported for re-export, so the `from sim.policies import ...` lines in later tasks stay short. Leave the import in.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_policies.py -v`
Expected: 9 passed

- [ ] **Step 5: Checkpoint: run the full suite**

Run: `python3 -m pytest -q`
Expected: all passed

---

### Task 5: Engine, agents and run metrics

**Files:**
- Create: `prototype/sim/agents.py`, `prototype/sim/engine.py`, `prototype/sim/metrics.py`
- Test: `prototype/tests/test_engine.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces:
  - `sim.agents`: `accepts(mode: "today"|"permissive"|"picky", rng, nurse_detail: dict, median_strain: float) -> bool`; constants `P_ACCEPT=0.9`, `P_PICKY_LOW=0.3`
  - `sim.engine`:
    - `EventRecord(event_id, day, shift, absent, notice_h, n_options, chosen, chosen_rank_baseline, chosen_rank_strain, changes, offers, baseline_top, strain_top)`
    - `RunResult(seed, policy_name, acceptance, ward, base, final, blocked, records)`
    - `Scenario(seed, ward_cfg=None, absence_rate=None)` with attributes `seed`, `cfg`, `ward`, `base`, `events`, `roster`, `blocked`, `unfilled`; property `remaining`; methods `next_context() -> RepairContext|None`, `apply(ctx, option)`, `mark_unfilled(ctx)`
    - `run_scenario(seed, policy_name, policy, acceptance="today", ward_cfg=None, absence_rate=None, on_event=None) -> RunResult`, where `on_event(ctx, scored)` is called before the decision
  - `sim.metrics`: `gini(values)`, `top_share(values, frac=0.1)`, `understaffed(roster) -> int`, `max_qr_in_28d(roster, nid)`, `run_metrics(result, weights) -> dict` with keys:
    - `n_events, unfilled, no_senior_shifts`
    - `QR_total, N_total, LR_total, OT_total, SN_total`
    - `gini_strain, top10_qr_share, max_qr, nurses_qr_ge3_28d, gini_sn`
    - `changes_per_repair, nurses_disturbed, repair_share_qr, offers_per_fill`

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_engine.py`:
```python
from collections import deque

import numpy as np
import pytest

from sim.absences import AbsenceEvent
from sim.agents import accepts
from sim.engine import Scenario, run_scenario
from sim.metrics import gini, run_metrics, top_share, understaffed
from sim.rules import roster_violations
from sim.ward import load_json

POLICY = load_json("policy.json")


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("policy_name", ["baseline", "strain"])
def test_final_roster_is_always_legal_and_coverage_accounts(seed, policy_name):
    res = run_scenario(seed, policy_name, POLICY)
    assert roster_violations(res.final, res.blocked) == []
    unfilled = sum(1 for r in res.records if r.chosen is None)
    assert understaffed(res.final) == understaffed(res.base) + unfilled


def test_paired_seeds_give_identical_ward_and_events():
    a, b = Scenario(7), Scenario(7)
    assert a.base.by_nurse == b.base.by_nurse
    assert a.events == b.events


def test_runs_are_deterministic():
    m1 = run_metrics(run_scenario(3, "strain", POLICY), POLICY["weights"])
    m2 = run_metrics(run_scenario(3, "strain", POLICY), POLICY["weights"])
    assert m1 == m2


def test_event_for_unassigned_day_is_skipped_but_blocked():
    sc = Scenario(0)
    nid = sc.ward.nurses[0].id
    day = next(d for d in range(sc.ward.days) if sc.roster.get(nid, d) is None)
    sc._queue = deque([AbsenceEvent(0.0, day, nid, 0, 10.0)])
    assert sc.next_context() is None
    assert (nid, day) in sc.blocked


def test_metrics_keys_and_ranges():
    m = run_metrics(run_scenario(0, "baseline", POLICY), POLICY["weights"])
    for k in ("n_events", "unfilled", "no_senior_shifts", "QR_total", "gini_strain", "top10_qr_share",
              "max_qr", "nurses_qr_ge3_28d", "gini_sn", "changes_per_repair", "nurses_disturbed",
              "repair_share_qr", "offers_per_fill"):
        assert k in m
    assert 0 <= m["gini_strain"] <= 1 and 0 <= m["repair_share_qr"] <= 1
    assert m["n_events"] > 0


def test_gini_and_top_share():
    assert gini([0, 0, 0]) == 0.0
    assert gini([1, 1, 1]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 1]) == pytest.approx(0.75)
    assert top_share([10] + [0] * 9) == 1.0
    assert top_share([1] * 10) == pytest.approx(0.1)


def test_acceptance_models():
    rng = np.random.default_rng(0)
    calm = {"before": {"QR": 0}, "after": {"QR": 0}, "strain_before": 1.0}
    adds_qr = {"before": {"QR": 0}, "after": {"QR": 1}, "strain_before": 1.0}
    assert accepts("today", rng, adds_qr, 0.0)
    perm = np.mean([accepts("permissive", rng, calm, 0.0) for _ in range(4000)])
    picky_bad = np.mean([accepts("picky", rng, adds_qr, 5.0) for _ in range(4000)])
    picky_ok = np.mean([accepts("picky", rng, calm, 5.0) for _ in range(4000)])
    assert abs(perm - 0.9) < 0.03 and abs(picky_bad - 0.3) < 0.03 and abs(picky_ok - 0.9) < 0.03
    with pytest.raises(ValueError):
        accepts("bogus", rng, calm, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sim.agents'`

- [ ] **Step 3: Write `sim/agents.py`**

```python
"""Acceptance models for the agentic-future test (spec §6, E4). Probabilities are assumptions."""
from __future__ import annotations

P_ACCEPT = 0.9
P_PICKY_LOW = 0.3


def accepts(mode: str, rng, nurse_detail: dict, median_strain: float) -> bool:
    if mode == "today":
        return True
    if mode == "permissive":
        return bool(rng.random() < P_ACCEPT)
    if mode == "picky":
        adds_qr = nurse_detail["after"]["QR"] > nurse_detail["before"]["QR"]
        calm = not adds_qr and nurse_detail["strain_before"] <= median_strain
        return bool(rng.random() < (P_ACCEPT if calm else P_PICKY_LOW))
    raise ValueError(f"unknown acceptance mode {mode!r}")
```

- [ ] **Step 4: Write `sim/engine.py`**

```python
"""Scenario runner shared by the app and all evaluations (spec §9)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

import numpy as np

from sim.absences import generate_absences
from sim.agents import accepts
from sim.policies import (RepairContext, apply_option, generate_candidates, rank_options,
                          score_options, ward_strains)
from sim.roster import generate_base_roster
from sim.ward import build_ward, load_json


@dataclass
class EventRecord:
    event_id: int
    day: int
    shift: str
    absent: str
    notice_h: float
    n_options: int
    chosen: str | None
    chosen_rank_baseline: int | None
    chosen_rank_strain: int | None
    changes: tuple
    offers: int
    baseline_top: str | None
    strain_top: str | None


@dataclass
class RunResult:
    seed: int
    policy_name: str
    acceptance: str
    ward: object
    base: object
    final: object
    blocked: set
    records: list


class Scenario:
    """One seeded ward with its base roster and absence stream, stepped event by event."""

    def __init__(self, seed: int, ward_cfg: dict | None = None, absence_rate: float | None = None):
        cfg = dict(ward_cfg) if ward_cfg else load_json("ward.json")
        if absence_rate is not None:
            cfg["absence_rate"] = absence_rate
        rng = np.random.default_rng(seed)
        self.seed = seed
        self.cfg = cfg
        self.ward = build_ward(cfg, rng)
        self.base = generate_base_roster(self.ward, rng)
        self.events = generate_absences(self.base, cfg, rng)
        self.roster = self.base.copy()
        self.blocked: set = set(self.ward.leave)
        self._queue = deque(self.events)
        self.unfilled: list[tuple[int, str]] = []

    @property
    def remaining(self) -> int:
        return len(self._queue)

    def next_context(self) -> RepairContext | None:
        while self._queue:
            ev = self._queue.popleft()
            self.blocked.add((ev.nurse, ev.day))
            shift = self.roster.unassign(ev.nurse, ev.day)
            if shift is None:
                continue
            return RepairContext(ward=self.ward, roster=self.roster, blocked=self.blocked,
                                 day=ev.day, shift=shift, absent=ev.nurse, notice_h=ev.notice_h,
                                 event_id=ev.event_id, seed=self.seed)
        return None

    def apply(self, ctx: RepairContext, option) -> None:
        apply_option(self.roster, option, ctx.notice_h)

    def mark_unfilled(self, ctx: RepairContext) -> None:
        self.unfilled.append((ctx.day, ctx.shift))


def run_scenario(seed: int, policy_name: str, policy: dict, acceptance: str = "today",
                 ward_cfg: dict | None = None, absence_rate: float | None = None,
                 on_event=None) -> RunResult:
    sc = Scenario(seed, ward_cfg, absence_rate)
    agent_rng = np.random.default_rng(seed + 10_000)
    records = []
    while (ctx := sc.next_context()) is not None:
        scored = score_options(ctx, generate_candidates(ctx), policy)
        if on_event is not None:
            on_event(ctx, scored)
        order = rank_options(scored, policy_name)
        med = median(ward_strains(ctx, policy).values()) if acceptance == "picky" else 0.0
        chosen, offers = None, 0
        for so in order:
            offers += 1
            if all(accepts(acceptance, agent_rng, nd, med) for nd in so.nurses):
                chosen = so
                break
        if chosen is not None:
            sc.apply(ctx, chosen.option)
        else:
            sc.mark_unfilled(ctx)
        records.append(EventRecord(
            event_id=ctx.event_id, day=ctx.day, shift=ctx.shift, absent=ctx.absent,
            notice_h=ctx.notice_h, n_options=len(scored),
            chosen=chosen.option.id if chosen else None,
            chosen_rank_baseline=chosen.rank_baseline if chosen else None,
            chosen_rank_strain=chosen.rank_strain if chosen else None,
            changes=chosen.option.changes if chosen else (), offers=offers,
            baseline_top=rank_options(scored, "baseline")[0].option.id if scored else None,
            strain_top=rank_options(scored, "strain")[0].option.id if scored else None,
        ))
    return RunResult(seed, policy_name, acceptance, sc.ward, sc.base, sc.roster, sc.blocked, records)
```

- [ ] **Step 5: Write `sim/metrics.py`**

```python
"""Run-level evaluation metrics (spec §6, E1)."""
from __future__ import annotations

import math

from sim.strain import nurse_metrics, qr_transitions, strain
from sim.ward import SHIFT_CODES


def gini(values) -> float:
    x = sorted(float(v) for v in values)
    n, total = len(x), sum(x)
    if n == 0 or total == 0:
        return 0.0
    cum = sum((i + 1) * v for i, v in enumerate(x))
    return 2 * cum / (n * total) - (n + 1) / n


def top_share(values, frac: float = 0.1) -> float:
    x = sorted((float(v) for v in values), reverse=True)
    total = sum(x)
    if total == 0:
        return 0.0
    k = max(1, math.ceil(len(x) * frac))
    return sum(x[:k]) / total


def understaffed(roster) -> int:
    ward = roster.ward
    return sum(max(0, ward.demand[s] - len(roster.staff(d, s)))
               for d in range(ward.days) for s in SHIFT_CODES)


def max_qr_in_28d(roster, nid: str) -> int:
    days = [d2 for _, d2 in qr_transitions(roster, nid)]
    return max((sum(1 for e in days[i:] if e < d + 28) for i, d in enumerate(days)), default=0)


def run_metrics(result, weights: dict) -> dict:
    ward, final = result.ward, result.final
    per = {n.id: nurse_metrics(final, n.id, 0, ward.days - 1) for n in ward.nurses}
    strains = [strain(m, weights) for m in per.values()]
    qr = [m["QR"] for m in per.values()]
    sn = [m["SN"] for m in per.values()]
    filled = [r for r in result.records if r.chosen is not None]
    total_qr = repair_qr = 0
    for n in ward.nurses:
        for d1, d2 in qr_transitions(final, n.id):
            total_qr += 1
            if (n.id, d1) in final.added or (n.id, d2) in final.added:
                repair_qr += 1
    return {
        "n_events": len(result.records),
        "unfilled": len(result.records) - len(filled),
        "no_senior_shifts": sum(1 for d in range(ward.days) for s in SHIFT_CODES
                                if final.staff(d, s) and not final.has_senior(d, s)),
        "QR_total": sum(qr),
        "N_total": sum(m["N"] for m in per.values()),
        "LR_total": sum(m["LR"] for m in per.values()),
        "OT_total": round(sum(m["OT"] for m in per.values()), 1),
        "SN_total": sum(sn),
        "gini_strain": gini(strains),
        "top10_qr_share": top_share(qr),
        "max_qr": max(qr),
        "nurses_qr_ge3_28d": sum(1 for n in ward.nurses if max_qr_in_28d(final, n.id) >= 3),
        "gini_sn": gini(sn),
        "changes_per_repair": (sum(len(r.changes) for r in filled) / len(filled)) if filled else 0.0,
        "nurses_disturbed": len({c.nurse for r in filled for c in r.changes}),
        "repair_share_qr": repair_qr / total_qr if total_qr else 0.0,
        "offers_per_fill": (sum(r.offers for r in filled) / len(filled)) if filled else 0.0,
    }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_engine.py -v`
Expected: 12 passed. Allow roughly a minute for this, since it runs full scenarios.

- [ ] **Step 7: Checkpoint**

Run: `python3 -m pytest -q`
Expected: all passed

---

### Task 6: Ward calibration

**Files:**
- Create: `prototype/evaluation/__init__.py` (empty), `prototype/evaluation/calibrate.py`
- Modify (only if a check fails): `prototype/config/ward.json`
- Test: `prototype/tests/test_calibration.py`

**Interfaces:**
- Consumes: `Scenario`, `generate_candidates`, `run_scenario`, `understaffed`, `nurse_metrics`.
- Produces: `evaluation.calibrate.calibration_rows(seeds) -> list[dict]` with keys `seed, base_gaps, events, mean_direct, mean_options, base_qr_per_nurse`.

- [ ] **Step 1: Write the failing test**

`prototype/tests/test_calibration.py`:
```python
from evaluation.calibrate import calibration_rows


def test_ward_is_calibrated():
    rows = calibration_rows(range(3))
    assert all(r["base_gaps"] == 0 for r in rows), rows
    mean_direct = sum(r["mean_direct"] for r in rows) / len(rows)
    assert 2.0 <= mean_direct <= 8.0, rows
    assert all(50 <= r["events"] <= 120 for r in rows), rows
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_calibration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.calibrate'`

- [ ] **Step 3: Write `evaluation/calibrate.py`**

```python
"""Calibration report: base roster fully staffed, ~2-8 direct-fill candidates per absence (spec §3)."""
from __future__ import annotations

import time

from sim.engine import Scenario, run_scenario
from sim.metrics import understaffed
from sim.policies import generate_candidates
from sim.strain import nurse_metrics
from sim.ward import load_json


def calibration_rows(seeds) -> list[dict]:
    rows = []
    for seed in seeds:
        sc = Scenario(seed)
        gaps = understaffed(sc.base)
        qr = sum(nurse_metrics(sc.base, n.id, 0, sc.ward.days - 1)["QR"] for n in sc.ward.nurses)
        direct, total, events = [], [], 0
        while (ctx := sc.next_context()) is not None:
            events += 1
            opts = generate_candidates(ctx)
            direct.append(sum(o.kind == "direct" for o in opts))
            total.append(len(opts))
            if opts:
                sc.apply(ctx, opts[0])
            else:
                sc.mark_unfilled(ctx)
        rows.append({"seed": seed, "base_gaps": gaps, "events": events,
                     "mean_direct": sum(direct) / max(1, len(direct)),
                     "mean_options": sum(total) / max(1, len(total)),
                     "base_qr_per_nurse": qr / len(sc.ward.nurses)})
    return rows


def main() -> None:
    rows = calibration_rows(range(10))
    for r in rows:
        print(r)
    t0 = time.perf_counter()
    run_scenario(0, "strain", load_json("policy.json"))
    print(f"one strain-aware run: {time.perf_counter() - t0:.1f}s")
    md = sum(r["mean_direct"] for r in rows) / len(rows)
    print("base gaps zero:", all(r["base_gaps"] == 0 for r in rows), "| mean direct:", round(md, 2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the calibration and tune if needed**

Run: `python3 -m evaluation.calibrate`

Tuning rules. Change only `config/ward.json`, one knob at a time, and re-run after each change:
- `base_gaps > 0` → lower `demand` by 1, trying `E` first, then `D`.
- mean direct < 2 → raise `repair_availability_p` by 0.05.
- mean direct > 8 → lower `repair_availability_p` by 0.05.
- `base_qr_per_nurse` should be above 0. If it is exactly 0 for every seed, the scenario has no baseline strain: report this to the user before continuing.

Record the final values and the runtime of one run. The runtime is needed to size E1.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_calibration.py -v`
Expected: 1 passed

---

### Task 7: Statistics, E1 policy A/B and all figure functions

**Files:**
- Create: `prototype/evaluation/stats.py`, `prototype/evaluation/e1_ab.py`, `prototype/evaluation/make_figures.py`
- Test: `prototype/tests/test_stats.py`

**Interfaces:**
- Consumes: `run_scenario`, `run_metrics`, `nurse_metrics`, `strain`, `load_json`.
- Produces:
  - `evaluation.stats`: `ROOT`, `RESULTS_DIR`, `FIGURES_DIR`, `paired_stats(df, metric, a="baseline", b="strain", key="seed", n_boot=2000, rng_seed=0) -> dict`, `paired_table(df, metrics, a="baseline", b="strain") -> DataFrame`
    - `paired_stats` columns: `metric, mean_<a>, mean_<b>, mean_diff, ci_low, ci_high, rel_change, wilcoxon_p, effect_dz, win_rate, tie_rate, n`
  - `evaluation.e1_ab`: `E1_METRICS`, `run_one((seed, policy_name)) -> (row, nurse_rows)`, `main()`
    - writes `results/e1_runs.csv`, `results/e1_nurses.csv`, `results/e1_stats.csv`
  - `evaluation.make_figures.main()`, which writes every figure whose input CSV exists:
    - `e1_concentration.png`, `e1_guardrails.png`, `e1_lorenz.png`
    - `e2_sensitivity.png`, `e3_faithfulness.png`, `e4_agents.png`

- [ ] **Step 1: Write the failing test**

`prototype/tests/test_stats.py`:
```python
import pandas as pd
import pytest

from evaluation.stats import paired_stats


def _df(base, strain):
    rows = [{"seed": i, "policy": "baseline", "m": b} for i, b in enumerate(base)]
    rows += [{"seed": i, "policy": "strain", "m": s} for i, s in enumerate(strain)]
    return pd.DataFrame(rows)


def test_consistent_improvement():
    r = paired_stats(_df([5, 6, 7, 8], [4, 5, 6, 7]), "m")
    assert r["mean_diff"] == pytest.approx(-1.0)
    assert r["ci_low"] == pytest.approx(-1.0) and r["ci_high"] == pytest.approx(-1.0)
    assert r["win_rate"] == 1.0 and r["n"] == 4


def test_no_difference():
    r = paired_stats(_df([1, 2, 3], [1, 2, 3]), "m")
    assert r["mean_diff"] == 0 and r["wilcoxon_p"] == 1.0 and r["effect_dz"] == 0.0
    assert r["tie_rate"] == 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.stats'`

- [ ] **Step 3: Write `evaluation/stats.py`**

```python
"""Paired statistics shared by all experiments (spec §6). All metrics: lower is better."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
FIGURES_DIR = ROOT / "figures"


def paired_stats(df: pd.DataFrame, metric: str, a: str = "baseline", b: str = "strain",
                 key: str = "seed", n_boot: int = 2000, rng_seed: int = 0) -> dict:
    p = df.pivot_table(index=key, columns="policy", values=metric).dropna()
    diff = (p[b] - p[a]).to_numpy(dtype=float)
    rng = np.random.default_rng(rng_seed)
    boots = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    pval = 1.0 if np.allclose(diff, 0) else float(wilcoxon(diff).pvalue)
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    mean_a = float(p[a].mean())
    return {
        "metric": metric, f"mean_{a}": mean_a, f"mean_{b}": float(p[b].mean()),
        "mean_diff": float(diff.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "rel_change": float(diff.mean() / mean_a) if mean_a else float("nan"),
        "wilcoxon_p": pval, "effect_dz": float(diff.mean() / sd) if sd > 0 else 0.0,
        "win_rate": float((diff < 0).mean()), "tie_rate": float((diff == 0).mean()), "n": len(diff),
    }


def paired_table(df: pd.DataFrame, metrics, a: str = "baseline", b: str = "strain") -> pd.DataFrame:
    return pd.DataFrame([paired_stats(df, m, a, b) for m in metrics])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_stats.py -v`
Expected: 2 passed

- [ ] **Step 5: Write `evaluation/e1_ab.py`**

```python
"""E1 — paired policy A/B: ORTEC-like baseline vs strain-aware (spec §6)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.strain import nurse_metrics, strain
from sim.ward import load_json

E1_METRICS = ["unfilled", "no_senior_shifts", "QR_total", "N_total", "LR_total", "OT_total",
              "SN_total", "gini_strain", "top10_qr_share", "max_qr", "nurses_qr_ge3_28d", "gini_sn",
              "changes_per_repair", "nurses_disturbed", "repair_share_qr"]


def run_one(job):
    seed, policy_name = job
    policy = load_json("policy.json")
    res = run_scenario(seed, policy_name, policy)
    row = run_metrics(res, policy["weights"])
    row.update(seed=seed, policy=policy_name)
    nurses = []
    for n in res.ward.nurses:
        m = nurse_metrics(res.final, n.id, 0, res.ward.days - 1)
        nurses.append({"seed": seed, "policy": policy_name, "nurse": n.id, "QR": m["QR"],
                       "strain": strain(m, policy["weights"])})
    return row, nurses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    jobs = [(s, p) for s in range(args.seeds) for p in ("baseline", "strain")]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        out = list(ex.map(run_one, jobs, chunksize=4))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs = pd.DataFrame([r for r, _ in out])
    runs.to_csv(RESULTS_DIR / "e1_runs.csv", index=False)
    pd.DataFrame([x for _, ns in out for x in ns]).to_csv(RESULTS_DIR / "e1_nurses.csv", index=False)
    stats = paired_table(runs, E1_METRICS)
    stats.to_csv(RESULTS_DIR / "e1_stats.csv", index=False)
    print(stats.to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Write `evaluation/make_figures.py`**

```python
"""Slide-ready figures (spec §6). Each figure is skipped if its input CSV does not exist yet."""
from __future__ import annotations

import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from evaluation.stats import FIGURES_DIR, RESULTS_DIR  # noqa: E402

COLORS = {"baseline": "#8a8f98", "strain": "#1f6feb"}
LABELS = {"baseline": "ORTEC-like", "strain": "Strain-aware"}
POLICIES = ("baseline", "strain")
plt.rcParams.update({"savefig.dpi": 300, "font.size": 12,
                     "axes.spines.top": False, "axes.spines.right": False})


def _save(fig, name: str) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / name)
    plt.close(fig)
    print("wrote", FIGURES_DIR / name)


def _boxes(ax, runs, metric, title):
    data = [runs.loc[runs.policy == p, metric] for p in POLICIES]
    bp = ax.boxplot(data, tick_labels=[LABELS[p] for p in POLICIES], patch_artist=True, widths=0.6)
    for patch, p in zip(bp["boxes"], POLICIES):
        patch.set_facecolor(COLORS[p])
        patch.set_alpha(0.85)
    ax.set_title(title, fontsize=12)


def fig_e1_concentration(runs):
    panels = [("gini_strain", "Gini of per-nurse strain"),
              ("top10_qr_share", "Top-10% share of quick returns"),
              ("max_qr", "Max quick returns (one nurse)"),
              ("nurses_qr_ge3_28d", "Nurses with ≥3 QR in 28 days")]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
    for ax, (m, t) in zip(axes, panels):
        _boxes(ax, runs, m, t)
    fig.suptitle("E1 — Concentration of roster strain (lower is better)")
    _save(fig, "e1_concentration.png")


def fig_e1_guardrails(runs):
    panels = [("unfilled", "Unfilled shifts"), ("QR_total", "Total quick returns"),
              ("changes_per_repair", "Changes per repair"), ("nurses_disturbed", "Nurses disturbed")]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5))
    for ax, (m, t) in zip(axes, panels):
        _boxes(ax, runs, m, t)
    fig.suptitle("E1 — Guardrails and stability trade-off")
    _save(fig, "e1_guardrails.png")


def fig_e1_lorenz(nurses):
    fig, ax = plt.subplots(figsize=(6, 6))
    for p in POLICIES:
        v = np.sort(nurses.loc[nurses.policy == p, "QR"].to_numpy(dtype=float))
        cum = np.concatenate([[0], np.cumsum(v) / v.sum()]) if v.sum() else np.zeros(len(v) + 1)
        ax.plot(np.linspace(0, 1, len(cum)), cum, color=COLORS[p], lw=2.5, label=LABELS[p])
    ax.plot([0, 1], [0, 1], ls="--", color="#bbb", label="Perfect equality")
    ax.set_xlabel("Share of nurses (sorted by quick returns)")
    ax.set_ylabel("Share of all quick returns")
    ax.set_title("E1 — Who absorbs the quick returns?")
    ax.legend()
    _save(fig, "e1_lorenz.png")


def fig_e2(stats):
    sub = stats[stats.metric == "gini_strain"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    y = np.arange(len(sub))
    err = [sub.mean_diff - sub.ci_low, sub.ci_high - sub.mean_diff]
    ax.barh(y, sub.mean_diff, xerr=err, color=COLORS["strain"], alpha=0.85, capsize=4)
    ax.set_yticks(y, sub.config)
    ax.axvline(0, color="#555", lw=1)
    ax.set_xlabel("Δ Gini of strain vs ORTEC-like (negative = more even)")
    ax.set_title("E2 — Sensitivity of the effect")
    _save(fig, "e2_sensitivity.png")


def fig_e3(summary):
    cols = [("json_valid_rate", "Valid JSON"), ("claim_accuracy", "Claim accuracy"),
            ("recommendation_agreement", "Picks top option"), ("tradeoff_correct", "Right trade-off"),
            ("pct_flagged", "Flagged (false/unsupported)")]
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.8 / max(1, len(summary))
    x = np.arange(len(cols))
    for i, (_, row) in enumerate(summary.iterrows()):
        ax.bar(x + i * width, [row[c] for c, _ in cols], width, label=row["model"])
    ax.set_xticks(x + width * (len(summary) - 1) / 2, [label for _, label in cols])
    ax.set_ylim(0, 1)
    ax.set_title("E3 — Explanation faithfulness (local LLM)")
    ax.legend()
    _save(fig, "e3_faithfulness.png")


def fig_e4(summary):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    modes = ["today", "permissive", "picky"]
    x = np.arange(len(modes))
    for ax, (m, t) in zip(axes, [("unfilled", "Unfilled shifts"), ("QR_total", "Total quick returns")]):
        for i, p in enumerate(POLICIES):
            vals = [summary[(summary["mode"] == md) & (summary.policy == p)][m].mean() for md in modes]
            ax.bar(x + i * 0.38, vals, 0.38, color=COLORS[p], label=LABELS[p])
        ax.set_xticks(x + 0.19, ["Planner assigns", "Permissive agents", "Picky agents"])
        ax.set_title(t)
    axes[0].legend()
    fig.suptitle("E4 — Agentic future: nurses' agents accept or decline offers")
    _save(fig, "e4_agents.png")


def main() -> None:
    def read(name):
        path = RESULTS_DIR / name
        return pd.read_csv(path) if path.exists() else None

    if (runs := read("e1_runs.csv")) is not None:
        fig_e1_concentration(runs)
        fig_e1_guardrails(runs)
    if (nurses := read("e1_nurses.csv")) is not None:
        fig_e1_lorenz(nurses)
    if (e2 := read("e2_stats.csv")) is not None:
        fig_e2(e2)
    e3_files = sorted(glob.glob(str(RESULTS_DIR / "e3_summary_*.csv")))
    if e3_files:
        fig_e3(pd.concat([pd.read_csv(f) for f in e3_files], ignore_index=True))
    if (e4 := read("e4_summary.csv")) is not None:
        fig_e4(e4)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Smoke-run E1 small, then the full run**

Run: `python3 -m evaluation.e1_ab --seeds 4 --workers 2 && python3 -m evaluation.make_figures`
Expected: a stats table prints; `results/e1_runs.csv` has 8 rows; `figures/e1_concentration.png`, `e1_guardrails.png` and `e1_lorenz.png` are written.

Then run the full E1 in the background, since it takes several minutes:
`python3 -m evaluation.e1_ab --seeds 200 --workers 4 && python3 -m evaluation.make_figures`
Expected: `results/e1_stats.csv` with 15 metric rows. **Report the headline numbers to the user** (gini_strain, top10_qr_share, max_qr, unfilled, changes_per_repair). This is the first piece of deck evidence.

---

### Task 8: LLM layer (payload, checker, template, Ollama client, service)

**Files:**
- Create: `prototype/llm/__init__.py` (empty), `prototype/llm/prompt.py`, `prototype/llm/checker.py`, `prototype/llm/template.py`, `prototype/llm/ollama_client.py`, `prototype/llm/service.py`
- Test: `prototype/tests/test_llm.py`

**Interfaces:**
- Consumes: `RepairContext`, `ScoredOption`, `rank_options`, `METRICS`, `TRADEOFF_NAMES`, `TRADEOFFS`.
- Produces:
  - `llm.prompt`: `SYSTEM_PROMPT: str`, `OUTPUT_SCHEMA: dict`, `build_payload(ctx, scored, policy, k=3) -> dict`
    - payload keys: `event{absent, day(1-based), shift, notice_h}`, `weights`, `options[]`
    - each option has `{id, rank_strain, rank_baseline, is_baseline_top, kind, n_changes, delta_strain, changes[{nurse, day(1-based), from, to}], nurses[...]}`
  - `llm.checker`: `comparison_pair(payload) -> (top_opt, other_opt|None)`, `ground_truth_tradeoff(payload) -> str`, `check(expl, payload) -> dict`
    - `check` returns keys `claims_total, claims_false, unsupported_numbers, recommendation_correct, tradeoff_correct, ground_truth, verified`
  - `llm.template`: `template_explanation(payload) -> dict` (same schema as the LLM output)
  - `llm.ollama_client`: `OLLAMA_URL`, `chat_json(system, user, schema, model, timeout) -> (dict|None, str|None)`, `is_available(timeout=2.0) -> bool`
  - `llm.service`: `explain(payload, model, timeout, use_llm=True) -> {"explanation", "source", "latency_ms", "error", "check"}`

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_llm.py`:
```python
import copy
import json

from helpers import make_ward, roster_with
from llm import service
from llm.checker import check, ground_truth_tradeoff
from llm.prompt import OUTPUT_SCHEMA, build_payload
from llm.template import template_explanation
from sim.policies import RepairContext, generate_candidates, score_options

ZERO = {"QR": 0, "N": 0, "LR": 0, "OT": 0.0, "SN": 0}
PAYLOAD = {
    "event": {"absent": "N03", "day": 3, "shift": "D", "notice_h": 5.0},
    "weights": {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5},
    "options": [
        {"id": "opt2", "rank_strain": 1, "rank_baseline": 2, "is_baseline_top": False, "kind": "direct",
         "n_changes": 1, "delta_strain": 1.5, "changes": [{"nurse": "N02", "day": 3, "from": None, "to": "D"}],
         "nurses": [{"nurse": "N02", "before": dict(ZERO), "after": dict(ZERO, SN=1),
                     "strain_before": 0.0, "strain_after": 1.5}]},
        {"id": "opt1", "rank_strain": 2, "rank_baseline": 1, "is_baseline_top": True, "kind": "direct",
         "n_changes": 1, "delta_strain": 4.5, "changes": [{"nurse": "N01", "day": 3, "from": None, "to": "D"}],
         "nurses": [{"nurse": "N01", "before": dict(ZERO), "after": dict(ZERO, QR=1, SN=1),
                     "strain_before": 0.0, "strain_after": 4.5}]},
    ],
}
GOOD = {"recommended_option": "opt2", "main_tradeoff": "quick_returns",
        "claims": [{"nurse": "N01", "metric": "QR", "before": 0, "after": 1}],
        "text": "opt2 avoids giving N01 a quick return (0 to 1)."}


def test_ground_truth_is_quick_returns():
    assert ground_truth_tradeoff(PAYLOAD) == "quick_returns"


def test_ground_truth_concentration_when_increments_equal():
    p = copy.deepcopy(PAYLOAD)
    for opt in p["options"]:
        opt["nurses"][0]["after"] = dict(ZERO, N=1)
    p["options"][1]["nurses"][0]["strain_before"] = 9.0
    assert ground_truth_tradeoff(p) == "concentration"


def test_ground_truth_single_option_is_stability():
    p = copy.deepcopy(PAYLOAD)
    p["options"] = p["options"][:1]
    assert ground_truth_tradeoff(p) == "stability"


def test_correct_explanation_is_verified():
    r = check(GOOD, PAYLOAD)
    assert r["verified"] and r["claims_false"] == 0 and r["unsupported_numbers"] == []
    assert r["recommendation_correct"] and r["tradeoff_correct"]


def test_wrong_number_unknown_nurse_and_malformed_claims_are_flagged():
    bad = dict(GOOD, claims=[{"nurse": "N01", "metric": "QR", "before": 0, "after": 2},
                             {"nurse": "N99", "metric": "QR", "before": 0, "after": 1},
                             "junk", {"nurse": "N01"}])
    r = check(bad, PAYLOAD)
    assert r["claims_false"] == 4 and not r["verified"]


def test_unsupported_number_in_text_is_flagged():
    r = check(dict(GOOD, text="opt2 saves 17 hours."), PAYLOAD)
    assert r["unsupported_numbers"] == ["17"] and not r["verified"]


def test_wrong_or_unknown_recommendation_is_flagged():
    assert not check(dict(GOOD, recommended_option="opt1"), PAYLOAD)["recommendation_correct"]
    assert not check(dict(GOOD, recommended_option="opt9"), PAYLOAD)["verified"]


def test_template_is_verified_for_two_and_one_options():
    t = template_explanation(PAYLOAD)
    assert t["recommended_option"] == "opt2" and check(t, PAYLOAD)["verified"]
    single = copy.deepcopy(PAYLOAD)
    single["options"] = single["options"][:1]
    assert check(template_explanation(single), single)["verified"]


def test_service_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: (None, "ConnectError: refused"))
    r = service.explain(PAYLOAD, "qwen3:4b", 1)
    assert r["source"] == "template" and r["check"]["verified"] and "ConnectError" in r["error"]


def test_service_rejects_wrong_shape(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: ({"foo": 1}, None))
    assert service.explain(PAYLOAD, "qwen3:4b", 1)["source"] == "template"


def test_service_uses_model_output(monkeypatch):
    monkeypatch.setattr(service, "chat_json", lambda *a, **k: (dict(GOOD), None))
    r = service.explain(PAYLOAD, "qwen3:4b", 1)
    assert r["source"] == "qwen3:4b" and r["check"]["verified"]


def test_build_payload_from_real_context():
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"N01": {1: "E"}, "N02": {5: "D", 6: "D", 7: "D", 8: "D"}})
    ctx = RepairContext(w, r, {("N03", 2)}, 2, "D", "N03", 5.0, 0, 0)
    policy = {"weights": PAYLOAD["weights"], "back_days": 28, "forward_days": 28, "squared": True}
    p = build_payload(ctx, score_options(ctx, generate_candidates(ctx), policy), policy)
    assert p["event"]["day"] == 3
    assert any(o["is_baseline_top"] for o in p["options"])
    assert min(o["rank_strain"] for o in p["options"]) == 1
    json.dumps(p)
    assert set(OUTPUT_SCHEMA["required"]) == {"recommended_option", "main_tradeoff", "claims", "text"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm'`

- [ ] **Step 3: Write `llm/prompt.py`**

```python
"""LLM payload and prompt (spec §5). Only pseudonymous IDs and computed metrics are sent."""
from __future__ import annotations

from sim.policies import rank_options
from sim.strain import METRICS, TRADEOFFS

SYSTEM_PROMPT = """You explain nurse roster repair options to a hospital ward planner.
You receive JSON with one absence, the hospital's strain weights, and up to four feasible repair
options. For every affected nurse each option lists metrics before and after the repair, counted
over the planning window: QR = quick returns (less than 11 h rest), N = night shifts,
LR = runs of 6+ consecutive working days, OT = overtime hours above contract,
SN = short-notice changes absorbed. Days are numbered from 1.
Rules:
- recommended_option must be the option with rank_strain 1.
- Explain in at most 80 words why it is preferred over the option with is_baseline_top true
  (or over rank_strain 2 if the baseline top is the same option).
- Only use numbers that appear in the JSON.
- Every before/after number you mention about a nurse must also be listed in claims.
- main_tradeoff is the single factor that most separates the two options.
- Never speculate about health, burnout, motivation or private circumstances."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_option": {"type": "string"},
        "main_tradeoff": {"type": "string", "enum": list(TRADEOFFS)},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nurse": {"type": "string"},
                    "metric": {"type": "string", "enum": list(METRICS)},
                    "before": {"type": "number"},
                    "after": {"type": "number"},
                },
                "required": ["nurse", "metric", "before", "after"],
            },
        },
        "text": {"type": "string"},
    },
    "required": ["recommended_option", "main_tradeoff", "claims", "text"],
}


def _option_payload(so, is_base_top: bool) -> dict:
    return {
        "id": so.option.id,
        "rank_strain": so.rank_strain,
        "rank_baseline": so.rank_baseline,
        "is_baseline_top": is_base_top,
        "kind": so.option.kind,
        "n_changes": so.option.n_changes,
        "delta_strain": so.delta_strain,
        "changes": [{"nurse": c.nurse, "day": c.day + 1, "from": c.old, "to": c.new}
                    for c in so.option.changes],
        "nurses": so.nurses,
    }


def build_payload(ctx, scored, policy: dict, k: int = 3) -> dict:
    by_strain = rank_options(scored, "strain")
    base_top = rank_options(scored, "baseline")[0]
    chosen = list(by_strain[:k])
    if not any(so is base_top for so in chosen):
        chosen.append(base_top)
    return {
        "event": {"absent": ctx.absent, "day": ctx.day + 1, "shift": ctx.shift,
                  "notice_h": round(ctx.notice_h, 1)},
        "weights": dict(policy["weights"]),
        "options": [_option_payload(so, so is base_top) for so in chosen],
    }
```

- [ ] **Step 4: Write `llm/checker.py`**

```python
"""Deterministic faithfulness checker for explanations (spec §5)."""
from __future__ import annotations

import re

from sim.strain import METRICS, TRADEOFF_NAMES

OT_TOLERANCE = 0.5
DOMAIN_NUMBERS = {"6", "7", "8", "11", "28", "46", "48"}  # rule constants an explanation may cite
_NUM = re.compile(r"\d+(?:\.\d+)?")


def comparison_pair(payload: dict):
    opts = sorted(payload["options"], key=lambda o: o["rank_strain"])
    top = opts[0]
    base = next((o for o in opts if o["is_baseline_top"]), None)
    if base is not None and base["id"] != top["id"]:
        return top, base
    return top, (opts[1] if len(opts) > 1 else None)


def _increment(opt: dict, metric: str) -> float:
    return sum(nd["after"][metric] - nd["before"][metric] for nd in opt["nurses"])


def ground_truth_tradeoff(payload: dict) -> str:
    top, other = comparison_pair(payload)
    if other is None:
        return "stability"
    w = payload["weights"]
    diffs = {m: w[m] * abs(_increment(other, m) - _increment(top, m)) for m in METRICS}
    best = max(METRICS, key=lambda m: diffs[m])
    if diffs[best] > 0:
        return TRADEOFF_NAMES[best]
    loaded = lambda o: max(nd["strain_before"] for nd in o["nurses"])  # noqa: E731
    return "concentration" if loaded(other) != loaded(top) else "stability"


def _norm(value) -> str:
    r = round(float(value), 1)
    return str(int(r)) if r == int(r) else str(r)


def _payload_numbers(obj, out: set) -> set:
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(_norm(obj))
    elif isinstance(obj, str):
        out.update(_norm(x) for x in _NUM.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _payload_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _payload_numbers(v, out)
    return out


def _matches(record: dict, claim: dict) -> bool:
    metric = claim.get("metric")
    if metric not in METRICS:
        return False
    tol = OT_TOLERANCE if metric == "OT" else 1e-9
    try:
        return (abs(float(record["before"][metric]) - float(claim["before"])) <= tol
                and abs(float(record["after"][metric]) - float(claim["after"])) <= tol)
    except (KeyError, TypeError, ValueError):
        return False


def check(expl: dict, payload: dict) -> dict:
    index: dict[str, list[dict]] = {}
    for opt in payload["options"]:
        for nd in opt["nurses"]:
            index.setdefault(nd["nurse"], []).append(nd)
    claims = expl.get("claims") if isinstance(expl.get("claims"), list) else []
    false = 0
    for c in claims:
        if not isinstance(c, dict) or not any(_matches(r, c) for r in index.get(c.get("nurse"), [])):
            false += 1
    allowed = _payload_numbers(payload, set()) | DOMAIN_NUMBERS
    text = expl.get("text") if isinstance(expl.get("text"), str) else ""
    unsupported = [x for x in _NUM.findall(text) if _norm(x) not in allowed]
    top, _ = comparison_pair(payload)
    truth = ground_truth_tradeoff(payload)
    rec_ok = expl.get("recommended_option") == top["id"]
    return {
        "claims_total": len(claims),
        "claims_false": false,
        "unsupported_numbers": unsupported,
        "recommendation_correct": rec_ok,
        "tradeoff_correct": expl.get("main_tradeoff") == truth,
        "ground_truth": truth,
        "verified": false == 0 and not unsupported and rec_ok,
    }
```

- [ ] **Step 5: Write `llm/template.py`**

```python
"""Template explanation used when the LLM is unavailable (spec §5). Uses only payload numbers."""
from __future__ import annotations

from llm.checker import comparison_pair, ground_truth_tradeoff
from sim.strain import METRICS


def _desc(opt: dict) -> str:
    return "; ".join(f"{c['nurse']}: {c['from'] or 'off'} → {c['to'] or 'off'}" for c in opt["changes"])


def _changed(opt: dict) -> list[dict]:
    return [{"nurse": nd["nurse"], "metric": m, "before": nd["before"][m], "after": nd["after"][m]}
            for nd in opt["nurses"] for m in METRICS if nd["after"][m] != nd["before"][m]]


def _fmt(claims: list[dict]) -> str:
    return ", ".join(f"{c['nurse']} {c['metric']} {c['before']}→{c['after']}" for c in claims[:3])


def template_explanation(payload: dict) -> dict:
    top, other = comparison_pair(payload)
    tradeoff = ground_truth_tradeoff(payload)
    top_claims = _changed(top)
    text = f"Recommended {top['id']} ({_desc(top)})."
    claims = list(top_claims)
    if other is None:
        text += " It is the only feasible option."
    else:
        other_claims = _changed(other)
        claims += other_claims
        text += f" Compared with {other['id']} ({_desc(other)}), the main difference is " \
                f"{tradeoff.replace('_', ' ')}."
        if other_claims:
            text += f" {other['id']}: {_fmt(other_claims)}."
        if top_claims:
            text += f" {top['id']}: {_fmt(top_claims)}."
    return {"recommended_option": top["id"], "main_tradeoff": tradeoff, "claims": claims, "text": text}
```

- [ ] **Step 6: Write `llm/ollama_client.py`**

```python
"""Minimal Ollama chat client with JSON-schema structured output (spec §5)."""
from __future__ import annotations

import json
import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def chat_json(system: str, user: str, schema: dict, model: str, timeout: float):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "think": False,
        "format": schema,
        "options": {"temperature": 0},
    }
    try:
        resp = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"]), None
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def is_available(timeout: float = 2.0) -> bool:
    try:
        return httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False
```

- [ ] **Step 7: Write `llm/service.py`**

```python
"""explain(): local LLM with template fallback, always followed by the deterministic check."""
from __future__ import annotations

import json
import time

from llm.checker import check
from llm.ollama_client import chat_json
from llm.prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT
from llm.template import template_explanation


def _valid_shape(expl) -> bool:
    return (isinstance(expl, dict)
            and isinstance(expl.get("recommended_option"), str)
            and isinstance(expl.get("main_tradeoff"), str)
            and isinstance(expl.get("claims"), list)
            and isinstance(expl.get("text"), str))


def explain(payload: dict, model: str, timeout: float, use_llm: bool = True) -> dict:
    t0 = time.perf_counter()
    expl, error, source = None, None, model
    if use_llm:
        expl, error = chat_json(SYSTEM_PROMPT, json.dumps(payload, separators=(",", ":")),
                                OUTPUT_SCHEMA, model, timeout)
        if expl is not None and not _valid_shape(expl):
            error, expl = "invalid output shape", None
    else:
        error = "LLM disabled"
    if expl is None:
        expl, source = template_explanation(payload), "template"
    return {"explanation": expl, "source": source,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "error": error, "check": check(expl, payload)}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: 12 passed

- [ ] **Step 9: Live smoke test, if Ollama is running**

Run:
```bash
python3 -c "
import sys, json; sys.path.insert(0, 'tests')
from llm.ollama_client import is_available; print('ollama up:', is_available())
from test_llm import PAYLOAD; from llm.service import explain
print(json.dumps(explain(PAYLOAD, 'qwen3:4b', 60), indent=2))"
```
Expected when Ollama is up: `source: qwen3:4b`, a `check` object, and a latency in the low seconds. When it is down: `source: template`. If Ollama is up but every call errors with an unknown `think` field (older Ollama), tell the user to update Ollama. Do not remove the field.

---

### Task 9: FastAPI server

**Files:**
- Create: `prototype/app/__init__.py` (empty), `prototype/app/server.py`, `prototype/app/static/index.html`, which is a placeholder overwritten in Task 10. Write `<!doctype html><title>Roster Repair</title>` for now.
- Test: `prototype/tests/test_server.py`

**Interfaces:**
- Consumes: `Scenario`, `generate_candidates`, `score_options`, `rank_options`, `period_hours`, `describe`, `nurse_metrics`, `strain`, `window`, `gini`, `top_share`, `build_payload`, `explain`, `load_json`.
- Produces HTTP endpoints. These JSON shapes are what the frontend relies on:
  - `POST /api/scenario {seed}` → state
  - `GET /api/state` → state
    - state has `{seed, days, nurses[{id, fte, senior, night_ok}], grid{nid:{day:shift}}, changed[[nid,day]], absent[[nid,day]], leave[[nid,day]], event|null, remaining_events, unfilled[[day,shift]], strain[{nurse, strain, QR}], kpis{gini, top10_qr_share, max_qr}}`
    - event has `{event_id, absent, day(0-based), shift, notice_h, unfilled}`
  - `POST /api/next-event` → `{done, state}`. Returns 409 if an event is still open.
  - `GET /api/options?mode=baseline|strain` → `{mode, options[]}`
    - baseline option: `{id, rank, kind, change_text, nurse, contract_h, hours_period, n_changes}`
    - strain option: `{id, rank, rank_baseline, kind, change_text, n_changes, delta_strain, nurses[...]}`
    - Returns 409 if no event is open.
  - `POST /api/explain` → the `explain()` result. Returns 409 if no event is open.
  - `POST /api/apply {option_id, mode, override_reason?}` → `{state}`
    - 409 if there is no event or the option is unknown or stale
    - 422 if a non-top option is chosen without a reason
  - `GET /api/policy` → policy; `PUT /api/policy {weights{QR,N,LR,OT,SN ≥0}, forward_days 1..28, squared}` → policy (422 if invalid)
  - `GET /api/audit` → `{entries[]}` (last 50)
  - `/` → static files

- [ ] **Step 1: Write the failing tests**

`prototype/tests/test_server.py`:
```python
import pytest
from fastapi.testclient import TestClient

import app.server as server
from sim.ward import load_json


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(server.STATE, "policy", load_json("policy.json"))
    monkeypatch.setattr("llm.service.chat_json", lambda *a, **k: (None, "ConnectError: down"))
    c = TestClient(server.app)
    c.post("/api/scenario", json={"seed": 1})
    return c


def _open_event(client):
    for _ in range(20):
        r = client.post("/api/next-event").json()
        if r["state"]["event"] and not r["state"]["event"]["unfilled"]:
            return r["state"]["event"]
    pytest.fail("no fillable event found")


def test_state_and_index(client):
    s = client.get("/api/state").json()
    assert s["seed"] == 1 and len(s["nurses"]) == 70 and s["event"] is None
    assert client.get("/").status_code == 200


def test_full_repair_flow_and_audit(client):
    _open_event(client)
    base = client.get("/api/options?mode=baseline").json()["options"]
    strain = client.get("/api/options?mode=strain").json()["options"]
    assert base[0]["rank"] == 1 and "contract_h" in base[0]
    assert strain[0]["rank"] == 1 and "nurses" in strain[0]
    assert {o["id"] for o in base} <= {o["id"] for o in client.get("/api/options?mode=strain&limit=100").json()["options"]}
    ex = client.post("/api/explain").json()
    assert ex["source"] == "template" and ex["check"]["verified"]
    r = client.post("/api/apply", json={"option_id": strain[0]["id"], "mode": "strain"})
    assert r.status_code == 200 and r.json()["state"]["event"] is None
    entries = client.get("/api/audit").json()["entries"]
    assert entries[-1]["option_id"] == strain[0]["id"] and entries[-1]["explanation_source"] == "template"


def test_non_top_without_reason_is_rejected_then_accepted_with_reason(client):
    _open_event(client)
    opts = client.get("/api/options?mode=baseline").json()["options"]
    if len(opts) < 2:
        pytest.skip("event has a single option")
    bad = client.post("/api/apply", json={"option_id": opts[1]["id"], "mode": "baseline"})
    assert bad.status_code == 422
    assert client.get("/api/state").json()["event"] is not None
    ok = client.post("/api/apply", json={"option_id": opts[1]["id"], "mode": "baseline",
                                         "override_reason": "local_knowledge"})
    assert ok.status_code == 200
    assert client.get("/api/audit").json()["entries"][-1]["override_reason"] == "local_knowledge"


def test_stale_option_and_no_event_return_409(client):
    _open_event(client)
    top = client.get("/api/options?mode=baseline").json()["options"][0]
    client.post("/api/apply", json={"option_id": top["id"], "mode": "baseline"})
    assert client.post("/api/apply", json={"option_id": top["id"], "mode": "baseline"}).status_code == 409
    assert client.get("/api/options?mode=strain").status_code == 409
    assert client.post("/api/explain").status_code == 409


def test_next_event_while_open_returns_409(client):
    _open_event(client)
    assert client.post("/api/next-event").status_code == 409


def test_invalid_policy_is_rejected_and_unchanged(client):
    before = client.get("/api/policy").json()
    bad = {"weights": {"QR": -1, "N": 1, "LR": 2, "OT": 0.5, "SN": 1.5}, "forward_days": 28, "squared": True}
    assert client.put("/api/policy", json=bad).status_code == 422
    missing = {"weights": {"QR": 1}, "forward_days": 28, "squared": True}
    assert client.put("/api/policy", json=missing).status_code == 422
    assert client.get("/api/policy").json() == before


def test_valid_policy_rescores_open_event(client):
    _open_event(client)
    zero = {"weights": {k: 0 for k in ("QR", "N", "LR", "OT", "SN")}, "forward_days": 14, "squared": False}
    assert client.put("/api/policy", json=zero).status_code == 200
    b = [o["id"] for o in client.get("/api/options?mode=baseline&limit=100").json()["options"]]
    s = [o["id"] for o in client.get("/api/options?mode=strain&limit=100").json()["options"]]
    assert b == s
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.server'`

- [ ] **Step 3: Write `app/server.py`**

```python
"""Planner web app API (spec §5). One in-memory scenario at a time."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm.prompt import build_payload
from llm.service import explain
from sim.engine import Scenario
from sim.metrics import gini, top_share
from sim.policies import (describe, generate_candidates, period_hours, rank_options,
                          score_options)
from sim.strain import nurse_metrics, strain, window
from sim.ward import load_json

APP_DIR = Path(__file__).resolve().parent
AUDIT_PATH = APP_DIR / "data" / "audit.jsonl"
Mode = Literal["baseline", "strain"]
Reason = Literal["local_knowledge", "preference", "skill_mix", "other"]


class AppState:
    def __init__(self) -> None:
        self.policy = load_json("policy.json")
        self.reset(0)

    def reset(self, seed: int) -> None:
        self.scenario = Scenario(seed)
        self.ctx = None
        self.options = []
        self.scored = []
        self.explanation = None
        self.last_day = 0


STATE = AppState()
app = FastAPI(title="Strain-aware roster repair")


class ScenarioIn(BaseModel):
    seed: int = Field(default=0, ge=0)


class ApplyIn(BaseModel):
    option_id: str
    mode: Mode
    override_reason: Reason | None = None


class WeightsIn(BaseModel):
    QR: float = Field(ge=0)
    N: float = Field(ge=0)
    LR: float = Field(ge=0)
    OT: float = Field(ge=0)
    SN: float = Field(ge=0)


class PolicyIn(BaseModel):
    weights: WeightsIn
    forward_days: int = Field(ge=1, le=28)
    squared: bool = True


def _append_audit(entry: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "seed": STATE.scenario.seed, **entry}
    with AUDIT_PATH.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _event_json(ctx, unfilled: bool = False) -> dict:
    return {"event_id": ctx.event_id, "absent": ctx.absent, "day": ctx.day, "shift": ctx.shift,
            "notice_h": round(ctx.notice_h, 1), "unfilled": unfilled}


def _state_json(event: dict | None = None) -> dict:
    sc, policy = STATE.scenario, STATE.policy
    ward, roster = sc.ward, sc.roster
    lo, hi = window(STATE.last_day, ward.days, policy["back_days"], policy["forward_days"])
    per = {n.id: nurse_metrics(roster, n.id, lo, hi) for n in ward.nurses}
    strains = {nid: strain(m, policy["weights"]) for nid, m in per.items()}
    qr = [m["QR"] for m in per.values()]
    if event is None and STATE.ctx is not None:
        event = _event_json(STATE.ctx)
    return {
        "seed": sc.seed,
        "days": ward.days,
        "nurses": [{"id": n.id, "fte": n.fte, "senior": n.senior, "night_ok": n.night_ok}
                   for n in ward.nurses],
        "grid": roster.by_nurse,
        "changed": sorted(roster.added),
        "absent": sorted(b for b in sc.blocked if b not in ward.leave),
        "leave": sorted(ward.leave),
        "event": event,
        "remaining_events": sc.remaining,
        "unfilled": sc.unfilled,
        "strain": [{"nurse": nid, "strain": round(s, 2), "QR": per[nid]["QR"]} for nid, s in strains.items()],
        "kpis": {"gini": round(gini(strains.values()), 3), "top10_qr_share": round(top_share(qr), 3),
                 "max_qr": max(qr) if qr else 0},
    }


def _option_json(so, mode: str) -> dict:
    opt = so.option
    if mode == "baseline":
        nurse = opt.extra_nurse
        return {"id": opt.id, "rank": so.rank_baseline, "kind": opt.kind, "change_text": describe(opt),
                "nurse": nurse, "contract_h": STATE.scenario.ward.nurse(nurse).weekly_hours,
                "hours_period": period_hours(STATE.scenario.roster, nurse, STATE.ctx.day),
                "n_changes": opt.n_changes}
    return {"id": opt.id, "rank": so.rank_strain, "rank_baseline": so.rank_baseline, "kind": opt.kind,
            "change_text": describe(opt), "n_changes": opt.n_changes, "delta_strain": so.delta_strain,
            "nurses": so.nurses}


def _require_event() -> None:
    if STATE.ctx is None:
        raise HTTPException(status_code=409, detail="No open event")


@app.post("/api/scenario")
def new_scenario(body: ScenarioIn) -> dict:
    STATE.reset(body.seed)
    return _state_json()


@app.get("/api/state")
def get_state() -> dict:
    return _state_json()


@app.post("/api/next-event")
def next_event() -> dict:
    if STATE.ctx is not None:
        raise HTTPException(status_code=409, detail="Resolve the current event first")
    ctx = STATE.scenario.next_context()
    if ctx is None:
        return {"done": True, "state": _state_json()}
    STATE.last_day = ctx.day
    options = generate_candidates(ctx)
    if not options:
        STATE.scenario.mark_unfilled(ctx)
        _append_audit({"event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift,
                       "absent": ctx.absent, "mode": "-", "option_id": None, "unfilled": True})
        return {"done": False, "state": _state_json(event=_event_json(ctx, unfilled=True))}
    STATE.ctx, STATE.options, STATE.explanation = ctx, options, None
    STATE.scored = score_options(ctx, options, STATE.policy)
    return {"done": False, "state": _state_json()}


@app.get("/api/options")
def get_options(mode: Mode = "baseline", limit: int = 10) -> dict:
    _require_event()
    ranked = rank_options(STATE.scored, mode)[:max(1, limit)]
    return {"mode": mode, "options": [_option_json(so, mode) for so in ranked]}


@app.post("/api/explain")
def explain_current() -> dict:
    _require_event()
    payload = build_payload(STATE.ctx, STATE.scored, STATE.policy)
    STATE.explanation = explain(payload, STATE.policy.get("model", "qwen3:4b"),
                                STATE.policy.get("ui_timeout_s", 20))
    return STATE.explanation


@app.post("/api/apply")
def apply_option(body: ApplyIn) -> dict:
    _require_event()
    match = next((so for so in STATE.scored if so.option.id == body.option_id), None)
    if match is None:
        raise HTTPException(status_code=409, detail="Option is not part of the current event")
    rank = match.rank_baseline if body.mode == "baseline" else match.rank_strain
    if rank != 1 and body.override_reason is None:
        raise HTTPException(status_code=422, detail="override_reason is required for a non-top option")
    ctx = STATE.ctx
    STATE.scenario.apply(ctx, match.option)
    expl = STATE.explanation if body.mode == "strain" else None
    _append_audit({
        "event_id": ctx.event_id, "day": ctx.day, "shift": ctx.shift, "absent": ctx.absent,
        "mode": body.mode, "option_id": match.option.id, "rank": rank,
        "top_option": rank_options(STATE.scored, body.mode)[0].option.id,
        "override_reason": body.override_reason,
        "explanation_source": expl["source"] if expl else None,
        "verified": expl["check"]["verified"] if expl else None,
    })
    STATE.ctx, STATE.options, STATE.scored, STATE.explanation = None, [], [], None
    return {"state": _state_json()}


@app.get("/api/policy")
def get_policy() -> dict:
    return STATE.policy


@app.put("/api/policy")
def put_policy(body: PolicyIn) -> dict:
    STATE.policy = {**STATE.policy, "weights": body.weights.model_dump(),
                    "forward_days": body.forward_days, "squared": body.squared}
    if STATE.ctx is not None:
        STATE.scored = score_options(STATE.ctx, STATE.options, STATE.policy)
        STATE.explanation = None
    return STATE.policy


@app.get("/api/audit")
def get_audit() -> dict:
    if not AUDIT_PATH.exists():
        return {"entries": []}
    lines = AUDIT_PATH.read_text().splitlines()[-50:]
    return {"entries": [json.loads(line) for line in lines if line.strip()]}


app.mount("/", StaticFiles(directory=APP_DIR / "static", html=True), name="static")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_server.py -v`
Expected: 7 passed (one may be reported as skipped if seed 1's first event has a single option)

- [ ] **Step 5: Checkpoint**

Run: `python3 -m pytest -q`
Expected: all passed

---

### Task 10: Planner frontend

**Files:**
- Create: `prototype/app/static/index.html` (overwrite the placeholder), `prototype/app/static/style.css`, `prototype/app/static/app.js`
- Create: `prototype/app/static/vendor/chart.umd.min.js` (download)

**Interfaces:**
- Consumes: the HTTP API from Task 9, exactly as specified in its Interfaces block.

- [ ] **Step 1: Vendor Chart.js**

Run:
```bash
mkdir -p app/static/vendor && curl -fsSL -o app/static/vendor/chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js && wc -c app/static/vendor/chart.umd.min.js
```
Expected: about 200 KB. If the download returns 404, retry with `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js`, saved to the same filename. The app degrades gracefully (no chart) if the file is missing.

- [ ] **Step 2: Write `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Roster Repair</title>
  <link rel="stylesheet" href="style.css">
  <script src="vendor/chart.umd.min.js"></script>
</head>
<body>
<header class="bar">
  <h1>Roster Repair <span class="sub">37-bed ward · synthetic data</span></h1>
  <label>Seed <input id="seed" type="number" value="0" min="0"></label>
  <button id="btn-new">New scenario</button>
  <div class="toggle">
    <button class="mode active" data-mode="baseline">ORTEC-like baseline</button>
    <button class="mode" data-mode="strain">Strain-aware + AI</button>
  </div>
  <button id="btn-next" class="primary">Next event ▶</button>
  <span id="remaining" class="muted"></span>
</header>
<main>
  <section class="card"><h2>Current event</h2><div id="event"></div></section>
  <section class="card"><h2>Repair options</h2><div id="options"></div></section>
  <section id="explain-card" class="card hidden">
    <h2>Why the top option <span id="explain-meta"></span></h2>
    <p id="explain-text"></p>
    <ul id="explain-claims"></ul>
  </section>
  <section class="card wide"><h2>Roster</h2><div id="grid-wrap"><table id="grid"></table></div></section>
  <section class="card"><h2>Ward strain <span id="ward-kpis" class="muted"></span></h2>
    <canvas id="strain-chart" height="220"></canvas></section>
  <section id="policy-card" class="card hidden"><h2>Hospital policy (weights)</h2><form id="policy-form"></form></section>
  <section class="card wide"><h2>Audit log</h2><table id="audit"></table></section>
</main>
<dialog id="override-dlg">
  <form method="dialog">
    <h3>Why not the top option?</h3>
    <select id="override-reason">
      <option value="local_knowledge">Local knowledge</option>
      <option value="preference">Nurse preference</option>
      <option value="skill_mix">Skill mix</option>
      <option value="other">Other</option>
    </select>
    <menu><button value="cancel">Cancel</button><button value="ok" class="primary">Apply</button></menu>
  </form>
</dialog>
<div id="toast"></div>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Write `app/static/style.css`**

```css
:root { --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --muted:#6b7280; --line:#e5e7eb;
  --accent:#1f6feb; --warn:#b45309; --bad:#b91c1c; --ok:#15803d;
  --D:#dbeafe; --E:#fde68a; --N:#c7d2fe; --leave:#e5e7eb; --absent:#fecaca; }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.45 system-ui, -apple-system, sans-serif; color:var(--ink); background:var(--bg); }
.bar { display:flex; flex-wrap:wrap; gap:12px; align-items:center; padding:10px 16px; background:var(--card);
  border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; }
.bar h1 { font-size:17px; margin:0 12px 0 0; } .sub, .muted { color:var(--muted); font-weight:400; font-size:13px; }
button { font:inherit; padding:6px 12px; border:1px solid var(--line); border-radius:6px; background:#fff; cursor:pointer; }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.toggle { display:flex; } .toggle .mode { border-radius:0; } .toggle .mode:first-child { border-radius:6px 0 0 6px; }
.toggle .mode:last-child { border-radius:0 6px 6px 0; } .mode.active { background:var(--ink); color:#fff; }
input[type=number] { width:70px; padding:5px; }
main { display:grid; grid-template-columns:repeat(auto-fit, minmax(420px, 1fr)); gap:14px; padding:14px 16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; min-width:0; }
.card.wide { grid-column:1 / -1; } .card h2 { font-size:15px; margin:0 0 8px; } .hidden { display:none; }
table { border-collapse:collapse; width:100%; } th, td { padding:4px 6px; border-bottom:1px solid var(--line); text-align:left; }
table.opts tr.top { background:#eef5ff; } .up { color:var(--bad); font-weight:600; }
.warn { color:var(--warn); } .badge { font-size:12px; padding:2px 6px; border-radius:4px; }
.badge.ok { background:#dcfce7; color:var(--ok); } .badge.bad { background:#fee2e2; color:var(--bad); }
.src { font-size:12px; color:var(--muted); }
#grid-wrap { overflow:auto; max-height:420px; }
#grid { font-size:11px; width:auto; } #grid td, #grid th { padding:1px 3px; text-align:center; border:1px solid #f0f0f0; min-width:20px; }
#grid th:first-child { position:sticky; left:0; background:#fff; text-align:left; }
#grid .s-D { background:var(--D); } #grid .s-E { background:var(--E); } #grid .s-N { background:var(--N); }
#grid .leave { background:var(--leave); color:var(--muted); } #grid .absent { background:var(--absent); color:var(--bad); font-weight:700; }
#grid .changed { outline:2px solid var(--accent); outline-offset:-2px; } #grid .event { outline:3px solid #f59e0b; outline-offset:-3px; }
#grid .wk { border-left:2px solid #cbd5e1; } #grid tr.focus th { color:var(--accent); font-weight:700; }
#policy-form { display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:8px; align-items:end; }
#toast { position:fixed; bottom:16px; right:16px; background:var(--ink); color:#fff; padding:10px 14px; border-radius:8px;
  opacity:0; transition:opacity .2s; pointer-events:none; } #toast.show { opacity:1; }
dialog { border:1px solid var(--line); border-radius:10px; } menu { display:flex; gap:8px; justify-content:flex-end; padding:0; }
@media (max-width: 600px) { main { grid-template-columns:1fr; padding:10px; } }
```

- [ ] **Step 4: Write `app/static/app.js`**

```javascript
"use strict";
const $ = (sel) => document.querySelector(sel);
const METRICS = ["QR", "N", "LR", "OT", "SN"];
const METRIC_LABEL = { QR: "Quick returns", N: "Nights", LR: "Long runs", OT: "Overtime h", SN: "Short-notice" };
let mode = "baseline";
let state = null;
let options = [];
let chart = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || res.statusText));
  return body;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 4000);
}

async function guarded(fn) {
  try { await fn(); } catch (e) { toast(e.message); }
}

function focusNurses() {
  return new Set(options.flatMap((o) => (o.nurses ? o.nurses.map((n) => n.nurse) : [o.nurse])));
}

async function newScenario() {
  state = await api("/api/scenario", { method: "POST", body: JSON.stringify({ seed: Number($("#seed").value) || 0 }) });
  options = [];
  hideExplanation();
  render();
  await loadAudit();
}

async function nextEvent() {
  const r = await api("/api/next-event", { method: "POST" });
  state = r.state;
  if (r.done) toast("All absence events processed.");
  await loadOptions();
  render();
  await loadAudit();
}

async function loadOptions() {
  hideExplanation();
  if (!state || !state.event || state.event.unfilled) { options = []; return; }
  options = (await api(`/api/options?mode=${mode}`)).options;
  if (mode === "strain") explain();
}

function hideExplanation() { $("#explain-card").classList.add("hidden"); }

async function explain() {
  $("#explain-card").classList.remove("hidden");
  $("#explain-text").textContent = "Generating explanation…";
  $("#explain-meta").textContent = "";
  $("#explain-claims").innerHTML = "";
  try { renderExplanation(await api("/api/explain", { method: "POST" })); }
  catch (e) { $("#explain-text").textContent = `Explanation unavailable: ${e.message}`; }
}

function renderExplanation(r) {
  const e = r.explanation;
  const c = r.check;
  const badge = c.verified ? '<span class="badge ok">✅ verified</span>' : '<span class="badge bad">⚠️ claim mismatch</span>';
  $("#explain-meta").innerHTML = `${badge} <span class="src">${esc(r.source)} · ${r.latency_ms} ms</span>`;
  $("#explain-text").textContent = e.text;
  const issues = [];
  if (c.claims_false) issues.push(`${c.claims_false} of ${c.claims_total} claims do not match the data`);
  if (c.unsupported_numbers.length) issues.push(`unsupported numbers: ${c.unsupported_numbers.join(", ")}`);
  if (!c.recommendation_correct) issues.push("recommendation differs from the top-ranked option");
  $("#explain-claims").innerHTML = `<li>Main trade-off: ${esc(String(e.main_tradeoff).replace("_", " "))}</li>` +
    issues.map((i) => `<li class="warn">${esc(i)}</li>`).join("");
}

function askReason() {
  return new Promise((resolve) => {
    const dlg = $("#override-dlg");
    dlg.returnValue = "";
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok" ? $("#override-reason").value : null), { once: true });
    dlg.showModal();
  });
}

async function applyOption(opt) {
  let reason = null;
  if (opt.rank !== 1) {
    reason = await askReason();
    if (!reason) return;
  }
  const r = await api("/api/apply", { method: "POST", body: JSON.stringify({ option_id: opt.id, mode, override_reason: reason }) });
  state = r.state;
  options = [];
  hideExplanation();
  render();
  await loadAudit();
}

async function setMode(m) {
  mode = m;
  document.querySelectorAll(".mode").forEach((b) => b.classList.toggle("active", b.dataset.mode === m));
  $("#policy-card").classList.toggle("hidden", m !== "strain");
  if (state) { await loadOptions(); render(); }
}

function render() { renderEvent(); renderOptions(); renderGrid(); renderStrain(); }

function renderEvent() {
  $("#remaining").textContent = state ? `${state.remaining_events} events left · ${state.unfilled.length} unfilled` : "";
  const ev = state && state.event;
  const el = $("#event");
  if (!ev) { el.textContent = "No open event. Press “Next event”."; return; }
  el.innerHTML = `<b>${esc(ev.absent)}</b> is absent for the <b>${ev.shift}</b> shift on day <b>${ev.day + 1}</b> ` +
    `(week ${Math.floor(ev.day / 7) + 1}), notified <b>${ev.notice_h} h</b> before the start.` +
    (ev.unfilled ? '<div class="warn">No feasible repair option — the shift runs short.</div>' : "");
}

function applyBtn(o) {
  return `<button data-opt="${esc(o.id)}" class="${o.rank === 1 ? "primary" : ""}">${o.rank === 1 ? "Apply (top)" : "Apply"}</button>`;
}

function metricCell(n, m) {
  const b = n.before[m];
  const a = n.after[m];
  return `<span class="${a > b ? "up" : ""}">${esc(n.nurse)}: ${b}→${a}</span>`;
}

function renderOptions() {
  const el = $("#options");
  if (!options.length) { el.innerHTML = ""; return; }
  const head = mode === "baseline"
    ? "<tr><th>#</th><th>Change</th><th>Nurse</th><th>Contract h/wk</th><th>Hours this period</th><th>Changes</th><th></th></tr>"
    : "<tr><th>#</th><th>ORTEC #</th><th>Change</th>" + METRICS.map((m) => `<th title="${METRIC_LABEL[m]}">${m}</th>`).join("") + "<th>Δ strain</th><th></th></tr>";
  const rows = options.map((o) => (mode === "baseline"
    ? `<tr class="${o.rank === 1 ? "top" : ""}"><td>${o.rank}</td><td>${esc(o.change_text)}</td><td>${esc(o.nurse)}</td>` +
      `<td>${o.contract_h.toFixed(1)}</td><td>${o.hours_period.toFixed(1)}</td><td>${o.n_changes}</td><td>${applyBtn(o)}</td></tr>`
    : `<tr class="${o.rank === 1 ? "top" : ""}"><td>${o.rank}</td><td>${o.rank_baseline}</td><td>${esc(o.change_text)}</td>` +
      METRICS.map((m) => `<td>${o.nurses.map((n) => metricCell(n, m)).join("<br>")}</td>`).join("") +
      `<td>${o.delta_strain.toFixed(2)}</td><td>${applyBtn(o)}</td></tr>`)).join("");
  el.innerHTML = `<table class="opts">${head}${rows}</table>`;
  el.querySelectorAll("button[data-opt]").forEach((b) =>
    b.addEventListener("click", () => guarded(() => applyOption(options.find((o) => o.id === b.dataset.opt)))));
}

function renderGrid() {
  const g = $("#grid");
  if (!state) { g.innerHTML = ""; return; }
  const key = ([n, d]) => `${n}|${d}`;
  const leave = new Set(state.leave.map(key));
  const absent = new Set(state.absent.map(key));
  const changed = new Set(state.changed.map(key));
  const focus = focusNurses();
  const ev = state.event;
  let html = "<tr><th></th>" + Array.from({ length: state.days }, (_, d) => `<th class="${d % 7 === 0 ? "wk" : ""}">${d + 1}</th>`).join("") + "</tr>";
  for (const n of state.nurses) {
    html += `<tr class="${focus.has(n.id) ? "focus" : ""}"><th>${n.id}${n.senior ? "★" : ""}</th>`;
    for (let d = 0; d < state.days; d++) {
      const k = `${n.id}|${d}`;
      const s = (state.grid[n.id] || {})[d] || "";
      let cls = s ? `s-${s}` : "";
      let txt = s;
      if (leave.has(k)) { cls = "leave"; txt = "L"; }
      if (absent.has(k)) { cls = "absent"; txt = "X"; }
      if (changed.has(k)) cls += " changed";
      if (ev && ev.absent === n.id && ev.day === d) cls += " event";
      if (d % 7 === 0) cls += " wk";
      html += `<td class="${cls}">${txt}</td>`;
    }
    html += "</tr>";
  }
  g.innerHTML = html;
}

function renderStrain() {
  if (!state) return;
  const k = state.kpis;
  $("#ward-kpis").textContent = `Gini ${k.gini.toFixed(3)} · top-10% QR share ${(k.top10_qr_share * 100).toFixed(0)}% · max QR ${k.max_qr}`;
  if (!window.Chart) return;
  const rows = [...state.strain].sort((a, b) => b.strain - a.strain);
  const focus = focusNurses();
  const data = {
    labels: rows.map((r) => r.nurse),
    datasets: [{ label: "Strain (window)", data: rows.map((r) => r.strain),
      backgroundColor: rows.map((r) => (focus.has(r.nurse) ? "#d97706" : "#1f6feb")) }],
  };
  if (chart) { chart.data = data; chart.update(); return; }
  chart = new Chart($("#strain-chart"), { type: "bar", data, options: { animation: false,
    plugins: { legend: { display: false } }, scales: { x: { ticks: { autoSkip: false, maxRotation: 90, font: { size: 9 } } } } } });
}

async function loadPolicy() {
  const p = await api("/api/policy");
  $("#policy-form").innerHTML = METRICS.map((m) =>
    `<label>${METRIC_LABEL[m]}<br><input type="number" step="0.5" min="0" name="${m}" value="${p.weights[m]}"></label>`).join("") +
    `<label>Look-ahead days<br><input type="number" min="1" max="28" name="forward_days" value="${p.forward_days}"></label>` +
    `<label><input type="checkbox" name="squared" ${p.squared ? "checked" : ""}> Penalise concentration</label>` +
    '<button type="submit" class="primary">Save policy</button>';
}

async function savePolicy(ev) {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const body = {
    weights: Object.fromEntries(METRICS.map((m) => [m, Number(f.get(m))])),
    forward_days: Number(f.get("forward_days")),
    squared: f.get("squared") === "on",
  };
  await api("/api/policy", { method: "PUT", body: JSON.stringify(body) });
  toast("Policy saved — options re-ranked");
  await loadOptions();
  render();
}

async function loadAudit() {
  const rows = (await api("/api/audit")).entries.slice(-15).reverse();
  $("#audit").innerHTML = "<tr><th>Time</th><th>Event</th><th>Mode</th><th>Chosen</th><th>Top</th><th>Override</th><th>Explanation</th></tr>" +
    rows.map((r) => `<tr><td>${esc(r.ts.slice(11, 19))}</td><td>${r.event_id}</td><td>${esc(r.mode)}</td>` +
      `<td>${esc(r.option_id ?? "unfilled")}</td><td>${esc(r.top_option ?? "")}</td><td>${esc(r.override_reason ?? "")}</td>` +
      `<td>${esc(r.explanation_source ?? "")}${r.verified === false ? " ⚠️" : ""}</td></tr>`).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  $("#btn-new").addEventListener("click", () => guarded(newScenario));
  $("#btn-next").addEventListener("click", () => guarded(nextEvent));
  document.querySelectorAll(".mode").forEach((b) => b.addEventListener("click", () => guarded(() => setMode(b.dataset.mode))));
  $("#policy-form").addEventListener("submit", (e) => guarded(() => savePolicy(e)));
  guarded(async () => {
    state = await api("/api/state");
    await loadPolicy();
    await setMode("baseline");
    render();
    await loadAudit();
  });
});
```

- [ ] **Step 5: Verify the server serves the page, and run the regression suite**

Run: `python3 -m pytest tests/test_server.py -q`
Expected: all passed. `test_state_and_index` now serves the real `index.html`.

- [ ] **Step 6: Manual check in the browser**

Run, in the background: `python3 -m uvicorn app.server:app --port 8000`
Then confirm with `curl -s localhost:8000/ | head -5` and `curl -s localhost:8000/app.js | head -2` that both return content. Ask the user to open `http://localhost:8000` and check:
- "Next event" shows an event, options and the grid.
- Toggling to "Strain-aware + AI" shows ranked options and an explanation card. It shows `template` if Ollama is off.
- Applying a non-top option asks for a reason.
- The audit log updates.
- Saving the policy re-ranks the options.

Stop the server afterwards.

---

### Task 11: E3 explanation faithfulness

**Files:**
- Create: `prototype/evaluation/e3_faithfulness.py`
- Test: `prototype/tests/test_e3.py`

**Interfaces:**
- Consumes: `run_scenario(on_event=...)`, `rank_options`, `build_payload`, `explain`, `is_available`, `RESULTS_DIR`, `load_json`.
- Produces:
  - `collect_payloads(n, policy, start_seed=1000, per_seed=5) -> list[dict]`. Half have a different baseline and strain top (`stratum` "differ"), half the same ("same"). Each payload has an added `"_stratum"` key, which is stripped before the LLM call.
  - `summarize(rows, model) -> dict` with keys `model, n, json_valid_rate, claim_accuracy, pct_flagged, recommendation_agreement, tradeoff_correct, latency_p50_ms, latency_p95_ms, fallback_rate`
  - Writes `results/e3_explanations_<model>.jsonl` and `results/e3_summary_<model>.csv`, where `<model>` has `:` replaced by `-`.

- [ ] **Step 1: Write the failing test**

`prototype/tests/test_e3.py`:
```python
from evaluation.e3_faithfulness import collect_payloads, summarize
from sim.ward import load_json


def test_collect_payloads_is_stratified():
    ps = collect_payloads(6, load_json("policy.json"), start_seed=1000, per_seed=3)
    assert len(ps) == 6
    assert sum(p["_stratum"] == "differ" for p in ps) == 3
    assert all(len(p["options"]) >= 2 for p in ps)


def test_summarize_rates():
    rows = [
        {"source": "m", "latency_ms": 100, "claims_total": 2, "claims_false": 0, "n_unsupported": 0,
         "recommendation_correct": True, "tradeoff_correct": True, "verified": True},
        {"source": "template", "latency_ms": 5, "claims_total": 2, "claims_false": 1, "n_unsupported": 1,
         "recommendation_correct": False, "tradeoff_correct": False, "verified": False},
    ]
    s = summarize(rows, "m")
    assert s["n"] == 2 and s["fallback_rate"] == 0.5 and s["json_valid_rate"] == 0.5
    assert s["claim_accuracy"] == 0.75 and s["pct_flagged"] == 0.5
    assert s["latency_p50_ms"] == 100
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_e3.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.e3_faithfulness'`

- [ ] **Step 3: Write `evaluation/e3_faithfulness.py`**

```python
"""E3 — faithfulness of local-LLM explanations, checked against computed numbers (spec §6)."""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from evaluation.stats import RESULTS_DIR
from llm.ollama_client import OLLAMA_URL, is_available
from llm.prompt import build_payload
from llm.service import explain
from sim.engine import run_scenario
from sim.policies import rank_options
from sim.ward import load_json


def collect_payloads(n: int, policy: dict, start_seed: int = 1000, per_seed: int = 5) -> list[dict]:
    want = {"differ": n // 2, "same": n - n // 2}
    got: dict[str, list[dict]] = {"differ": [], "same": []}
    seed = start_seed
    while any(len(got[k]) < want[k] for k in want) and seed < start_seed + 300:
        bucket: dict[str, list[dict]] = {"differ": [], "same": []}

        def on_event(ctx, scored):
            if len(scored) < 2:
                return
            same = rank_options(scored, "baseline")[0] is rank_options(scored, "strain")[0]
            payload = build_payload(ctx, scored, policy)
            payload["_stratum"] = "same" if same else "differ"
            bucket[payload["_stratum"]].append(payload)

        run_scenario(seed, "strain", policy, on_event=on_event)
        rng = np.random.default_rng(seed)
        for k in want:
            items = bucket[k]
            take = min(per_seed, len(items), want[k] - len(got[k]))
            if take > 0:
                got[k].extend(items[i] for i in rng.choice(len(items), size=take, replace=False))
        seed += 1
    return got["differ"] + got["same"]


def summarize(rows: list[dict], model: str) -> dict:
    df = pd.DataFrame(rows)
    llm = df[df.source != "template"]
    claims = df.claims_total.sum()
    flagged = (df.claims_false > 0) | (df.n_unsupported > 0)
    return {
        "model": model, "n": len(df),
        "json_valid_rate": float((df.source != "template").mean()),
        "claim_accuracy": float(1 - df.claims_false.sum() / claims) if claims else 1.0,
        "pct_flagged": float(flagged.mean()),
        "recommendation_agreement": float(df.recommendation_correct.mean()),
        "tradeoff_correct": float(df.tradeoff_correct.mean()),
        "latency_p50_ms": float(llm.latency_ms.median()) if len(llm) else float("nan"),
        "latency_p95_ms": float(llm.latency_ms.quantile(0.95)) if len(llm) else float("nan"),
        "fallback_rate": float((df.source == "template").mean()),
    }


def main() -> None:
    policy = load_json("policy.json")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--model", default=policy["model"])
    ap.add_argument("--timeout", type=float, default=policy["eval_timeout_s"])
    args = ap.parse_args()
    if not is_available():
        print(f"Ollama is not reachable at {OLLAMA_URL}. Start it with `ollama serve` and run "
              f"`ollama pull {args.model}` first.")
        sys.exit(2)
    payloads = collect_payloads(args.n, policy)
    tag = args.model.replace(":", "-")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"e3_explanations_{tag}.jsonl"
    rows = []
    with out.open("w") as fh:
        for i, p in enumerate(payloads):
            stratum = p.pop("_stratum")
            r = explain(p, args.model, args.timeout)
            c = r["check"]
            row = {"i": i, "stratum": stratum, "model": args.model, "source": r["source"],
                   "latency_ms": r["latency_ms"], "error": r["error"],
                   "claims_total": c["claims_total"], "claims_false": c["claims_false"],
                   "n_unsupported": len(c["unsupported_numbers"]),
                   "recommendation_correct": c["recommendation_correct"],
                   "tradeoff_correct": c["tradeoff_correct"], "verified": c["verified"],
                   "ground_truth": c["ground_truth"],
                   "main_tradeoff": r["explanation"].get("main_tradeoff")}
            rows.append(row)
            fh.write(json.dumps({**row, "text": r["explanation"].get("text"), "payload": p}) + "\n")
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{len(payloads)} done")
    summary = pd.DataFrame([summarize(rows, args.model)] +
                           [dict(summarize([r for r in rows if r["stratum"] == s], args.model), model=f"{args.model} [{s}]")
                            for s in ("differ", "same")])
    summary.to_csv(RESULTS_DIR / f"e3_summary_{tag}.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
```

`make_figures.fig_e3` plots every row of the concatenated summaries, including the per-stratum rows. That is intended: it shows whether faithfulness differs when the policies disagree.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_e3.py -v`
Expected: 2 passed

- [ ] **Step 5: Run E3 (requires Ollama)**

Ask the user to run `ollama serve` and `ollama pull qwen3:4b` if they haven't. Then run in the background:
`python3 -m evaluation.e3_faithfulness --n 150`
Optionally, after `ollama pull qwen3:1.7b`: `python3 -m evaluation.e3_faithfulness --n 150 --model qwen3:1.7b`
Expected: `results/e3_summary_qwen3-4b.csv`. Report `claim_accuracy`, `pct_flagged`, `recommendation_agreement` and `latency_p50_ms` to the user. If Ollama is not available, record that E3 is pending and continue with Task 12.

---

### Task 12: E4 agentic future and E2 sensitivity

**Files:**
- Create: `prototype/evaluation/e4_agents.py`, `prototype/evaluation/e2_sensitivity.py`
- Test: `prototype/tests/test_e2_e4.py`

**Interfaces:**
- Consumes: `run_scenario(acceptance=..., absence_rate=...)`, `run_metrics`, `paired_table`, `RESULTS_DIR`, `load_json`.
- Produces:
  - `evaluation.e4_agents`: `MODES=("today","permissive","picky")`, `run_one((seed, policy_name, mode)) -> dict`, `main()`
    - writes `results/e4_runs.csv`, `results/e4_summary.csv` (columns `mode, policy` + metrics), `results/e4_stats.csv`
  - `evaluation.e2_sensitivity`: `CONFIGS`, `make_policy(overrides) -> dict`, `run_one((config, policy_name, seed, overrides, rate)) -> dict`, `main()`
    - writes `results/e2_runs.csv`, `results/e2_stats.csv` (with a `config` column)

- [ ] **Step 1: Write the failing test**

`prototype/tests/test_e2_e4.py`:
```python
from evaluation.e2_sensitivity import CONFIGS, make_policy
from evaluation.e2_sensitivity import run_one as e2_run
from evaluation.e4_agents import run_one as e4_run


def test_make_policy_overrides():
    p = make_policy({"weights_scale": {"QR": 2}, "forward_days": 7, "squared": False})
    assert p["weights"]["QR"] == 6.0 and p["weights"]["N"] == 1.0
    assert p["forward_days"] == 7 and p["squared"] is False
    assert [c[0] for c in CONFIGS][0] == "default"


def test_e4_picky_agents_run():
    row = e4_run((0, "strain", "picky"))
    assert row["mode"] == "picky" and row["policy"] == "strain" and row["offers_per_fill"] >= 1


def test_e2_run_uses_default_weights_for_measurement():
    row = e2_run(("w_qr_x2", "strain", 0, {"weights_scale": {"QR": 2}}, None))
    assert row["config"] == "w_qr_x2" and "gini_strain" in row
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_e2_e4.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.e2_sensitivity'`

- [ ] **Step 3: Write `evaluation/e4_agents.py`**

```python
"""E4 — agentic future: nurse agents accept or decline offers (spec §6, Section 8 numbers)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.ward import load_json

MODES = ("today", "permissive", "picky")
E4_METRICS = ["unfilled", "QR_total", "gini_strain", "top10_qr_share", "max_qr", "offers_per_fill"]


def run_one(job) -> dict:
    seed, policy_name, mode = job
    policy = load_json("policy.json")
    row = run_metrics(run_scenario(seed, policy_name, policy, acceptance=mode), policy["weights"])
    row.update(seed=seed, policy=policy_name, mode=mode)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    jobs = [(s, p, m) for s in range(args.seeds) for p in ("baseline", "strain") for m in MODES]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        runs = pd.DataFrame(list(ex.map(run_one, jobs, chunksize=4)))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs.to_csv(RESULTS_DIR / "e4_runs.csv", index=False)
    summary = runs.groupby(["mode", "policy"], as_index=False)[E4_METRICS].mean()
    summary.to_csv(RESULTS_DIR / "e4_summary.csv", index=False)
    stats = pd.concat([paired_table(runs[runs["mode"] == m], E4_METRICS).assign(mode=m) for m in MODES],
                      ignore_index=True)
    stats.to_csv(RESULTS_DIR / "e4_stats.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `evaluation/e2_sensitivity.py`**

```python
"""E2 — sensitivity and ablation of the strain-aware effect (spec §6)."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from evaluation.stats import RESULTS_DIR, paired_table
from sim.engine import run_scenario
from sim.metrics import run_metrics
from sim.ward import load_json

CONFIGS = [
    ("default", {}, None),
    ("w_qr_x0.5", {"weights_scale": {"QR": 0.5}}, None),
    ("w_qr_x2", {"weights_scale": {"QR": 2}}, None),
    ("forward_7d", {"forward_days": 7}, None),
    ("forward_14d", {"forward_days": 14}, None),
    ("linear_cost", {"squared": False}, None),
    ("absence_3pct", {}, 0.03),
    ("absence_8pct", {}, 0.08),
]
E2_METRICS = ["gini_strain", "top10_qr_share", "QR_total", "max_qr", "nurses_qr_ge3_28d",
              "unfilled", "changes_per_repair"]


def make_policy(overrides: dict) -> dict:
    p = load_json("policy.json")
    scale = overrides.get("weights_scale", {})
    p["weights"] = {k: v * scale.get(k, 1) for k, v in p["weights"].items()}
    for k in ("forward_days", "squared"):
        if k in overrides:
            p[k] = overrides[k]
    return p


def run_one(job) -> dict:
    config, policy_name, seed, overrides, rate = job
    res = run_scenario(seed, policy_name, make_policy(overrides), absence_rate=rate)
    # Always measure with the default weights so every configuration is comparable.
    row = run_metrics(res, load_json("policy.json")["weights"])
    row.update(config=config, policy=policy_name, seed=seed, rate=rate if rate is not None else -1)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    rates = sorted({r for _, _, r in CONFIGS}, key=lambda r: -1 if r is None else r)
    jobs = [(f"baseline@{r}", "baseline", s, {}, r) for r in rates for s in range(args.seeds)]
    jobs += [(name, "strain", s, ov, r) for name, ov, r in CONFIGS for s in range(args.seeds)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        runs = pd.DataFrame(list(ex.map(run_one, jobs, chunksize=4)))
    RESULTS_DIR.mkdir(exist_ok=True)
    runs.to_csv(RESULTS_DIR / "e2_runs.csv", index=False)
    tables = []
    for name, _, r in CONFIGS:
        rate = r if r is not None else -1
        pair = runs[((runs.config == name) | (runs.config == f"baseline@{r}")) & (runs.rate == rate)]
        tables.append(paired_table(pair, E2_METRICS).assign(config=name))
    stats = pd.concat(tables, ignore_index=True)
    stats.to_csv(RESULTS_DIR / "e2_stats.csv", index=False)
    print(stats[stats.metric.isin(["gini_strain", "unfilled"])].to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_e2_e4.py -v`
Expected: 3 passed

- [ ] **Step 6: Run E4 and E2 (background), then the figures**

Run: `python3 -m evaluation.e4_agents --seeds 100 --workers 4 && python3 -m evaluation.e2_sensitivity --seeds 50 --workers 4 && python3 -m evaluation.make_figures`
Expected:
- `results/e4_summary.csv` with 6 rows (3 modes × 2 policies) and `results/e2_stats.csv` with 8 configs × 7 metrics.
- `figures/e4_agents.png` and `figures/e2_sensitivity.png`.

Report the E4 numbers (unfilled and QR_total per mode × policy) to the user. These **replace** the unsupported "49 → ~1" and "+26%" figures in report Sections 7 and 8.

---

### Task 13: Summary with economics bridge, and README

**Files:**
- Create: `prototype/evaluation/make_summary.py`, `prototype/README.md`
- Test: `prototype/tests/test_summary.py`

**Interfaces:**
- Consumes: the CSVs from Tasks 7, 11 and 12, `RESULTS_DIR`, `load_json`.
- Produces:
  - `md_table(df, cols) -> str`
  - `economics_bridge(runs, ward_cfg) -> dict` with keys `dqr_per_nurse_month, vedaa_pct, rct_pct, vedaa_days, rct_days, value_low_eur, value_high_eur`
  - `build_summary() -> str`
  - `main()`, which writes `results/summary.md`

- [ ] **Step 1: Write the failing test**

`prototype/tests/test_summary.py`:
```python
import pandas as pd
import pytest

from evaluation.make_summary import economics_bridge, md_table


def test_md_table():
    out = md_table(pd.DataFrame([{"a": 1.23456, "b": "x"}]), ["a", "b"])
    assert out.splitlines()[0] == "| a | b |" and "1.235" in out


def test_economics_bridge():
    runs = pd.DataFrame([{"policy": "baseline", "QR_total": 140}, {"policy": "strain", "QR_total": 100}])
    e = economics_bridge(runs, {"n_nurses": 70, "days": 56})
    assert e["dqr_per_nurse_month"] == pytest.approx(40 / 140)
    assert e["vedaa_pct"] == pytest.approx(40 / 140 * 0.07)
    assert e["rct_pct"] == pytest.approx(min(0.44, 0.44 * (40 / 140) / 0.5))
    assert e["vedaa_days"] == pytest.approx(700 * e["vedaa_pct"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_summary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evaluation.make_summary'`

- [ ] **Step 3: Write `evaluation/make_summary.py`**

```python
"""Auto-generated evaluation summary for the deck (spec §6), incl. the economics bridge."""
from __future__ import annotations

import glob
import json

import pandas as pd

from evaluation.stats import RESULTS_DIR
from sim.ward import load_json

WARD_ABSENCE_DAYS = 700           # report Component 1/4: 60-FTE ward at 5.33% absence
DAY_VALUE_EUR = (250, 550)        # report Component 4 range per absence day
VEDAA_PER_QR_MONTH = 0.21 / 3     # Vedaa et al. 2017: ~3 QR/month ~ +21% absence days
RCT_MAX = 0.44                    # 2025 cluster RCT: IRR 0.56 when short rest roughly halved


def md_table(df: pd.DataFrame, cols: list[str]) -> str:
    def fmt(v):
        return f"{v:.3f}" if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join(lines)


def economics_bridge(runs: pd.DataFrame, ward_cfg: dict) -> dict:
    qb = runs.loc[runs.policy == "baseline", "QR_total"].mean()
    qs = runs.loc[runs.policy == "strain", "QR_total"].mean()
    nurse_months = ward_cfg["n_nurses"] * ward_cfg["days"] / 28
    dqr = (qb - qs) / nurse_months
    vedaa = max(0.0, dqr * VEDAA_PER_QR_MONTH)
    rel = (qb - qs) / qb if qb else 0.0
    rct = min(RCT_MAX, max(0.0, RCT_MAX * rel / 0.5))
    lo, hi = sorted([vedaa, rct])
    return {"dqr_per_nurse_month": dqr, "vedaa_pct": vedaa, "rct_pct": rct,
            "vedaa_days": WARD_ABSENCE_DAYS * vedaa, "rct_days": WARD_ABSENCE_DAYS * rct,
            "value_low_eur": WARD_ABSENCE_DAYS * lo * DAY_VALUE_EUR[0],
            "value_high_eur": WARD_ABSENCE_DAYS * hi * DAY_VALUE_EUR[1]}


def _read(name):
    path = RESULTS_DIR / name
    return pd.read_csv(path) if path.exists() else None


def build_summary() -> str:
    ward_cfg, policy = load_json("ward.json"), load_json("policy.json")
    out = ["# Evaluation summary (auto-generated)", "",
           "Synthetic ward; ORTEC-like baseline is a proxy built from vendor-described logic. "
           "Lower is better for every metric. ★ = |effect dz| ≥ 0.5 and p < 0.01 (deck candidate).", ""]
    if (e1 := _read("e1_stats.csv")) is not None:
        e1 = e1.assign(abs_dz=e1.effect_dz.abs()).sort_values("abs_dz", ascending=False)
        e1["flag"] = ["★" if (abs(d) >= 0.5 and p < 0.01) else "" for d, p in zip(e1.effect_dz, e1.wilcoxon_p)]
        out += ["## E1 — Policy A/B (paired seeds)", "",
                md_table(e1, ["flag", "metric", "mean_baseline", "mean_strain", "mean_diff", "ci_low",
                              "ci_high", "rel_change", "wilcoxon_p", "effect_dz", "win_rate", "n"]), ""]
    if (e2 := _read("e2_stats.csv")) is not None:
        sub = e2[e2.metric.isin(["gini_strain", "top10_qr_share", "unfilled"])]
        out += ["## E2 — Sensitivity and ablation", "",
                md_table(sub, ["config", "metric", "mean_diff", "ci_low", "ci_high", "wilcoxon_p"]), ""]
    e3_files = sorted(glob.glob(str(RESULTS_DIR / "e3_summary_*.csv")))
    if e3_files:
        e3 = pd.concat([pd.read_csv(f) for f in e3_files], ignore_index=True)
        out += ["## E3 — Explanation faithfulness", "",
                md_table(e3, ["model", "n", "json_valid_rate", "claim_accuracy", "pct_flagged",
                              "recommendation_agreement", "tradeoff_correct", "latency_p50_ms",
                              "latency_p95_ms", "fallback_rate"]), ""]
    else:
        out += ["## E3 — Explanation faithfulness", "", "_Not run yet (requires Ollama)._", ""]
    if (e4 := _read("e4_summary.csv")) is not None:
        out += ["## E4 — Agentic future", "",
                md_table(e4, ["mode", "policy", "unfilled", "QR_total", "gini_strain", "max_qr",
                              "offers_per_fill"]), "",
                "Acceptance probabilities (0.9 permissive; picky 0.9 / 0.3) are assumptions.", ""]
    if (runs := _read("e1_runs.csv")) is not None:
        e = economics_bridge(runs, ward_cfg)
        out += ["## Economics bridge (extrapolation — not a simulation result)", "",
                f"- Quick returns avoided per nurse-month: **{e['dqr_per_nurse_month']:.3f}**",
                f"- Vedaa et al. (2017) anchor: ~{e['vedaa_pct'] * 100:.1f}% fewer absence days "
                f"≈ {e['vedaa_days']:.0f} days per 60-FTE ward-year",
                f"- 2025 cluster-RCT anchor: ~{e['rct_pct'] * 100:.1f}% ≈ {e['rct_days']:.0f} days",
                f"- Value at €250–€550/day: **€{e['value_low_eur']:,.0f} – €{e['value_high_eur']:,.0f}** "
                "per ward-year (compare with the Economics section's 1–18% assumption)",
                "- Assumes the absence effects transfer from Norwegian settings and scale linearly.", ""]
    out += ["## Run configuration", "", "```json", json.dumps({"ward": ward_cfg, "policy": policy}, indent=2),
            "```", ""]
    return "\n".join(out)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "summary.md").write_text(build_summary())
    print("wrote", RESULTS_DIR / "summary.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_summary.py -v`
Expected: 2 passed

- [ ] **Step 5: Write `prototype/README.md`**

````markdown
# Strain-aware roster repair — prototype

Synthetic 37-bed ward (~60 FTE). Compares an ORTEC-like repair (stability + contract fit) with a
strain-aware repair that ranks the same feasible options by cumulative person-level strain, and
explains the trade-off with a local LLM. Spec: `../docs/superpowers/specs/2026-10-05-roster-repair-prototype-design.md`.

## Setup
Python packages are already installed (numpy, pandas, scipy, matplotlib, fastapi, uvicorn, httpx, pytest).
For the LLM (optional — the app falls back to a template):
```bash
brew install ollama
ollama serve            # keep running in a separate terminal
ollama pull qwen3:4b    # optional lighter model: qwen3:1.7b
```

## Run the app (demo)
```bash
cd prototype
python3 -m uvicorn app.server:app --port 8000
```
Open http://localhost:8000 → "Next event" → toggle "ORTEC-like" / "Strain-aware + AI".

## Run the evaluation
```bash
cd prototype
python3 -m evaluation.calibrate                 # sanity check of the synthetic ward
python3 -m evaluation.e1_ab --seeds 200         # policy A/B
python3 -m evaluation.e3_faithfulness --n 150   # needs Ollama
python3 -m evaluation.e4_agents --seeds 100     # agentic future
python3 -m evaluation.e2_sensitivity --seeds 50 # sensitivity
python3 -m evaluation.make_figures && python3 -m evaluation.make_summary
```
Outputs: `results/*.csv`, `results/summary.md`, `figures/*.png`.

## Tests
```bash
cd prototype && python3 -m pytest -q
```

## Limitations
Synthetic data; the baseline is a proxy for ORTEC's vendor-described logic, not its real configuration;
batch runs assume the planner accepts the top option; absences are exogenous; agent acceptance
probabilities and policy weights are assumptions.
````

- [ ] **Step 6: Final checkpoint**

Run: `python3 -m pytest -q && python3 -m evaluation.make_figures && python3 -m evaluation.make_summary`
Expected: all tests pass; `results/summary.md` exists, with E1, E2 and E4 sections, the E3 section (or "Not run yet") and the economics bridge. Show the user the E1 table and the economics-bridge lines.
