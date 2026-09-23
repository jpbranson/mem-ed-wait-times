# M1 method and validation

Validated locally on 2026-09-14; not deployed. This is dated evidence about
published observations, not a live report, patient wait prediction, or care-quality
assessment. The implementation is [analysis.py](../edwait/analysis.py),
[prepare.py](../edwait/prepare.py), and [the browser comparison module](../dashboard/comparisons.mjs).
Full counts, source partitions, per-facility results, and exact example timestamps
are in [m1-replay-evidence.json](m1-replay-evidence.json).

Current M1 presentation: all 20 hospital lines open in a seven-day overview;
24-hour/seven-day controls also update individual wait/deviation charts below.
The overview y-axis follows the visible time window and hospital selection.
Methodology, tables, and diagnostics are expandable. Local Inter and responsive
chart geometry keep text at least 16 CSS px. The latest completed validation is
35 Python and 15 JavaScript tests plus the desktop/mobile checks in
[Typography and spacing follow-up](#typography-and-spacing-follow-up).
Earlier cell counts, layouts, test totals, and browser interruptions below are
dated development history, not outstanding work in the current M1 presentation.

## Selected method: self-comparison-v1

| Setting | Selected behavior |
| --- | --- |
| Baseline window | Previous 28 complete `America/Chicago` calendar days, excluding the observation's entire local day |
| Primary group | Same weekday/weekend type; observation's local hour and one neighboring hour on either side, wrapping at midnight |
| Fallbacks, in order | Two neighboring hours on either side with the same day type, then those wider hours across all days |
| Minimum support | Eight contributing days, 64 readings, and 75% coverage of expected slots across all eligible calendar days |
| Contributing day | At least 75% of that day's selected 15-minute slots must have observations; thinner days contribute no baseline values |
| Typical range | 25th–75th percentiles; median is the 50th percentile; linear interpolation at `(n - 1) * p` |
| Historical percentile | `100 * (lower count + half the tied count) / reference count`; display rounded to a whole percentile |
| Unusual reading | At or beyond the 10th/90th percentile **and** at least 10 minutes below/above the median |
| Recent direction | Latest minus median of at least two readings 40–80 minutes earlier; up/down requires at least 10 minutes; otherwise little change |
| Gaps | Reference observations for direction must be no more than 20 minutes apart; chart lines and bands break at gaps over 20 minutes |

The distinct-day rule prevents six or seven occurrences from being presented as
adequate support. Slot coverage includes missing calendar dates, including dates
before the available dataset starts. Its denominator counts actual UTC slots
between local midnights, including missing/repeated DST hours. A deterministic
maximum of one observation per facility per UTC 15-minute slot prevents retries
from inflating support. The last observed reading wins; ties use batch time and
wait value after M0 logical-key deduplication. Raw observations are unchanged.

Zero remains a reported numeric value, including in the band and percentile;
ties receive half their mass. There is no division by a baseline wait and no
percentage-change display. Negative integer readings also remain as reported
under M0's unconfirmed sentinel contract. Missing periods are never filled with
earlier values. Unsupported references have null median, band, and percentile;
the UI identifies insufficient history and the attempted group's support.

Models depend only on preceding local days, even when a replay index contains
later observations. Each plotted historical point receives its own past-only
reference, rather than today's reference. No individual weekday pattern, forecast,
or causal effect is estimated. Current comparisons require M0-confirmed freshness
and a successfully fetched reference less than two hours old and before its local
date expires. Historical charts remain explicitly dated when current comparisons
are unavailable.

## Replay inputs and candidate comparison

Read-only snapshot: `s3://mem-ed-wait-times`, UTC batch window
`[2026-07-29T00:00:00Z, 2026-09-14T00:00:00Z)`. The M0 reader selected raw snapshots
for all 47 partitions, without mixing compacted copies. It returned **89,978
records**, zero rejected records, and zero logical duplicates. Source availability
is not proof that every scheduled collection ran. Snapshot SHA-256:
`61df6eb59d43aa0db800d0ec5aca98d12a5626cc062231f50bbba7b1c10a3896`.

The replay samples the first observation for each facility per UTC hour to reduce
repetitive scoring. Candidate selection covers August 19–September 6 inclusive
(9,120 comparisons); later inspection covers September 7–13 (3,360 comparisons,
168 per facility). All boundaries are UTC. The four candidates share the support
rules above. A common subset prevents missing support from artificially improving
a candidate's deviation score.

| Lookback / primary hour radius | Selection supported | Mean absolute deviation on 3,740 common selection cases (min) | Later mean absolute deviation (min) | Later within middle-50% band |
| --- | ---: | ---: | ---: | ---: |
| **28 days / ±1 hour** | **98.87%** | **22.15** | **20.67** | **49.73%** |
| 28 days / ±2 hours | 98.63% | 22.12 | 20.61 | 50.95% |
| 42 days / ±1 hour | 41.23% | 21.97 | 20.90 | 50.18% |
| 42 days / ±2 hours | 41.01% | 21.97 | 20.90 | 51.34% |

All four candidates supported all later cases. The 42-day candidate's common-case
improvement was about 0.18 minutes, small beside the 10-minute display threshold,
while its startup coverage was much lower. The 28-day window and narrower primary
hours retain more local-time specificity and become usable earlier. This is a
bounded first-release choice, not proof of a globally optimal window. Revisit it
with a longer history and seasonal/holiday periods.

For the selected candidate, selection support used 8,037 primary groups, 20 wider
same-type groups, and 960 all-day fallbacks; 103 cases were insufficient. All later
cases used the primary group. Median absolute deviation in the later period was
11 minutes. Middle-band inclusion varied by facility (for example, DeSoto 35.7%,
Memphis 41.1%, Arlington 61.9%, and Crittenden 67.3%). The band summarizes reference
readings; it is not a calibrated prediction interval.

## Unusualness and direction checks

The middle 50% is an interpretable description of the reference's center, not an
alert boundary. Tail and minute thresholds were inspected separately. Selected
examples below use the outer 10% plus 10 minutes; the full evidence includes the
nine combinations of 5/10/15% tails and 5/10/15-minute thresholds.

| Tail on each side / minimum difference | Selection flagged | Later flagged |
| --- | ---: | ---: |
| 5% / 10 minutes | 14.20% | 10.80% |
| 10% / 5 minutes | 24.34% | 21.52% |
| **10% / 10 minutes** | **22.45%** | **19.40%** |
| 10% / 15 minutes | 19.46% | 15.71% |
| 15% / 10 minutes | 30.76% | 28.90% |

The selected rule requires both a relatively extreme reading and an absolute
difference large enough to label. Ten minutes is a display convention informed
by this sensitivity check, not a clinically established benefit. “No large
departure” does not guarantee that a reading lies within the middle-50% band.

Direction was inspected across all 12,480 hourly targets. The 40–80-minute
reference allows timing drift around the 15-minute collection schedule. An
initial 45–75-minute window dropped valid edge readings due to request timing
jitter; the widened window avoids that artifact while retaining an approximately
one-hour comparison.

| Center / minimum change | Up or down labels | Insufficient reference | Opposite direction at next adjacent hour |
| --- | ---: | ---: | ---: |
| 30 minutes / 5 minutes | 4,110 | 5 | 10.12% |
| 30 minutes / 10 minutes | 2,410 | 5 | 5.95% |
| 60 minutes / 5 minutes | 6,148 | 1 | 15.85% |
| **60 minutes / 10 minutes** | **3,975** | **1** | **10.59%** |

All candidates use ±20-minute tolerance. The reversal denominator is adjacent
sampled pairs less than 75 minutes apart, including pairs labeled little change.
The 10-minute rule reduces reversals relative to 5 minutes at the same horizon.
The hour comparison is understandable and can use the hourly history artifact
between builds. It was **not** quieter than the 30-minute candidate. These are
descriptive sensitivity checks, not forecast evaluation. The later period was
also inspected when refining direction tolerance and labels, so it must not be
claimed as an untouched final validation set.

## Inspected historical examples

These are selected low/high deviations, not representative frequency estimates.
UTC times below are truncated to the minute; the evidence JSON retains exact
timestamps, percentile, coverage, and direction. All listed later examples had
100% slot coverage.

| Facility / UTC observation | Reported wait | Median | Middle-50% range | Difference | Contributing days |
| --- | ---: | ---: | --- | ---: | ---: |
| Memphis, Sep 10 08:08 | 13 | 162 | 99.5–228 | −149 | 20 |
| Memphis, Sep 9 10:08 | 404 | 106 | 38.75–209 | +298 | 20 |
| DeSoto, Sep 8 18:09 | 19 | 54 | 39–64 | −35 | 20 |
| DeSoto, Sep 12 13:08 | 322 | 80 | 46.75–111.75 | +242 | 8 |
| Crittenden, Sep 9 22:08 | 0 | 49 | 26.75–77 | −49 | 20 |
| Crittenden, Sep 7 07:08 | 215 | 18.5 | 0–58 | +196.5 | 20 |
| Arlington, Sep 12 20:08 | 11 | 52.5 | 39–80 | −41.5 | 8 |
| Arlington, Sep 10 00:08 | 122 | 39 | 19–67 | +83 | 20 |
| Yazoo, Sep 8 02:09 | 0 | 16.5 | 9–32 | −16.5 | 20 |
| Yazoo, Sep 10 18:09 | 77 | 12 | 2.75–24 | +65 | 20 |

Sparse startup: Arlington on August 19 at 00:08 UTC reported 74 minutes. The
broadest group had 20 contributing days and 400 readings, but only 401 of 560
expected slots (71.6%). The reference was unavailable; sample count alone did
not bypass coverage. On August 22 at 05:08 UTC, the all-day fallback had 24 days,
478 reference readings, and 86.6% slot coverage. Its 134-minute reading compared
with a 12-minute median, explicitly labeled as a broader fallback.

## Implementation and UI validation

- **35 Python tests passed**, covering the M0 contracts plus past-only baselines,
  same-day/future exclusion, slot deduplication, support/fallbacks, zeros and ties,
  DST denominators, direction gaps, empty preparation, and the comparison schema.
- **11 JavaScript tests passed**, including live changes without rebuilding
  history, minute/percentile arithmetic, duplicate live slots, stale/failure
  suppression, expired/malformed context, 24-hour/seven-day charts, gaps, and
  accessible data tables. M0's HTTP timeout and real AWS CLI exclusion dry run
  remain in the suite.
- A read-only live preparation at `2026-09-14T15:35:38.690324+00:00` produced
  20 facilities and 13,440 historical points (about 2 MB); the complete artifact
  passed its JSON schema with date-time format validation. Quarto 1.10.18 rendered
  the prepared site. Empty rendering keeps registry controls and explicit missing
  history; Quarto itself performs no S3 reads.
- Chrome desktop and 390 × 844 mobile inspection used local synthetic latest
  readings alongside the dated real history. The Memphis fixture showed 350
  minutes, a 43-minute median, 32–58-minute band, and +307-minute difference with
  “Above usual.” Those values are UI fixtures, not a live hospital report.
  Stale and missing fixtures showed text labels and unavailable comparisons.
- Keyboard selection changed facilities; Tab reached refresh and chart/table
  controls; Enter expanded the data table. Seven-day selection exposed 672
  historical points. Mobile content stayed within the page width, with charts
  and tables in labeled scrollable regions. Wait and deviation remain adjacent
  in the current panel and aligned in the chart. Unusualness, freshness, and
  missingness have text labels independent of color. Latency is in an operator
  disclosure below the comparison view.

This validates local behavior and the dated replay. Production collector-to-site
validation remains a release operation; see [M1 operations](m1-operations.md).

## Overview follow-up

On 2026-09-14, user review requested the all-hospital line chart on first visit.
[The overview](../dashboard/overview.py) now precedes the individual selector.
It uses the original Plotly library already in the project, shows all 20 hospitals
initially, defaults to seven days, and offers a 24-hour view. Hover labels identify
the facility, exact collected time, and published minutes. Legend clicks toggle
lines; double-clicks isolate a hospital. Individual comparisons and their data
tables remain below the overview.

The chart is rendered from the existing comparison artifact without new source
reads or contract changes. UTC positions preserve chronological order across DST;
axis/hover labels use America/Chicago. Gaps over 20 minutes insert explicit nulls,
and markers preserve isolated readings and zero values. The plot has a bounded
horizontal scroll region on narrow screens. Its preparation time and hourly site
build update behavior are displayed separately from live readings below it.

Validation for this follow-up: all 35 Python tests passed, including execution of
all four dashboard cells with empty input. Direct figure checks confirmed 20
initially visible traces, all 13,440 prepared points, the seven-day default and
24-hour control, and preserved zero/gap/Chicago tooltip behavior. Quarto rendered
successfully, and the localhost response placed the chart before the individual
selector. This follow-up used render/data checks; the earlier browser inspection
above applies to the preceding individual-comparison implementation. No production
deployment was performed.

## Visualization and scaling follow-up

A second 2026-09-14 review requested a visualization-first page with little text,
and identified that changing the overview from seven days to 24 hours retained
the older period's y-axis maximum. The page now uses a full-width dark canvas,
native keyboard-accessible hospital toggles, shared time controls, and a compact
selected-hospital range graphic beside the wait/deviation history. Explanations,
tables, and operator diagnostics are collapsed; current freshness, comparison
states, day support, and coverage remain explicit.

[Overview controls](../dashboard/overview.mjs) calculate the scale from only the
visible traces and selected time window. Zero remains a baseline; negative
published values extend it below zero. Empty/all-zero selections have a finite
0–10 range. The range includes interpolated boundary points of continuous line
segments, but never spans an explicit missing-data gap. Hiding, isolating, or
restoring hospitals applies the same calculation. Both history views follow
the global seven-day/24-hour controls.

All **35 Python and 15 JavaScript tests passed**. The four added
[overview regressions](../tests/overview.test.mjs) cover an older 900-minute peak
that changes from a 0–1,000 weekly scale to 0–65 for a day containing a 60-minute
maximum, restoration of the weekly scale, hidden outliers, zero/negative/empty
series, window-edge continuity, gaps, and the wired window/legend controller.
The empty dashboard check executes all five presentation cells. Fresh read-only
preparation at `2026-09-14T16:29:26.200821+00:00` produced 20 facilities and 13,440
historical points; Quarto rendered the redesigned page successfully.

Fresh browser visual/interaction inspection was not completed. Microsoft Edge
was not approved for Computer Use, and the subsequent approved Chrome attempt
was stopped by the user's physical Escape key. No further browser control was
performed. The localhost preview is ready for user visual review. Earlier UI
evidence above remains historical and is not attributed to this redesign.

## Typography and spacing follow-up

A further 2026-09-14 review requested a smaller chart-to-legend gap, Inter
throughout, and no text below 12 pt (16 CSS px).

The generated HTML exposed the spacing defect: Quarto's Plotly dependency
detector moved the entire combined library/plot output into the document header,
leaving an empty, explicitly sized chart container in the page. The library now
uses its own display output; the plot remains in `#all-hospitals-chart` immediately
before the hospital legend. No negative margins mask the displaced content.

The site now serves the Google Fonts Inter Latin variable WOFF2 locally with its
SIL Open Font License. Page text, form controls, legend labels, Plotly ticks and
hover labels, table captions, disclosures, and diagnostic text use Inter at a
minimum of 16 CSS px. The local preview notice follows the same rule. The focused
history and reference SVGs use their displayed width as the viewBox width, so
responsive scaling does not reduce their 16 px labels. Time labels use two lines
and fewer ticks on small charts. At the narrowest width, the history chart scrolls
within its labeled region. Controls and summary metrics wrap without smaller text.

Validation:

- All **35 Python and 15 JavaScript tests passed**, including the five-cell empty
  dashboard, historical gaps/zero values, live refresh, and overview scaling.
- Quarto rendered successfully and included the 48,256-byte Inter WOFF2 and its
  license. Rendered HTML and the live DOM place the plot inside its intended host.
- Chrome screenshots and DOM measurements checked the default desktop viewport
  (1,703 CSS px content width), a 390 × 844 override (375 px content width after
  the scrollbar), and a 320 × 844 override (305 px content width). All showed
  no page-level horizontal overflow and no empty block before the legend. The
  legend container starts exactly at the plot element's bottom; its internal
  padding supplies the small intended separation.
- A computed-style audit, including SVG screen transforms, measured a **16 px
  minimum** with Inter as the font family at all three widths. The audit found a
  Bootstrap table caption at 14.4 px on the first pass; its rule was corrected,
  rebuilt, and verified at 16 px before completion.
- The real-history overview changed its top labeled tick from 500 minutes in
  seven-day view to 200 in 24-hour view, then restored 500 on return. Both history
  panels followed the time control. Selecting the Children's hospital exercised
  a longer name and the narrow summary layout. These are dated UI observations,
  not current hospital claims or a new analytical assessment.
- No browser console errors were observed. The temporary viewport override was
  reset, and the preview was left at its seven-day/all-hospital opening view.

The previously pending browser review is now complete for this local version.
No production deployment or analytical, record, or storage-contract changes were
made. Production rollout checks remain in [M1 operations](m1-operations.md).
