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
Published as [`de91ac3`](https://github.com/jpbranson/mem-ed-wait-times/commit/de91ac3).
[Run 35820272143](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35820272143)
completed successfully at **04:56:51 UTC**, including all **57 Python / 33 JavaScript
tests**, preparation, Quarto, protected sync, and the new public verification step.
That step compared public HTML/comparisons/travel bytes to the actual build output
and passed at 04:56:48 UTC. Both runs in this follow-up were manual dispatches.

An independent check at 04:57:06 UTC accepted the public artifacts and **20/20
current facilities**. Context was generated at 04:56:03 and latest at 04:54:07;
HTML was published at 04:56:48. Its SHA-256 was
`01ae0cf7b74d7c57b4b9d25691a5d9220b7d846f29a35e225e7f10976d34aec6`.
Local evidence: `.cache/production-mitigation.json`. The source/cron mitigation is
published and its manual execution validated; future scheduled cadence is not yet
established. No Lambda code, EventBridge rules, bucket policies or raw schemas changed.

This mitigation is not a delivery guarantee. Continue observing scheduled starts
and context age. The local-midnight expiry still intentionally pauses comparisons
until the first fresh build after midnight; moving the minute does not remove
that gap. If delayed starts persist, select a reliable scheduler separately rather
than lengthening freshness limits to hide stale context.

## Requested redeployment of current main

On the user's request to deploy, commit and push, confirmed `main` was clean and
already synchronized with origin at `1a2b16be755a4fe503d03a4a07803f697c97b9f5`.
Dispatched [run 35820920480](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35820920480)
at 05:04:43 UTC. The run deployed that revision and completed successfully at
05:06:28 UTC. Both test suites, history preparation, Quarto rendering, the S3 sync
with `data/*` excluded, and exact public build/freshness verification passed.

An independent public check at **05:07:19 UTC** passed with **20/20 current
facilities**. Context was generated at 05:05:45, after Chicago midnight; latest
observations were generated at 04:54:07 and remained current. Public HTML was
modified at 05:06:25, with SHA-256
`d47c9ed33d25c52aa215dab1d8c96a805733a96c9d6827c9044459294c2bf88e`.
Local sanitized evidence: `.cache/production-redeploy-20260923.json`.

This was another manual dispatch; scheduled cadence remains unverified. The
follow-up commit records deployment evidence only. Public routing and forecasts
remain gated; no application, Lambda, storage or record contract changed.

## Scheduled delivery observation

Checked the public Actions API at 06:52 and again at 07:11 UTC. The newest
scheduled run was still [run 35805147090](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35805147090)
at **01:09:45 UTC**, built from `00bbef4` under the old `0 * * * *` schedule. No
scheduled run followed the minute-17 publication at about 04:55 UTC: neither the
05:17 nor the 06:17 slot had started by 07:11. The runs after
01:09 UTC are the three manual dispatches recorded above. Earlier scheduled spacing
under the old cron was 2.5–4.6 hours, so this ~6-hour gap is the longest observed.

A read-only public check at 06:52:31 UTC (`.cache/schedule-observation-20260923.json`)
passed with 20/20 current facilities, but the 05:05:45 context was 107 minutes old;
the browser pauses comparisons at two hours (about 07:06 UTC) until another build.
The next deployment in this session refreshes it; that is a manual dispatch, not
scheduled evidence.

Conclusion: GitHub's schedule is not delivering an hourly cadence for this
repository. Minute-17 does not demonstrably help. Choosing a reliable trigger
(for example an AWS EventBridge schedule dispatching the workflow, or building
the site inside AWS) is an open decision that needs the user's approval because
it adds credentials or infrastructure. Freshness limits are unchanged.

## M2/M3 release from a validated local build

On the user's request to deploy, commit and push, committed and pushed
[`fa842c8`](https://github.com/jpbranson/mem-ed-wait-times/commit/fa842c8). A
workflow dispatch was not possible from this session: the GitHub CLI is not
installed and the browser was not signed in to GitHub, and no credentials were
entered. Following the documented direct publication in
[M1 operations](m1-operations.md), the site built from that revision (58 Python /
40 JavaScript tests passed; preparation from read-only S3 at 07:17:34 UTC; Quarto
render) was dry-run and then synced with `--delete --exclude "data/*"` at about
07:21 UTC. No workflow run was active.

The local Windows toolchain produced different Quarto bootstrap assets and line
endings for two JSON assets than the GitHub runner; the old bootstrap stylesheet
was removed by the sync. The next GitHub-hosted build will replace these with the
runner's output. This deployment is not scheduled-delivery evidence.

The updated `scripts/check_public.mjs --expected-site` passed at **07:21:21 UTC**:
public HTML, comparisons, travel and four browser modules matched the build;
context generated 07:17:34 (227 s old); latest generated 07:09:08 by the collector
and preserved; **20/20 current facilities**; recommendations disabled. HTML SHA-256
`6808f8eee87699889ccee231e1972d81a392ac4b687562be1a441986ad8b843c`. Local evidence:
`.cache/release-20260923-m3.json`. Chrome on the public URL showed 20 heatmap rows,
row selection moved the focus chart, comparisons were current, Compare stayed
disabled with "Emergency destinations awaiting verification", and no console errors.
No Lambda, EventBridge, bucket policy, raw/latest/comparison/travel schema changed.

## Campus-fallback release through GitHub Actions

With `gh` now installed and authenticated, dispatched
[run 35833123203](https://github.com/jpbranson/mem-ed-wait-times/actions/runs/35833123203)
at 07:42:26 UTC for [`36d89bf`](https://github.com/jpbranson/mem-ed-wait-times/commit/36d89bf).
It completed successfully at 07:44:01 UTC: 64 Python and 41 JavaScript tests, read-only
preparation, Quarto render, protected sync (`data/*` excluded) and the exact public
build/freshness check (including four browser modules) all passed. The runner's
build replaced the Windows-built assets from the 07:21 direct publication.

An independent check at **07:44:28 UTC** passed (`.cache/release-20260923-campus.json`):
context generated 07:43:24 (64 s old), **20/20 current facilities**, recommendations
disabled, HTML modified 07:43:59 with SHA-256
`1bce3e2011fc58fb2a31db8fdf2e1ea43ea9fbb30a505f23cd1a609ae09acaeb`. Public
`travel.json` reports `arrival: "campus"` for all 20 facilities, 18 adult and 4
child eligible destinations, and the campus recommendation blocker. Public
`/api/routes/status` returns HTTP 403, so the page shows "4 eligible destinations ·
all to campus center, ER entrance unconfirmed · road estimates not available on
this site yet" for children and keeps Compare disabled; no coordinates are sent.
This was a manual dispatch, not scheduled-delivery evidence.

## Later scheduled runs on 2026-09-23

GitHub scheduled runs resumed after the observation above, but not hourly. The
public run list at 00:31 UTC on 2026-09-24 showed successful scheduled runs at
10:02:49, 15:04:05, 19:05:41 and 22:20:28 UTC, gaps of about 5.0, 4.0 and 3.25
hours. The two-hour comparison context therefore expired between most of them.

## Hourly dispatch through EventBridge

The user chose an AWS EventBridge schedule that dispatches the existing workflow
and configured it with the AWS CLI between about 00:16 and 00:30 UTC on 2026-09-24
(evening of September 23 in America/Chicago). All resources are in `us-east-1`:

| Resource | Configuration |
| --- | --- |
| Connection `github-dashboard-dispatch` | API-key authorization sending `Authorization: Bearer <token>`. The token is a fine-grained GitHub personal access token limited to this repository with only Actions read/write; EventBridge keeps it in a Secrets Manager secret it manages. Expiry and rotation are the user's responsibility. |
| API destination `github-dashboard-dispatch` | `POST https://api.github.com/repos/jpbranson/mem-ed-wait-times/actions/workflows/dashboard.yml/dispatches`, at most 1 invocation per second |
| Rule `dashboard_hourly` | Default event bus, `cron(17 * * * ? *)`, enabled |
| Target | Input `{"ref":"main"}`; `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28` headers; up to 3 retries within 900 seconds; no dead-letter queue |
| IAM role `eventbridge-github-dashboard-dispatch` | Trusted by `events.amazonaws.com`; inline policy `invoke-github-dispatch` allows only `events:InvokeApiDestination` on this destination |
| Alarm `dashboard-dispatch-failed` | Sum of the rule's `FailedInvocations` ≥ 1 in an hour notifies SNS topic `dashboard-dispatch-alerts` by email |

A read-only check at 00:31–00:33 UTC found the connection `AUTHORIZED`, the
destination `ACTIVE`, the rule enabled with that target, the alarm `OK`, and the
email subscription still `PendingConfirmation`. The rule had no invocations yet:
the role was created at 00:24:06 UTC, after the 00:17 slot. The first eligible
slot is 01:17 UTC, so **delivery has not yet been observed**. A dispatched run
appears in GitHub Actions with event `workflow_dispatch` ("Manually run"); runs
labeled "Scheduled" still come from GitHub's cron.

The workflow's `schedule:` trigger is retained as a backup until EventBridge has
delivered hourly for about a day; the workflow's concurrency group queues any
duplicate. Remove the cron after that observation. The existing collector
(`trigger_15`) and compaction (`compact_daily`) rules are unchanged. No repository,
Lambda, bucket policy or record/storage contract changed. Expected cost is
negligible (about 720 API-destination invocations per month).
