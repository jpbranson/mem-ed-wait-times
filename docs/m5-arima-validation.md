# M5 ARIMA development pilot — 2026-09-23 UTC

Status: two nonseasonal candidates evaluated locally; no public forecast qualifies for release. Calibration and final holdout remain unscored.

The [frozen protocol](m5-study-protocol.md) named ARIMA(1,0,0) and ARIMA(1,1,0) before these scores were calculated. The [benchmark checkpoint](m5-validation.md) supplies the exact input snapshot. Both pilots use at most 28 days, daily UTC refits, hourly state updates, no gap imputation, and nonnegative output clipping. ARIMA(1,0,0) includes a constant; ARIMA(1,1,0) has no drift. No neighboring or unavailable future regressors were used.

The study evaluated 20 hospitals and four horizons in 26.3 seconds using four local workers. There were 520 converged daily fits and 40 support abstentions; 0 fits failed. Every facility abstained on the first development day because its padded 28-day training window includes the partial start of the source snapshot. This is counted, not silently trimmed.

The better ARIMA candidate lowered matched-origin MAE in 41/80 combinations. Only 1/80 met the provisional **error-only** screen of at least 5% and 1 minute MAE reduction with no worse RMSE. Availability was about 92.8%, below the provisional 95% gate. This is development selection on a common subset, not a final-test improvement claim. Intervals, dependent-error uncertainty, seasonal diagnostics, SARIMA/SARIMAX and delayed-availability ARIMA sensitivity remain unevaluated. All public-release decisions stay disabled.

| Facility | Horizon | Strongest simple | Better pilot | Simple MAE | Pilot MAE | Gain (min) | Error screen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| anderson | 15 | carry_forward | arima_110 | 10.91 | 11.22 | -0.31 | Fail |
| anderson | 30 | carry_forward | arima_110 | 21.85 | 21.71 | +0.14 | Fail |
| anderson | 60 | m1_median | arima_100 | 32.00 | 30.88 | +1.12 | Fail |
| anderson | 120 | m1_median | arima_100 | 31.70 | 32.24 | -0.55 | Fail |
| arlington | 15 | carry_forward | arima_110 | 5.42 | 6.00 | -0.57 | Fail |
| arlington | 30 | carry_forward | arima_110 | 9.88 | 10.14 | -0.26 | Fail |
| arlington | 60 | m1_median | arima_110 | 15.13 | 15.30 | -0.17 | Fail |
| arlington | 120 | m1_median | arima_110 | 15.12 | 17.77 | -2.65 | Fail |
| baptist-medical-center | 15 | carry_forward | arima_110 | 12.78 | 13.20 | -0.42 | Fail |
| baptist-medical-center | 30 | carry_forward | arima_100 | 22.04 | 22.22 | -0.18 | Fail |
| baptist-medical-center | 60 | carry_forward | arima_100 | 34.55 | 33.33 | +1.21 | Fail |
| baptist-medical-center | 120 | carry_forward | arima_110 | 39.75 | 39.47 | +0.29 | Fail |
| baptist-medical-center-attala | 15 | carry_forward | arima_110 | 1.27 | 1.34 | -0.07 | Fail |
| baptist-medical-center-attala | 30 | carry_forward | arima_110 | 3.04 | 3.08 | -0.04 | Fail |
| baptist-medical-center-attala | 60 | carry_forward | arima_100 | 6.34 | 6.32 | +0.02 | Fail |
| baptist-medical-center-attala | 120 | carry_forward | arima_100 | 10.60 | 10.26 | +0.34 | Fail |
| baptist-medical-center-leake | 15 | carry_forward | arima_110 | 1.31 | 1.34 | -0.02 | Fail |
| baptist-medical-center-leake | 30 | carry_forward | arima_110 | 2.40 | 2.41 | -0.01 | Fail |
| baptist-medical-center-leake | 60 | carry_forward | arima_110 | 3.85 | 3.84 | +0.01 | Fail |
| baptist-medical-center-leake | 120 | carry_forward | arima_110 | 6.56 | 6.54 | +0.02 | Fail |
| baptist-medical-center-yazoo | 15 | carry_forward | arima_110 | 4.56 | 4.81 | -0.25 | Fail |
| baptist-medical-center-yazoo | 30 | carry_forward | arima_110 | 8.47 | 8.55 | -0.07 | Fail |
| baptist-medical-center-yazoo | 60 | m1_median | arima_100 | 13.21 | 13.34 | -0.13 | Fail |
| baptist-medical-center-yazoo | 120 | m1_median | arima_100 | 13.23 | 13.69 | -0.47 | Fail |
| booneville | 15 | carry_forward | arima_110 | 0.84 | 0.87 | -0.03 | Fail |
| booneville | 30 | carry_forward | arima_110 | 1.45 | 1.47 | -0.02 | Fail |
| booneville | 60 | carry_forward | arima_110 | 2.30 | 2.29 | +0.01 | Fail |
| booneville | 120 | carry_forward | arima_100 | 3.90 | 3.79 | +0.11 | Fail |
| calhoun | 15 | carry_forward | arima_110 | 0.58 | 0.63 | -0.04 | Fail |
| calhoun | 30 | carry_forward | arima_110 | 1.90 | 1.93 | -0.03 | Fail |
| calhoun | 60 | carry_forward | arima_110 | 2.83 | 2.85 | -0.02 | Fail |
| calhoun | 120 | carry_forward | arima_100 | 4.69 | 4.63 | +0.06 | Fail |
| childrens | 15 | carry_forward | arima_110 | 2.40 | 2.36 | +0.04 | Fail |
| childrens | 30 | carry_forward | arima_110 | 4.01 | 3.83 | +0.17 | Fail |
| childrens | 60 | carry_forward | arima_110 | 6.89 | 6.63 | +0.27 | Fail |
| childrens | 120 | carry_forward | arima_110 | 12.51 | 12.21 | +0.29 | Fail |
| collierville | 15 | carry_forward | arima_110 | 12.96 | 13.04 | -0.08 | Fail |
| collierville | 30 | carry_forward | arima_110 | 20.46 | 20.47 | -0.01 | Fail |
| collierville | 60 | carry_forward | arima_100 | 27.68 | 26.12 | +1.56 | Pass |
| collierville | 120 | m1_median | arima_100 | 34.14 | 34.80 | -0.66 | Fail |
| crittenden | 15 | carry_forward | arima_110 | 13.58 | 15.61 | -2.03 | Fail |
| crittenden | 30 | carry_forward | arima_110 | 26.47 | 27.43 | -0.96 | Fail |
| crittenden | 60 | m1_median | arima_100 | 32.78 | 34.57 | -1.79 | Fail |
| crittenden | 120 | m1_median | arima_100 | 32.82 | 35.94 | -3.11 | Fail |
| desoto | 15 | carry_forward | arima_110 | 3.02 | 2.97 | +0.05 | Fail |
| desoto | 30 | carry_forward | arima_110 | 5.62 | 5.37 | +0.25 | Fail |
| desoto | 60 | carry_forward | arima_110 | 9.92 | 9.56 | +0.36 | Fail |
| desoto | 120 | carry_forward | arima_110 | 18.31 | 17.95 | +0.36 | Fail |
| golden-triangle | 15 | carry_forward | arima_110 | 1.36 | 1.34 | +0.01 | Fail |
| golden-triangle | 30 | carry_forward | arima_110 | 2.75 | 2.54 | +0.21 | Fail |
| golden-triangle | 60 | carry_forward | arima_110 | 4.95 | 4.62 | +0.32 | Fail |
| golden-triangle | 120 | carry_forward | arima_110 | 9.11 | 8.82 | +0.29 | Fail |
| huntingdon | 15 | carry_forward | arima_110 | 2.30 | 2.33 | -0.03 | Fail |
| huntingdon | 30 | carry_forward | arima_110 | 4.15 | 4.17 | -0.02 | Fail |
| huntingdon | 60 | carry_forward | arima_110 | 7.58 | 7.56 | +0.02 | Fail |
| huntingdon | 120 | carry_forward | arima_100 | 13.18 | 12.49 | +0.68 | Fail |
| memphis | 15 | carry_forward | arima_110 | 15.46 | 15.51 | -0.05 | Fail |
| memphis | 30 | carry_forward | arima_110 | 24.33 | 24.38 | -0.05 | Fail |
| memphis | 60 | carry_forward | arima_110 | 33.46 | 33.14 | +0.32 | Fail |
| memphis | 120 | carry_forward | arima_110 | 38.97 | 38.85 | +0.12 | Fail |
| nea | 15 | carry_forward | arima_110 | 1.04 | 1.07 | -0.03 | Fail |
| nea | 30 | carry_forward | arima_110 | 1.64 | 1.63 | +0.00 | Fail |
| nea | 60 | carry_forward | arima_110 | 2.69 | 2.67 | +0.02 | Fail |
| nea | 120 | carry_forward | arima_100 | 4.56 | 4.38 | +0.18 | Fail |
| north-mississippi | 15 | carry_forward | arima_110 | 2.05 | 2.08 | -0.03 | Fail |
| north-mississippi | 30 | carry_forward | arima_110 | 3.72 | 3.39 | +0.33 | Fail |
| north-mississippi | 60 | carry_forward | arima_110 | 7.51 | 6.72 | +0.79 | Fail |
| north-mississippi | 120 | carry_forward | arima_110 | 14.45 | 13.55 | +0.90 | Fail |
| tipton | 15 | carry_forward | arima_110 | 2.44 | 2.50 | -0.06 | Fail |
| tipton | 30 | carry_forward | arima_110 | 3.78 | 3.79 | -0.01 | Fail |
| tipton | 60 | carry_forward | arima_110 | 5.82 | 5.76 | +0.07 | Fail |
| tipton | 120 | carry_forward | arima_100 | 10.05 | 9.88 | +0.17 | Fail |
| union-city | 15 | carry_forward | arima_110 | 1.25 | 1.29 | -0.04 | Fail |
| union-city | 30 | carry_forward | arima_110 | 2.28 | 2.29 | -0.01 | Fail |
| union-city | 60 | carry_forward | arima_100 | 4.18 | 4.17 | +0.00 | Fail |
| union-city | 120 | carry_forward | arima_100 | 6.78 | 6.50 | +0.28 | Fail |
| union-county | 15 | carry_forward | arima_100 | 1.06 | 1.10 | -0.04 | Fail |
| union-county | 30 | carry_forward | arima_110 | 1.90 | 1.88 | +0.03 | Fail |
| union-county | 60 | carry_forward | arima_100 | 3.41 | 3.38 | +0.03 | Fail |
| union-county | 120 | carry_forward | arima_100 | 5.74 | 5.54 | +0.20 | Fail |

Full own-support and common-support MAE/RMSE/bias, abstentions, fit statuses and specification hashes are in [aggregate results](m5-arima-results.json). Origin-level predictions remain in `build/m5-study/arima-origins.json`.

```powershell
.venv\Scripts\python.exe scripts/m5_arima.py .cache/m5-history-20260923.json
.venv\Scripts\python.exe scripts/m5_arima_report.py
```

Next: inspect residual/calendar structure and support before expanding the candidate set; address cold-start availability on development data; freeze all choices before scoring calibration/holdout. The eight M5 tests cover slot semantics, future mutation, DST, zeros/missingness, fitting cutoffs, hourly arrivals and failed-fit abstention. Successful numerical convergence alone is not a release gate.
