# Production follow-up — 2026-09-23 UTC

This work began September 22 in America/Chicago. It follows the
[initial deployment](aws-deployment-2026-09-22.md); that dated evidence is retained.

## First GitHub-hosted release build

After explicit user approval, manually dispatched the existing workflow on `main`
at 04:36:26 UTC. [Run 35819014774](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35819014774)
built `b5232f2` and completed successfully at 04:37:58 UTC. Python and JavaScript
tests, read-only history preparation, Quarto rendering and protected S3 sync all
passed. The build preserved the collector-owned `data/*` path.

At 04:44:06 UTC, the new read-only `scripts/check_public.mjs` accepted all three
public data artifacts using the actual browser validators. HTML was modified at
04:37:57; comparisons were generated at 04:37:26; latest observations were generated
at 04:39:08, after publication, with **20/20 current facilities** and no-store
headers. Recommendations remained disabled. The comparison context expires at
05:00 UTC (Chicago midnight), earlier than its ordinary two-hour lifetime.
Local sanitized evidence: `.cache/production-followup.json`.

## Public browser review

Chrome review of the HTTPS production page completed at its desktop viewport and
at 390×844 and 320×740 viewport overrides. The opening chart/legend were adjacent;
hospital isolation changed the count to 1/20; the shared 24-hour control updated
both sections; restoring All and 7 days returned 20/20. Observed text sizes were
at least 16 CSS px with Inter, and both narrow views had no page-width overflow.

The map loaded; Use map center selected the default public map center and updated
the coordinate inputs; Clear removed that selection. Adult selection showed
destinations awaiting verification and kept Compare disabled. The fictional
example retained its label and 92/60/88-minute arithmetic. No actual device
location was requested and no hospital route was sent. Captured browser console
warnings/errors were empty. Temporary viewport overrides were reset afterward.

## Schedule mitigation

The pre-change API check still showed the observed 2.5–4.6-hour spacing between
earlier scheduled builds, with no new scheduled run of the release. A successful
manual build establishes runner/build/deployment functionality, not cron reliability.
[GitHub documents](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
that schedules can be delayed/dropped and advises avoiding the top of the hour.

The user explicitly approved moving the hourly cron to minute 17, serializing
deployments without cancellation, a 30-minute timeout, read-only repository-token
permissions, and a post-publication check of freshness and exact build artifacts.
The `data/*` exclusion and manual trigger remain. No push trigger is added.
Local implementation and validation are in this change; publication and run
evidence will be recorded below after verification.

This mitigation is not a delivery guarantee. Continue observing scheduled starts
and context age. The local-midnight expiry still intentionally pauses comparisons
until the first fresh build after midnight; moving the minute does not remove
that gap. If delayed starts persist, select a reliable scheduler separately rather
than lengthening freshness limits to hide stale context.
