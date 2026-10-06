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
