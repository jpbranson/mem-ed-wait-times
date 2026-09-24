# M4 validation: area counts and wait stability

Dated 2026-09-24 UTC. Local implementation and validation only; nothing here was
deployed. Figures describe published `CV_ED_Wait` readings, not individual patient
waits, occupancy, capacity or care quality.

## Scope

| M4 feature | Status | Notes |
| --- | --- | --- |
| Area-wide elevated waits | Implemented locally | Browser view over existing M1 comparisons; no new artifact |
| Wait stability | Implemented locally | Additive `stability` summaries in `comparisons.json` |
| Historical alternative availability | Deferred | Needs M2 travel inputs. Replaying alternatives needs assumed or recorded travel times per origin, and routing is not public or validated for heavy traffic |

## Area-wide elevated waits

[area.mjs](../dashboard/area.mjs) counts, for a chosen area, hospitals whose
reading is **above usual** or **below usual** under M1's existing rule: the outer
10% of the past-only reference plus at least 10 minutes from its median. It uses
the same rule as the focus summary rather than the middle-50% band, which a
hospital exceeds about a quarter of the time by construction.

- **Areas** ([areas.py](../edwait/areas.py)): all hospitals; registry states
  (Tennessee 7, Arkansas 2, Mississippi 11); and M3's straight-line neighbor groups
  with at least three members: Memphis area (Arlington, Children's, Collierville,
  Memphis, Tipton, Crittenden, DeSoto) and Booneville / North Mississippi / Union
  County. The two-hospital Attala–Leake pair is not summarized as an area. The
  groups are campus centers linked within 50 km. They are not travel times or
  service areas.
- **Now:** live readings from `data/latest.json` compared against the current
  references. Each hospital is counted as compared, without a usual range, or not
  recently collected. Counts pause when the historical context is unavailable,
  more than two hours old, or past local midnight, as the focus summary does.
- **History:** hourly (seven days) or 15-minute (24 hours) columns, following the
  shared time control. Each column uses each hospital's latest reading in that
  period. Bars above the zero line count hospitals above usual; bars below the line
  count hospitals below usual. A pale column shows how many had a usual range, so
  coverage stays visible. A note gives the window's median count ("typical count
  above usual"), and a disclosed table lists periods per hospital.

### Evidence: counts versus chance (7 days to 2026-09-24 02:04 UTC)

Computed from the locally prepared `comparisons.json` (167 compared hourly
periods). "Independent" is the count distribution expected if each hospital were
above usual independently, at its own observed rate in the window.

| Area | Median count | Max | Periods with ≥1 above | ≥3 above: observed / independent | ≥5 above: observed / independent |
| --- | --- | --- | --- | --- | --- |
| All hospitals (20) | 2 | 6 | 86% | 33% / 30% | 2.4% / 3.5% |
| Memphis area (7) | 1 | 3 | 55% | 4.8% / 3.2% | 0 / 0 |

Each hospital was above usual in about 10% of its compared periods (mean 9.6%
across all hospitals and 11% in the Memphis area). In this window, area counts are
close to what independent hospitals would produce. This agrees with M3's finding
that no pair association was confirmed. The view therefore reports counts beside a
typical count. It does not label any count a surge or an area-wide event, and one
week is too short to calibrate such a threshold.

## Wait stability

[stability.py](../edwait/stability.py) summarizes how far each hospital's
published reading moved over 15, 30, 60 and 120 minutes. It uses the complete
previous 28 local days, M1's latest-per-slot series and M2's support rules:
covered days only, pairs within ±7.5 minutes of the horizon, no pair bridging a
gap over 20 minutes, and at least 64 pairs from eight days. For each horizon it
reports the median and 90th percentile absolute change and the share of pairs
that rose or fell by 10 or more minutes. Pairs overlap, so they are not
independent. These are descriptive statistics, not prediction intervals.

The focus summary shows one row per horizon: a median bar, a whisker to the 90th
percentile, a dashed 10-minute mark and the share that moved 10+ minutes, with an
exact hover text and an accessible label.

Selected results (reference 2026-08-26 to 2026-09-23 local days; ~2,680 pairs
over 28 days per horizon):

| Hospital | 15 min median / p90 / 10+ share | 1 h | 2 h |
| --- | --- | --- | --- |
| Memphis | 10 / 44 / 50% | 23 / 89 / 75% | 29 / 98 / 82% |
| Crittenden | 4 / 38 / 35% | 21 / 79 / 73% | 24 / 83 / 77% |
| Collierville | 4 / 28 / 32% | 15 / 64 / 66% | 21 / 81 / 71% |
| DeSoto | 2 / 8 / 7% | 7 / 23 / 36% | 12 / 43 / 60% |
| NEA Baptist | 0 / 2 / 0% | 1 / 6 / 3% | 2 / 10 / 10% |

All 20 hospitals had support at every horizon.

### M2 movement correction

The refactor found an M2 defect: `build_travel` took the 90th percentile from
absolute changes in chronological rather than sorted order. `quantile()`
interpolates in the order it is given. Published `travel.json` movement values were
therefore essentially arbitrary, for example Memphis at 15 minutes 5.2 versus a
sorted 44.4 minutes. The movement screen appears only beside routes, and public
routing is disabled, so the incorrect values were never shown to users.
Both features now share `horizon_changes`, and the fixed `travel.json` sorts before
taking the quantile. The travel schema and policy are unchanged. A sawtooth
regression test fails under the old ordering.

## Contracts

`comparisons.json` keeps schema version 1 and method `self-comparison-v1`. It adds
a required top-level `stability` object (method `wait-stability-v1`, policy,
source window) and a four-row `stability` array per facility. The schema is in
[comparisons.schema.json](comparisons.schema.json). The browser accepts artifacts
without it during rollout and then shows no movement summary. The area groups are
embedded in the page at render time. No raw, compacted, latest or travel record
shape changed, and no new S3 object was introduced.

## Validation

- **Tests:** 84 Python and 46 JavaScript tests passed (up from 79 and 41).
  - [test_stability.py](../tests/test_stability.py): sorted magnitudes and signed
    shares, gaps and sparse history, the M2 regression, and the schema contract
    with rejected rows.
  - [area.test.mjs](../tests/area.test.mjs): area validation, the
    above/below rule, latest-per-period binning, current counts with
    missing/unsupported/paused states, and stability rendering and validation.
  - The published-module check now requires `area.mjs`, and the public smoke
    check requires the module and the stability summaries.
- **Real data:** preparation from read-only S3 produced 20 facilities and 13,435
  seven-day points. Both artifacts passed their schemas, and Quarto 1.10.18
  rendered successfully.
- **Chrome (local review server with live S3 readings):** checked the area view
  (all hospitals and the Memphis area), the stability graphic, and 390/320 px
  frames. At phone width the area select initially caused a 471 px page overflow;
  it now shrinks, and neither width has horizontal overflow. The minimum text size
  measured 16 px, and no console errors were observed after load. The area chart
  scrolls inside its own container at phone width, as the heatmap does.

## Remaining

- Deploy through the existing workflow when approved. The public check then
  covers `area.mjs` and the stability summaries.
- Revisit area typical counts and stability with longer history. Around
  2026-10-15, alongside the M3/M5 revisits, check whether counts stay close to
  independence.
- Historical alternative availability waits on M2 travel validation.
