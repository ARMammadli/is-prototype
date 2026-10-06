from helpers import make_ward, roster_with
from sim.rules import nurse_violations


def test_single_quick_return_is_legal():
    r = roster_with(make_ward(), {"Nurse_01": {0: "E", 1: "D"}})
    assert nurse_violations(r, "Nurse_01") == []


def test_two_quick_returns_within_seven_days_violate():
    r = roster_with(make_ward(), {"Nurse_01": {0: "E", 1: "D", 3: "E", 4: "D"}})
    assert any("quick returns" in v for v in nurse_violations(r, "Nurse_01"))


def test_quick_returns_exactly_seven_days_apart_are_legal():
    r = roster_with(make_ward(), {"Nurse_01": {0: "E", 1: "D", 7: "E", 8: "D"}})
    assert nurse_violations(r, "Nurse_01") == []


def test_night_then_evening_is_a_legal_quick_return():
    r = roster_with(make_ward(), {"Nurse_01": {0: "N", 1: "E"}})
    assert nurse_violations(r, "Nurse_01") == []


def test_night_then_day_violates_minimum_rest():
    r = roster_with(make_ward(), {"Nurse_01": {0: "N", 1: "D"}})
    assert any("rest" in v for v in nurse_violations(r, "Nurse_01"))


def test_six_consecutive_days_are_legal():
    r = roster_with(make_ward(), {"Nurse_01": {d: "D" for d in range(6)}})
    assert nurse_violations(r, "Nurse_01") == []


def test_seven_consecutive_days_violate():
    r = roster_with(make_ward(), {"Nurse_01": {d: "D" for d in range(7)}})
    assert any("consecutive" in v for v in nurse_violations(r, "Nurse_01"))


def test_short_rest_after_three_nights_violates():
    r = roster_with(make_ward(), {"Nurse_01": {0: "N", 1: "N", 2: "N", 4: "D"}})
    assert any("46" in v for v in nurse_violations(r, "Nurse_01"))


def test_enough_rest_after_three_nights_is_legal():
    r = roster_with(make_ward(), {"Nurse_01": {0: "N", 1: "N", 2: "N", 5: "E"}})
    assert nurse_violations(r, "Nurse_01") == []


def test_night_exempt_nurse_cannot_work_nights():
    w = make_ward(night_ok=[False, True, True, True])
    r = roster_with(w, {"Nurse_01": {0: "N"}})
    assert any("night" in v for v in nurse_violations(r, "Nurse_01"))


def test_work_on_blocked_day_violates():
    r = roster_with(make_ward(), {"Nurse_01": {2: "D"}})
    assert any("blocked" in v for v in nurse_violations(r, "Nurse_01", blocked={("Nurse_01", 2)}))


def test_window_restricts_the_check():
    r = roster_with(make_ward(), {"Nurse_01": {0: "N", 1: "D"}})
    assert nurse_violations(r, "Nurse_01", lo=5, hi=10) == []


def test_roster_copy_is_independent():
    r = roster_with(make_ward(), {"Nurse_01": {0: "D"}})
    c = r.copy()
    c.assign("Nurse_01", 1, "E")
    c.short_notice["Nurse_01"].append(1)
    assert r.get("Nurse_01", 1) is None and r.short_notice["Nurse_01"] == []
