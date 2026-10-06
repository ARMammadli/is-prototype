from helpers import make_ward, roster_with
from sim.policies import (RepairContext, generate_candidates, rank_options, score_options)

POLICY = {"weights": {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5},
          "back_days": 28, "forward_days": 28, "squared": True}


def _ctx(ward, roster, day, shift, absent="Nurse_03", notice_h=5.0):
    return RepairContext(ward=ward, roster=roster, blocked={(absent, day)}, day=day, shift=shift,
                         absent=absent, notice_h=notice_h, event_id=0, seed=0)


def _qr_setup():
    # Nurse_01 worked E on day 1 (taking D on day 2 creates a quick return) and has the most
    # remaining contract hours; Nurse_02 has fewer remaining hours but no quick return.
    w = make_ward(n=3, days=14, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {"Nurse_01": {1: "E"}, "Nurse_02": {5: "D", 6: "D", 7: "D", 8: "D"}})
    return w, r, _ctx(w, r, 2, "D")


def test_baseline_prefers_contract_fit_strain_prefers_no_quick_return():
    _, _, ctx = _qr_setup()
    scored = score_options(ctx, generate_candidates(ctx), POLICY)
    base_top = rank_options(scored, "baseline")[0].option
    strain_top = rank_options(scored, "strain")[0].option
    assert base_top.changes[0].nurse == "Nurse_01"
    assert strain_top.changes[0].nurse == "Nurse_02"


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
    r = roster_with(w, {"Nurse_01": {1: "N"}})  # N on day 1 ends 07:30 on day 2 -> cannot take D on day 2
    w.available.discard(("Nurse_02", 2))
    ctx = _ctx(w, r, 2, "D", absent="Nurse_04")
    nurses = {o.changes[0].nurse for o in generate_candidates(ctx)}
    assert nurses == {"Nurse_03"}


def test_move_with_backfill_is_generated_and_ranked_after_direct_by_baseline():
    w = make_ward(n=4, days=14, demand={"D": 1, "E": 1, "N": 0})
    r = roster_with(w, {"Nurse_01": {2: "E"}})
    ctx = _ctx(w, r, 2, "D", absent="Nurse_04")
    options = generate_candidates(ctx)
    kinds = sorted(o.kind for o in options)
    assert kinds == ["direct", "direct", "move", "move"]
    scored = score_options(ctx, options, POLICY)
    ranked = rank_options(scored, "baseline")
    assert [s.option.kind for s in ranked[:2]] == ["direct", "direct"]
    move = next(o for o in options if o.kind == "move")
    assert move.n_changes == 2 and move.extra_nurse in {"Nurse_02", "Nurse_03"}


def test_only_senior_candidates_when_shift_lost_its_senior():
    w = make_ward(n=3, days=14, seniors=[False, True, True], demand={"D": 1, "E": 0, "N": 0})
    ctx = _ctx(w, roster_with(w, {}), 2, "D")  # Nurse_03 (senior) is absent
    assert {o.changes[0].nurse for o in generate_candidates(ctx)} == {"Nurse_02"}


def test_non_senior_fallback_when_no_senior_is_available():
    w = make_ward(n=3, days=14, seniors=[False, False, True], demand={"D": 1, "E": 0, "N": 0})
    ctx = _ctx(w, roster_with(w, {}), 2, "D")
    assert {o.changes[0].nurse for o in generate_candidates(ctx)} == {"Nurse_01", "Nurse_02"}


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

def test_senior_only_filter_applies_before_move_sampling():
    w = make_ward(n=7, days=14, seniors=[False] * 4 + [True] * 3, demand={"D": 1, "E": 0, "N": 0})
    r = roster_with(w, {f"Nurse_0{i}": {2: "E"} for i in range(1, 7)})
    ctx = _ctx(w, r, 2, "D", absent="Nurse_07")  # senior absent; only movers exist (4 non-senior, 2 senior)
    for seed in range(10):
        ctx.seed = seed
        opts = generate_candidates(ctx, max_moves=2)
        assert opts and all(w.nurse(o.changes[0].nurse).senior for o in opts)
