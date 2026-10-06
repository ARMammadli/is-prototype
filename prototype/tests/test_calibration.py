from evaluation.calibrate import calibration_rows


def test_ward_is_calibrated():
    rows = calibration_rows(range(3))
    assert all(r["base_gaps"] == 0 for r in rows), rows
    mean_direct = sum(r["mean_direct"] for r in rows) / len(rows)
    assert 2.0 <= mean_direct <= 8.0, rows
    assert all(50 <= r["events"] <= 120 for r in rows), rows
    mean_qr = sum(r["base_qr_per_nurse"] for r in rows) / len(rows)
    assert 1.0 <= mean_qr <= 4.0, rows
