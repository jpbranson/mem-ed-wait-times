# Regional ER publication collector

Implemented and locally validated 2026-09-27. **Not deployed or scheduled.**
The [collector](../edwait/regional_collector.py) includes the relevant research
from this chat in a commented section at the top, with sources and dated findings.

## Sources and measures

| Facility slugs | Public information | Collection |
| --- | --- | --- |
| `methodist-university`, `methodist-north`, `methodist-south`, `methodist-germantown`, `methodist-olive-branch` | Estimated ER wait bounds; Germantown excludes the children's ED | Anonymous MyChart page and its read-only `GetOnMyWayDepartmentData` request. Match exact ER names and ED/ASAP flags; exclude Minor Medical Centers |
| `saint-francis-memphis`, `saint-francis-bartlett` | Projected ER check-in/treatment slots, subject to triage | InQuicker anonymous public token, facility lookup, verified ER schedules, available times. Resolve facility/schedule IDs on each run; no booking or patient form requests |
| `forrest-city` | Numeric ER wait widget and a separate initial-assessment pledge | Public ER page: `wait-time-menu` widget and the "NN-Minute ER Pledge" text anywhere in its visible content |

These are a separate eight-facility collector roster in `regional_collector.py`.
The existing 20-facility Baptist collector, dashboard and analytical inputs
remain as documented. Adding these publishers to the map and displaying their
different measures is subsequent presentation work.

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
normalized `value`, and `source_value` evidence. `latency_ms` is time spent in that
source's HTTP requests, body included and parsing excluded; the five Methodist rows
share one page request and one data request, and Saint Francis excludes the shared
token request. Evidence is selected Methodist department fields; Saint Francis slot
rows reduced to `schedule-id`, `appointment-type-id`, `times` and `next-time`; or
Forrest City's `{widget_text, matches}` and `{pledge_snippets, matches}`, trimmed
visible text kept even when nothing matched, so a wording change can be seen in
stored data. `observed_at` means collection
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
- `initial_assessment_target`: the pledge's minutes. This is a service target,
  not a current wait. A page fetch failure cannot generate a pledge observation
  from the historical research comments.

Invalid rows preserve source evidence but are unusable as wait values. A valid
pledge alongside an invalid widget produces a partial facility attempt. A missing
or conflicting widget/pledge is invalid. HTML script/style text is ignored.
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
`duration_ms`. Successful source reads can still report explicitly
unavailable information. A facility whose rows are all invalid is `failed` with
`invalid_source_value`, yet those rows are still stored and listed in
`collected_metrics`; request failures leave no row. Failures are isolated by facility; a shared Methodist
or InQuicker bootstrap failure is recorded for each affected facility. No exception
body, cookie, CSRF token, bearer token or patient information is persisted.
The bundled InQuicker client key is public application configuration; ephemeral
anonymous bearer tokens are obtained on each batch and remain in memory.

## Optional Lambda storage entry point

Handler: `edwait.regional_collector.lambda_handler`; environment: `BUCKET`.
Package `edwait/` and the existing Python dependencies using the platform-correct
[Lambda packaging procedure](m0-operations.md). This is a separate handler;
do not replace `mem-ed-lambda.lambda_handler` or call it from the website build.

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
  at that sample size and 5,760 S3 PUTs. There are ten public HTTP requests per
  successful batch; no browser bundle download or paid API is required.
- Before free allowances, using a conservative 60 seconds at 128 MB per run
  yields about $0.36/month Lambda compute plus less than $0.001 requests, about
  $0.029 S3 PUTs and less than $0.01 for one month of this stored volume. Budget
  approximately $0.40/month incremental under those assumptions, excluding logs,
  trigger choice and future reads; retained storage accumulates (about 29 MB/month
  at the 15:53 batch's size). Both live batches took about 2.1–2.2 s end to end, so
  the 60-second figure is deliberately conservative; within free allowances, S3
  PUTs would dominate (about $0.03/month). Verify the
  chosen deployment memory and actual runtime against the project's $5/month
  total limit. [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/),
  [S3 pricing](https://aws.amazon.com/s3/pricing/).

No AWS objects, functions, IAM policies, schedules, deployed site files or paid
tiers were changed. Public map/analytics integration and a production release
remain separate work.

## Deployment steps (not yet run)

User decisions, 2026-09-27: the sources' terms are acceptable for scheduled
collection, and the collector runs every 15 minutes like the Baptist collector.
(robots.txt, checked the same day, does not block the paths used: MyChart has none,
InQuicker's rules do not cover `/v4/...`, and Forrest City allows all with a
10-second crawl delay.) Build from the committed collector. Prefer an IAM identity
over root keys for these commands. From the repository root in PowerShell, `us-east-1`:

1. Build a Linux package with the same layout as the existing Lambdas (tested
   2026-09-27: 16.8 MB, forward-slash entry names, no `__pycache__`, `bin/` or
   `.lock`):

   ```powershell
   $py = "$PWD\.venv\Scripts\python.exe"; $dir = "build\regional-$(Get-Date -Format yyyyMMdd)"; $zip = "$PWD\$dir.zip"
   uv pip install --python $py --python-version 3.14 --python-platform x86_64-manylinux2014 --only-binary :all: --target $dir -r requirements.txt
   Copy-Item -Recurse edwait "$dir\edwait"
   Get-ChildItem $dir -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
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
   this file and the S3 reference. An alarm on the function's `Errors` metric helps
   only once the alert topic has a confirmed email subscription.

To pause: `aws events disable-rule --name regional_15`. Stored objects stay in place.
