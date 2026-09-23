# M0 operations and deployment

Implementation date: 2026-09-14. Deployed to production on 2026-09-22; both Lambdas
run version 2 code, and the collector publishes latest readings and attempts.
See the [deployment record](aws-deployment-2026-09-22.md) for permissions, package
identity, preserved schedules, smoke checks, and remaining operational checks.

## Local validation

Use Python 3.12+ (inspected Lambdas use 3.14) and Node 22+:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --test tests/*.test.mjs
python -m edwait.prepare
quarto render dashboard/ --to html
```

Tests use in-memory S3 and a localhost HTTP server; they do not publish production
objects or call the provider. Since M1, preparation reads S3 through the usual AWS
credential chain; `BUCKET` defaults to `mem-ed-wait-times`. Quarto consumes the
prepared artifact and embeds the registry independently of history. Live values start
missing/loading when `data/latest.json` is absent.
See [M1 operations](m1-operations.md) for comparison preparation and ownership,
and [M1 validation](m1-validation.md) for the current validation record.
The following M0 evidence predates M1's
comparison view.

The HTTP integration serves fixed HTML and successive latest artifacts, exercises
the production fetch/state/render functions, and verifies a changed reading
without an HTML rebuild. It injects HTTP failure, advances time, verifies stale
and failure labels, then checks recovery. This is local integration evidence,
not a deployed collector-to-public-site check. The AWS CLI dry-run test uses a
local S3 listing fixture to verify excluded objects survive `--delete`, while
ordinary obsolete site files are selected for deletion. Local browser validation
also changed a Python-generated synthetic observation without rebuilding HTML,
then verified 404 failure labels and recovery. All 24 Python and 6 JavaScript
tests passed on 2026-09-14; Quarto 1.10.18 rendered against read-only live history.

## Ownership and required access

| Component | Owns | Access needed |
| --- | --- | --- |
| Collector `ed-wait-times` | Raw, attempts, latest | Put raw/operations in data bucket; Get/Put `data/latest.json` and ListBucket on website bucket for initial missing-object detection |
| Compactor `ed-wait-compaction` | Compacted gzip and snapshot metadata | List/Get raw, Put compacted |
| Quarto job | HTML and website assets | List/Get history; website sync with `data/*` exclusion |
| Browser | No writes | Same-origin public Get of `data/latest.json` |

The website policy allowed public Get on all website objects when inspected
2026-09-14. Operations summaries belong in the data bucket. No patient or origin
information is collected. No CORS change is needed for same-origin requests.

Required collector environment (compactor requires only `BUCKET`):

```text
BUCKET=mem-ed-wait-times
LATEST_BUCKET=mem-ed-wait-times-dashboard
STALE_AFTER_SECONDS=1800
```

Missing `LATEST_BUCKET` fails before collection; stale threshold must be positive.
The object key is fixed at `data/latest.json`. See [storage contracts](s3-buckets.md)
for the schema, cache, merge, and freshness rules.

Package both entry points with `edwait/`, including `facilities.json`, and
`requirements.txt` dependencies. Preserve existing handlers
`mem-ed-lambda.lambda_handler` and `lambda_function.lambda_handler`. Example Linux
packaging from the repository root, using a clean build directory:

```sh
python -m pip install -r requirements.txt --target build/lambda
cp mem-ed-lambda.py lambda_function.py build/lambda/
cp -r edwait build/lambda/
cd build/lambda
zip -r ../ed-wait-lambdas.zip .
```

Use a clean build directory to avoid stale dependencies. boto3 must support S3
PutObject `IfMatch` and `IfNoneMatch`; validation used boto3 1.43.93. No historical
rewrite is required. Legacy compacted partitions use raw fallback until a later
compaction adds snapshot metadata.

## Rollout order

1. Deploy the workflow's `--exclude "data/*"` protection before independently
   publishing data. Preserve it in manual sync commands and rollback versions.
2. Prepare collector IAM/environment and package the shared module with both
   Lambdas. Keep existing EventBridge schedules. Monitor timeout margins: the
   60-second collector records deadline failures when less than 25 seconds remain
   before starting another request.
3. Deploy collector/compactor. Verify a scheduled run writes raw, operations, and
   schema-valid latest data with no-store headers. A first-run failed facility
   stays missing until its first success. Total facility failure publishes attempt
   state and then raises. Storage errors preserve the prior public object.
4. Render/sync the site. Verify latest's ETag survives deployment and a later
   observation appears on an already-open page without an HTML build. Check
   deployed ages and failure labels. Record deployment time/evidence in the plan.

## Operator checks

- Compare `succeeded + failed` with `expected_facilities`; inspect per-facility
  error codes and structured `collection_summary`/facility logs.
- Review last-success and last-attempt times separately. A new generation time
  does not make an old observation current.
- Review historical diagnostics for missing partitions, batch gaps, facility
  omissions, unknown slugs, rejected inputs, and conflicting duplicates. These
  describe collection coverage, not occupancy or proof of upstream updates.
- Resolve publication IAM/network/schema errors and allow the next collection
  to merge. Do not delete prior state to bypass validation. Raw and operations
  writes precede public publication. Timeouts or process termination can prevent
  operations summaries; inspect Lambda errors alongside completed-attempt data.
- A collector rollback can stop public updates; retained data ages into stale
  state. Keep the website exclusion. M0 adds no automated production alarms.

The 30-minute threshold is provisional, informed by the verified 15-minute
schedule and the plan's dated cadence assessment. The provider's current API
averaging window, update behavior, and sentinel meanings remain unconfirmed.
