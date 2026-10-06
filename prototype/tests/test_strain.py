from helpers import make_ward, roster_with
from sim.strain import nurse_metrics, qr_transitions, strain, window

W = {"QR": 3.0, "N": 1.0, "LR": 2.0, "OT": 0.5, "SN": 1.5}


def test_metrics_on_fixed_roster():
    w = make_ward(days=28)
    r = roster_with(w, {"Nurse_01": {0: "E", 1: "D", 3: "N", 4: "N",
                                10: "D", 11: "D", 12: "D", 13: "D", 14: "D", 15: "D"}})
    r.short_notice["Nurse_01"].extend([11, 30])
    assert nurse_metrics(r, "Nurse_01", 0, 27) == {"QR": 1, "N": 2, "LR": 1, "OT": 0.0, "SN": 1}


def test_overtime_above_contract():
    w = make_ward(days=7, fte=0.25)  # 9 h/week
    r = roster_with(w, {"Nurse_01": {0: "D", 1: "D"}})
    assert nurse_metrics(r, "Nurse_01", 0, 6)["OT"] == 8.0


def test_window_is_clipped_to_horizon():
    assert window(2, 56) == (0, 30)
    assert window(50, 56) == (22, 55)
    assert window(10, 56, back=28, forward=7) == (0, 17)


def test_qr_transitions():
    r = roster_with(make_ward(), {"Nurse_01": {0: "E", 1: "D", 2: "D", 3: "N", 4: "E"}})
    assert qr_transitions(r, "Nurse_01") == [(0, 1), (3, 4)]


def test_strain_weighted_sum():
    assert strain({"QR": 1, "N": 2, "LR": 1, "OT": 0.0, "SN": 1}, W) == 8.5
