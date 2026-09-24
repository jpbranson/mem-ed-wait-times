# M5 offline study protocol — 2026-09-23 UTC

Status: first study checkpoint in progress; no public forecast or routing claim.
This protocol is fixed before inspecting forecast scores. Its target is the
collected `CV_ED_Wait` reading, not an individual patient's experience.

## Frozen inputs and time policy

- Freeze M0-selected history from `2026-07-29T00:00:00Z` through
  `2026-09-23T00:00:00Z` (exclusive); retain the exact snapshot and SHA-256 locally.
  The manifest records the source partitions, validation counts, software versions,
  and evaluation policy. Raw observations are never modified.
- Assign observations to half-open 15-minute UTC slots by `observed_at`; each
  slot is labeled by its ending boundary. Latest observed time, batch time, then
  value break ties deterministically. Different metrics never mix.
- Issue forecasts hourly at UTC boundaries after the preceding slot is complete.
  A horizon of 15/30/60/120 minutes targets the slot ending that far after issue.
  Missing targets stay missing. Zeros are real observations; negative values are
  counted and excluded from this nonnegative modeling target, without changing raw.
- No forward/backward filling or interpolation. Report missing slots, targets,
  and abstentions. Require a reading in the last completed slot at issue time.
- `observed_at` is an availability proxy. The historical records do not contain
  original publication/ingestion timestamps; this is an offline accuracy study,
  not a faithful replay of operational availability. Recheck with a 15-minute
  availability delay before any release decision.
- UTC daily/weekly seasonal-naive baselines use exact 96/672-slot lags. They are
  explicitly UTC seasonality. The M1 baseline uses America/Chicago calendar
  groups with its existing support/fallback policy, including DST.

## Chronological phases

| Phase | Forecast issue times, inclusive start/exclusive end | Purpose |
| --- | --- | --- |
| Initial training | 2026-07-29 through 2026-08-26 UTC | Up to 28 days before first origin |
| Development | 2026-08-26 through 2026-09-09 UTC | Compare candidates and choose per facility/horizon |
| Calibration | 2026-09-09 through 2026-09-16 UTC | Assess intervals and failure/support gates |
| Final holdout | 2026-09-16 through 2026-09-23 UTC | Later-period evaluation after choices freeze |

Targets must fall strictly before a phase's end; discard the last origins whose
horizons cross it. Never select model orders or thresholds from the final holdout.
Every fit/reference uses only records available at its origin. M1 references
exclude the origin's current local day, including forecasts crossing midnight.

## First checkpoint and subsequent candidates

Implement and run all four simple benchmarks first: carry-forward, UTC daily
naive, UTC weekly naive, and M1 local-time median. Report MAE, RMSE, signed bias,
missing-target counts and abstention rates by facility/horizon; compare the
benchmarks on common supported origins, alongside their own coverage. Report
zero-target and spike errors separately (spike: target above the origin's past
28-day 90th percentile). Freeze the strongest simple benchmark on development
data before evaluating any final model.

The first bounded ARIMA candidates are `(1,0,0)` and `(1,1,0)`; daily refits use
at most 28 days, with updates between refits using only arrived observations.
SARIMA/SARIMAX require separate seasonal diagnostics and measured runtime before
inclusion. Do not imply those models were evaluated by running the benchmarks.
The first checkpoint leaves calibration and holdout unscored so model development
can continue without consuming the final test set.

Provisional release gates, to be reviewed on development data and frozen before
holdout scoring: at least 5% **and** 1 minute lower MAE than the strongest simple
benchmark; RMSE no worse; at least 200 matched targets across seven days;
forecast availability at least 95% of eligible origins; fit failure at most 1%;
candidate 80%/95% interval coverage within 5 percentage points of nominal; and
total update runtime under 10 minutes for all 20 facilities. Use paired daily
block bootstrap intervals for gains, and require the gain interval to exclude
zero. A seven-day holdout offers weak uncertainty evidence; insufficient support
means no release. A useful negative result is acceptable.

## Deliverables and boundaries

Check in the protocol, evaluation code/tests and dated aggregate report; retain
the exact input snapshot and detailed origin-level output in ignored local files.
Generate standalone backtest/error figures from the saved results. Offline
analysis dependencies are separate from deployment requirements. No forecast
schema, S3 object, production fit, public forecast layer or M2 integration is
introduced by the first checkpoint.

Method references: [rolling-origin evaluation](https://otexts.com/fpp3/tscv.html)
and [statsmodels ARIMA](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html).

## Amendment — 2026-09-24 UTC, before calibration scoring

Written after development scoring and before any calibration or holdout score.
The [freeze record](m5-freeze.json) fixes the resulting specification hash,
per-facility/horizon selections, shortlist and release rule. The
[v2 development report](m5-candidates-validation.md) holds the evidence.

- **Diagnostics (data before 2026-09-09 only).** Local hour of day explains 1–35%
  of each hospital's reading variance (Memphis highest; 13 hospitals at or below about 10%).
  Lag-96 (one day) autocorrelation is 0.02–0.52 and one-week lag −0.01–0.40; weekly
  medians shift substantially (DeSoto 26→90 minutes). A 96-slot seasonal ARIMA
  is therefore not justified; bounded calendar-regressor and profile candidates are.
- **Cold start.** Every model now drops training slots through the last missing
  run longer than four slots (including the snapshot's partial first day), then
  applies the unchanged 14-day/95%-coverage/latest-slot support rule. v2
  reproduces v1 ARIMA forecasts exactly wherever windows are identical.
- **Candidates (v2).** ARIMA(1,0,0) with constant; ARIMA(1,1,0); ARIMA(1,0,0)
  with constant and two daily Fourier harmonics of America/Chicago slot-midpoint
  time (deterministic, known in advance, DST-aware); and a direct profile model:
  the forecast is the 28-day local hour × weekday/weekend median at the target plus
  a per-step persistence coefficient (least squares through zero, clipped to
  [0, 1]) times the origin's deviation from its own profile cell. All refit daily,
  forecast hourly, clip at zero and never impute.
- **Intervals.** Every model's 80%/95% interval adds the empirical 10/90% and
  2.5/97.5% quantiles of its own errors from the previous seven days, counting
  only targets observed by the origin; fewer than 72 errors means no interval.
  Replays start seven days before each scored phase for this history only.
- **Selection.** Per facility/horizon, the strongest simple benchmark and the
  candidate are the lowest development MAE on origins matched across all eight
  models, ties to the simpler model. The five combinations that pass every gate
  on development form the shortlist. Development passes are selection-biased and
  are not evidence of release-quality skill.
- **Gates.** Unchanged except support: at least 150 matched hourly targets on at
  least six days, replacing 200 targets, which hourly origins cannot reach in a
  seven-day phase (at most 168). Gain: at least 1 minute and 5% lower MAE; RMSE no
  worse; paired daily-block bootstrap (2,000 resamples, fixed seed) 95% interval
  for the MAE gain above zero; availability ≥95%; fit failure ≤1%; 80%/95%
  coverage each within 5 points; and the largest per-day sum of all fit times
  for 20 facilities and four candidates under 10 minutes.
- **Release rule.** A shortlisted combination qualifies only if it passes every
  gate with its frozen pair on calibration and again on the final holdout, and
  the holdout with a one-slot availability delay still meets the minimum gain.
  Anything else stays disabled. Calibration results cannot change the
  specification; a changed specification needs a new study with fresh data.
