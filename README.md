# Memphis ED wait times

Collects published emergency department wait observations from configured Baptist
facilities, stores historical batches in S3, and renders a Quarto dashboard.

**[Open the dashboard](https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/index.html).**
M0 (data and freshness) and M1 (hospital self-comparisons) were deployed on
2026-09-22. M2's map and illustrative travel interface are published; real routing
and recommendations remain disabled. M3's difference-from-usual heatmap is
published and an offline relationship study found no confirmed pair association. M4's area counts and
wait-stability summaries were deployed on 2026-09-24; its historical-alternatives
replay waits on M2. M5's offline forecast
study has scored development and calibration under a frozen selection; one hospital/horizon
remains eligible for the unscored final holdout, and there are no public forecasts.
See the [release evidence](docs/aws-deployment-2026-09-22.md) and
[current plan](docs/development-plan.md).

The [production follow-up](docs/production-followup-2026-09-23.md) records a
successful updated GitHub build and public desktop/mobile review. The approved
workflow mitigation moves the hourly cron to minute 17 and verifies public
freshness/build artifacts after publication. GitHub's scheduled delivery proved
unreliable (runs 3–9 hours apart on 2026-09-23), so since 2026-09-24 UTC an AWS
EventBridge rule dispatches the workflow hourly; its first four dispatches
(01:17–04:17 UTC) all produced successful builds.

## Project documentation

- [Development plan and design](docs/development-plan.md): priorities, milestone
  status, self-comparisons, travel-and-wait comparison, relationship exploration,
  time-series/ARIMA modeling, validation criteria, and ongoing progress.
- [S3 bucket reference](docs/s3-buckets.md): storage layout, reading rules, and
  dated verification of source data and website assets.
- [Observation schema](docs/ed-wait.schema.json): the current JSON record contract.
- [Latest artifact schema](docs/latest.schema.json): live readings, attempts, and freshness.
- [M0 operations](docs/m0-operations.md): validation, packaging, rollout, and operator checks.
- [AWS deployment record](docs/aws-deployment-2026-09-22.md): deployed revision,
  Lambda versions, permissions, production verification, and rollback evidence.
- [Comparison artifact schema](docs/comparisons.schema.json): historical references,
  support, seven-day history, and operator diagnostics.
- [M1 method and validation](docs/m1-validation.md): past-only replay, selected
  baseline/trend settings, historical examples, and UI evidence.
- [M1 operations](docs/m1-operations.md): environment setup, local preview,
  preparation, website publication, and release checks.
- [M2 operations](docs/m2-operations.md) and [validation](docs/m2-validation.md): free
  routing prototype, local review, privacy, and unresolved activation gates.
- [M2 readiness follow-up](docs/m2-readiness-2026-09-23.md): live TomTom check,
  remaining destination/metric evidence, and free hosting design.
- [M2 destination evidence](docs/m2-destinations-2026-09-23.md): official status,
  service and age evidence for all 20 facilities, labeled campus-center fallback,
  live route validation and the entrance-review tool.
- [M2 benefit-rule backtest](docs/m2-benefit-validation.md) and [protocol](docs/m2-benefit-protocol.md):
  how often a lower drive-plus-wait estimate still held at arrival; no rule qualified.
- [M3 validation](docs/m3-validation.md) and [relationship protocol](docs/m3-relationship-protocol.md):
  difference-from-usual heatmap, neighbor groups, pair-association study and limits.
- [M4 validation](docs/m4-validation.md): area counts versus chance, wait-stability
  summaries, the M2 movement-percentile correction, and the deferred alternatives replay.
- [M5 benchmarks](docs/m5-validation.md) and [ARIMA pilot](docs/m5-arima-validation.md):
  frozen development study, error/support results, and remaining validation.
- [M5 candidate study](docs/m5-candidates-validation.md) and [freeze record](docs/m5-freeze.json):
  diagnostics, calendar/profile candidates, empirical intervals, frozen gates and calibration.
- [Travel context schema](docs/travel.schema.json): eligibility and historical wait movement.
- [Route response schema](docs/routes.schema.json): transient TomTom timing and traffic delay.
- [Development instructions](AGENTS.md): how to keep the plan and data
  documentation aligned with implementation.

## Source entry points

- [Collector](mem-ed-lambda.py)
- [Daily compactor](lambda_function.py)
- [Shared historical reader](edwait/data.py) and [facility registry](edwait/facilities.json)
- [Latest publisher](edwait/latest.py) and [browser refresh](dashboard/latest.mjs)
- [Self-comparison analysis](edwait/analysis.py), [artifact preparation](edwait/prepare.py),
  and [comparison application](dashboard/app.mjs)
- [Dashboard](dashboard/index.qmd)
- [All-hospital renderer](dashboard/overview.py), [time/legend controls](dashboard/overview.mjs),
  and [page styles](dashboard/latest.css)
- [Area counts](dashboard/area.mjs) with [area groups](edwait/areas.py), and
  [wait stability](edwait/stability.py) (M4)
- [Difference-from-usual heatmap](dashboard/heatmap.mjs) and offline
  [relationship study](edwait/relationships.py) with its [runner](scripts/m3_relationships.py) (M3)
- [Render and deployment workflow](.github/workflows/dashboard.yml)
- [Travel context](edwait/travel.py), [TomTom Routing adapter](edwait/routing.py),
  [comparison bars](dashboard/travel.mjs), [origin controls](dashboard/origin.mjs),
  [clickable map](dashboard/origin-map.mjs), [local review server](edwait/serve.py),
  [entrance review tool](edwait/entrances.py), and [live route check](scripts/check_routes.py)
- [Cloudflare routing gateway](gateway/README.md) (M2; local only)

## Dashboard behavior and limits

The dashboard opens with a full-width all-hospital plotting canvas, with an axis
that fits the selected time window and visible hospitals. M1 adds individual
current wait versus usual, explicit support and freshness, recent direction,
and selectable 24-hour/seven-day history. Seven days and all 20 hospitals are
selected on first visit; the same time control drives both chart sections.
History in the overview updates with the build, while individual readings refresh
independently. A Versus usual heatmap (M3) colors each hospital's hourly or
15-minute median difference from its own usual median; selecting a row focuses
that hospital. It describes readings, not patient movement between hospitals.
Below it, a map (implemented 2026-09-26, not yet deployed) places each hospital at
its campus center in the same colors, with a replay slider and area views.
M4 adds an Across an area view that counts hospitals above or below
their own usual in a chosen area (all, state, or 50 km neighbor group) beside a
typical count, and a per-hospital typical-change graphic (median and 90th
percentile movement over 15 minutes to 2 hours across 28 past days).
Explanations, tables, and operator diagnostics are expandable.
Inter is served locally with a 16 CSS px (12 pt) minimum, including chart labels.
Release checks passed 64 Python and 41 JavaScript tests on 2026-09-23, plus public data/asset
and live-refresh checks; earlier desktop/mobile browser evidence remains in the
dated validation records above. These describe published observations, not an
individual patient's wait or hospital care quality.

M2's published Drive + wait prototype includes a labeled example. Its local
gateway has a TomTom Routing API v3 adapter that requests live traffic where
available. Keys stay server-side;
a persistent request budget bounds usage within the free allowance. A user-provided
local key passed one live API contract check on 2026-09-23 UTC. Destinations have
official status/service/age evidence; until emergency entrances are reviewed from
imagery, 18 adult and 4 child destinations route to OpenStreetMap campus centers
labeled "ER entrance unconfirmed" (54/54 live validation routes passed). Add
reviewed entrances with `python -m edwait.entrances` (see
[M2 operations](docs/m2-operations.md#adding-imagery-reviewed-entrances)).
Account/billing settings have not been audited.
M2 remains in progress; recommendations and public routing are not enabled.
The page enables Compare only when `GET /api/routes/status` confirms a gateway,
so the static S3 site never posts coordinates. A free
[Cloudflare Workers gateway](docs/m2-operations.md#cloudflare-gateway) that would
serve the page and routing at one origin is implemented and validated locally
(2026-09-26) but not deployed; it needs the account owner's Cloudflare setup.
See [M2 setup](docs/m2-operations.md#preparation-and-local-review) for local key
configuration and preview commands. Representative hospital-route validation remains pending.
The free origin map and Use my location work independently of routing eligibility
or a TomTom key. Click/tap to place a pin, drag it to adjust, or enter coordinates.
Map labels use Inter at 16 px minimum. See [map operation and privacy](docs/m2-operations.md#origin-map-and-location-controls).

## Running and maintaining the dashboard

[Local setup and preview](docs/m1-operations.md#environment-setup) require Python
3.12+, Node 22+, Quarto, and read-only S3 history access. The review server binds
to `http://127.0.0.1:8765/`; a TomTom key is optional and does not enable
unverified destinations. Preparation and rendering must be rerun to refresh the
local historical context.

In production, the existing collector is scheduled every 15 minutes; the browser
polls its latest artifact every 60 seconds. The website workflow is dispatched
hourly at minute 17 by the AWS EventBridge rule `dashboard_hourly`, keeps a backup
GitHub cron at the same minute, and can be run manually. It rebuilds history and comparison context; it
does not deploy Lambda code. A Git push alone does not trigger publication.
Actual workflow starts can be delayed, so current comparisons pause when their
context is two hours old or reaches the next Chicago midnight. The page's refresh
button refetches artifacts; it does not start a build. See
[refresh and troubleshooting](docs/m1-operations.md#refresh-and-troubleshooting).
