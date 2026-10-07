## Item 6: GenAI-chooser arm (arm C, from git history c3385cf)

Seeds and A rows identical to the current E6 run: True.

| Measure | Arm C mean | C better than A (wards) | equal |
|---|---|---|---|
| QR_total | 120.000 | 5 | 0 |
| nurses_qr_ge3_28d | 10.000 | 5 | 0 |
| max_qr | 5.000 | 4 | 1 |
| unfilled | 1.000 | 1 | 4 |
| SN_total | 137.000 | 0 | 0 |
| changes_per_repair | 1.968 | 0 | 0 |
| gini_sn | 0.343 | 5 | 0 |

## Item 7: quick returns created by repairs vs already in the base roster (E2 robustness runs, 50 wards per row)

| Absence | Policy | QR total | Kept from base roster | Created by repairs | Share created by repairs | QR_total = kept + created |
|---|---|---|---|---|---|---|
| 3% | ORTEC-like | 182.1 | 175.7 | 6.4 | 3.5% | True (n=50) |
| 3% | Rule | 142.7 | 142.3 | 0.4 | 0.3% | True (n=50) |
| 8% | ORTEC-like | 173.9 | 158.7 | 15.1 | 8.7% | True (n=50) |
| 8% | Rule | 87.3 | 86.2 | 1.0 | 1.2% | True (n=50) |