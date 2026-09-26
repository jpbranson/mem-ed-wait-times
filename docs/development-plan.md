# Development plan

Last updated: 2026-09-26 00:40 UTC (evening of September 25 America/Chicago)

Status: M0 and M1 are implemented, locally validated, and deployed to AWS as of
2026-09-22. M2's static interface is published, but routing and acceptance work
remain in progress; official status/service/age evidence covers all 20
destinations, and by user decision 18 adult/4 child destinations route to labeled
campus centers (ER entrance unconfirmed) until imagery-reviewed entrances are added.
A Cloudflare Workers routing gateway is implemented and validated locally, including
one live comparison, but not deployed (2026-09-26). A pre-registered backtest found
no benefit rule reliable enough to adopt, so preferred-option claims stay disabled.
M3 is in progress with a difference-from-usual heatmap, an offline relationship
study that found no confirmed pair association, and a campus map with replay that
is validated locally but not deployed (2026-09-26). M4 is in progress: area counts and wait-stability
summaries were deployed on 2026-09-24 (`8242ad1`, 03:17 UTC build); the historical
alternatives replay is deferred until M2 routing is validated. M5 is in progress offline: after benchmarks and
ARIMA pilots, a v2 candidate study scored development, froze its selections and
gates, then scored calibration. Only Collierville at 60 minutes remains eligible for
the final holdout, which the user chose to keep reserved while more data is
collected; no public forecasts exist.
Website builds are now also dispatched hourly by a user-configured AWS EventBridge
rule because GitHub cron proved unreliable. All 47 hourly dispatches from 01:17 UTC
on 2026-09-24 through 23:17 UTC on 2026-09-25 produced successful builds. The backup
cron stays until the failure alarm has a confirmed email subscription. The original
subscription was never confirmed and lapsed about two days after creation; a link
re-sent at 00:07 UTC on 2026-09-26 did not extend it, and by 00:37 UTC the topic had
no subscriptions. The user must re-create and confirm it.

Local preview rebuilt and started on 2026-09-22 at `http://127.0.0.1:8765/`
using read-only S3 history and the existing review server. That local launch
preceded the [AWS release](aws-deployment-2026-09-22.md) recorded below.

This is the project's living development and design document. It records current
capabilities, intended behavior, implementation order, open decisions, and
validation requirements. Update it in the same change as relevant development;
the maintenance rules below define how.

## Product direction

Help people understand a hospital's published emergency department wait, how it
compares with that hospital's usual readings, and how nearby suitable options
compare after accounting for travel. Provide a separate analytical view for
exploring relationships among hospitals over time.

Presentation direction from user review: lead with visual exploration and little
visible prose. A full-width plotting canvas, compact hospital/time controls, and
a focused graphical comparison take priority. Keep methodology and operator
detail in disclosures, while observation age, missing/stale states, support, and
brief interpretation/emergency guidance remain available.
Use Inter throughout and keep all text at least 12 pt (16 CSS px), including
chart labels. Reflow controls and redraw charts at the available width rather
than shrinking their text on smaller screens.

The first release should answer: **What is the reported wait, is it unusual for
this hospital at this time, and how recent is the observation?**

The next release should answer: **How much additional travel would buy a
meaningfully lower combined travel-and-published-wait estimate?**

The relationship explorer should answer: **Which facilities have elevated waits
together, which changes precede others, and which alternatives remain near their
usual readings?**

The forecasting track should answer: **How might this hospital's published
reading change over the next 15–120 minutes, and how uncertain is that forecast?**

## Current implementation and evidence

| Component | Current behavior | Reference |
| --- | --- | --- |
| Collection | Uses 20 registry slugs; preserves raw observations, writes attempt summaries, and conditionally publishes latest readings and failures | [Collector](../mem-ed-lambda.py), [publisher](../edwait/latest.py) |
| Compaction | Concatenates raw without rewriting provenance; attaches a fingerprint of copied raw objects | [Compactor](../lambda_function.py) |
| Shared history | Selects one source per UTC batch-date partition, validates and deduplicates by facility/metric, reports coverage/gaps/rejections | [Reader](../edwait/data.py) |
| Registry | Stable slugs, verified names/state groupings, timezone/source dates; 2026-09-23 official evidence for active status, general-emergency service and explicit age groups, with per-facility `destination_evidence`; OpenStreetMap `campus_point` fallbacks labeled "ER entrance unconfirmed"; `emergency_entrance` null until reviewed via `python -m edwait.entrances` | [Registry](../edwait/facilities.json), [destination evidence](m2-destinations-2026-09-23.md) |
| Travel prototype | Independent origin controls/map, TomTom v3 adapter and persistent usage budget; user supplied a local key and one live nonclinical API probe passed on 2026-09-23 UTC. Compare is enabled only after a `GET /api/routes/status` gateway confirmation, so static hosting never receives coordinates. 18 adult/4 child destinations route to labeled campus centers; 54/54 live validation routes passed. A Cloudflare Workers gateway (Worker plus one SQLite Durable Object) serving page and API at one origin, with destinations read from the published `travel.json`, passed unit, local-runtime, browser and one live check on 2026-09-26; not deployed. Metric evidence, reviewed entrances and gateway deployment remain pending; recommendations disabled | [M2 operations](m2-operations.md), [gateway](m2-operations.md#cloudflare-gateway), [readiness follow-up](m2-readiness-2026-09-23.md) |
| Self-comparisons | Past-only 28-day local references, minimum support and fallbacks, median/band/percentile, minute differences, and recent direction | [Analysis](../edwait/analysis.py), [dated replay](m1-validation.md) |
| Relationship study | Geography-only neighbor groups (campus centers ≤50 km) and a frozen discovery/confirmation test of same-time co-deviation, same-time changes and 1–3 h lagged changes for all 190 pairs, with autocorrelation-adjusted p-values, BH, system-wide and residual-hour checks. One discovery candidate, none confirmed; offline only | [Protocol](m3-relationship-protocol.md), [results](m3-validation.md#relationship-study--2026-09-24-utc) |
| Area counts and stability (M4) | Deployed 2026-09-24 (`8242ad1`). An Across an area view counts hospitals above or below their own usual (M1 rule) for all hospitals, registry states or M3's ≥3-member 50 km neighbor groups: live now, plus 24-hour/seven-day columns beside a typical count. A per-hospital typical-change graphic shows 28-day median/90th percentile movement and the 10+ minute share at 15–120 minutes, from additive `comparisons.json` fields. This week's area counts were close to independent chance | [Area view](../dashboard/area.mjs), [areas](../edwait/areas.py), [stability](../edwait/stability.py), [validation](m4-validation.md) |
| Offline forecasting | Frozen 107,257-record snapshot; four simple benchmarks, ARIMA(1,0,0)/(1,1,0), Fourier-regressor ARIMA and a profile-persistence model with trailing empirical 80/95% intervals. Development and calibration scored under a frozen selection; one pair (Collierville 60 min) is holdout-eligible; holdout unscored; no public forecasts | [Protocol and amendment](m5-study-protocol.md), [benchmarks](m5-validation.md), [ARIMA pilot](m5-arima-validation.md), [candidate study](m5-candidates-validation.md), [freeze](m5-freeze.json) |
| Dashboard | Full-width dark chart canvas with all 20 hospitals and an adjacent legend; shared 24-hour/seven-day controls fit the overview y-axis to visible lines; responsive individual charts below; an M3 difference-from-usual heatmap links rows to the focus chart, with a campus map and replay below it (local only, 2026-09-26); locally served Inter and a 16 px text minimum; details in disclosures | [Dashboard](../dashboard/index.qmd), [overview renderer](../dashboard/overview.py), [overview controls](../dashboard/overview.mjs), [heatmap](../dashboard/heatmap.mjs), [application](../dashboard/app.mjs) |
| Deployment | M0/M1, M2 static assets and the M3 heatmap deployed to S3 (latest `36d89bf` via GitHub Actions run 35833123203 at 07:44 UTC 2026-09-23, after an earlier direct publication of `fa842c8`); both Lambda packages updated. Minute-17 hourly/manual workflow, serialized deployments and exact public build/freshness checks published and manually validated on 2026-09-23 UTC; `data/*` protected; Lambda schedules unchanged. EventBridge rule `dashboard_hourly` dispatches the workflow at minute 17 (user-configured 2026-09-24 UTC; dispatched runs at 01:17–04:17 UTC all succeeded). M4 (`8242ad1`) was first published by the 03:17 UTC dispatch (run 35950813345), and an independent public check passed at 04:26 UTC; GitHub cron retained as a backup until about a day of hourly delivery is observed | [AWS release](aws-deployment-2026-09-22.md), [follow-up](production-followup-2026-09-23.md), [workflow](../.github/workflows/dashboard.yml) |
| Data documentation | Raw provenance, compaction metadata, attempts/latest, website-owned comparison/travel schemas, schedules, and dated verification | [S3 reference](s3-buckets.md), [raw schema](ed-wait.schema.json), [latest schema](latest.schema.json), [comparison schema](comparisons.schema.json), [travel schema](travel.schema.json) |

Implementation and production deployment are recorded separately. Public artifact
and refresh checks passed for the 2026-09-22 AWS release. The first updated
GitHub-hosted build and public desktop/mobile review passed on 2026-09-23 UTC.
The approved workflow schedule/verification mitigation is published and its
manual run passed, including 57 Python/33 JavaScript tests and the public smoke check.
Scheduled delivery was observed on 2026-09-23: no scheduled run started between
01:09 and at least 07:11 UTC, including both minute-17 slots after publication.
[Follow-up evidence](production-followup-2026-09-23.md#scheduled-delivery-observation).
Later scheduled runs that day were 3–5 hours apart. On 2026-09-24 UTC the user
configured an EventBridge rule that dispatches the workflow hourly; its resources
were verified read-only at 00:33 UTC, before any dispatch. Its first four
dispatches, at 01:17–04:17 UTC, each started a `workflow_dispatch` run that
succeeded in about two minutes, with no failed invocations.
[Trigger evidence](production-followup-2026-09-23.md#hourly-dispatch-through-eventbridge).

A read-only assessment on 2026-09-14 inspected the 47 compacted partitions from
2026-07-29 through 2026-09-13, inclusive, under
`s3://mem-ed-wait-times/compacted/ed_wait/dt=YYYY-MM-DD/data.jsonl.gz`.
Raw copies were not combined with those files.

- The inspected files contained 89,978 observations from 4,499 collection batches
  across 20 facilities. All observations used `CV_ED_Wait`.
- Median spacing between batch timestamps was approximately 15 minutes. There
  were two intervals longer than 20 minutes. The first day was partial.
- There were two missing facility observations relative to those collected
  batches and no duplicate `(batch_id, facility, metric)` keys. This does not
  establish that every scheduled collection ran or every upstream value was fresh.
- Median published waits were 94 minutes for `memphis`, 47 for `desoto`, and 28
  for `crittenden`. These are medians across the inspected observations, without
  time-of-day adjustment or patient weighting.
- Approximately 19% of `arlington` readings and 33% of
  `baptist-medical-center-yazoo` readings were zero. Their upstream meaning remains
  unverified.
- The median absolute difference between published readings approximately
  30 minutes apart was 17 minutes for `memphis` and 2 minutes for `desoto`.
  This describes movement in published readings, not individual patient outcomes.

These findings motivate facility-specific baselines and travel uncertainty. They
are a dated assessment, not a continuously refreshed report. Refresh them from
the stated partitions when using them to make new release decisions. The earlier
verification in the S3 reference retains its own date and narrower scope.

## Scope and interpretation

- Make coverage explicit: the configured Baptist facilities span multiple regions;
  the product does not have a complete inventory of all regional emergency departments.
- Treat `observed_at` as collection time. It does not establish when the hospital
  last changed its published metric. Request latency is operational telemetry.
- Historical percentiles and bands describe published observations. They do not
  describe the distribution of individual patient waits or hospital care quality.
- Preserve reported zero values until source evidence establishes their meaning.
  Missing, failed, stale, and zero observations must remain distinguishable.
- Confirm the current clinical definition, averaging window, update behavior,
  and sentinel values of `CV_ED_Wait`. A [2017 Baptist Tipton explanation](https://www.baptistonline.org/news/baptist-tipton-makes-er-wait-times-visible-to-patients/)
  describes a previous-hour average from arrival to first seeing a doctor or nurse
  practitioner, updated every five minutes. It is historical evidence for that
  facility, not confirmation of today's API contract across all facilities.
- Routing must compare appropriate facilities and explain the limits of the
  published estimate. Include emergency guidance consistent with [Baptist's
  emergency services information](https://www.baptistonline.org/services/emergency),
  which explains that serious conditions receive priority through triage.
- Wait histories alone cannot establish patient transfers, diversion, occupancy,
  available capacity, or causal spillover. Label relationship results as associations.

## Roadmap and status

Statuses: `Planned`, `In progress`, `Blocked`, `Complete`, or `Deferred`.
Completion requires the milestone's acceptance criteria and recorded evidence.
Deployment status must be recorded separately from implementation status.

| ID | Milestone | Priority | Status | Dependencies |
| --- | --- | --- | --- | --- |
| M0 | Reliable shared data, facility registry, and freshness | First release foundation | Complete | Existing collection and storage |
| M1 | Hospital self-comparisons and recent trends | First public feature | Complete | M0 reader, baseline inputs, freshness states |
| M2 | Travel-and-wait comparison | Next public feature | In progress: static prototype published; local fixtures and one live provider probe validated; acceptance work remains | M0, M1, verified destinations, travel-time source, metric interpretation |
| M3 | Relationships and spillover exploration | Analytical track | In progress: heatmap deployed; offline relationship study run (no confirmed pair association); map and replay implemented and validated locally 2026-09-26 (not deployed); predictive check remains for the 2026-10-15 revisit | M0, M1; the map uses OpenStreetMap campus centers |
| M4 | Area summaries, stability, and historical alternatives | Follow-on features | In progress: area counts and stability validated and deployed 2026-09-24; historical alternatives deferred to M2 | M1; geographic summaries need region metadata; travel scenarios need M2 |
| M5 | Time-series modeling and short-horizon forecasts | Analytical track; conditional forecast release | In progress: v2 candidates scored on development and calibration under a frozen selection; one pair holdout-eligible; holdout unscored; no public forecast | M0 validated history and freshness, M1 benchmarks; M2/M3 integration follows separate validation |

M0 and M1 acceptance criteria are satisfied by local validation described below;
their AWS release is documented separately on 2026-09-22. M3 analysis can begin
after M1's data preparation without waiting for M2's UI. M5 can also begin after
M0/M1; its number preserves existing milestone references rather than requiring
M2–M4 to finish first. M2's initial release does not depend on forecasting.

### M0: Shared data and freshness

Deliverables:

- Extract reusable data loading and validation from the dashboard. Select a single
  source per date, handle partial compacted days explicitly, deduplicate logical
  keys deterministically, and filter or group by metric as well as facility.
- Use explicit UTC boundaries for storage reads and `America/Chicago` for local
  comparisons. Handle empty datasets, malformed records, missing facilities,
  and collection gaps without silently producing plausible current values.
- Create a facility registry with stable slug, display name, region, timezone,
  official source URL, and verification date. Add verified coordinates, emergency
  entrance, service/age applicability, and active status before using a destination
  in travel comparisons. Unknown metadata must remain explicit.
- Publish a small latest-observation artifact after each successful collection.
  Include per-facility observation time and reporting state; preserve failed
  attempt information separately from the last successful reading.
- Refresh current values independently of the hourly Quarto build. Expose
  observation age, refresh failure, and stale/missing states per facility.
- Make freshness thresholds explicit and configurable, informed by the observed
  collection cadence and confirmed source behavior. Repeated equal values alone
  must not be treated as proof of a failed feed.
- Document the collection and compaction schedules when verified. Add coverage
  and collection-failure summaries for operators.

Acceptance criteria:

- Focused validation covers raw/compacted overlap, duplicate handling, partial
  days, metric separation, timezone boundaries, empty input, and failed facilities.
- An integration check demonstrates that a new observation can appear without a
  site rebuild, and stale values cannot appear current after a failed refresh.
- Website deployment preserves independently published data artifacts. The
  existing `aws s3 sync --delete` requires an explicit exclusion or separate
  deployment location before data is published outside the render output.
- Storage and schema documentation reflect any changed contracts. Existing raw
  observations retain their provenance.

Implementation and validation evidence (2026-09-14):

- [Shared reader tests](../tests/test_data.py) cover raw/compacted overlap,
  fingerprint mismatch after late raw arrival, open/legacy/compacted-only days,
  deterministic duplicate ties, metric separation, UTC midnight and local DST,
  empty input, malformed lines/gzip, gaps, missing facilities, and storage errors.
- [Collector/latest tests](../tests/test_latest.py) cover partial/total failures,
  deadline skips, absent expected metrics, raw/operations/publication ordering,
  zero values, integer validation, conditional-write retry, retained prior state,
  and out-of-order batches. [Schema tests](../tests/test_contracts.py) validate
  emitted artifacts including embedded observations. At M0 validation, the
  [empty dashboard check](../tests/test_dashboard.py) executed the then-current
  four Python cells with no history and retained the registry and explicit
  unavailable-history message. All **24 Python tests passed**. M1 later updated
  this check for its initial three-cell prepared-artifact view; the overview
  follow-up below restores a fourth presentation cell.
- All **6 JavaScript tests passed** in [the client suite](../tests/latest.test.mjs),
  including localhost HTTP refresh without HTML rebuild, stale/failure/recovery,
  missing/zero/future values, malformed/regressing artifacts, and request timeout.
  The actual AWS CLI was also run against a local S3 listing fixture with
  `--dryrun`: ordinary stale website files were selected for deletion, while
  `data/latest.json` was preserved and a local `data/*` file was excluded from upload.
- Quarto 1.10.18 successfully rendered the full site using read-only live S3
  history. Browser inspection confirmed the live cards, history, and operator
  disclosure. Synthetic local latest artifacts generated by the Python publisher
  changed a card from 0 to 321 minutes on an already-open page. The HTML SHA-256
  remained `019A8CE60E172A916E7F682EC706EEF56C8F357A667112238E6EC975A855284B`.
  A local 404 then displayed `Refresh failed` and `Stale · Refresh failed` on
  retained readings; recovery and final client loading were checked with no
  browser console errors. These numbers are test fixtures, not hospital readings.
- Verified EventBridge rule schedules and target names, Lambda runtimes/timeouts,
  and existing website read policy without changing AWS. Contract, schedule,
  ownership, cache, and rollout details are in [S3 reference](s3-buckets.md) and
  [M0 operations](m0-operations.md). Original raw records were not rewritten.

Deployment: **deployed 2026-09-22**. IAM/environment setup, Linux packaging of both
Lambdas, workflow data-path protection, and S3 publication are complete. Scheduled
collection, public schemas/headers, ETag preservation, and production client refresh
were verified; browser automation was unavailable at that release. The public
desktop/mobile review passed in the [2026-09-23 UTC follow-up](production-followup-2026-09-23.md).
See the [release evidence](aws-deployment-2026-09-22.md). Provider API
clinical/update/sentinel semantics remain unconfirmed; the provisional freshness
policy measures collection age only. Verified travel metadata is required before
M2 uses any destination. These limits are explicit in the UI and registry.

### M1: Self-comparisons and trends

Deliverables:

- Open with the all-hospital line chart, showing every configured facility over
  seven days by default, with hover readings, legend controls, and a 24-hour
  option. Keep individual comparisons below this overview (user review preference).
- Fit the overview's y-axis to the values visible in the selected time window
  and hospital selection. Use a visualization-first page with compact controls
  and expandable explanations instead of prominent prose and summary cards.
- Show current published wait, observation age, typical range, median baseline,
  difference from baseline in minutes, historical percentile, and recent direction.
- Provide a selectable 24-hour history with a shaded typical range, plus access
  to longer history. Keep absolute wait and deviation from usual visible together.
- Use the selected rolling baseline of 28 previous local days, comparable local
  hours, and weekday/weekend groups, with explicit broader fallbacks. The
  evaluated 42-day alternative and its results remain recorded below.
- Report contributing distinct days and coverage. Define a minimum-support rule,
  broader fallback groups, and an insufficient-history state before release.
  Avoid presenting six or seven repetitions of an exact weekday/time as a precise
  estimate. Add finer weekday patterns only when supported by history.
- Specify the typical percentile band, unusualness thresholds, trend window,
  and minimum meaningful change after historical replay. Avoid unstable percentage
  changes where the baseline is near zero.
- Keep request-latency diagnostics available to operators without occupying the
  main hospital-comparison view.

Acceptance criteria:

- Baselines used in replay are derived only from observations available before
  the comparison time. Document treatment of gaps, zeros, and sparse groups.
- Inspect historical replays across facilities, low/high-wait periods, and sparse
  history. Record the selected settings and supporting examples here.
- Check mobile layout, keyboard access, readable labels, and non-color indicators
  for unusual, stale, and missing values.
- The first-release view answers reported wait, historical context, and freshness
  without implying an individual patient's wait or care quality.

Implementation and validation evidence (2026-09-14):

- [Past-only replay and selected settings](m1-validation.md) inspect 89,978
  validated observations from 47 UTC partitions, without combining raw and
  compacted copies. Selection used 9,120 hourly cases, followed by 3,360 later
  cases across all 20 facilities. Exact inputs, settings, candidate metrics,
  sensitivity checks, and 12 low/high/zero/sparse/fallback examples are recorded
  in [the evidence artifact](m1-replay-evidence.json).
- Selected 28 previous local days, same weekday/weekend type and hour ±1;
  fallback to hour ±2, then all days. Require eight adequately covered distinct
  days, 64 readings, and 75% expected-slot coverage; a contributing day itself
  needs 75% coverage. Missing dates count against coverage; DST denominators are
  explicit. The 42-day candidate improved common-case mean absolute deviation
  by only about 0.18 minutes while supporting 41.2% rather than 98.9% of early
  cases. All later cases had support. These are bounded descriptive results,
  not proof of an optimal baseline or a calibrated patient-wait interval.
- The middle-50% band and median describe historical published readings.
  Unusualness requires the outer 10% plus a 10-minute difference. Recent direction
  compares with at least two observations 40–80 minutes earlier, using the same
  10-minute threshold and a 20-minute maximum internal gap. Ties use midpoint
  percentiles; reported zeros are retained without percentage changes. Same-day
  and future observations cannot enter the reference. Sparse groups expose
  support and unavailable context rather than fabricated values.
- Website-owned `comparisons.json` combines versioned reference models and seven
  rolling days of past-only historical comparisons in one complete artifact.
  Hourly preparation uses the M0 reader; the browser appends live readings and
  refreshes current comparisons independently. Reference failure, age of two
  hours, local-date expiration, or unconfirmed live freshness pauses comparisons.
  Latency remains in an operator disclosure. [Storage](s3-buckets.md),
  [schema](comparisons.schema.json), and [operations](m1-operations.md) document
  ownership, cache behavior, preparation, and release checks.
- All **35 Python and 11 JavaScript tests passed**, including M0 regressions and
  M1 timezone/DST, leakage, support/fallback, duplicate slots, zero/tie arithmetic,
  direction gaps, schema, live-change/failure integration, chart gaps, and
  accessible tables. A live read-only preparation produced 20 facilities and
  13,440 historical points; the complete artifact passed schema validation and
  Quarto rendered successfully. Desktop/mobile Chrome checks verified hospital
  selection, 24-hour/seven-day history, keyboard navigation/table expansion,
  readable layout, and text labels for unusual, stale, and missing fixtures.

Deployment: **deployed 2026-09-22** with M0. No required local M1 implementation or
acceptance work remains. Public comparison/context schemas and current client
state were verified, including a real collector update with unchanged HTML.
The public visual review and updated manual GitHub build passed in the
[2026-09-23 UTC follow-up](production-followup-2026-09-23.md); scheduled delivery
still needs observation. The limited 47-day assessment
does not establish seasonal stability; revisit settings with longer history.
Provider metric/sentinel semantics remain unconfirmed. M2 was still planned at
this M1 completion checkpoint; the later M2 section records its current progress.

Review follow-up (2026-09-14): restored the Plotly all-hospital line chart as the
first feature on page load at the user's request. All 20 facilities are initially
shown; legend clicks hide/show lines and double-clicks isolate a hospital. The
overview has seven-day/24-hour controls, Chicago labels and hover times, explicit
collection gaps, and a dated preparation note. It uses the existing prepared
history and updates with the site build; live individual comparisons remain below.
All 35 Python tests passed, including the updated four-cell empty-page check.
Data checks confirmed all 13,440 prepared points and 20 traces, preserved zero and
gap behavior, and the seven-day default. Quarto rendered and the localhost preview
served the overview before the individual selector. Storage/record contracts and
deployment are unchanged. See [follow-up validation](m1-validation.md#overview-follow-up).

Second review follow-up (2026-09-14): changed the presentation to a full-width
dark plotting canvas with compact native hospital controls and a shared time
switch. The overview now fits its y-axis to visible hospitals and the selected
24-hour/seven-day window, including line segments crossing a window boundary
without joining collection gaps. Individual context uses a compact range graphic,
wait/difference values, and aligned history; methodology, data tables, and operator
detail are collapsed. Freshness and insufficient-history states remain explicit.
All 35 Python and 15 JavaScript tests passed, including four new scaling and
control regressions. Quarto rendered with freshly prepared history. Browser
inspection was not completed: Edge was not approved for Computer Use, and the
subsequent approved-browser attempt was stopped by the user's Escape key. The
preview is ready for visual review; no production deployment or contract change.

Typography/layout follow-up (2026-09-14): user review identified a large blank
area before the overview legend and requested Inter with a 12 pt minimum.
Quarto had classified the combined Plotly library and chart output as a header
dependency, moving the chart and leaving its sized container empty. Emitting the
library separately keeps the plot inside that container, directly above the
legend. Inter is bundled with its license and served locally. All page text,
including chart ticks/tooltips, captions, controls, and disclosures, uses at least
16 CSS px; SVG charts redraw at their displayed width to preserve label size.
Controls and comparison metrics wrap instead of reducing their font size.
All 35 Python and 15 JavaScript tests passed, followed by a successful Quarto
render. Chrome inspection at desktop and 390/320 px viewport overrides confirmed
the plot/legend adjacency, a measured 16 px minimum, no page overflow, and working
seven-day/24-hour scaling. No browser console errors were observed. This completes
the previously pending browser review for the current presentation; dated earlier
observations above remain historical. [Detailed validation](m1-validation.md#typography-and-spacing-follow-up).
Deployment and record/storage contracts are unchanged; the update is local only.

### M2: Travel-and-wait comparison

Started 2026-09-14 after the documentation audit through M1. **In progress:** the
local prototype and TomTom adapter are implemented with automated validation;
destination/metric verification, representative hospital-route evaluation, and
public hosting implementation remain unresolved. A local user-provided key and
one live nonclinical TomTom v3 request passed on 2026-09-23 UTC. Cloudflare Workers
Free with a shared SQLite Durable Object is the selected design, implemented and
validated locally on 2026-09-26 (below) but not configured or deployed.
[Readiness evidence](m2-readiness-2026-09-23.md).
Destination research on 2026-09-23 UTC recorded official active-status, service and
age evidence for all 20 facilities in the registry but found no verifiable
emergency-entrance coordinates. By user decision, destinations now route to
OpenStreetMap campus centers labeled "ER entrance unconfirmed" until entrances are
added from reviewed imagery with `python -m edwait.entrances`; a reviewed entrance
always takes precedence. 18 adult and 4 child destinations are eligible (Leake:
active status unverified). A budgeted live check sent 54 routes from three public
city centers: 54/54 succeeded, ending at most 61 m from the campus points (300 m
tolerance). The page probes `GET /api/routes/status` and keeps Compare disabled
without a confirmed gateway. [Destination evidence](m2-destinations-2026-09-23.md).
M2 is not complete. Its static interface was deployed with M0/M1 on 2026-09-22,
but routing remains local-only and no preferred hospital recommendations are enabled.
Correction (2026-09-24 UTC, found during M4): `travel.json` 90th percentile movement
was read from unsorted changes, so published values were not percentiles (Memphis
15 minutes: 5.2 versus a sorted 44.4). The screen only appears beside routes and
never reached public users. Preparation now sorts first, with a regression test and
an unchanged schema; corrected values were published with M4 on 2026-09-24. [Evidence](m4-validation.md#m2-movement-correction).
Gateway (2026-09-26 UTC, local only): [`gateway/`](../gateway/) implements the
public design as a Worker that passes the S3 dashboard through and serves
`/api/routes` at the same origin, with one SQLite Durable Object that serializes
comparisons, holds the only usage ledger and persists the provider cooldown.
Destinations come from the published `travel.json`, which gains an additive
`arrival_point` per facility, so the gateway always routes to exactly the page's
eligible set. 14 unit tests (in the site's Node suite), 11/11 end-to-end checks in
`wrangler dev` with a mock provider, a browser Compare through the served page, and
one live comparison (18/18 routes, 4.6 s) passed. Deployment needs the account
owner's Cloudflare account, terms review and secret; see
[gateway operations](m2-operations.md#cloudflare-gateway). Leake recheck
(2026-09-26): official pages still lack 24/7 wording, while CMS lists it as a
critical access hospital with emergency services (42 CFR 485.618 requires 24-hour
availability); the user decides whether that evidence qualifies. Traffic profiles
(2026-09-26): TomTom's historical-mode routes for Monday 2026-09-28 at 08:00 and
17:00 Chicago time averaged about 4 minutes (at most about 8, ratio up to 1.21)
longer than at 03:00 across 54 public-origin routes. Its `live` delay field counts
only jams, so the zero delays seen so far do not establish live coverage; a live
weekday-peak run remains. [Evidence](m2-validation.md#traffic-profiles-and-rush-hour--2026-09-26-utc).
Benefit rule (2026-09-26, offline): a [pre-registered backtest](m2-benefit-protocol.md)
on the frozen snapshot before M5's holdout asked how often an alternative's lower
estimate still held with published waits at arrival. No candidate reached the 0.90
reliability gate (fixed 10–60 minute margins about 0.84–0.86; the current screen
0.85; half-weighted screen 0.875), so no rule was selected and preferred-option
claims stay disabled. Memphis-origin claims failed most (exploratory). [Results](m2-benefit-validation.md).

Implemented locally:

- Origin coordinates, opt-in GPS, or a clickable map with a draggable pin,
  keyboard center selection, and synchronized inputs. GPS/map selection work
  independently of age, destination eligibility, routing context, or a TomTom key;
  only Compare is gated. GPS progress/errors are separate from routing status,
  and newer origin choices cannot be overwritten by late callbacks.
  Adult/child controls, explicit Compare/Clear,
  drive-plus-wait bars, component ages, closest-by-road differences, and a labeled
  fictional example. The opening all-hospital chart and M1 interactions remain.
- Lazy-loaded MapLibre GL JS 6.9.1 with a local dark style, bundled Inter labels
  at least 16 px, and free OpenFreeMap tiles/sprites. No map account or key is
  needed. Clear removes the pin and returns the view to Memphis. Map-area
  sharing, provider attribution, local assets, and privacy are documented in
  [M2 operations](m2-operations.md#origin-map-and-location-controls).
- A TomTom Orbis Routing v3 gateway, replacing the initial OSRM adapter at the
  user's request. One individual Routing call per verified destination requests
  live traffic where available; the key stays in a server-side header. A durable
  date/count-only budget reserves usage before calls, bounded concurrency and
  deadlines limit requests, and quota/configuration errors pause estimates.
  Routes expire after five minutes with no automatic retries or fallback.
  A user-provided local key passed one live provider probe on 2026-09-23 UTC;
  account settings and representative hospital routes remain unverified.
  [Provider, free allowance, and operating policy](m2-operations.md).
- Past-only 15/30/60/120-minute historical movement context, with support/gap
  checks and a provisional 10-minute-plus-both-movements screen. This is
  descriptive and cannot enable recommendations. No M5 forecasts are used.
- Same-origin POST with transient origins, no app location logs/storage,
  in-flight cancellation, and disclosed transmission to TomTom. Website-owned
  `travel.json` contains no origins or routes; raw/latest contracts are unchanged.
  The transient v2 response has a separate [route schema](routes.schema.json);
  requested traffic mode does not assert coverage, and delay is not counted twice.

Validation: the TomTom follow-up passes 49 Python and 25 JavaScript tests,
including v3 request/response fixtures, HTTP integration, persistent/atomic quota
accounting, failures, and traffic-delay arithmetic. Actual TomTom connectivity
was untested at that checkpoint; the later live check is recorded in the
[readiness follow-up](m2-readiness-2026-09-23.md). Quarto rendered, and refreshed Chrome desktop/mobile
checks confirmed provider disclosure, example arithmetic, empty eligibility,
Inter at 16 px minimum, and no horizontal overflow. Initial prototype artifact,
render, OSRM connectivity,
and desktop/mobile evidence remain dated history; the OSRM check is not evidence
for TomTom. [Dated evidence and remaining gates](m2-validation.md).

Origin-selection follow-up (2026-09-14): fixed the eligibility gate that kept
Use my location disabled. Eight added JavaScript checks cover independent GPS,
permission/timeout/insecure errors, map/manual/keyboard synchronization, Clear,
late callbacks, map failure, and explicit-only route requests. The full validation
now totals 49 Python and 33 JavaScript tests. Quarto and Chrome desktop/mobile
checks verified the actual map, click/drag/keyboard selection, clearing, Inter,
and no horizontal overflow. GPS results/errors were simulated; no actual user
position was read and no TomTom route request was made. No deployment or M2
acceptance-status change. [Detailed evidence](m2-validation.md#origin-selection-follow-up--2026-09-14).

Deliverables:

- Allow a user-provided origin or opt-in location access. Filter destinations by
  verified applicability and active status before comparing estimates.
- Support map click/tap, draggable-pin, coordinate and keyboard origin selection
  independently of routing availability. Preserve transient origins and disclose
  the map provider's area requests separately from route transmission.
- Obtain road travel times to eligible facilities. The local prototype selects
  TomTom's individual Routing API with traffic requested; validate the live v3
  contract, free-plan configuration, provider terms, coverage, bounded usage,
  failure behavior, and free gateway hosting before public activation.
- Initially calculate `travel_minutes + latest_published_wait_minutes` and show
  both components, observation age, extra travel, and estimated difference from
  the closest suitable option. Define closest by estimated road travel time.
- Clearly label the sum as a comparison estimate, not a promised time to treatment.
  Suppress a preferred-option claim when observations are stale, suitability is
  unknown, or the apparent benefit is too uncertain.
- Evaluate uncertainty using historical changes over relevant travel horizons.
  Define a meaningful-benefit rule and label its limitations before release;
  historical variability is not automatically a calibrated prediction interval.
- Keep precise origins transient by default. Document any provider transmission
  and avoid logging or retaining location unless a product requirement warrants it.
- Consider forecasts at expected arrival time only after forward-in-time
  evaluation against carrying the latest reading forward and a historical baseline.
  Use M5's validated facility/horizon results for any later forecast integration;
  do not extrapolate beyond a model's evaluated horizon or transfer its accuracy
  claim to the combined travel-and-wait estimate without separate validation.

Acceptance criteria:

- Confirm source metric interpretation and destination applicability before
  publishing preferred-option recommendations.
- Verify component arithmetic, route failures, unavailable traffic, stale waits,
  denied location access, ineligible facilities, and an empty candidate set.
- Record provider choice and the uncertainty/benefit policy. Hypothetical examples
  must be labeled, and retrospective comparisons must not claim measured patient
  time savings.
- Any forecast must demonstrate useful improvement on held-out later periods,
  by facility and horizon, with documented error and interval coverage if intervals
  are shown. Disable forecast-based claims where performance is inadequate.

### M3: Relationships and spillover exploration

Started 2026-09-23 UTC. **In progress:** the first deliverable's facility-by-time
heatmap is implemented in [heatmap.mjs](../dashboard/heatmap.mjs) from existing
`comparisons.json` history, with no new artifact or contract. Cells show the
median M1 difference from usual per hour (seven days) or 15 minutes (24 hours)
in seven discrete diverging steps, neutral within ±10 minutes; blank periods lack
readings and hatched periods lack a usual range. Rows focus the individual chart
by click or keyboard; a summary table and limits note sit in a disclosure.
Validated with five JavaScript tests, a published-module check, live-history
render and Chrome desktop/390/320 px review. [Evidence](m3-validation.md).
Relationship study (2026-09-24 UTC, offline): a [protocol](m3-relationship-protocol.md)
fixed before scoring defines neighbor pairs as campus centers within 50 km (21
pairs; Memphis metro, Attala–Leake and Booneville–North Mississippi–Union County
groups) and tests all 190 pairs on M5's frozen snapshot. Hourly difference from
M1's past-only usual median is screened on 2026-08-12 to 09-02 (supported from
08-19) and candidates are re-tested on 09-02 to 09-16; M5's final holdout is not
read. Of 1,520 same-time co-deviation, same-time change and 1–3 hour lagged-change
tests, one passed discovery (Tipton–Leake, 311 km apart) and it failed
confirmation. Neighbor pairs' median correlations (−0.02 to 0.04) match distant
pairs. Autocorrelation-adjusted p-values were essential: unadjusted, 85 of 190
co-deviation pairs looked significant, against 12 adjusted. The co-deviation
screen can miss moderate effects (|ρ| below about 0.37 after BH); hour-to-hour
co-movement above about 0.2 is unlikely in this window. Eight tests cover it.
[Results and limits](m3-validation.md#relationship-study--2026-09-24-utc).
Map and replay (2026-09-26 UTC, local, not deployed): under the heatmap, each
hospital sits at its campus center colored with the same binned values (▲/▼/●/?
glyphs, accessible labels, select to focus), with a replay slider, Play and Latest
that outline the period in the heatmap, and area views that separate the Memphis
cluster. No new artifact; the page's embedded registry gains campus points. Seven
new tests; headless Chrome confirmed markers, replay, focus linking and 390/320 px
layouts. [Evidence](m3-validation.md#map-and-replay--2026-09-26-utc). Held-out
predictive checks remain for the 2026-10-15 revisit; with no confirmed association
there are no specific episodes to inspect. No relationship finding is claimed.

Deliverables:

- Start with a facility-by-time heatmap colored by deviation from usual and linked
  facility histories. Add geographic placement and historical replay controls.
- Define neighboring groups using verified geography or travel times. Account for
  distinct regions and service populations when interpreting relationships.
- Align observations at an appropriate common cadence, preserve missing periods,
  and adjust for facility-specific time-of-day and calendar patterns.
- Examine simultaneous changes and plausible time lags. Account for serial
  dependence and the number of pairs/lags explored when evaluating evidence.
- Evaluate whether neighboring histories improve prediction beyond each facility's
  own history and shared regional patterns on later, held-out time periods.
  Share the chronological forecast evaluation harness with M5; add neighboring
  readings only when they would be available at the forecast's issue time.
- Show sample support, missingness, lag, and stability of findings. Use language
  such as "often rises together" or "historically preceded" only when supported.
- Do not draw patient-flow arrows or make causal spillover claims from wait data
  alone. Record additional evidence needed for that interpretation, such as
  arrivals, transfers, diversion records, or a defensible causal study design.

Acceptance criteria:

- The explorer makes it possible to inspect the episodes behind an association.
- Relationship estimates survive checks for common calendar patterns, gaps,
  serial dependence, and stability in later periods, or are labeled exploratory.
- Geographic adjacency and time precedence are clearly distinguished from
  evidence of patient movement. Weak or unstable results are not promoted as findings.

### M4: Follow-on opportunities

Started 2026-09-24 UTC at the user's request. **In progress:** area counts and wait
stability are implemented, validated, and deployed (2026-09-24). Historical
alternative availability is deferred.

| Feature | Intended behavior | Validation or dependency | Status |
| --- | --- | --- | --- |
| Area-wide elevated waits | Count reporting facilities above their own usual range in a selected region; display reporting coverage | M1 baselines and region metadata; describe facility counts, not occupancy or patient-weighted load | Deployed 2026-09-24 |
| Wait stability | Summarize the frequency and magnitude of changes alongside the latest reading | Horizon-specific history, adequate coverage, and clear distinction from patient wait uncertainty | Deployed 2026-09-24 |
| Historical alternative availability | Replay how often an alternative had a lower travel-plus-published-wait estimate during elevated episodes | M2 inputs; identify assumed travel times and distinguish scenarios from observed historical traffic | Deferred: needs validated travel times per origin, and M2 routing is neither public nor validated at traffic hours |

Deliverables (defined 2026-09-24):

- Area counts use M1's above/below-usual rule (outer 10% plus 10 minutes), not the
  middle-50% band. The band is exceeded about a quarter of the time by construction.
- Areas are all hospitals, registry states, and M3's pre-registered 50 km
  campus-center neighbor groups with at least three members. Label the basis:
  straight-line grouping, not travel time or service area.
- Show current counts from live readings, and keep compared, unsupported and
  not-current hospitals distinct. Pause counts when M1 comparisons pause. Show
  history in the shared 24-hour/seven-day window, with coverage visible and a
  window-typical count. Do not label any count an area-wide event.
- Stability uses complete previous local days and M2's support rules. For each
  horizon it shows the median and 90th percentile absolute change and the shares
  rising or falling by 10+ minutes. Label it as past movement of published readings,
  not a forecast or a patient's wait range.

Acceptance criteria:

- Tests cover the classification rule, binning, missing/stale/unsupported states,
  gaps, sparse history, schema contracts and accessible text.
- Compare area counts with an independence reference before claiming anything
  area-wide. Revisit that comparison with longer history.
- Desktop/mobile review confirms Inter at 16 px minimum and no page overflow.
  A deployed smoke check covers the new module and fields.

Implementation evidence (2026-09-24 UTC): [area view](../dashboard/area.mjs),
[area groups](../edwait/areas.py), [stability](../edwait/stability.py), preparation
and schema changes. Tests: 84 Python and 46 JavaScript passed. Real S3-backed data
preparation validated both schemas, and Quarto rendered. The Chrome review covered
desktop plus 390/320 px frames. It found and fixed a phone-width overflow caused
by the area select, then measured a 16 px text minimum.

Over seven days, hospitals were each above usual in about 10% of compared hours.
All-hospital counts had a median of 2, and 3+ occurred in 33% of hours against 30%
expected under independence. Memphis-area counts had a median of 1, and 3+
occurred in 4.8% of hours against 3.2% expected. Counts are shown descriptively.
Stability had support for all 20 hospitals at every horizon. Memphis's 1-hour
median/90th percentile change was 23/89 minutes, against NEA Baptist's 1/6.

The shared stability code exposed an M2 defect: `travel.json` percentiles came from
unsorted changes. Both features now use sorted values; the M2 section records the
correction. [Evidence](m4-validation.md).

Deployment: **deployed 2026-09-24** after the user approved the push. The 03:17
UTC EventBridge dispatch built `8242ad1` (run [35950813345](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35950813345)), and the 04:17 dispatch
rebuilt it (run [35955001963](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35955001963)). Both workflow public checks passed. An independent check
at 04:26 UTC passed as well: 20/20 current facilities, `area.mjs` and the area
section published, stability for all 80 facility-horizons, and corrected
`travel.json` percentiles (Memphis 15 min: 44.4). A Chrome check of the public page
showed live area counts, 168 hourly columns, the stability graphic, no page
overflow and no console errors after a reload.
[Release evidence](production-followup-2026-09-23.md#m4-release).

New provider coverage and stronger causal analysis remain optional extensions
requiring separate evidence and scope decisions before implementation.

### M5: Time-series modeling and short-horizon forecasts

Status: **In progress**. Began the reproducible offline modeling study on
2026-09-23 UTC, then add
forecast visualization only for facility/horizon combinations that satisfy the
release criteria. Forecast the collected `CV_ED_Wait` reading in minutes;
individual patient waits and care outcomes are outside this modeling target.

Deliverables:

- Prepare one regular time series per facility/metric using the M0 reader.
  Evaluate a 15-minute UTC grid, with explicit slot assignment, duplicate
  selection, missingness, and America/Chicago calendar features including DST.
  Retain reported zeros and original records. Document any training-only
  treatment of unusual or negative readings; never silently rewrite raw values.
  Any imputation must use only data available at each forecast origin, must be
  marked, and must not create validation targets or bridge long outages.
- Inspect trend, daily/weekly patterns, autocorrelation and partial
  autocorrelation, differencing needs, structural changes, and residuals by
  hospital. Establish minimum training length, complete seasonal repetitions,
  and gap limits. The dated 47-day assessment is a starting dataset, not evidence
  of stable seasonality or adequate support for every seasonal specification.
- Benchmark last-observation carry-forward, seasonal naive forecasts, and the
  M1 local-time median against facility-specific ARIMA models. Evaluate seasonal
  ARIMA (SARIMA) and calendar regressors with ARIMA errors (SARIMAX) where
  supported. Bound order/seasonality searches, inspect convergence and residual
  dependence, and prefer simpler models when later-period accuracy is similar.
  Statsmodels is the initial Python implementation candidate; its ARIMA interface
  supports seasonal terms and external regressors. [Official ARIMA reference](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html).
- Start with candidate horizons of 15, 30, 60, and 120 minutes. Select training
  windows, model orders, transformations, and refit cadence using chronological
  development folds, then freeze choices before a final later-period holdout.
  Evaluate successive forecast origins using only their past observations and
  score each horizon separately. [Rolling-origin evaluation reference](https://otexts.com/fpp3/tscv.html).
  Match targets to explicit future slots; exclude missing targets and report
  their counts. Replay collection availability as well as observation time;
  document any unavailable ingestion-timing evidence. Never use randomly shuffled
  splits, future-filled gaps, or actual future hospital values as regressors.
- Report MAE, RMSE, signed bias, and errors during spikes, low/zero periods,
  gaps, and changing regimes, by facility and horizon as well as overall.
  Compare models on matched origins and include failure/abstention rates.
  Avoid percentage-error metrics that divide by zero. Assess candidate 80% and
  95% prediction intervals using empirical coverage and width; validate any
  transformations or nonnegative output constraints in the same replay.
- Produce visual backtests with observed and forecast lines, uncertainty bands,
  and error-by-horizon comparisons. Any dashboard forecast should be a selectable
  layer in the focused hospital chart, with a clear forecast boundary and visual
  distinction from M1's historical middle-50% band. Preserve the opening
  all-hospital observations chart, Inter/16 px minimum, and little visible prose.
- Define forecast issue time, last observation, training cutoff, target times,
  model/version, support, interval levels, expiration, and unavailable/fallback
  reasons before publishing an artifact. Benchmark fitting/update cost within
  the existing Python build pipeline. Set refit/update cadence and monitoring
  for error, interval coverage, drift, and fit failures from measured results.

Acceptance criteria:

- A reproducible, dated report records input snapshots, dependencies, model
  specifications, split boundaries, target-slot policy, training-only processing,
  all baseline results, and a per-facility/per-horizon release decision.
  Tests cover leakage, missing/zero readings, DST, sparse histories,
  nonconvergent fits, and unavailable future regressors.
- Set minimum useful error improvement, interval-coverage tolerance, support,
  failure-rate, and runtime limits on development data before the final holdout.
  Release a model only where it meets these gates against the strongest simple
  benchmark on later data. Account for dependent forecast errors when estimating
  uncertainty in gains; a pooled improvement must not hide weak hospitals or
  horizons. Residual diagnostics and in-sample fit alone do not establish value.
- A validated negative result is an acceptable study outcome: record it and
  keep model forecasts disabled where they fail the gates. Any fallback must
  be labeled as the baseline used, and stale/failed source data, expired models,
  or inadequate support must produce an unavailable forecast state.
- If forecasts qualify for display, validate time alignment, band/observation
  distinctions, expiration/failure recovery, keyboard access, mobile readability,
  and a deployed artifact-to-chart smoke check before public release. M2 routing
  claims still require its own interpretation and travel validation.

Implementation evidence (2026-09-23 UTC): froze 107,257 records across 56 UTC
partitions with SHA-256 provenance. Four simple benchmarks were evaluated over
14 development days, plus a one-slot availability-delay sensitivity. Carry-forward
had the lowest matched MAE in 70/80 combinations, M1 median in 10/80. Two bounded
ARIMA candidates produced 520 converged daily fits and 40 support abstentions;
only 1/80 combinations passed the provisional error-only screen and availability
was about 92.8%. Eight focused M5 tests cover leakage, UTC/DST, sparse/missing/zero
data, availability and failed fits. [Benchmark report](m5-validation.md),
[ARIMA pilot](m5-arima-validation.md), [frozen protocol](m5-study-protocol.md).

Candidate study v2 (2026-09-24 UTC): diagnostics on data before calibration found
weak daily/weekly structure (local hour explains 1–35% of variance) and shifting
weekly levels, so a 96-slot SARIMA was not fitted. Instead, a
[protocol amendment](m5-study-protocol.md#amendment--2026-09-24-utc-before-calibration-scoring)
added a cold-start trimming rule, ARIMA(1,0,0) with local daily Fourier regressors,
direct profile persistence, trailing seven-day empirical 80/95% intervals for every
model, a paired daily-block bootstrap, and a shortlist release rule. It also
replaced the unreachable 200-target support gate with 150 targets on at least six
days. Development: 1,120/1,120 fits succeeded; v2 reproduced all 61,200 overlapping
v1 forecasts; intervals were near nominal; and 5/80 pairs passed every gate. The
[freeze](m5-freeze.json) fixed those pairs, the specification/code hash and the rule
before calibration. On calibration, only Collierville 60 min (Fourier ARIMA vs latest
reading, +1.70 min, bootstrap +0.18 to +3.50) passed again. North Mississippi's
development gains vanished. Four non-shortlisted pairs, all using profile persistence,
passed calibration but cannot qualify in this study.
[Report](m5-candidates-validation.md). Seven new tests; 79 Python and 41 JS passed.

Completion records distinguish the modeling study, forecast display, and
deployment. By user decision on 2026-09-24, the final holdout (2026-09-16 to 09-23)
stays unscored and reserved while more data is collected; scoring it is a one-time
action and needs the user's explicit go-ahead. If Collierville 60 min passes
there, including the delayed-availability gain check, display would still need the
forecast artifact contract, chart validation and a deployed smoke check. Otherwise
the study ends with forecasts disabled. No public forecast artifacts, record/storage
contracts, or production forecasting changes exist.

## Implementation approach

Retain Python, S3, and Quarto for the first release. The inspected data volume
does not itself justify a database, application-framework migration, or complex
model infrastructure.

Separate responsibilities into collection, validated historical loading, derived
summaries, and presentation. M0/M1 implement the first two artifacts below; the
M2 prototype adds travel context. Relationship and forecast outputs remain proposed:

| Artifact | Update trigger | Contents |
| --- | --- | --- |
| `data/latest.json` | Completed collection, including partial/total facility failures | Versioned latest per-facility observation, separate attempt, timestamps, coverage, and freshness policy |
| `comparisons.json` | Each successful website preparation, before Quarto render (configured hourly/manual) | Versioned local-day/hour references, empirical distributions, support, coverage, seven rolling days of historical comparisons, M4 28-day wait-stability summaries (added and deployed 2026-09-24), and operator latency |
| `travel.json` | Same history read as M1 preparation | M2 eligibility reasons, arrival kind and (additive 2026-09-26, not deployed) arrival point, 15/30/60/120-minute historical movement and support, fixed provisional policy, disabled recommendation gate; no origins/routes |
| `relationships.json` | Validated analytical refresh | Supported pair/lag summaries, evaluation period, and limitations |
| `forecasts.json` (proposed, M5) | Validated model update cadence, to be selected after benchmarking | Facility/metric, issue time, last observation/training cutoff, future target times, point forecasts and interval levels, model version, support, expiration, and unavailable/fallback states |

M0/M1 outputs identify their schema/method version, generation time, source time
range, and coverage. Preparation writes a complete local replacement; failed
preparation/rendering prevents workflow sync. The browser retains dated history
on a failed fetch while pausing current comparisons. Reference fetches revalidate
every five minutes; latest observations retain M0's independent no-store polling.
Root `comparisons.json` and `travel.json` are website-owned; `data/latest.json` remains collector-owned
and excluded from website sync. Apply the same explicit contracts before wiring
future artifacts into the browser.

`POST /api/routes` is an ephemeral v2 response, not a website/S3 artifact; its
[schema](routes.schema.json) excludes origins, keys, and geometry. Local routing
usage persists only UTC date/count reservations in `.cache/tomtom-usage.sqlite3`.
Preserve this counter across restarts; free public hosting needs durable shared
accounting. This integration changes no raw/latest/travel artifact schema or S3
object layout. [Storage reference](s3-buckets.md#travel-context-artifact-m2-prototype).
The Cloudflare gateway (2026-09-26, not deployed) provides that shared accounting
in its Durable Object and reads `travel.json` arrival points; it writes nothing to S3.
The origin-map follow-up adds static renderer/style assets and direct browser
requests to OpenFreeMap. It stores no selected points, location history, or map
tiles in S3 and changes no observation, latest, travel, or route-response schema.

M5 has started with offline Python experiments using a frozen M0 snapshot.
Forecast schema, ownership, publication, and cache rules remain proposed until
implementation; update the storage reference and add a forecast schema in that
change. Offline study outputs do not alter existing record/storage contracts.

## Open decisions and immediate next work

| Question | Needed by | Next action |
| --- | --- | --- |
| What does each current upstream wait value mean, including zero? | M0 interpretation; required before M2 recommendations | Current emergency/location pages reviewed 2026-09-14 confirm published waits and triage guidance but do not establish this API's averaging/update/sentinel contract; preserve zeros and label uncertainty until confirmed. 2026-09-26: the API response carries no timestamp or caching headers; an inquiry to Baptist is drafted for the user to send ([draft](m2-metric-inquiry-2026-09-26.md), not sent) |
| What schedules and completion guarantees exist in deployment? | M0/M1 | Decided 2026-09-24 UTC: the user configured EventBridge rule `dashboard_hourly` to dispatch the workflow at minute 17 with a repository-scoped token, plus a failed-invocation alarm. GitHub cron ran 3–9 hours apart on 2026-09-23. Dispatches at 01:17–04:17 UTC on 2026-09-24 succeeded (4 invocations, 0 failed; alarm `OK`). Observed through 2026-09-25 23:17 UTC: all 47 hourly `workflow_dispatch` runs since 01:17 UTC on 2026-09-24 succeeded, while the backup cron ran 5 times a day, 3–6 hours apart. The email subscription was never confirmed and lapsed about two days after creation: a link re-sent at 2026-09-26 00:07 UTC did not extend it, and by 00:37 UTC the topic had no subscriptions, so the alarm notifies no one. CloudTrail redacts the address, so it could not be restored on the user's behalf. Next: the user re-creates and confirms the subscription, then remove the workflow's `schedule:` trigger; do not lengthen freshness limits. [Evidence](production-followup-2026-09-23.md#hourly-dispatch-through-eventbridge) |
| Where will independently refreshed public data live? | M0 | Resolved and deployed 2026-09-22: website-bucket `data/latest.json`, collector-owned, no-store, same-origin fetch; workflow excludes `data/*`; public refresh and preservation verified |
| What baseline groups and support thresholds work reliably? | M1 | Resolved for first release: 28 local days, weekday/weekend hour ±1 with explicit broader fallbacks, eight days/64 readings/75% coverage; [replay and limits](m1-validation.md). Revisit with more seasons and confirmed metric semantics |
| Which facilities are valid alternatives for each supported use case? | M2 | 2026-09-23: 19 active general-emergency destinations (Children's child-only; Anderson, DeSoto and Mississippi Baptist adult and child; others adult) and Leake unverified. Official pages and OpenStreetMap give no emergency-entrance coordinates (one unconfirmed OSM candidate at North Mississippi). User decided 2026-09-23: route to labeled campus centers now; add imagery-reviewed entrances later with `python -m edwait.entrances`. Next: the user's entrance reviews, then Leake's status and child scope at other general ERs. 2026-09-26: Leake's official pages unchanged; CMS lists it as a critical access hospital with emergency services, which federal rules require 24 hours a day. The user decides whether that meets the evidence rule or phones the hospital. [Evidence](m2-destinations-2026-09-23.md) |
| Which travel provider and benefit rule should be used? | M2 | TomTom key supplied locally; one budgeted live v3 contract probe passed. Validate actual hospital routes/coverage and benefit sensitivity after destination verification. Cloudflare Workers Free/shared SQLite Durable Object gateway implemented and validated locally on 2026-09-26 ([operations](m2-operations.md#cloudflare-gateway)); the user's account/terms review, secret and deployment pending. 2026-09-26: typical weekday-peak profiles add about 3–8 minutes to these routes; a live peak run (next Monday) must measure jams and reported-delay coverage. Benefit rule: a pre-registered backtest found no margin or screen reaching 0.90 precision, so none is adopted; revisit with fresh data at the 2026-10-15 checkpoint, pre-registering any per-area rule. [Results](m2-benefit-validation.md). Historical movement remains descriptive |
| Which geographic groups and lag ranges are defensible? | M3 | 2026-09-24: 50 km campus-center neighbor groups and 0–3 hour lags tested under a frozen protocol; no pair association confirmed and neighbors match distant pairs. User decided 2026-09-24 to revisit in a few weeks (around 2026-10-15): then consider a rerun on a fresh post-2026-09-23 snapshot (longer window, more power), whether a held-out predictive check is still worthwhile, and whether the negative result belongs in the heatmap disclosure. [Evidence](m3-validation.md#relationship-study--2026-09-24-utc) |
| Which time-series models add useful forecast skill, for which hospitals and horizons? | M5 | 2026-09-24: diagnostics done; v2 candidates selected on development and frozen; calibration left one eligible pair (Collierville 60 min, Fourier ARIMA). User decided 2026-09-24 to defer the one-time holdout and collect more data first; it stays reserved and unscored. When enough post-2026-09-23 history exists (for example, alongside M3's revisit around 2026-10-15), decide whether to score the reserved holdout and pre-register a new study on the fresh data, including profile persistence at 60–120 min for high-variance hospitals. [Evidence](m5-candidates-validation.md) |
| When do area counts indicate something beyond chance? | M4 | 2026-09-24: one week of counts matched an independence reference (all hospitals: 3+ above usual in 33% of hours versus 30% expected), so counts are shown descriptively beside a typical count. Revisit around 2026-10-15 with M3/M5 on longer history before adding any area-wide label. [Evidence](m4-validation.md) |
| What support, improvement, interval calibration, and update-cost limits justify forecast display? | M5; later M2/M3 integration | Frozen 2026-09-24 in the [protocol amendment](m5-study-protocol.md#amendment--2026-09-24-utc-before-calibration-scoring) and [freeze](m5-freeze.json): ≥1 min and 5% MAE gain, RMSE no worse, bootstrap gain interval above zero, ≥150 targets/6 days, ≥95% availability, ≤1% fit failure, coverage within 5 points, ≤10 min daily fitting; pass on calibration and holdout. Unavailable/fallback display behavior remains to be defined with the artifact contract if a pair qualifies |

Next checkpoint: all 47 hourly EventBridge dispatches through 23:17 UTC on
2026-09-25 succeeded. Once the user re-creates and confirms the alarm's email
subscription (it lapsed unconfirmed on 2026-09-26), remove the unreliable GitHub
`schedule:` trigger. M2's
destinations route to labeled campus centers with live routes validated, and the
free gateway is implemented and validated locally; next are the user's
imagery-reviewed entrances, Leake decision, metric inquiry, Cloudflare account and
deployment, plus traffic-hour route and uncertainty validation. M3's map and replay
await review and deployment. M3's heatmap is deployed and its
offline relationship study found no confirmed association; by user decision it is
revisited around 2026-10-15 with more history (rerun, predictive check, presentation). M5's development and calibration are scored under a frozen selection; only
Collierville 60 min remains eligible. By user decision the one-time holdout stays
reserved while more data is collected. M4's area counts and wait stability are
deployed; revisit area counts against chance around 2026-10-15. Historical
alternatives wait on M2. Provider-contract
uncertainty still blocks preferred-option claims, and no forecast display or public
routing service has been released.

## Maintenance and completion rules

- Before changing product behavior, data contracts, analytics, or deployment,
  read this plan and identify the affected milestone.
- Update the plan in the same change as implementation. Keep the status table,
  current implementation, dependencies, open decisions, and next task accurate.
- For completed work, record the date, affected milestone, implementation reference,
  validation performed, and deployment status in the progress log. Link commits
  or PRs when available; otherwise link the relevant source files.
- A milestone is complete only when its acceptance criteria are satisfied. Record
  partial completion and remaining tasks explicitly. Do not equate code written,
  locally validated, merged, and deployed.
- Record significant design choices, changed assumptions, and scope changes in
  the decision log. Replace superseded active guidance while preserving the reason
  for the change in that log.
- Update [S3 documentation](s3-buckets.md) and [the schema](ed-wait.schema.json)
  whenever their underlying contracts change. Keep dated audit findings distinct
  from newly verified evidence.
- Routine fixes that do not alter roadmap progress or design need no artificial
  milestone entry. Explain in the change summary when the plan remains applicable.
- Maintain this document during development work; no background monitoring or
  automatic synchronization is configured.

## Decision log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-09-26 UTC | Keep total project cost under $5 per month; estimate cost before adding any service, schedule or data volume, and never enable paid tiers (TomTom prepaid credit, Cloudflare Workers Paid) | User requirement. Measured: August $0.07, September 1–25 $0.17, all S3 requests (hourly builds read history); Lambda, EventBridge, SNS, the alarm and 1.7 GB/week egress were within free allowances; the public repo's Actions minutes are free. Main risk is S3 egress if traffic grows (5.5 MB page, 100 GB/month free) |
| 2026-09-26 UTC | M3 map: place hospitals at campus centers with MapLibre HTML-button markers colored by the heatmap's own bins, replay the shared window with an outline in the heatmap, and frame views with the existing area groups | Reuses validated values and colors, so map and heatmap cannot disagree; buttons keep markers keyboard- and screen-reader-accessible; area views separate the dense Memphis cluster; no new artifact or contract. Lazy loading keeps the opening chart first |
| 2026-09-26 UTC | M2 benefit rule: adopt none; keep preferred-option claims disabled and the movement screen descriptive | Pre-registered backtest: no candidate reached 0.90 precision on discovery (best 0.875), and confirmation matched. Larger fixed margins did not raise reliability. Uses only data before M5's final holdout so that holdout stays untouched |
| 2026-09-26 UTC | M2 gateway: read destinations from the published `travel.json`, which gains an additive `arrival_point` per facility, instead of bundling the registry into the Worker | The page validates route coverage against `travel.json` eligibility, so the gateway must compare exactly that set. A bundled copy would need a Worker redeploy for every registry change and could drift. The bucket already serves the page's code, so trusting its artifact adds no new trust. Fetched with `no-store` per comparison; stale or malformed context stops before reserving usage |
| 2026-09-26 UTC | M2 gateway: run every TomTom call in one SQLite Durable Object; the Worker only validates and passes through; serialize route starts and anchor them to the clock | Free-plan Workers allow 10 ms CPU per request, Durable Objects 30 s. One object gives one shared ledger, one comparison at a time and a persisted cooldown across redeploys. Timers can fire early: a naive limiter measured 14.7 ms between starts in tests, so grants are chained and wait until the clock reaches each slot, as the Python lock does |
| 2026-09-24 UTC | M4: count hospitals above/below usual under M1's outer-10%-plus-10-minute rule for all hospitals, states and M3's ≥3-member 50 km groups, shown beside a typical count with no area-wide event label. Add 28-day stability summaries to `comparisons.json` (additive, schema version unchanged) and defer the historical alternatives replay | Reuses validated rules and pre-registered groups rather than inventing regions. One week of counts matched independence, and M3 found no confirmed association. Stability shares M2's support rules. Travel replay needs validated routes |
| 2026-09-24 UTC | Sort changes before M2's movement 90th percentile | `quantile()` interpolates in the order given. Unsorted input made published values arbitrary. Found while sharing the code with M4 |
| 2026-09-24 UTC | Defer M5's final holdout; keep it reserved and unscored while more data is collected | User decision after the calibration checkpoint. Scoring is irreversible, a pass would support only one modest pair, and the busier-hospital profile hypothesis needs fresh post-2026-09-23 data anyway. Nothing public changes while it waits |
| 2026-09-24 UTC | M5 v2: add Fourier-regressor ARIMA and profile persistence (no 96-slot SARIMA), trim training through the last long outage, use trailing seven-day empirical intervals, shortlist pairs passing every development gate and release only if they pass again on calibration and holdout; support gate becomes 150 targets on six days | Diagnostics showed weak seasonality and shifting levels. The partial snapshot start caused all v1 abstentions. Empirical intervals are model-agnostic and use only passed targets. Hourly origins cannot reach 200 targets in seven days. Requiring two later passes guards against selection bias across 80 pairs. Frozen before calibration scoring |
| 2026-09-24 UTC | Test M3 relationships offline on M5's frozen snapshot with a pre-registered discovery (to 09-02) and confirmation (09-02 to 09-16) split, 50 km campus-center neighbor pairs, autocorrelation-adjusted Spearman tests, BH per family and system-wide/residual-hour checks; never read M5's final holdout | Wait histories are highly persistent, so naive tests overstate association. A fixed protocol, later-period confirmation and M5 holdout isolation keep a negative or positive result credible. Distance does not select tests, so neighbors can be compared with distant pairs |
| 2026-09-24 UTC | Dispatch the website workflow hourly from an EventBridge rule through an API destination and a repository-scoped fine-grained token (Actions read/write only), with a CloudWatch alarm on failed invocations; keep GitHub cron only until hourly delivery is observed | User decision. GitHub cron ran 3–9 hours apart on 2026-09-23, so two-hour context expired between builds. Reuses the tested workflow, protected sync and public checks without moving the build into AWS; an expired or revoked token fails without retry, hence the alarm |
| 2026-09-23 UTC | Route eligible destinations to OpenStreetMap campus centers labeled "ER entrance unconfirmed" until entrances are reviewed; reviewed entrances (official, imagery or site visit, within 1 km of campus) always take precedence; 300 m campus snap tolerance | User decision after no entrance evidence was found; supersedes the 2026-09-14 rule that campus points cannot enable routing. Labels, a recommendation blocker and the `arrival` field keep the approximation visible; 54/54 live routes ended ≤61 m from campus points |
| 2026-09-23 UTC | Record official active/service/explicit-age evidence per facility in the registry, keep `emergency_entrance` null, and never substitute campus centers, address geocodes or unconfirmed volunteer map points | Official pages and OpenStreetMap give no emergency arrival coordinates; the 2026-09-14 gate requires exact entrances. Explicit-only age evidence avoids assuming pediatric scope |
| 2026-09-23 UTC | Enable Compare only after `GET /api/routes/status` confirms a routing gateway | Once any destination qualifies, the static S3 page would otherwise post user coordinates to an endpoint that cannot serve them. The probe carries no origin and does not delay context loading |
| 2026-09-23 UTC | Begin M3 with a browser-side facility-by-time heatmap of median M1 difference from usual (hourly/15-minute bins, seven discrete diverging steps, neutral within ±10 minutes), linked to the focus chart | Reuses the validated `comparisons.json` history with no new artifact or contract; discrete steps tie colors to M1's meaningful distance; hatching separates unsupported from missing periods; descriptive only |
| 2026-09-23 UTC | Move hourly website cron to minute 17; serialize deployments, bound runtime, restrict repository-token permissions and check exact public build artifacts/freshness | User explicitly approved workflow edit/publication after a successful manual build. GitHub documents top-of-hour delays; mitigation does not guarantee delivery or remove local-midnight context expiry |
| 2026-09-23 UTC | Start M5 with frozen development data, explicit slot/availability rules, four benchmarks and two bounded ARIMA pilots | Prevent target leakage and preserve untouched calibration/holdout. Small development gains and support abstentions do not authorize public forecasts |
| 2026-09-23 UTC | Select Cloudflare Workers Free plus one SQLite Durable Object as the M2 hosting design target | Free quotas support a shared counter design; account/terms, privacy handling, implementation and destination gates must be validated before deployment |
| 2026-09-22 | Release through the existing S3 website and Lambda functions, preserve schedules and hourly/manual triggers, and grant only the collector's needed publication permissions | User approved the GitHub source push and exact AWS changes; maintain `data/*` protection and prior Lambda versions without adding a public routing service or new deployment trigger |
| 2026-09-14 | Separate origin selection from route eligibility and add a free OpenFreeMap/MapLibre picker | User reported the disabled GPS button and requested a clickable map. Locations can be selected before destination verification; only Compare sends TomTom requests. Pin/GPS/manual state stays transient, map-area requests are disclosed, and local Inter labels preserve the 16 px minimum |
| 2026-09-14 | Replace the initial OSRM adapter with TomTom Orbis Routing v3, using individual live-traffic Routing requests, not Matrix | User explicitly selected TomTom. Standard Routing's checked free allowance is 20,000 requests/month; keep the account without prepaid credit, bound usage with a persistent 32-date counter, keep keys server-side, and label coverage uncertainty. Account setup, actual responses and public deployment remain unvalidated |
| 2026-09-14 | Use free FOSSGIS OSRM for a local M2 prototype, with no billing/account and no live traffic | User requires zero cost; Google requires billing even inside its allowance. Bound usage, disclose provider logging, and leave public gateway/terms review open |
| 2026-09-14 | Gate every destination on current age/service/entrance evidence and retain an explicitly fictional M2 example | Current sources do not verify the full destination contract. Unknown facilities cannot enter a real comparison; code/UI review can proceed with labeled fixtures |
| 2026-09-14 | Use past 28-day absolute-change summaries at 15/30/60/120 minutes and a provisional 10-minute-plus-both-changes screen; recommendations remain disabled | Historical movement is descriptive, nonmonotonic and uncalibrated. Metric and traffic uncertainty cannot be resolved by arithmetic alone |
| 2026-09-14 | Ship freshness and self-comparisons before routing recommendations | Existing history supports facility context; routing additionally needs verified destinations, travel times, and uncertainty handling |
| 2026-09-14 | Treat spillover as exploratory relationships until stronger evidence exists | Published wait histories do not observe patient movements or establish causality |
| 2026-09-14 | Retain the existing stack for initial implementation | The current scale supports precomputed artifacts and incremental dashboard changes |
| 2026-09-14 | Use UTC batch-start read windows and one snapshot source per date; prefer closed-day compaction only when raw fingerprints match | Preserves cross-midnight provenance and avoids losing late raw batches behind partial/legacy compaction; matching storage snapshots do not prove scheduled completeness |
| 2026-09-14 | Publish collector-owned `data/latest.json` with conditional replacements and protect `data/*` from website sync | Allows independent refresh and prevents deployment deletion or out-of-order writes from discarding newer attempt state |
| 2026-09-14 | Use provisional 30-minute collection-age freshness, 60-second browser polling, and 15-second age updates | Verified collection interval is 15 minutes; source-update semantics remain unconfirmed, so repeated equal values are not failure evidence |
| 2026-09-14 | Keep registry regions at state level and travel metadata unknown; retain `huntingdon` with Carroll County display name | Names/location grouping can be sourced now without assuming service equivalence, emergency entrances, or routing eligibility |
| 2026-09-14 | Use a scrolling Quarto HTML page for live cards, with history and expandable operator diagnostics | Current values refresh outside the build; build timestamps and historical plots remain visibly separate without changing the Python/S3/Quarto stack |
| 2026-09-14 | Select 28 previous local days and hour ±1, with ±2/all-day fallbacks and eight-day/64-reading/75%-coverage support | Past-only replay found little common-case improvement from 42 days and much less early support; coverage includes missing calendar dates and contributing-day completeness |
| 2026-09-14 | Use a middle-50% descriptive band, outer-10% plus 10-minute unusualness, and a 40–80-minute direction reference | Replay and sensitivity checks support readable minute-based context; timing tolerance avoids cadence-edge jitter, and thresholds make no clinical-benefit or forecasting claim |
| 2026-09-14 | Combine references and bounded history in website-owned `comparisons.json`, prepared hourly | Keeps model and plotted-reference versions together, avoids a Lambda contract change, and allows live comparisons between builds; expire current context after two hours or at local midnight |
| 2026-09-14 | Restore the all-hospital line chart as the opening view, ahead of individual comparisons | User review confirmed the shared overview is an important way to explore the site; reuse the prepared history and original Plotly interaction style |
| 2026-09-14 | Prioritize a plotting canvas with little visible text; fit y-axis to the selected window and visible hospitals | User requested a more visualization-forward design and reported the fixed scale obscured shorter-window variation; retain essential states and move explanations into disclosures |
| 2026-09-14 | Use locally served Inter with a minimum 12 pt / 16 CSS px across page and chart text; resize layouts instead of shrinking labels | User requested consistent, larger typography; responsive SVG geometry and wrapping controls preserve readable labels without adding prose |
| 2026-09-14 | Add M5 for time-series/ARIMA modeling, with seasonal/regressor candidates and release conditioned on later-period forecast skill | User explicitly requested modeling in the plan; make the previously optional forecasting direction actionable while preserving M2's initial scope and distinguishing an evaluated study from a deployed forecast |

## Progress log

| Date | Milestone | Progress and evidence | Deployment |
| --- | --- | --- | --- |
| 2026-09-26 UTC | M2 gateway | Added `gateway/` (Worker, SQLite Durable Object, pinned wrangler 4.141.0, local-check harness), `tests/gateway.test.mjs`, additive `travel.json` `arrival_point` with schema/test updates, and the Cloudflare mention in the page's privacy line. 84 Python and 60 JS tests passed; 11/11 mock checks in `wrangler dev`; browser Compare through the served page returned 18 rows with no console errors; one live comparison returned 18/18 routes in 4.6 s. [Evidence](m2-operations.md#cloudflare-gateway) | Local only; not deployed. No Cloudflare account, secret or route exists |
| 2026-09-26 UTC | M3 map and replay | Added `dashboard/geo.mjs`, `dashboard/geo-map.mjs`, the heatmap replay outline, campus points in the page registry, styles, Quarto resources and public-check modules. 90 Python / 67 JS tests passed; Quarto rendered; headless Chrome desktop/390/320 px checks passed. [Evidence](m3-validation.md#map-and-replay--2026-09-26-utc) | Local only; not deployed |
| 2026-09-26 UTC | M2 benefit-rule backtest | Protocol, route-profile input, `edwait/benefit.py`, runner and six tests committed before scoring (`996a2f1`); 90 Python tests passed. Run on 93,818 pre-holdout records: 14,170 discovery / 7,924 confirmation opportunities; no rule met the gates. [Results](m2-benefit-validation.md) | Offline only; no artifact, schema or page change |
| 2026-09-26 UTC | M2 traffic profiles | Added `--traffic`/`--departure` to `scripts/check_routes.py` and `scripts/compare_routes.py`. 162 historical-mode requests (Monday 03:00/08:00/17:00 CDT, 3 public origins × 18 destinations) all within tolerance; peaks add median 4.3/4.5 min, at most 8.4 min. [Evidence](m2-validation.md#traffic-profiles-and-rush-hour--2026-09-26-utc) | Offline evidence; live weekday-peak run pending (time-gated) |
| 2026-09-26 UTC | M0/M1 hourly dispatch observation | 47/47 EventBridge `workflow_dispatch` runs from 2026-09-24 01:17 to 2026-09-25 23:17 UTC succeeded; backup cron 5 per day, 3–6 hours apart. The alert email subscription (created 2026-09-24 00:24:56 UTC) was never confirmed; a confirmation re-sent at 2026-09-26 00:07 UTC did not extend it, and by 00:37 UTC the topic had no subscriptions. Restoring it failed safely because CloudTrail redacts the address. Metric inquiry drafted ([draft](m2-metric-inquiry-2026-09-26.md)); Leake rechecked | Workflow unchanged; cron removal waits for a confirmed subscription |
| 2026-09-24 UTC | M4 release | The user approved the push of `8242ad1`. The EventBridge dispatch at 03:17 UTC built and published it (run [35950813345](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35950813345)), and the 04:17 dispatch rebuilt it (run [35955001963](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35955001963)); both public checks passed. An independent public check and a Chrome review passed at 04:26 UTC. [Evidence](production-followup-2026-09-23.md#m4-release) | Deployed. Dispatches 01:17–04:17 all succeeded (4 invocations, 0 failed); the backup cron has not run since 01:27 |
| 2026-09-24 UTC | M0/M1 hourly dispatch observation | EventBridge rule `dashboard_hourly` recorded one invocation each at 01:17 and 02:17 UTC and no failed invocations; alarm `OK`. Resulting `workflow_dispatch` runs [35942241664](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35942241664) and [35946597828](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35946597828) succeeded in about two minutes each, including the public freshness checks. The backup cron also ran at 01:27. Alert email subscription still `PendingConfirmation`. [Evidence](production-followup-2026-09-23.md#observed-dispatches) | Hourly builds delivered by EventBridge; about a day of delivery still to observe before removing the cron |
| 2026-09-24 UTC | M4 area counts and wait stability | Added `edwait/stability.py`, `edwait/areas.py`, `dashboard/area.mjs`, stability rendering, schema/storage docs and [validation](m4-validation.md). Corrected M2 movement percentiles. Tests: 84 Python and 46 JavaScript passed. Real-data preparation and render passed, as did the Chrome desktop/390/320 px review after an overflow fix. Area counts were close to independence | Local only; not deployed. `comparisons.json` gains additive stability fields when next published |
| 2026-09-24 UTC | M5 candidate study (v2) | Added `edwait/forecast_models.py`, diagnostics/runner/freeze/report scripts, seven tests, protocol amendment, freeze record, aggregate results and three figures. Development: 1,120 fits, no abstentions/failures, exact v1 reproduction, 5/80 shortlisted. Calibration (frozen): 1 shortlisted pair passed (Collierville 60 min); 18 selected candidates missed coverage at one or both levels; max daily fit 13 s. 79 Python/41 JS tests passed. [Evidence](m5-candidates-validation.md) | Offline only; holdout deliberately left unscored (user decision below); no artifact, schema, S3 or dashboard change |
| 2026-09-24 UTC | M3 relationship study | Added protocol, `edwait/relationships.py`, runner, eight tests, aggregate results and two figures. 1,520 tests per period; one discovery candidate, none confirmed; neighbors indistinguishable from distant pairs. Discovery supported only from 2026-08-19 because of M1's coverage rule (recorded as an execution note, no rule changed). 72 Python/41 JS tests passed. [Evidence](m3-validation.md#relationship-study--2026-09-24-utc) | Offline only; no artifact, schema, S3 or dashboard change. `relationships.json` remains proposed |
| 2026-09-24 UTC | M0/M1 hourly build trigger | User configured connection/API destination `github-dashboard-dispatch`, rule `dashboard_hourly` (`cron(17 * * * ? *)`), role `eventbridge-github-dashboard-dispatch` and alarm `dashboard-dispatch-failed`. Read-only check at 00:31–00:33 UTC confirmed the configuration; no invocation yet (created after the 00:17 slot); alert email pending confirmation. Later 2026-09-23 scheduled runs were 3–5 hours apart. [Evidence](production-followup-2026-09-23.md#hourly-dispatch-through-eventbridge) | AWS configuration live; hourly delivery not yet observed. Repository workflow unchanged (cron retained as backup) |
| 2026-09-23 UTC | M2 campus fallback and entrance tooling | Added `campus_point` for all 20 facilities, `arrival()` precedence, `arrival` in `travel.json`, campus labeling in status/rows/disclosure, `python -m edwait.entrances` (list/geojson/set/clear with eligibility-rule validation) and `scripts/check_routes.py`. 54/54 live routes passed; local end-to-end Compare returned 18 labeled rows. 64 Python/41 JS tests passed. [Evidence](m2-destinations-2026-09-23.md#campus-center-fallback-user-decision-2026-09-23) | Deployed `36d89bf` via [run 35833123203](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35833123203) (07:44 UTC); independent public check passed. Public Compare stays disabled without a gateway. [Evidence](production-followup-2026-09-23.md#campus-fallback-release-through-github-actions) |
| 2026-09-23 UTC | M3 heatmap | Implemented the Versus usual heatmap with shared time control, row-to-focus linking (click/Enter/Space), tooltips, summary table and limits. Five JS tests plus a published-module check; live-history render and Chrome desktop/390/320 px review passed. [Evidence](m3-validation.md) | Deployed 07:21 UTC with `fa842c8` via documented direct S3 publication; public check passed. M3 remains in progress |
| 2026-09-23 UTC | M2 destinations and routing gate | Official evidence recorded for all 20 facilities: 19 active general ERs, Leake unverified; child scope explicit only at Children's, Anderson, DeSoto and Mississippi Baptist. No entrance coordinates found, so all remain excluded with specific reasons. Added the `/api/routes/status` probe and tests. 58 Python/40 JS tests passed. [Evidence](m2-destinations-2026-09-23.md) | Deployed 07:21 UTC with `fa842c8`; public Compare remains disabled, no routing or recommendations. [Release evidence](production-followup-2026-09-23.md#m2m3-release-from-a-validated-local-build) |
| 2026-09-23 UTC | M0/M1 schedule observation | Public Actions API showed no scheduled run from 01:09 to at least 07:11 UTC, including both minute-17 slots after publication; public context would pause about 07:06 UTC. [Observation](production-followup-2026-09-23.md#scheduled-delivery-observation) | Documentation only; reliable-trigger choice awaits user decision |
| 2026-09-23 UTC | M0/M1 requested redeployment | Redeployed clean, synchronized `main`; both test suites, preparation, rendering, protected sync and exact public build/freshness verification passed. Independent check at 05:07:19 UTC found fresh post-midnight context and 20/20 current facilities. [Evidence](production-followup-2026-09-23.md#requested-redeployment-of-current-main) | Deployed `1a2b16b`; [run 35820920480](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35820920480) succeeded at 05:06:28 UTC. Evidence-only follow-up commit; scheduled cadence, M2 and M5 gates unchanged |
| 2026-09-23 UTC | M0/M1 operations | Two updated manual GitHub runs passed; public client validation found 20/20 current readings; Chrome desktop/390/320 px review passed. Approved workflow mitigation passed 57 Python/33 JS tests and exact-public-build/freshness verification. [Evidence](production-followup-2026-09-23.md) | Published `de91ac3`; [run 35820272143](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35820272143) passed. Scheduled delivery remains a separate observation follow-up |
| 2026-09-23 UTC | M2 readiness | User supplied local key; one budgeted TomTom v3 request passed response/endpoint checks. Documented partial official destination/metric evidence and selected free hosting design. [Evidence](m2-readiness-2026-09-23.md) | No public routing or verified hospital destinations; no recommendation gate changes |
| 2026-09-23 UTC | M5 development study | Frozen 107,257-record snapshot; four baselines, delayed-availability sensitivity and two ARIMA pilots; eight focused tests; dated reports and static figures. [Benchmarks](m5-validation.md), [ARIMA](m5-arima-validation.md) | Offline only; full study remains in progress, calibration/holdout unscored, no public forecasts or storage-contract changes |
| 2026-09-22 | Documentation audit | Reconciled the [README](../README.md), operating guides, schemas, validation history, storage reference, and plan with the deployed release and current sources. Checked local links across all 11 Markdown files, all five schemas and 16 schema references, six recorded vendor hashes, and four command help interfaces. Preserved dated evidence; schema validation rules are unchanged. Recorded observed workflow spacing and refresh troubleshooting. | Documentation only; no application, workflow, or AWS changes. M0/M1 remain deployed; M2 routing acceptance, the next updated GitHub build, and public visual review remain open |
| 2026-09-22 | AWS production release | Published source `17d4e57`, deployed both Lambdas as version 2, configured scoped collector access/latest output, and uploaded the rebuilt site. 49 Python/33 JS tests passed; verified 39 public files, three schemas, 20 successful scheduled readings, 1,920 compacted records with fingerprint metadata, preserved latest ETag across sync, and real client refresh for 20 facilities without rebuilding HTML. [Full evidence and rollback notes](aws-deployment-2026-09-22.md). | M0/M1 deployed; M2 static interface published with routing/recommendations disabled. Existing schedules retained. Browser automation unavailable; public visual review and the next GitHub-hosted run remain follow-ups |
| 2026-09-22 | AWS rollout preparation | User authorized production deployment. Existing 15-minute collection and daily compaction schedules remain enabled. Preserved both prior Lambda packages as AWS version 1; prepared a Linux x86_64/Python 3.14 package and scoped access for collection attempts and latest data. Local validation passed 49 Python/33 JavaScript tests, rendering, and artifact/asset checks. | In progress: first publish source and the existing hourly/manual workflow with protected `data/*`, then update the Lambdas and website, and verify public artifacts. No new push trigger or routing service |
| 2026-09-22 | M0/M1/M2 local launch | Refreshed context from read-only S3 history for 20 facilities and 13,439 seven-day points; Quarto rendered successfully. All 49 Python and 33 JavaScript tests passed. HTTP checks confirmed the updated page, 12 required assets, and schema-valid comparisons, travel, and latest artifacts; latest returned 20 reporting facilities with observations through 2026-09-23 03:54 UTC. Browser automation was unavailable, so no new visual review was completed. | [Local review server](../edwait/serve.py) started at `http://127.0.0.1:8765/` with `--live-s3`. Latest readings refresh through the server; historical context remains build-time and needs another preparation/render when it expires. Pre-M0 collection failure metadata cannot be reconstructed. Production rollout remains pending; M2 activation gates are unchanged |
| 2026-09-14 | M2 origin selection | Fixed GPS being disabled by destination/context gates; added click/tap map, draggable pin, keyboard center selection, independent location status, synchronized coordinates, Clear and late-response cancellation. Bundled the map renderer/style and updated privacy/storage docs. 49 Python/33 JS tests, Quarto, actual map rendering and desktop/mobile click/drag/keyboard checks passed. GPS responses were simulated. [Evidence](m2-validation.md#origin-selection-follow-up--2026-09-14). | Local only; no user GPS read, TomTom route call, account, billing or deployment. M2 remains in progress with existing activation gates |
| 2026-09-14 | M2 TomTom integration | Replaced OSRM with TomTom Orbis Routing v3 individual POST calls, live traffic requested, server-only key, persistent request reservations, bounded failures and v2 route schema. Updated setup/privacy/traffic presentation and storage reference. 49 Python/25 JS tests, Quarto render, and Chrome desktop/mobile checks passed. [Evidence](m2-validation.md#tomtom-follow-up--2026-09-14). | Local only; no key configured or live TomTom request validated; destinations/recommendations remain disabled; M2 in progress; no account, paid credit or deployment |
| 2026-09-14 | M2 prototype | Implemented free OSRM adapter, local POST gateway, transient origins, verified-destination gates, visual travel/wait comparison and example, and historical movement artifact. 42 Python/23 JS tests, schemas, Quarto, public-coordinate connectivity, and desktop/mobile checks passed. [Evidence and outstanding acceptance work](m2-validation.md). | Local only; M2 remains in progress; real destinations and recommendations disabled; no paid service or deployment |
| 2026-09-14 | Documentation through M1 | Audited README, M0/M1 operations, validation history, schemas, workflow, and storage reference against the current sources. Updated active baseline guidance, current UI/test summary, all-hospital controls, Inter/font assets, and release checks. Preserved historical evidence and the local-versus-deployed distinction. | Documentation only; M0/M1 remain locally complete and undeployed |
| 2026-09-14 | Planning | Reviewed repository sources and the dated S3 assessment; established this plan and repository maintenance instructions. All feature milestones remain planned. | Documentation only; no application deployment |
| 2026-09-14 | M0 | Implemented shared reading/validation, registry, compaction fingerprints, attempts/latest publication, independent browser refresh, diagnostics, and protected deployment. 24 Python and 6 JavaScript tests passed; JSON schemas, live-data Quarto render, browser refresh/failure recovery, and actual AWS CLI exclusion dry run validated. Detailed evidence and source/test links are in the M0 section above. | Local implementation complete; no Lambda, IAM, schedule, bucket-policy, or website deployment performed; [rollout checklist](m0-operations.md) pending |
| 2026-09-14 | M1 | Implemented past-only self-comparisons, support/fallbacks, recent direction, selectable wait/deviation history, versioned preparation, and operator disclosure. All 35 Python and 11 JavaScript tests passed; 89,978-record replay, full generated artifact schema, live-data Quarto render, and desktop/mobile/keyboard/state checks validated. [Method and evidence](m1-validation.md). | Local implementation complete; no production deployment performed; [M1 release checks](m1-operations.md) pending with M0 rollout |
| 2026-09-14 | M1 review | Restored an initially visible all-hospital Plotly chart with seven-day default, 24-hour option, hover readings, and legend controls. Existing individual comparisons remain below. All 35 Python tests, overview data/gap/zero checks, Quarto render, and localhost page-order checks passed. | Updated local preview only; not deployed |
| 2026-09-14 | M1 visual review | Reworked the page around full-width charts, compact controls and a graphical selected-hospital reference; fixed visible-window/visible-hospital y scaling. 35 Python and 15 JavaScript tests passed; refreshed data and Quarto render validated. Browser inspection stopped by the user; visual review remains pending. | Updated local preview only; not deployed |
| 2026-09-14 | M1 typography and spacing | Corrected Quarto's relocation of the overview plot, eliminating the empty chart-sized gap. Bundled Inter; raised text to 16 px minimum and made chart geometry/controls responsive. 35 Python and 15 JavaScript tests passed; Quarto render and Chrome desktop/mobile checks confirmed spacing, font sizes, containment, and time-window scaling. [Evidence](m1-validation.md#typography-and-spacing-follow-up). | Updated local preview only; not deployed |
| 2026-09-14 | M5 planning | Added time-series/ARIMA deliverables, simple benchmarks, candidate horizons, chronological validation, uncertainty/release gates, and conditional chart integration. Updated roadmap, M2/M3 links, proposed artifact, and open decisions; reviewed plan consistency and formatting. No model fitting or forecast validation performed. | Documentation only; M5 remains planned, with no production change |
