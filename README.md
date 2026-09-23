# Memphis ED wait times

Collects published emergency department wait observations from configured Baptist
facilities, stores historical batches in S3, and renders a Quarto dashboard.

## Project documentation

- [Development plan and design](docs/development-plan.md): priorities, milestone
  status, self-comparisons, travel-and-wait comparison, relationship exploration,
  time-series/ARIMA modeling, validation criteria, and ongoing progress.
- [S3 bucket reference](docs/s3-buckets.md): storage layout, reading rules, and
  dated verification of source data and website assets.
- [Observation schema](docs/ed-wait.schema.json): the current JSON record contract.
- [Latest artifact schema](docs/latest.schema.json): live readings, attempts, and freshness.
- [M0 operations](docs/m0-operations.md): validation, packaging, rollout, and operator checks.
- [Comparison artifact schema](docs/comparisons.schema.json): historical references,
  support, seven-day history, and operator diagnostics.
- [M1 method and validation](docs/m1-validation.md): past-only replay, selected
  baseline/trend settings, historical examples, and UI evidence.
- [M1 operations](docs/m1-operations.md): preparation, local build, and release checks.
- [M2 operations](docs/m2-operations.md) and [validation](docs/m2-validation.md): free
  routing prototype, local review, privacy, and unresolved activation gates.
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
- [Render and deployment workflow](.github/workflows/dashboard.yml)
- [Travel context](edwait/travel.py), [TomTom Routing adapter](edwait/routing.py),
  [comparison bars](dashboard/travel.mjs), [origin controls](dashboard/origin.mjs),
  [clickable map](dashboard/origin-map.mjs), and [local review server](edwait/serve.py)

M0 and M1 were deployed to AWS on 2026-09-22. [Open the dashboard](https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/index.html)
or see the [deployment evidence](docs/aws-deployment-2026-09-22.md). The dashboard opens with a full-width all-hospital plotting canvas, with
an axis that fits the selected time window and visible hospitals. M1 adds individual
current wait versus usual, explicit support and freshness, recent direction,
and selectable 24-hour/seven-day history. Seven days and all 20 hospitals are
selected on first visit; the same time control drives both chart sections.
History in the overview updates with the build, while individual readings refresh
independently. Explanations, tables, and operator diagnostics are expandable.
Inter is served locally with a 16 CSS px (12 pt) minimum, including chart labels.
Release checks passed 49 Python and 33 JavaScript tests, plus public data/asset
and live-refresh checks; earlier desktop/mobile browser evidence remains in the
dated validation record above. These describe
published observations, not an individual patient's wait or hospital care quality.

M2 has a local Drive + wait prototype with a labeled example and a TomTom Routing
API v3 adapter that requests live traffic where available. Keys stay server-side;
a persistent request budget bounds usage within the free allowance. No account,
key, or billing is configured, and real destinations still need verification.
M2 remains in progress; recommendations and public routing are not enabled.
See [M2 setup](docs/m2-operations.md#preparation-and-local-review) for local key
configuration and preview commands. Live TomTom validation remains pending.
The free origin map and Use my location work independently of routing eligibility
or a TomTom key. Click/tap to place a pin, drag it to adjust, or enter coordinates.
Map labels use Inter at 16 px minimum. See [map operation and privacy](docs/m2-operations.md#origin-map-and-location-controls).
