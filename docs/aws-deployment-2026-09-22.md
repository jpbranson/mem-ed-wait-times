# AWS deployment — 2026-09-22

Deployed on September 22 in America/Chicago (2026-09-23 UTC).
Source release: [`17d4e57`](https://github.com/jpbranson/mem-ed-wait-times/commit/17d4e57).

- [Dashboard over HTTPS](https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/index.html)
- [S3 website endpoint](http://mem-ed-wait-times-dashboard.s3-website-us-east-1.amazonaws.com/)

## Deployed components

The updated M0 collector/latest publisher, compactor, M1 dashboard and comparison
artifacts are deployed in `us-east-1`. The M2 static interface, origin map and
fictional example are included; no public routing gateway or TomTom key was
configured. All real destinations remain ineligible and recommendations remain off.

Both `ed-wait-times` and `ed-wait-compaction` now have published version **2**
and matching `$LATEST` code. Their previous code is retained as version **1**.
Handlers, Python 3.14 runtime, x86_64 architecture, 128 MB memory, and 60-second
timeouts were preserved. The deployment archive was built for Linux with the
shared `edwait/` package and registry; boto3 1.43.100 supports conditional writes.
Its base64 SHA-256 is `S9l8FemKYpjfdMjco35iWvUKF1A+k33ThnZ12P3qkh8=`.

The collector retains `BUCKET=mem-ed-wait-times` and now has
`LATEST_BUCKET=mem-ed-wait-times-dashboard` and `STALE_AFTER_SECONDS=1800`.
Inline policy `EdWaitLatestPublication` on `ed-wait-times-role-4v9ld2te` grants:

- `s3:PutObject` on `mem-ed-wait-times/operations/collection/*`.
- `s3:GetObject` and `s3:PutObject` on `mem-ed-wait-times-dashboard/data/latest.json`.
- `s3:ListBucket` on the dashboard bucket, so missing-object reads return 404
  during first publication ([AWS GetObject behavior](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)).

Existing compactor permissions were sufficient. Enabled EventBridge rules remain
`trigger_15` at `rate(15 minutes)` and `compact_daily` at `cron(30 1 * * ? *)`,
targeting the unqualified functions. No schedules or public bucket policies changed.

The existing GitHub hourly/manual workflow now contains the release sources,
tests, preparation, and `--delete --exclude "data/*"` sync protection. No new push
trigger was added. This release was prepared/rendered locally and uploaded directly
with that exclusion; a post-release GitHub-hosted run was not yet observed.

## Validation evidence

- Before release, all **49 Python and 33 JavaScript tests** passed, followed by
  successful data preparation and Quarto rendering.
- Manual collector invocation at 04:07 UTC wrote 20 raw observations, a collection
  summary, and latest readings with no failed/missing facilities. A subsequent
  scheduled run at 04:08:50 UTC also recorded 20 successes and published at
  04:09:04 UTC, confirmed in CloudWatch and the public artifact.
- The compactor processed the completed 2026-09-22 partition: 1,920 records from
  96 raw objects. Its metadata includes a source fingerprint and compaction time;
  the subsequent preparation selected this partition as `snapshot_matches_raw`.
- Context generated at 04:07:57 UTC contains 20 facilities and 13,459 seven-day
  historical points. The reader reported no rejected/conflicting/duplicate records
  or collection gaps; three facility observations are missing across 3,474 observed
  batches in the wider baseline window. Those coverage limits remain explicit.
- The website's `index.html` was uploaded at 04:09:38 UTC. All **39 static files**
  were fetched publicly and matched their local bytes. JavaScript module MIME types
  were valid; comparisons, travel, and latest JSON passed their schemas.
- `data/latest.json` retained ETag `fa689df69c2a511c26b7cb5acb5a0f39` across website
  sync and serves `application/json` with `Cache-Control: no-store, max-age=0`.
- At 04:11 UTC, the production feed/context functions in Node fetched the public
  site, accepted its current comparisons, then refreshed all 20 observations after
  another real collector invocation. All 20 remained recently collected. The HTML
  stayed unchanged with SHA-256
  `36d0989fbefe9262285357d378d65f2f0b8ef7ce28de6738d6d3766e7b07eda9`.
- The HTTPS object URL returned `text/html`, and its same-origin latest JSON
  returned HTTP 200. No CDN or custom domain was provisioned.

Browser automation was unavailable in this session. The deployed refresh check
used the production client functions in Node; it was not a new visual browser
review. The dated local desktop/mobile evidence remains in the M1/M2 validation
documents. The next operational checks are the next hourly GitHub build and a
public browser review. These are distinct from the completed direct deployment.

## Rollback and retained evidence

The prior public website assets were downloaded to the ignored local directory
`.cache/aws-deploy-20260922/previous-website/`. The same directory holds the upload
dry run, invocation logs/results, package hash, ETag comparison, and full public
verification results. These local files are not a shared or durable backup service.

Prior Lambda code remains in AWS as version 1. Any website rollback must continue
excluding `data/*`; any collector rollback must account for live data ceasing to
refresh. Keep the production freshness checks enabled so retained readings age
into stale state. The source observation contract was not changed by this rollout.
