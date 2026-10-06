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
    for k in ("qr_base_roster", "qr_base_kept", "qr_from_repairs"):
        assert k in m
    assert m["qr_base_kept"] + m["qr_from_repairs"] == m["QR_total"]


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


def test_peek_event_id_tracks_queue():
    from sim.engine import Scenario
    sc = Scenario(1)
    first = sc.peek_event_id()
    assert first == sc.events[0].event_id
    ctx = sc.next_context()
    assert ctx is not None and (sc.peek_event_id() is None or sc.peek_event_id() > ctx.event_id)
    while sc.next_context() is not None:
        pass
    assert sc.peek_event_id() is None
