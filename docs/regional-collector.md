---
type: Data Collector
title: Regional ER publication collector
description: 'The separate regional collector deployed 2026-09-27 for Methodist, Saint Francis and Forrest City ERs: sources and measures, record contract, local runs, validation and cost, deployment, and dated research notes.'
tags: [regional, collector, lambda, operations]
status: stable
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-09-27T17:51:46Z
sources:
- id: methodist-emergency
  resource: https://www.methodisthealth.org/articles/emergency-care-information
  title: Methodist emergency care information
- id: methodist-on-my-way
  resource: https://mychart.methodisthealth.org/MyChart/Scheduling/OnMyWay
  title: Methodist MyChart On My Way
- id: saint-francis-locations
  resource: https://www.saintfrancishealthsystem.com/services/emergency-room/emergency-room-locations
  title: Saint Francis ER locations
- id: saint-francis-memphis
  resource: https://southern-checkin.inquicker.com/facility/saint-francis-hospital?service=10
  title: Saint Francis Memphis check-in
- id: saint-francis-bartlett
  resource: https://southern-checkin.inquicker.com/facility/saint-francis-hospital-bartlett?service=10
  title: Saint Francis Bartlett check-in
- id: forrest-city-er
  resource: https://forrestcitymedicalcenter.com/er/
  title: Forrest City Medical Center ER page
- id: forrest-city-pledge
  resource: https://forrestcitymedicalcenter.com/er-30-minute-pledge/
  title: Forrest City 30-minute initial-assessment pledge
- id: aws-lambda-pricing
  resource: https://aws.amazon.com/lambda/pricing/
  title: AWS Lambda pricing
- id: aws-s3-pricing
  resource: https://aws.amazon.com/s3/pricing/
  title: Amazon S3 pricing
---

# Regional ER publication collector

Implemented and validated 2026-09-27, and **deployed the same day** as Lambda
`ed-wait-regional`, run every 15 minutes by EventBridge rule `regional_15`
([deployment record](#deployment-2026-09-27)). Not yet shown on the dashboard or
used in analyses.
The dated research behind the [collector](../edwait/regional_collector.py) is in
[Research notes](#research-notes-checked-2026-09-27).

## Sources and measures

| Facility slugs | Public information | Collection |
| --- | --- | --- |
| `methodist-university`, `methodist-north`, `methodist-south`, `methodist-germantown`, `methodist-olive-branch` | Estimated ER wait bounds; Germantown excludes the children's ED | Anonymous MyChart page and its read-only `GetOnMyWayDepartmentData` request. Match exact ER names and ED/ASAP flags; exclude Minor Medical Centers |
| `saint-francis-memphis`, `saint-francis-bartlett` | Projected ER check-in/treatment slots, subject to triage | InQuicker anonymous public token, ER schedules and available times. Facility IDs are fixed and checked each run against the facility the schedules response includes; schedule IDs are resolved each run. No booking or patient form requests |
| `forrest-city` | Numeric ER wait widget | Public ER page `wait-time-menu` widget. The separate 30-minute pledge is a fixed service promise and is not collected |

These are a separate eight-facility collector roster in `regional_collector.py`.
The existing 20-facility Baptist collector, dashboard and analytical inputs
remain as documented. Adding these publishers to the map and displaying their different measures is subsequent presentation work.

## Run locally

Use the existing Python environment and `requirements.txt`; no new dependency or
browser installation is needed:

```powershell
.venv\Scripts\python.exe -m edwait.regional_collector --output .cache/regional-batch.json
```

`--output` creates missing folders before any request. Omit it to print JSON.
Output contains `summary` and `observations`.
The CLI only reads public sources and writes the requested local file; it makes
no AWS writes. Exit status is 0 when every facility succeeds, 1 for a partial or
failed collection. Inspect the written result even when the exit status is 1.

## Record contract

[er-publication.schema.json](er-publication.schema.json) is separate from the
six-field Baptist schema. Each row has `schema_version` 1, a facility, metric, UTC
batch/observation timestamps, source page/endpoint, `latency_ms`, status, reason,
normalized `value`, and `source_value` evidence. `latency_ms` is the facility's
request and parsing time; the five Methodist rows also include the page and data
requests they share, and Saint Francis excludes the shared token request. Evidence
is selected Methodist department fields; Saint Francis slot rows reduced to
`schedule-id`, `appointment-type-id`, `times` and `next-time`; or Forrest City's
`{widget_text, matches}`, trimmed visible text kept even when nothing matched, so a
wording change can be seen in stored data. `observed_at` means collection
time, not the source's last update or a patient's actual wait.

- `estimated_wait_range`: `lower_minutes`, `upper_minutes`, `lower_bound_only`.
  A published single value has equal bounds. A capped single value becomes a
  lower bound with null upper bound, matching Methodist's "or more" display.
  No midpoint is invented. Hidden/null waits are explicitly unavailable.
- `arrival_slots`: UTC `next_available_at`, sorted/deduplicated `available_slots`,
  requested 24-hour window, source schedule IDs, and display timezone
  `America/Chicago`. `max_days=1` requests the first day with available slots;
  this is the returned public listing, not a guarantee of exhaustive availability.
  A returned `next-time` may extend beyond the requested window. A listing with no
  slots and no `next-time` is `unavailable` / `no_slots_returned`; an empty window
  with a later `next-time` stays `available` with an empty slot list. Slots
  returned at or after the window end are counted in `slots_beyond_window` (and can
  set `next_available_at`) but not listed. Malformed, missing, wrongly scoped, naive
  or expired timestamps, including slots before the window start, fail collection.
  Never convert time until a slot into an ER wait duration.
- `published_wait`: Forrest City's displayed minutes. Negative values such as
  `-1` are `invalid` with null normalized value and original source evidence.
  Zero is preserved as published, with its meaning unverified.

Invalid rows preserve source evidence but are unusable as wait values. A missing
or conflicting widget is invalid. HTML script/style text is ignored.
HTTP failures produce attempt diagnostics with no fabricated observation.
There is no carry-forward or latest-value merge in this collector.

Attempt state is `success`, `partial` or `failed`, with expected/collected metrics,
a bounded `error_code` (`request_failed`, `invalid_response`, `invalid_source_value`,
or `collection_deadline`), an `error_detail` and an `http_status`. For request
failures the detail is `timeout`, `connection_error`, `http_error` (with the status,
such as 403) or `request_error`. For invalid responses it is the collector's own
fixed description of the failed check, such as `missing or duplicate ER department`
or `invalid JSON`; for invalid rows it lists their reasons. Details never contain
exception text or anything copied from a source. A body that is not JSON is an
invalid response, not a failed request. The summary also records the run's
`duration_ms`. Every facility now has one metric, so attempts are `success` or
`failed`; `partial` remains for a facility with several metrics. Successful source
reads can still report explicitly unavailable information. A facility whose rows are all invalid is `failed` with
`invalid_source_value`, yet those rows are still stored and listed in
`collected_metrics`; request failures leave no row. Failures are isolated by facility; a shared Methodist
or InQuicker bootstrap failure is recorded for each affected facility. No exception
body, cookie, CSRF token, bearer token or patient information is persisted.
The bundled InQuicker client key is public application configuration; ephemeral
anonymous bearer tokens are obtained on each batch and remain in memory.

## Optional Lambda storage entry point

Handler: `edwait.regional_collector.lambda_handler`; environment: `BUCKET`.
The package needs only `requests` plus `edwait/__init__.py` and this module; the
Lambda runtime provides boto3 ([steps](#deployment-steps)). This is a
separate handler; do not replace `mem-ed-lambda.lambda_handler` or call it from the
website build.

```text
raw/er_publications/dt=YYYY-MM-DD/YYYYMMDDTHHMMSSffffffZ.jsonl
operations/er_publications/dt=YYYY-MM-DD/YYYYMMDDTHHMMSSffffffZ.json
```

Raw rows are UTF-8 JSONL; operations are UTF-8 JSON. The UTC batch timestamp
determines both paths; filenames retain microseconds. Raw storage precedes the
operations summary. A complete source failure still writes the summary before
raising; storage errors propagate. These paths are outside `raw/ed_wait`, the
existing compactor/reader and `data/latest.json`. There is no new public artifact.
Requests use 3-second connect / 10-second read timeouts, no automatic retries,
and stop starting requests below 23 seconds of remaining Lambda time to reserve
time for diagnostics/storage. A killed process can still prevent a summary.

The handler logs the summary without attempts at INFO (`regional_collection_summary`)
and one WARNING line per failed or partial facility (`regional_facility_failed` or
`regional_facility_partial`, with code, detail and HTTP status). The module sets its
own logger to INFO because Lambda's root logger defaults to WARNING. Requests
identify the project with a User-Agent that includes the repository URL. If a source
keeps returning 403 to it, treat that as a refusal: pause that source and contact
the site rather than changing headers or addresses to get around it.

## Validation and cost assessment

- Simplification (2026-09-27, after the hardening below): Saint Francis reads its
  schedules with the included facility instead of a separate facility lookup
  (8 requests per run instead of 10); latency is measured once per facility;
  errors are classified by one function; the research notes moved into this file;
  timestamps ending in `Z` are parsed natively; Forrest City's pledge is no longer
  collected, so a full run has eight rows. 25 collector tests and the full Python
  and JS suites passed. A live batch at `2026-09-27T16:58:53.516702+00:00`
  collected all eight facilities in 1,945 ms with eight schema-valid rows:
  Methodist 50–75, 25–40, 80–110, 25–45 and 35–65 minutes, 16 Memphis / 8
  Bartlett slots with none past the window, and Forrest City's 5 minutes. Saint
  Francis took about 280 ms per facility (about 410 ms with the lookup). It would
  store 9,212 bytes (6,996 JSONL + 2,216 summary).
- 110 Python tests passed, including 19 new collector tests: captured source
  shapes, ED identity, bounds/caps/zero, empty/invalid/expired slots, incorrect
  facility relationships, source failures, partial batches, deadline skips,
  independent storage and the new schema.
- Hardening after the 2026-09-27 audit (failure detail and HTTP status, trimmed
  evidence, slots past the window counted, HTTP-only latency, run duration, INFO and
  WARNING logs, User-Agent, CLI output folder): 25 collector tests and 117 Python /
  72 JS tests passed. Every status each parser can produce now validates against the
  schema. A live CLI batch at `2026-09-27T15:53:21.931657+00:00` collected all eight
  facilities in 2,153 ms: nine schema-valid rows, Methodist ranges 15–35, 30–45,
  75–135, 10–55 and 55–70 minutes, 16 Memphis / 8 Bartlett slots with none past the
  window, and Forrest City's 11 minutes plus the 30-minute pledge. It would store
  10,124 bytes (7,850 JSONL + 2,274 summary). Historical evidence, not current readings.
- The actual CLI collected all eight facilities in the 2026-09-27
  `14:54:38.232068+00:00` batch, completing at `14:54:40.339063+00:00`: nine
  schema-valid observations, eight successful facilities, no partial/failures.
  Methodist returned five ranges, Saint Francis returned 16 Memphis / 8 Bartlett
  slots, and Forrest City returned 11 minutes plus the 30-minute pledge.
  These values are historical validation evidence, not current readings.
- Earlier direct Forrest City requests returned 403, and the page as rendered in a
  browser showed the `-1` sentinel with a valid pledge (kept as the test fixture);
  the 14:54 batch then succeeded. No stored batch recorded the `-1`.
- Raw JSONL plus summary for the successful sample totaled 9,193 bytes. At an
  illustrative 15-minute cadence, 2,880 monthly runs imply roughly 26.5 MB/month
  at that sample size and 5,760 S3 PUTs. There are eight public HTTP requests per
  successful batch (ten before the simplification); no browser bundle download or
  paid API is required.
- Before free allowances, using a conservative 60 seconds at 128 MB per run
  yields about $0.36/month Lambda compute plus less than $0.001 requests, about
  $0.029 S3 PUTs and less than $0.01 for one month of this stored volume. Budget
  approximately $0.40/month incremental under those assumptions, excluding logs,
  trigger choice and future reads; retained storage accumulates (about 26.5 MB/month
  at the 16:58 batch's size). Live batches took 1.9–2.2 s end to end, so the
  60-second figure is deliberately conservative; within free allowances, S3 PUTs
  would dominate (about $0.03/month). Verify the
  chosen deployment memory and actual runtime against the project's $5/month
  total limit. [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/),
  [S3 pricing](https://aws.amazon.com/s3/pricing/).

Validation itself changed nothing in AWS; the deployment below created the
function, role, log group and schedule. Public map/analytics integration remains
separate work.

## Deployment (2026-09-27)

Run by Claude at the user's request with the local AWS CLI (root credentials),
following the steps below, all in `us-east-1`:

| Resource | Configuration |
| --- | --- |
| IAM role `ed-wait-regional-collector` (created 17:18:19 UTC) | Trusted by Lambda; managed `AWSLambdaBasicExecutionRole` for logs; inline `RegionalPublicationWrites` allows only `s3:PutObject` on `mem-ed-wait-times/raw/er_publications/*` and `mem-ed-wait-times/operations/er_publications/*` |
| Log group `/aws/lambda/ed-wait-regional` | 30-day retention |
| Lambda `ed-wait-regional` | Python 3.14, x86_64, 128 MB, 60 s, handler `edwait.regional_collector.lambda_handler`, `BUCKET=mem-ed-wait-times`; asynchronous retries 0. Package `build/regional-20260927-9691589.zip` from commit `9691589` (0.66 MB), `CodeSha256` `gW+Iwtp91XHo3V+uaGjxH8On0NDGd0IsdwOFiKDSknQ=` |
| EventBridge rule `regional_15` (enabled 17:20:39 UTC) | `rate(15 minutes)`, target `ed-wait-regional`; Lambda permission `regional-15` allows only this rule |
| Metric filter `regional-facility-failures` | On the log group: each `regional_facility_failed` line adds 1 to `EdWait/Regional` `FacilityFailures` (0 for other lines) |
| CloudWatch alarms (added about 17:30 UTC) | `regional-collector-failed-run`: Lambda `Errors` ≥ 1 in 15 minutes (every facility failed, or a crash). `regional-collector-facility-failing`: `FacilityFailures` ≥ 1 in four consecutive 15-minute periods (some facility failed in every run for an hour). `regional-collector-stopped`: no invocations in an hour (missing data counts as breaching). All email SNS topic `dashboard-dispatch-alerts` |

Before the deployment, the role, function, rule and log group did not exist and
both prefixes were empty. The manual run at 17:19:41 UTC succeeded for all eight
facilities in 1,810 ms, with no 403 from AWS addresses. It stored 6,996 bytes of raw
rows (eight, all schema-valid) and a 2,216-byte summary, and CloudWatch showed the
INFO `regional_collection_summary` line. The first scheduled run, at 17:21:06 UTC,
also succeeded for all eight facilities in 1,472 ms.

At the user's request the alarms above were added, the alert topic was given the
display name "ED wait alerts", and a new email subscription (the user's address)
was created at 17:31:38 UTC; the user confirmed it the same day. The facility alarm also fires if Forrest City shows its `-1` sentinel
for an hour, since an invalid widget fails that facility.

## Deployment steps

User decisions, 2026-09-27: the sources' terms are acceptable for scheduled
collection, and the collector runs every 15 minutes like the Baptist collector.
(robots.txt, checked the same day, does not block the paths used: MyChart has none,
InQuicker's rules do not cover `/v4/...`, and Forrest City allows all with a
10-second crawl delay.) Build from the committed collector. Prefer an IAM identity
over root keys for these commands. From the repository root in PowerShell, `us-east-1`:

1. Build a Linux package with only `requests` and the collector module; the Lambda
   runtime provides boto3 (tested 2026-09-27: 0.66 MB, forward-slash entry names,
   no `__pycache__`, `bin/` or `.lock`):

   ```powershell
   $py = "$PWD\.venv\Scripts\python.exe"; $dir = "build\regional-$(Get-Date -Format yyyyMMdd)"; $zip = "$PWD\$dir.zip"
   uv pip install --python $py --python-version 3.14 --python-platform x86_64-manylinux2014 --only-binary :all: --target $dir "requests>=2.32,<3"
   New-Item -ItemType Directory -Force "$dir\edwait" | Out-Null; Copy-Item edwait\__init__.py, edwait\regional_collector.py "$dir\edwait\"
   Push-Location $dir; & $py -m zipfile -c $zip @(Get-ChildItem -Name | Where-Object { $_ -notin "bin", ".lock" }); Pop-Location
   ```

2. Create a role that can only write the two prefixes (JSON files avoid Windows
   quoting problems; `ascii` avoids a byte-order mark):

   ```powershell
   Set-Content -Encoding ascii build\regional-trust.json '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
   Set-Content -Encoding ascii build\regional-s3.json '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:PutObject","Resource":["arn:aws:s3:::mem-ed-wait-times/raw/er_publications/*","arn:aws:s3:::mem-ed-wait-times/operations/er_publications/*"]}]}'
   aws iam create-role --role-name ed-wait-regional-collector --assume-role-policy-document file://build/regional-trust.json
   aws iam attach-role-policy --role-name ed-wait-regional-collector --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
   aws iam put-role-policy --role-name ed-wait-regional-collector --policy-name RegionalPublicationWrites --policy-document file://build/regional-s3.json
   ```

3. Create the function with the Baptist collector's runtime settings, turn off
   automatic retries (a failed run would otherwise hit the sources three times), and
   keep logs for 30 days. If `create-function` says the role cannot be assumed, wait
   a few seconds for IAM and retry.

   ```powershell
   aws lambda create-function --function-name ed-wait-regional --runtime python3.14 --architectures x86_64 --memory-size 128 --timeout 60 --handler edwait.regional_collector.lambda_handler --role arn:aws:iam::666037347522:role/ed-wait-regional-collector --environment "Variables={BUCKET=mem-ed-wait-times}" --zip-file "fileb://$zip"
   aws lambda put-function-event-invoke-config --function-name ed-wait-regional --maximum-retry-attempts 0
   aws logs create-log-group --log-group-name /aws/lambda/ed-wait-regional
   aws logs put-retention-policy --log-group-name /aws/lambda/ed-wait-regional --retention-in-days 30
   ```

4. Run it once by hand from AWS before scheduling. Check that all eight facilities
   succeeded; an `http_status` of 403 means that source refuses AWS addresses, so
   decide whether to drop it or contact the site before continuing.

   ```powershell
   aws lambda invoke --function-name ed-wait-regional --cli-binary-format raw-in-base64-out --payload '{}' build\regional-invoke.json
   Get-Content build\regional-invoke.json
   aws s3 ls s3://mem-ed-wait-times/operations/er_publications/ --recursive
   aws logs tail /aws/lambda/ed-wait-regional --since 15m
   ```

5. Schedule it:

   ```powershell
   aws events put-rule --name regional_15 --schedule-expression "rate(15 minutes)" --state ENABLED
   aws lambda add-permission --function-name ed-wait-regional --statement-id regional-15 --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn arn:aws:events:us-east-1:666037347522:rule/regional_15
   aws events put-targets --rule regional_15 --targets "Id=regional,Arn=arn:aws:lambda:us-east-1:666037347522:function:ed-wait-regional"
   ```

6. After an hour, confirm four summaries and `regional_collection_summary` log lines;
   after a few days, confirm the cost. Record the deployment in the development plan,
   this file and the S3 reference.

7. Add the alarms. They email the alert topic, which needs a confirmed subscription
   (`aws sns subscribe --topic-arn $topic --protocol email --notification-endpoint <address>`,
   then the emailed link):

   ```powershell
   $topic = "arn:aws:sns:us-east-1:666037347522:dashboard-dispatch-alerts"
   aws logs put-metric-filter --log-group-name /aws/lambda/ed-wait-regional --filter-name regional-facility-failures --filter-pattern regional_facility_failed --metric-transformations "metricName=FacilityFailures,metricNamespace=EdWait/Regional,metricValue=1,defaultValue=0"
   aws cloudwatch put-metric-alarm --alarm-name regional-collector-failed-run --namespace AWS/Lambda --metric-name Errors --dimensions Name=FunctionName,Value=ed-wait-regional --statistic Sum --period 900 --evaluation-periods 1 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching --alarm-actions $topic
   aws cloudwatch put-metric-alarm --alarm-name regional-collector-facility-failing --namespace EdWait/Regional --metric-name FacilityFailures --statistic Sum --period 900 --evaluation-periods 4 --datapoints-to-alarm 4 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching --alarm-actions $topic
   aws cloudwatch put-metric-alarm --alarm-name regional-collector-stopped --namespace AWS/Lambda --metric-name Invocations --dimensions Name=FunctionName,Value=ed-wait-regional --statistic Sum --period 3600 --evaluation-periods 1 --threshold 1 --comparison-operator LessThanThreshold --treat-missing-data breaching --alarm-actions $topic
   ```

   The deployed alarms also carry `--alarm-description` text naming what to check.

To pause: `aws events disable-rule --name regional_15`. Stored objects stay in place.
Pausing trips `regional-collector-stopped` after an hour unless you also run
`aws cloudwatch disable-alarm-actions --alarm-names regional-collector-stopped`.
To ship a code change: rebuild the package (step 1) from the new commit, then
`aws lambda update-function-code --function-name ed-wait-regional --zip-file fileb://<zip>`
and check its `CodeSha256` and the next run's summary.

## Research notes (checked 2026-09-27)

Moved from the collector's comments on 2026-09-27. These are historical findings,
not live data; recheck them before relying on them.

- **Methodist.** Five ERs publish estimated wait ranges: University, North, South,
  Le Bonheur Germantown and Olive Branch. Germantown's estimate excludes the
  children's ED. The public MyChart listing also contains Minor Medical Centers,
  which are urgent care and must not be mistaken for the five ERs
  ([emergency care information](https://www.methodisthealth.org/articles/emergency-care-information),
  [MyChart On My Way](https://mychart.methodisthealth.org/MyChart/Scheduling/OnMyWay)).
  The anonymous page supplies a session-specific reason-for-visit ID and CSRF
  token. Its read-only `GetOnMyWayDepartmentData` POST returns `WaitTime` (upper),
  `WaitTimeLower`, `CanShowWaitInfo`, `IsEDDep` and `IsASAP`. The site's formatter
  renders equal or absent lower bounds as one value; `MaxValueHit` then means
  "or more". Readings during verification: University 5–20, Germantown 10–25,
  South 60–105, North 55–115 and Olive Branch 15–30 minutes. Do not reuse these.
- **Saint Francis.** Memphis (5959 Park Ave) and Bartlett (2986 Kate Bond Rd) offer
  InQuicker arrival/check-in slots, not a measured wait or guaranteed appointment;
  Memphis explicitly calls these projected treatment times, subject to triage
  ([ER locations](https://www.saintfrancishealthsystem.com/services/emergency-room/emergency-room-locations),
  [Memphis check-in](https://southern-checkin.inquicker.com/facility/saint-francis-hospital?service=10),
  [Bartlett check-in](https://southern-checkin.inquicker.com/facility/saint-francis-hospital-bartlett?service=10)).
  The public application obtains an anonymous token with its bundled public client
  key, then reads facilities, schedules and available appointment times; the
  collector reads only schedules (with the facility included) and available times.
  Observed facility IDs 953125689 / 953125690 are fixed in the collector and checked
  against the facility each schedules response includes; schedule IDs (17 / 18) are
  resolved on every run. UI service line 10 is not API ER service 36; the collector
  checks the service permalink `emergency-room` and each schedule's facility
  relation. Both returned next-time 2026-09-27T10:30:00-05:00 during verification.
  Store absolute timestamps and the query window, never minutes until a slot as an
  ER wait.
- **Forrest City.** Forrest City Medical Center (Forrest City, AR, near the search's
  50-mile radius boundary) publishes a numeric ER widget
  ([ER page](https://forrestcitymedicalcenter.com/er/)). Earlier checks showed
  inconsistent 0 / −1 values; the browser showed −1 again on 2026-09-27, and direct
  requests returned HTTP 403 during implementation. A later full collector run
  succeeded at 14:54 UTC with 11 minutes. The 403 is not a permanent policy claim,
  and 11 is not a fallback. Negative values are kept only as invalid source
  evidence, never reported as a wait; zero stays a published zero with unverified
  meaning; access failures are never replaced by cached research values. The
  hospital also publishes a
  [30-minute initial-assessment pledge](https://forrestcitymedicalcenter.com/er-30-minute-pledge/),
  a service target rather than a current wait. It was collected until the
  2026-09-27 simplification and no longer is.
- **Scope.** These eight publishers are separate from the eight map-only
  nonpublishers (Regional One, Le Bonheur Children's, Memphis VA, Highland Hills,
  Alliance, CrossRidge, SMC Regional, Lauderdale) and from the 20 Baptist
  `CV_ED_Wait` facilities. No clinical equivalence between these providers'
  measures has been established.
