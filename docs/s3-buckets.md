# S3 bucket reference

Contract updated: 2026-09-14 for M0 and M1; implementation is locally validated, not yet
deployed. Live record sampling below remains dated 2026-09-11 (three objects,
1,960 records). Read-only schedule and website policy checks on 2026-09-14 are
recorded separately below. New artifact paths describe the deployment contract,
not an assertion that those objects already exist in production.

## Overview

| Bucket | Purpose | Contents |
| --- | --- | --- |
| `s3://mem-ed-wait-times/` | Source data for ED wait-time analysis | Raw JSON Lines batches, daily gzip copies, and collection attempt summaries |
| `s3://mem-ed-wait-times-dashboard/` | Dashboard hosting | Rendered HTML, supporting assets, website-owned `comparisons.json`/`travel.json`, and independently published `data/latest.json`; new repository outputs remain undeployed |

The machine-readable [ED wait record schema](ed-wait.schema.json) describes one
JSON object per line in both raw and compacted data. The dashboard bucket is
documented by its object layout below; its website files do not share a tabular
record schema. The new [latest artifact schema](latest.schema.json) embeds the
same six-field observation under each facility's `last_success`.
M1's [comparison schema](comparisons.schema.json) defines a separate derived
artifact; it does not change raw, compacted, attempt, or latest records.

## Data bucket: `mem-ed-wait-times`

### Object layout and encoding

```text
s3://mem-ed-wait-times/
  raw/ed_wait/dt=YYYY-MM-DD/YYYYMMDDTHHMMSSZ.jsonl
  compacted/ed_wait/dt=YYYY-MM-DD/data.jsonl.gz
  operations/collection/dt=YYYY-MM-DD/YYYYMMDDTHHMMSSZ.json
```

| Property | Raw | Compacted |
| --- | --- | --- |
| Object granularity | One collection batch | One day's collected raw records |
| Serialization | UTF-8 JSON Lines; one object per line, with a trailing newline | The same JSON Lines, compressed with gzip |
| S3 `ContentType` | `application/x-ndjson` | `application/x-ndjson` |
| S3 `ContentEncoding` | Unset in inspected objects | `gzip` |
| Partition | `dt=YYYY-MM-DD`, from the batch's UTC start date | Same date as the source raw partition |

`dt` is part of the object key, not a field inside each record. The raw filename
uses the batch start time in UTC, at second precision. The `batch_id` field keeps
the full ISO timestamp. A facility observation can occur after the batch's start
date if collection crosses midnight.

### Record fields

All six fields are required and non-null in the repository producer and all
inspected records. No additional fields are emitted by the repository producer.

| Field | JSON type | Meaning |
| --- | --- | --- |
| `facility` | string | Facility slug sent as the upstream API's `fac` parameter, e.g. `arlington` |
| `metric` | string | Key returned by the upstream API. All inspected records use `CV_ED_Wait`; the producer accepts other keys too. |
| `wait_minutes` | integer | Upstream integer or integer string, stored in minutes; M0 rejects decimals, booleans, and null instead of truncating them |
| `observed_at` | string, date-time | UTC time recorded after the facility HTTP response succeeds, e.g. `2026-09-11T00:08:51.380937+00:00` |
| `batch_id` | string, date-time | UTC collection start timestamp shared by every record in a batch; this is not a UUID |
| `latency_ms` | integer | Python Requests `response.elapsed` converted to milliseconds and rounded; measures the facility HTTP request through response headers |

One record represents one facility and one API metric in one collection batch.
The expected logical key is `(batch_id, facility, metric)`; storage and compaction
retain all records. The shared reader normalizes batch timestamps to UTC for
key comparison and deduplicates, without modifying stored observations. Among
duplicates, the latest `observed_at` wins, then the lexicographically largest
source object key, then the last line. Duplicate and conflicting counts are
reported to operators.

The producer does not define valid ranges or sentinel meanings for
`wait_minutes`. The samples include zero, so retain it as a numeric value unless
upstream documentation establishes a different meaning. The precise clinical
definition of `CV_ED_Wait` is not defined in this repository.

Actual record from the first inspected raw object:

```json
{
  "facility": "arlington",
  "metric": "CV_ED_Wait",
  "wait_minutes": 34,
  "observed_at": "2026-09-11T00:08:51.380937+00:00",
  "batch_id": "2026-09-11T00:08:50.867368+00:00",
  "latency_ms": 512
}
```

### Facilities

The [facility registry](../edwait/facilities.json) supplies these 20 stable slugs,
all of which appeared in the 2026-09-11 samples:

```text
arlington
childrens
collierville
huntingdon
memphis
tipton
union-city
crittenden
nea
anderson
baptist-medical-center-attala
booneville
calhoun
desoto
golden-triangle
baptist-medical-center-leake
north-mississippi
union-county
baptist-medical-center-yazoo
baptist-medical-center
```

These are configured values, not a closed observation-schema enumeration. Names
and state-level region groupings were checked against Baptist's
[emergency facility listing](https://www.baptistonline.org/services/emergency)
and [Leake page](https://www.baptistonline.org/locations/leake) on 2026-09-14.
`huntingdon` remains the source slug for Carroll County. `America/Chicago` is the
comparison timezone for these locations. Each entry records source URL and
verification date. Coordinates, entrance, age/service applicability, active
status, and travel verification remain explicit null/unknown values; none is
eligible for travel comparisons on this registry alone. Regions are states for
display, not verified clinical service areas.

A failed facility request is logged and omitted from raw readings but recorded
in the attempt summary and latest artifact. A batch can contain fewer facilities.
All returned valid metrics retain separate raw records; `latest.json` and the
dashboard explicitly select `CV_ED_Wait`.

### Reading and combining records

Use [the shared reader](../edwait/data.py), which implements these rules:

1. Supply timezone-aware `[start, end)` boundaries. They are converted to UTC
   and apply to **batch start**, not observation time. Read each intersecting
   batch-date partition. Observations crossing midnight remain with their batch.
   For a later observation-time analysis, read an adequately padded batch window
   before applying observation-time bounds; do not treat partitions as local days.
2. Prefer compacted data only for a closed UTC day when its `source-fingerprint`
   metadata matches the currently listed raw objects. Otherwise use all raw
   objects for that date. An open UTC day always uses raw when available.
   Never concatenate both sources for one date.
3. When only compacted data is available, read it with
   `unverified_no_raw` completeness. With neither source, report a missing
   partition. Neither a raw snapshot nor a matching fingerprint proves every
   scheduled collection ran.
4. Each selected S3 read uses its listed/head ETag in `IfMatch`. An object changed
   during reading or an S3 permission/network failure aborts the read, preventing
   a successful-looking partial build. A malformed gzip/UTF-8 object or JSON line
   is excluded with a rejection count and bounded diagnostic examples.
5. Enforce the six-field schema, timezone-aware times, nonnegative integer
   latency, integer waits (including zero/negative values of unverified meaning),
   matching batch partition, observation at/after batch start, and no observations
   after the supplied read time. Deduplicate with the rule above. Group/filter by
   metric as well as facility. Convert to `America/Chicago` only for display or
   local-time comparisons, including daylight-saving transitions.

M1 preparation reads from UTC midnight 36 days before the run through its current
time, padding the 28-day local baseline and seven rolling display days. The
analysis then filters by observation time; partitions remain UTC batch partitions.
It reports empty inputs and coverage, and breaks chart lines for gaps over
20 minutes. `coverage()` reports per-facility missingness relative to observed
batches, unknown facilities, inter-batch gaps, rejected inputs, duplicates, and
source selection. Missing partitions and gaps are not filled with earlier waits.
Baseline support separately measures observed slots against all eligible local
calendar days, including dates with no batches; see [M1 method](m1-validation.md).

Do not concatenate raw and compacted data for the same date: compacted objects
contain copies of the raw records. The compactor concatenates raw files in object
key order; it does not aggregate, validate, or deduplicate their records. It
overwrites the destination object on rerun and leaves the source raw objects in
place. A compacted object reflects the raw files available at compaction time;
its existence alone does not establish that a day is complete. M0 adds S3 metadata
`source-fingerprint`, `source-object-count`, and `compacted-at`, on the gzip object
itself. The fingerprint is SHA-256 of sorted raw `{Key, ETag, Size}` objects
serialized as JSON with sorted keys and compact separators. Conditional reads
ensure the compactor copies the listed object versions; late raw files or changed
raw ETags invalidate reader preference for the compacted snapshot. Legacy compacted
objects without metadata fall back to raw when possible. Raw provenance is retained.

The compactor defaults to the previous UTC day and also accepts an explicit
`date` value in `YYYY-MM-DD` form. Live schedules were inspected on 2026-09-14:

| EventBridge rule | State | Expression | Verified target |
| --- | --- | --- | --- |
| `trigger_15` | Enabled | `rate(15 minutes)` | Lambda `ed-wait-times` |
| `compact_daily` | Enabled | `cron(30 1 * * ? *)` (01:30 UTC daily) | Lambda `ed-wait-compaction` |

Both targets had no explicit input or retry-policy override. Both Lambdas were
Python 3.14 with 60-second timeouts. Schedule configuration does not prove execution
or data completion. M0 reserves time to publish failures when the Lambda deadline
approaches; unattempted facilities receive `collection_deadline`. A process kill,
timeout during a request, or storage failure can still prevent a new artifact;
browser age checks handle that outage. No deployment settings were changed during
this inspection.

### Collection attempt summaries (new in M0)

One UTF-8 `application/json` object per completed attempt cycle under
`operations/collection/`, including all-facility failures. Fields are
`schema_version: 1`, `batch_id`, `metric: CV_ED_Wait`, `generated_at`, `records`,
`expected_facilities`, `succeeded`, `failed`, and `attempts` keyed by facility slug.
Each attempt has `batch_id`, `attempted_at`, `state` (`success` or `failed`), and
`error_code` (null, `request_failed`, `invalid_response`,
`expected_metric_missing`, or `collection_deadline`). For a deadline skip,
`attempted_at` is when the skip was recorded, not an HTTP request time.
Success means the expected metric was collected. Other valid metrics can still
be stored in raw when the expected metric is absent. Counts and failure codes
are also emitted as structured `collection_summary`/facility log messages.
No exception text or upstream response body is published.

## Website bucket: `mem-ed-wait-times-dashboard`

Expected repository output through M1 and the M2 local prototype (not yet deployed):

```text
s3://mem-ed-wait-times-dashboard/
  index.html
  data/latest.json  # new; collector-owned, independent of the render output
  comparisons.json # new in M1; website-owned, prepared before each render
  travel.json      # new in M2; website-owned eligibility and historical movement
  travel.mjs       # M2 comparison UI; routes are never stored in S3
  origin.mjs       # GPS/manual/map selection; selected origin remains transient
  origin-map.mjs   # MapLibre integration; map data comes directly from OpenFreeMap
  origin-map-style.json # static local style, not user data
  vendor/maplibre/ # pinned map renderer, CSS, shared module, worker, licenses
  app.mjs          # live individual comparison entry point
  latest.mjs
  comparisons.mjs
  overview.mjs     # shared time controls and visible-line y-axis scaling
  latest.css
  fonts/
    inter-latin.woff2
    OFL.txt
    README.md
  site_libs/       # generated Quarto/Bootstrap supporting assets
```

`index.html` has S3 `ContentType: text/html`. The `site_libs/` prefixes hold
supporting Quarto website assets; individual asset filenames can change with
the renderer version. The 2026-09-11 deployment inspection found Bootstrap,
clipboard, quarto-dashboard, quarto-html, quarto-nav, and quarto-search prefixes;
that historical inventory does not describe the current scrolling-page build.
No separate record dataset was observed at the bucket
root in the original sample. Use the data bucket for historical record analysis;
the new latest artifact is a bounded current-reading cache with retained failures.

The repository's deployment workflow renders `dashboard/` with Quarto and syncs
`dashboard/_site/` to this bucket with `--delete --exclude "data/*"`. The exclusion
protects independently published artifacts against both upload and deletion by
the website job ([AWS sync reference](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html)).
It is configured to run hourly
at minute zero and supports manual execution. Its AWS region setting is
`us-east-1`. On 2026-09-14 the website configuration named `index.html` as index
document, and the bucket policy allowed public `s3:GetObject` on all website
objects, which includes the new data path. No CORS change is needed for same-origin
relative fetches. TLS/custom-domain/CDN configuration was not inspected.

### Comparison artifact (new in M1)

The website build owns root `comparisons.json`, a complete UTF-8 JSON object
copied by Quarto and uploaded with the website. It is intentionally outside the
collector-owned `data/*` exclusion. No new historical source format or Lambda
write is introduced. [Schema version 1](comparisons.schema.json) records method
`self-comparison-v1`, metric, UTC generation/source timestamps, local timezone,
expiration, policy, reader coverage, operator latency summaries, and all registry
facilities. Each facility contains yesterday/today's local-date models (24 hours
each) and seven rolling days of historical tuples.

Models contain reference date boundaries, group/fallback, support counts,
coverage, median, band, and an empirical `[wait, count]` distribution for live
percentile calculation. Historical tuples contain, in order: observation time,
wait, past-only median, low/high band, minute difference, percentile, contributing
days, coverage, and group. Unsupported comparison values are null; raw published
waits remain visible. Latency describes collected HTTP requests, not patient waits.

Preparation runs hourly before Quarto using the M0 reader and writes an atomic
local replacement. A storage/preparation/render failure stops the workflow before
sync, preserving the published version. Browser requests use `cache: no-cache`
every five minutes to revalidate an unchanged object with its ETag, plus manual
refresh/tab visibility. Requests time out after 10 seconds. Sync infers JSON
content type and introduces no explicit context Cache-Control override. Verify
the actual serving path at rollout; the local generated artifact was about 2 MB.

Malformed or regressing artifacts fail validation. Current comparisons require
a successful context refresh, generation age below two hours, and time before
`valid_until` (the next local midnight), in addition to M0 live freshness. The
browser retains explicitly dated charts on failure but suppresses current
comparisons. Live readings may be appended in memory between builds, retaining
one observation per cadence slot. Hosting ownership, rollout, and reproduction
commands are in [M1 operations](m1-operations.md); dated replay findings are in
[M1 validation](m1-validation.md).

### Travel context artifact (M2 local prototype)

The same preparation read now also produces root `travel.json`, copied by Quarto
beside `comparisons.json`. The website owns it; it is outside the protected
collector `data/*` prefix. [Schema version 1](travel.schema.json) records method
`travel-wait-v1`, source/generation times, fixed policy, eligibility reasons by
adult/child group, and supported 90th percentile absolute changes in published
waits at 15/30/60/120-minute horizons. Recommendations are explicitly disabled.
The two context files have independent atomic replacements and expiry checks.

No origin, route response, precise location, or routing log is written to S3.
The TomTom integration uses a transient [v2 route response](routes.schema.json)
from local `POST /api/routes`; it is not an S3 artifact. It returns timing,
distance, requested traffic mode, and nullable delay, with no origins, keys, or
geometry. The ignored local `.cache/tomtom-usage.sqlite3` file stores only a
`requests(day, calls)` table of UTC dates and reserved request counts. Preserve
this usage counter across restarts; it is outside the served website directory.
No provider key is included in website files or collector configuration. Future
public gateway storage remains a separate deployment decision.
`POST /api/routes` exists only in the local review server; static S3 hosting does
not supply that endpoint. Public activation and free hosting remain unresolved.
The raw six-field observation schema, attempts/latest contracts, and compaction
layout are unchanged by M2. See [M2 operations](m2-operations.md).

### Latest artifact and browser freshness (new in M0)

The collector owns `data/latest.json` in `LATEST_BUCKET`, deployed as
`mem-ed-wait-times-dashboard`. It stores a complete JSON replacement with
`ContentType: application/json` and `CacheControl: no-store, max-age=0`.
The browser requests it with `cache: no-store` every 60 seconds independently of
Quarto; each request times out after 10 seconds. Ages are recomputed every 15
seconds and when the tab becomes visible. Manual refresh is also available.

[Version 1 schema](latest.schema.json): generation/method version, generation time,
metric, freshness policy, source range, coverage counts, and exactly one entry for
each configured facility. Each entry has identity/display metadata,
`last_success` (the unchanged observation or null), `last_attempt` (the attempt
object above or null), and `reporting_state` (`reporting`, `failed`, or `missing`).
Source range covers the retained successful observation times, which can be old.
Reporting state is collection status, not an assertion of current freshness.
The consumer verifies configured coverage and rejects malformed or regressing
artifacts while retaining its last valid data with a refresh-failure label.

Default settings are expected collection 900 seconds, stale after **1800 seconds
(inclusive)**, polling 60 seconds, request timeout 10 seconds. The collector's
`STALE_AFTER_SECONDS` environment variable configures the stale threshold; other
settings live in `edwait/latest.py` and travel in the artifact. Thirty minutes is
a provisional collection-age policy (two verified schedule intervals), not a
provider update guarantee. Current provider API averaging/update/zero semantics
remain unconfirmed. Repeated equal readings, including zero, remain successful.

An observation is labeled recently collected only when both observation and
artifact are younger than the threshold, timestamps are not in the future,
the latest facility attempt succeeded, and the last browser refresh succeeded.
Stale, missing, collection-failure, and refresh-failure labels can coexist.
Older readings stay visible as last published readings with ages and timestamps.
No build timestamp is used as an observation timestamp.

Publication reads the previous artifact and merges successes and attempts
independently by timestamp. It uses S3 `IfMatch`/`IfNoneMatch` complete replacements
with bounded conflict retries, protecting against out-of-order invocations.
Non-missing read errors, invalid prior JSON, and failed writes leave the old
object intact and fail the invocation. Raw storage and durable attempt summaries
precede public publication. All-facility failure publishes attempt state and then
raises an error. If collection/publication stops entirely, the browser ages the
retained artifact into stale state. Initial deployment has no historical backfill
of `last_success`; a failed facility remains missing until its first success.

See [M0 operations and deployment](m0-operations.md) for packaging, IAM, rollout
order, checks, and the local-versus-deployed validation record.

## Sources and verification

Repository sources:

- [Collector and raw record writer](../mem-ed-lambda.py): `fetch_facility`,
  `build_key`, `collect`, and `write_s3`.
- [Daily compactor](../lambda_function.py): `compact` and `lambda_handler`.
- [Shared data reader](../edwait/data.py), [comparison preparation](../edwait/prepare.py),
  and [dashboard](../dashboard/index.qmd).
- [Quarto output configuration](../dashboard/_quarto.yml).
- [Dashboard render and deployment workflow](../.github/workflows/dashboard.yml).

Both Lambda scripts take the data bucket from `BUCKET`. The collector also
requires `LATEST_BUCKET`. Comparison preparation defaults to `mem-ed-wait-times` with a
`BUCKET` override, and the workflow names `mem-ed-wait-times-dashboard` explicitly.
Deployed environment values were not inspected or changed.

Live record samples, all within `s3://mem-ed-wait-times/`:

| Object key | Parsed records |
| --- | ---: |
| `raw/ed_wait/dt=2026-09-11/20260911T000850Z.jsonl` | 20 |
| `raw/ed_wait/dt=2026-09-11/20260911T193850Z.jsonl` | 20 |
| `compacted/ed_wait/dt=2026-09-10/data.jsonl.gz` | 1,920 |

Every sampled record had exactly the six documented fields with the documented
JSON types, with no null or missing fields. The raw and compacted content types
and compression metadata matched the code. The bucket roots, recent date
prefixes, website asset prefixes, and dashboard HTML metadata were also checked.
This is a sampled verification, not a full historical inventory or a guarantee
of future upstream values.

To refresh this reference, review the producer and consumer files above, list
recent raw and compacted objects with `aws s3api list-objects-v2`, download a few
with `aws s3api get-object`, and compare parsed records with
[ed-wait.schema.json](ed-wait.schema.json). Apply the schema to each JSON line
after decompression, enabling date-time format validation in your validator.
Update this verification date and the sample keys when doing so.
