# M1 preparation and rollout

Implemented and locally validated 2026-09-14; **deployed 2026-09-22** with M0.
See the [release evidence](aws-deployment-2026-09-22.md) for public artifact and
refresh verification, including the limits of the browser checks. M1 uses M0's
collector/latest contract without changing Lambda behavior. Follow the
[M0 rollout](m0-operations.md) for the shared package, IAM, environment, and
collector-owned data path before verifying the complete public feature.

## Environment setup

Run commands from the repository root. Install Python 3.12+, Node 22+, Quarto,
and the AWS CLI. The deployed Lambdas use Python 3.14; local rendering was
validated with Quarto 1.10.18. Python dependencies are in
[`requirements-dev.txt`](../requirements-dev.txt). History preparation needs
AWS credentials that can list the data bucket and read raw/compacted objects;
ordinary local review does not need website write or Lambda permissions.

For a new checkout, create an environment with `python -m venv .venv` (use the
installed Python 3.12+ command, such as `python3`, if necessary). Install packages
with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` on Windows
or `.venv/bin/python -m pip install -r requirements-dev.txt` on Linux/macOS.
An existing uv-managed environment may omit pip; on the release workstation the
equivalent is `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt`.
Reuse an existing environment rather than recreating it for each build.

Quarto must be installed separately and available as `quarto` below. The release
workstation also has an ignored copy at `.cache\quarto\bin\quarto.cmd`; when
using that copy in PowerShell, replace `quarto` with
`& .\.cache\quarto\bin\quarto.cmd`. This cached executable is not in Git.

## Build and validate

PowerShell:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/*.test.mjs
.venv\Scripts\python.exe -m edwait.prepare
$env:QUARTO_PYTHON = Join-Path (Get-Location) '.venv\Scripts\python.exe'
quarto render dashboard/ --to html
```

Linux/macOS:

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.test.mjs
.venv/bin/python -m edwait.prepare
export QUARTO_PYTHON="$PWD/.venv/bin/python"
quarto render dashboard/ --to html
```

`BUCKET` defaults to `mem-ed-wait-times`. Preparation reads from UTC midnight
36 days before the run through the current time: 28 reference days plus seven
display days and padding for local-day/batch boundaries. M0 source selection,
conditional reads, validation, and coverage apply to each partition. Eight
parallel partition workers bound retrieval concurrency. AWS errors abort the
build; malformed records are counted and excluded, and sparse references remain
unavailable according to the support policy.

Preparation atomically replaces ignored `dashboard/comparisons.json`. Quarto
copies it to `_site/` with browser modules and renders operator diagnostics from
that same artifact. It does not read S3 in notebook cells. The hourly/manual
workflow runs tests, preparation, and rendering before website sync. A failed
step prevents that workflow's sync, preserving the published artifact.

The opening all-hospital Plotly chart is embedded in the HTML using the existing
local Plotly dependency, including its JavaScript so no chart CDN is required.
Emit the library separately from the plot: Quarto moves library display output
into the document head, so combining them relocates the chart and leaves its
container empty. The locally served `fonts/` resources include Inter's WOFF2,
source attribution, and SIL Open Font License; ship these with the site as well.
The overview displays the artifact's preparation time and updates with each site build.
Independent live refresh continues in the individual comparisons below it.
The native hospital toggles and shared 24-hour/seven-day buttons use
`overview.mjs` to fit the y-axis to visible lines. Ship this module with the HTML
and other resources. The current presentation places methodology and operational
detail in disclosures; failed/stale states remain visible in the comparison.
All text has a 16 CSS px minimum. The application redraws the focused SVG charts
when their available width changes to maintain that label size on mobile.

For a reproducible dated replay, without publishing, use the activated environment
(or replace `python` below with its explicit executable path):

```sh
python scripts/m1_snapshot.py --start 2026-07-29T00:00:00Z --end 2026-09-14T00:00:00Z --output .cache/m1-history.json
python scripts/m1_replay.py .cache/m1-history.json
python scripts/m1_report.py
python -m edwait.prepare --snapshot .cache/m1-history.json --now 2026-09-14T00:00:00Z --output build/replay-comparisons.json --travel-output build/replay-travel.json
```

Snapshot and report commands are dated audit tools. Re-reading corrected S3
objects can change the snapshot hash; retain the original evidence and record a
new audit when that happens. The report script expects the default `.cache`
filenames and writes the checked-in evidence JSON. An explicit `--now` is required
for snapshot preparation so old history cannot acquire an implicit current date.
Never publish synthetic latest fixtures or a replay artifact as current context.

## Local preview

After preparation and rendering, run
`.venv\Scripts\python.exe -m edwait.serve --live-s3` on Windows or
`.venv/bin/python -m edwait.serve --live-s3` on Linux/macOS. Open
`http://127.0.0.1:8765/`; stop the foreground server with Ctrl+C. An alternate
loopback port can be selected with `--port 8766`. No TomTom key is needed to
view charts, select an origin, or use the fictional travel example.

The server serves `dashboard/_site/`. With `--live-s3`, it reconstructs latest
successes from the newest batch in the last two hours and caches them for 30
seconds. It does not read the production attempt summaries or proxy the deployed
`data/latest.json`, so collection failures and retained earlier successes can
differ from production. This limitation still applies after M0 deployment.
Without the flag, it serves local files only; a clean render contains no
`data/latest.json`, so current readings remain unavailable unless a local artifact
has been supplied. See [M2 operations](m2-operations.md#preparation-and-local-review)
for optional local routing configuration.

Serving does not rebuild history. Rerun preparation and Quarto in another terminal
to renew comparison/travel context; reload the page to update the embedded
overview. The browser can refresh individual context between page loads, but the
overview changes only with the rendered page.

## Artifact ownership and caching

| Object | Owner | Update / consumer behavior |
| --- | --- | --- |
| `data/latest.json` | Collector | M0 complete replacements; no-store; browser polls every 60 seconds |
| `comparisons.json` | Website build | Complete replacement on each successful build (configured hourly/manual), beside `index.html`; browser revalidates every five minutes |
| `travel.json`, `travel.mjs` | Website build (M2 prototype) | Separate historical movement/eligibility context and comparison UI; no origins or routes stored; see [M2 operations](m2-operations.md) |
| HTML, modules, styles, `fonts/*` | Website build | Quarto output and locally served Inter/license, deployed with the context artifact |

The workflow retains `--delete --exclude "data/*"`. The root comparison file is
intentionally website-owned and travels with each render. It is not placed under
the collector's protected prefix. The existing public website read policy covers
this same-origin object. No new Lambda permission, CORS rule, or origin service
is needed for M1.

The context fetch uses `cache: no-cache` to revalidate a reusable response using
the server's ETag instead of downloading an unchanged roughly 2 MB file each
time. It has a 10-second timeout; manual refresh and tab visibility also refresh
both artifacts. Sync infers JSON content type and does not set a new explicit
Cache-Control policy for context. Confirm `application/json` and ETag behavior
through the actual serving path during rollout, especially if a CDN is added.

The browser accepts schema/method version 1 and `self-comparison-v1`, validates
facility coverage and model support, and rejects malformed or regressing context.
An unsuccessful refresh retains dated charts while pausing current comparisons.
References also expire at two hours of age or next local midnight, whichever
comes first. Comparisons pause after expiration until the next successful build
arrives; no prior-day model is relabeled as today's. A fresh reference never makes
a stale observation current. The browser may append newly fetched observations
to history in memory, capped at one per 15-minute slot; raw/latest contracts stay
unchanged. Direction becomes unavailable if the recent reference is too sparse.

## Refresh and troubleshooting

The [workflow](../.github/workflows/dashboard.yml) runs on the configured cron
`0 * * * *` and `workflow_dispatch`, using `main`. It has no push trigger.
It tests, prepares, renders, and uploads the website; it does not package or
deploy either Lambda. To request a website rebuild, use GitHub Actions →
**Render dashboard** → **Run workflow** on `main`. Publish source changes to
`main` before expecting a scheduled/manual build to include them.

The cron is a requested cadence, not evidence of hourly completion. GitHub
documents that scheduled jobs can be delayed or dropped under high load,
including at the start of an hour ([schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)).
The [dated release follow-up](aws-deployment-2026-09-22.md#documentation-audit-follow-up)
records the last observed runs. A delayed build can let comparisons expire even
while live readings continue updating successfully.

| Symptom | Check or action |
| --- | --- |
| Context out of date / comparisons paused | Check the last successful workflow and `comparisons.json` generation/expiry. Run the existing manual workflow, or prepare/render again for local review. The page refresh button only refetches existing artifacts. |
| Stale / collection failed / live refresh failed | Inspect `data/latest.json` observation and attempt times, collector CloudWatch summaries, S3 access, and the 15-minute EventBridge rule. A website rebuild does not repair collection. |
| Overview still shows older history | The overview is embedded in HTML. Confirm a fresh site build and reload the page; the independent live feed only refreshes the individual comparisons. |
| Local latest-data request returns 503 | Confirm AWS history read access; the local `--live-s3` endpoint returns `preview_history_read_failed` on a read failure. |
| Origin works but Compare is disabled | All real destinations are still unverified; the public site also has no routing gateway. A key alone cannot bypass eligibility gates. |

For direct website publication from a validated build, retain the exact protection:

```sh
aws s3 sync dashboard/_site/ s3://mem-ed-wait-times-dashboard/ --delete --exclude "data/*" --dryrun
aws s3 sync dashboard/_site/ s3://mem-ed-wait-times-dashboard/ --delete --exclude "data/*"
```

Inspect the dry run first. These commands modify the public website; local preview
requires neither command. Serialize manual publications with other website jobs,
retain rollback assets, and complete the checks below. The GitHub workflow has
no explicit concurrency group, so overlapping runs are an operator concern.

## Release and operator checks

1. Complete the M0 release prerequisites and preserve `data/*` exclusion in
   deployment and rollback commands. Run all checks above.
2. Use the workflow to prepare, render, and sync the site. Check the context
   schema, source range, generation time, support, and HTTP metadata; verify the
   collector latest object's ETag is unchanged by site deployment.
3. On an already-open page, observe a later collection change the current wait,
   difference, percentile, and direction without rebuilding HTML. Check a narrow
   viewport and keyboard selector/table operation. Confirm all 20 overview lines
   and seven days on first load, shared 24-hour/seven-day selection, y-axis
   refitting after time/legend changes, and the legend directly beneath the plot.
   Check Inter/font loading and at least 16 CSS px text, including chart labels
   and table captions. Verify failed refreshes and
   expired artifacts pause comparisons while retained readings keep their ages.
4. Review missing partitions, rejected/duplicate records, baseline slot coverage,
   fallback frequency, and the operator-only request latency table. A missing
   day counts against baseline coverage even when M0's observed-batch coverage
   appears high. Record deployed revision/time and smoke-check evidence in the
   living plan separately from local completion.

An unsuccessful preparation does not refresh generation time. Investigate source
access and validation failures and rerun; do not relabel old context as current.
S3 replaces each object completely, but multi-file website sync is not a
transaction. Deploy compatible versions together; the browser fails closed on
an unsupported context version. A website rollback must keep the protected data
path and compatible schema versions. M1 adds no production alarm or forecast.
