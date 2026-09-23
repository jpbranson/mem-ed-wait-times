# M1 preparation and rollout

Implemented and locally validated 2026-09-14; **not deployed**. M1 uses M0's
collector/latest contract without changing Lambda behavior. Follow the
[M0 rollout](m0-operations.md) for the shared package, IAM, environment, and
collector-owned data path before verifying the complete public feature.

## Build and validate

From the repository root, with the Python environment activated, dependencies
from `requirements-dev.txt`, Node 22+, Quarto, and read-only history credentials:

```sh
python -m unittest discover -s tests -v
node --test tests/*.test.mjs
python -m edwait.prepare
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

For a reproducible dated replay, without publishing:

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

## Artifact ownership and caching

| Object | Owner | Update / consumer behavior |
| --- | --- | --- |
| `data/latest.json` | Collector | M0 complete replacements; no-store; browser polls every 60 seconds |
| `comparisons.json` | Website build | Hourly complete replacement, beside `index.html`; browser revalidates every five minutes |
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
comes first. This can briefly pause comparisons at midnight until the next build
arrives; no prior-day model is relabeled as today's. A fresh reference never makes
a stale observation current. The browser may append newly fetched observations
to history in memory, capped at one per 15-minute slot; raw/latest contracts stay
unchanged. Direction becomes unavailable if the recent reference is too sparse.

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
