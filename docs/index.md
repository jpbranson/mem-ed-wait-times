---
okf_version: "0.2"
---

# About this bundle

* [Update log](log.md) - Creations, deprecations and structural changes to this bundle, newest first.
* [Bundle tooling](../scripts/okf.py) - Generates this index and checks conformance (`python scripts/okf.py index`).

# Plan

* [Development plan](development-plan.md) - Living design and status document: product direction, M0–M5 milestone status and acceptance criteria, open decisions, maintenance rules, and the decision and progress logs.

# Operations

* [M0 operations and deployment](m0-operations.md) - How to validate, package and roll out the M0 collector and latest-reading publisher, with ownership, required access and operator checks.
* [M1 preparation and rollout](m1-operations.md) - Environment setup, build and validation, local preview, artifact ownership and caching, refresh troubleshooting and release checks for the dashboard.
* [M2 travel comparison: local operation and release gates](m2-operations.md) - How the M2 travel comparison is prepared and released: TomTom free usage, origin map and privacy contracts, comparison and uncertainty policy, the Cloudflare gateway, and remaining acceptance work.
* [Regional ER publication collector](regional-collector.md) - The separate regional collector deployed 2026-09-27 for Methodist, Saint Francis and Forrest City ERs: sources and measures, record contract, local runs, validation and cost, deployment, and dated research notes.

# Data contracts

* [S3 bucket reference](s3-buckets.md) - Layout, record contracts, reading rules and verification history for the data bucket mem-ed-wait-times and the website bucket mem-ed-wait-times-dashboard.
* [M1 hospital self-comparison and M4 stability artifact](comparisons.schema.json) - JSON Schema: Atomic website-owned comparisons.json.
* [ED wait observation](ed-wait.schema.json) - JSON Schema: One facility/metric observation in a collection batch.
* [Regional ER public timing observation](er-publication.schema.json) - JSON Schema: One facility and published measure from the separate regional collector.
* [Latest published ED wait observations](latest.schema.json) - JSON Schema: Version 1 complete replacement at data/latest.json.
* [Transient TomTom route comparison response, without origins or credentials](routes.schema.json) - JSON Schema.
* [Website-owned M2 context, without origins](travel.schema.json) - JSON Schema.

# Validation reports

* [M1 method and validation](m1-validation.md) - How the M1 self-comparison method (self-comparison-v1) was selected and validated by past-only replay on 2026-09-14, with implementation, UI and later display follow-ups.
* [M2 benefit-rule backtest — 2026-09-26 UTC](m2-benefit-validation.md) - Result of the pre-registered M2 benefit-rule backtest (2026-09-26 UTC): no candidate rule for calling an alternative meaningfully lower qualified, so preferred-option claims stay disabled.
* [M2 local validation — 2026-09-14](m2-validation.md) - Local validation of the M2 travel-comparison prototype from 2026-09-14, the initial OSRM prototype history, and 2026-09-26 historical traffic-profile estimates of weekday-peak delay (a live peak run is still pending), with outstanding release work.
* [M3 validation — relationships explorer](m3-validation.md) - Validation of M3's difference-from-usual heatmap (2026-09-23), the offline relationship study that found no confirmed pair association (2026-09-24), and the campus map with replay (2026-09-26).
* [M4 validation: area counts and wait stability](m4-validation.md) - Local validation of M4's area-wide elevated-wait counts and wait-stability summaries, deployed 2026-09-24, and the work that remains.
* [M5 ARIMA development pilot — 2026-09-23 UTC](m5-arima-validation.md) - Development-period pilot of ARIMA(1,0,0) and ARIMA(1,1,0) against simple benchmarks (2026-09-23 UTC); no forecast qualified for release.
* [M5 candidate study (v2) — development and calibration, 2026-09-24 UTC](m5-candidates-validation.md) - M5 v2 candidate study scored on development and calibration under a frozen specification (2026-09-24 UTC); the final holdout remains unscored and no public forecast exists.
* [M5 benchmark checkpoint — 2026-09-23 UTC](m5-validation.md) - First M5 checkpoint (2026-09-23 UTC): the frozen 107,257-observation snapshot and simple forecasting benchmarks scored on the development period.

# Frozen study protocols

* [M2 benefit-rule backtest protocol — 2026-09-26 UTC](m2-benefit-protocol.md) - Candidate rules, metrics and selection plan, committed before any real-data scoring, for when an alternative's drive-plus-published-wait estimate may be called meaningfully lower. Not editable: its SHA-256 is recorded in [m2-benefit-results.json](m2-benefit-results.json).
* [M3 relationship study protocol — 2026-09-24 UTC](m3-relationship-protocol.md) - Inputs, periods, neighbor groups, statistics and confirmation rules fixed before computing any pair statistic among published readings. Not editable: its SHA-256 is recorded in [m3-relationship-results.json](m3-relationship-results.json).
* [M5 offline study protocol — 2026-09-23 UTC](m5-study-protocol.md) - Frozen inputs, time policy, chronological phases and provisional release gates for the offline forecasting study, with an amendment appended before calibration scoring. Not editable: its SHA-256 is recorded in [m5-study-manifest.json](m5-study-manifest.json).

# Deployment records

* [AWS deployment — 2026-09-22](aws-deployment-2026-09-22.md) - Dated record of the 2026-09-22 (America/Chicago) release of the M0 collector and latest publisher, compactor, M1 dashboard and M2 static interface to AWS us-east-1, with validation evidence and rollback notes.
* [Production follow-up — 2026-09-23 UTC](production-followup-2026-09-23.md) - Dated follow-up to the initial AWS release, 2026-09-23 to 2026-09-27 UTC: the first GitHub-hosted build, public browser review, schedule mitigation, the M2/M3, campus-fallback and M4 releases, and hourly EventBridge dispatch through removal of the backup cron.

# Research records

* [M2 destination evidence — 2026-09-23 UTC](m2-destinations-2026-09-23.md) - Official status, service and age evidence for the 20 registry destinations, the user's 2026-09-23 decision to route to labeled campus centers until entrances are reviewed, and the 2026-09-26 Leake recheck.
* [M2 readiness follow-up — 2026-09-23 UTC](m2-readiness-2026-09-23.md) - Dated M2 readiness follow-up: a live TomTom connectivity check, the destination evidence reviewed, and the free public hosting decision.
* [Memphis-area ERs without published wait information](map-facilities-2026-09-27.md) - Official evidence and map locations for eight Memphis-area ERs without published wait information, added as map-only directory records and released 2026-09-27.

# Work logs and drafts

* [Flight log: next-steps run (2026-09-26 UTC)](flight-log-2026-09-26.md) - Working record of the 2026-09-26 UTC next-steps run: each step's outcome, the human review queue, and where to resume; the development plan remains authoritative.
* [M2 metric inquiry draft — 2026-09-26 UTC](m2-metric-inquiry-2026-09-26.md) - Unsent draft inquiry to Baptist about what CV_ED_Wait measures; sending it is the user's decision, and any reply is to be recorded here. (draft)
