"""Create an aggregate development-only ARIMA report from the frozen pilot."""

from collections import Counter
import json
from pathlib import Path


def main():
    report = json.loads(Path("build/m5-study/arima-development.json").read_text())
    simple = ("carry_forward", "daily_naive", "weekly_naive", "m1_median")
    pilots = ("arima_100", "arima_110")
    rows, counts = [], Counter()
    for item in report["summary"]:
        scores = item["models"]
        baseline = min(simple, key=lambda m:scores[m]["matched"]["mae"])
        pilot = min(pilots, key=lambda m:scores[m]["matched"]["mae"])
        b, p = scores[baseline]["matched"], scores[pilot]["matched"]
        gain = b["mae"] - p["mae"]
        screen = gain >= 1 and gain >= .05 * b["mae"] and p["rmse"] <= b["rmse"]
        counts["lower_mae"] += gain > 0
        counts["error_screen"] += screen
        rows.append({"facility": item["facility"], "horizon_minutes": item["horizon_minutes"],
                     "simple": baseline, "pilot": pilot, "simple_mae": b["mae"], "pilot_mae": p["mae"],
                     "gain_minutes": gain, "error_screen_passed": screen,
                     "pilot_availability": scores[pilot]["all"]["availability_with_target"], "public_release": False})
    lines = ["# M5 ARIMA development pilot — 2026-09-23 UTC", "",
             "Status: two nonseasonal candidates evaluated locally; no public forecast qualifies for release. "
             "Calibration and final holdout remain unscored.", "",
             "The [frozen protocol](m5-study-protocol.md) named ARIMA(1,0,0) and ARIMA(1,1,0) before "
             "these scores were calculated. The [benchmark checkpoint](m5-validation.md) supplies the exact input snapshot. "
             "Both pilots use at most 28 days, daily UTC refits, hourly state updates, no gap imputation, "
             "and nonnegative output clipping. ARIMA(1,0,0) includes a constant; ARIMA(1,1,0) has no drift. "
             "No neighboring or unavailable future regressors were used.", "",
             f"The study evaluated 20 hospitals and four horizons in {report['runtime_seconds']:.1f} seconds using four local workers. "
             f"There were {report['fit_counts'].get('ok',0)} converged daily fits and "
             f"{report['fit_counts'].get('insufficient_history',0)} support abstentions; "
             f"{report['fit_counts'].get('fit_failed',0)} fits failed. "
             "Every facility abstained on the first development day because its padded 28-day training window "
             "includes the partial start of the source snapshot. This is counted, not silently trimmed.", "",
             f"The better ARIMA candidate lowered matched-origin MAE in {counts['lower_mae']}/80 combinations. "
             f"Only {counts['error_screen']}/80 met the provisional **error-only** screen of at least 5% and 1 minute "
             "MAE reduction with no worse RMSE. Availability was about 92.8%, below the provisional 95% gate. "
             "This is development selection on a common subset, not a final-test improvement claim. "
             "Intervals, dependent-error uncertainty, seasonal diagnostics, SARIMA/SARIMAX and delayed-availability "
             "ARIMA sensitivity remain unevaluated. All public-release decisions stay disabled.", "",
             "| Facility | Horizon | Strongest simple | Better pilot | Simple MAE | Pilot MAE | Gain (min) | Error screen |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['facility']} | {r['horizon_minutes']} | {r['simple']} | {r['pilot']} | {r['simple_mae']:.2f} | {r['pilot_mae']:.2f} | {r['gain_minutes']:+.2f} | {'Pass' if r['error_screen_passed'] else 'Fail'} |")
    lines.extend(["", "Full own-support and common-support MAE/RMSE/bias, abstentions, fit statuses and specification hashes "
                  "are in [aggregate results](m5-arima-results.json). Origin-level predictions remain in `build/m5-study/arima-origins.json`.", "",
                  "```powershell", ".venv\\Scripts\\python.exe scripts/m5_arima.py .cache/m5-history-20260923.json",
                  ".venv\\Scripts\\python.exe scripts/m5_arima_report.py", "```", "",
                  "Next: inspect residual/calendar structure and support before expanding the candidate set; address "
                  "cold-start availability on development data; freeze all choices before scoring calibration/holdout. "
                  "The eight M5 tests cover slot semantics, future mutation, DST, zeros/missingness, fitting cutoffs, "
                  "hourly arrivals and failed-fit abstention. Successful numerical convergence alone is not a release gate.", ""])
    Path("docs/m5-arima-validation.md").write_text("\n".join(lines), encoding="utf-8")
    Path("docs/m5-arima-results.json").write_text(json.dumps({**report, "comparisons": rows}, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(counts)))


if __name__ == "__main__":
    main()
