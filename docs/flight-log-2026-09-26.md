# Flight log: next-steps run (2026-09-26 UTC)

Working record for the next steps listed at 2026-09-26 00:00 UTC from the
[development plan](development-plan.md), worked one by one at the user's request.
It records what was done, what is blocked, and where to resume after an
interruption. The development plan remains the authoritative status document.

Branch: `next-steps-2026-09-26`, from `main` at `eb4e7fb`. Nothing on this branch
is pushed or deployed unless an entry below says so.

## Resume here

Next action: step 7 (draft the benefit rule); re-check the SNS topic between steps.

## Rules for this run

- A step is **Done** only when its stated outcome exists and was verified.
  Prepared, local-only, and partial work are recorded as such.
- A step that needs a human decision or action is **Blocked (human)** and goes in
  the review queue; work continues with the next step where possible.
- Pushing to `main` publishes the site within the hour (the EventBridge dispatch
  builds `main`), so product changes stay on this branch until the user approves.

## Steps

| # | Step | Owner | Status | Evidence and notes |
| --- | --- | --- | --- | --- |
| 1 | Confirm the `dashboard-dispatch-alerts` SNS email subscription | Human | Blocked (human) | Subscription (created 2026-09-24 00:24:56 UTC) never confirmed. A re-send at 2026-09-26 00:07 UTC did not extend it; by 00:37 UTC the topic had **no subscriptions** (0 confirmed, 0 pending). Restoring it failed safely: CloudTrail redacts the address. The user must re-create and confirm it |
| 2 | Remove the backup GitHub `schedule:` trigger | Claude, after step 1 | Blocked on step 1 | Observation gate met: 47/47 hourly dispatches succeeded, 2026-09-24 01:17 to 2026-09-25 23:17 UTC. Re-check the topic between steps; do this once a subscription is confirmed |
| 3a | Review ER entrances from imagery | Human | Blocked (human) | Tooling checked: `python -m edwait.entrances list` prints aerial links for all 20 (all still `campus`); review file `.cache/entrance-review-20260926.geojson` (Git-ignored) |
| 3b | Verify Leake's active emergency status | Human; Claude researched | Blocked (human decision) | Official pages unchanged (Level IV ER, live wait shown, no 24/7 wording, absent from the emergency list). CMS lists CCN 251315 as a critical access hospital with emergency services; 42 CFR 485.618(a) requires 24-hour availability. Registry unchanged |
| 3c | Cloudflare account and terms for the gateway | Human | Blocked (human) | Claude cannot create accounts or accept terms |
| 4 | Establish what `CV_ED_Wait` measures | Human or Baptist; Claude drafted the inquiry | Blocked (human) | Draft in [m2-metric-inquiry-2026-09-26.md](m2-metric-inquiry-2026-09-26.md), not sent. API response has no timestamp or caching headers |
| 5 | Build the Cloudflare routing gateway locally | Claude | Done (local only; not deployed) | `gateway/` Worker + SQLite Durable Object; 14 unit tests; 11/11 workerd checks with a mock provider; browser Compare through the served page (18 rows, no console errors); one live comparison 18/18 in 4.6 s. Docs: m2-operations "Cloudflare gateway", s3-buckets, README, plan. Deployment needs step 3c |
| 6 | Test routes at rush hour | Claude; weekday peak only | Partial; live run blocked (time) | Profile evidence done: 162 historical-mode requests for Monday 03:00/08:00/17:00 CDT, all within tolerance; peaks add median ~4.4 min, max 8.4 min ([m2-validation](m2-validation.md#traffic-profiles-and-rush-hour--2026-09-26-utc)). The live weekday-peak run needs Monday 2026-09-28, 12:00–14:00 or 21:00–23:00 UTC |
| 7 | Draft the meaningful-difference (benefit) rule | Claude | Not started | |
| 8 | M4 historical-alternatives replay | Blocked on M2 | Not started | |
| 9 | M3 map view and replay controls | Claude | Not started | |
| 10 | 2026-10-15 checkpoint: M3 rerun, M5 holdout decision and new study, M4 re-test | Time-gated | Not started | |

## Human review queue

1. **Re-create and confirm the alarm email.** The topic has no subscribers, so the
   `dashboard-dispatch-failed` alarm reaches no one. Any "Subscription Confirmation"
   email already received is for the lapsed subscription and will likely fail. In the
   SNS console (us-east-1) open topic `dashboard-dispatch-alerts` → Create subscription
   → Email → your address, then click the new link within two days. CLI equivalent:
   `aws sns subscribe --topic-arn arn:aws:sns:us-east-1:666037347522:dashboard-dispatch-alerts --protocol email --notification-endpoint <address>`.
   Step 2 waits for this.
2. **Review ER entrances (step 3a).** Run `.venv\Scripts\python.exe -m edwait.entrances list`
   for aerial links (or open `.cache/entrance-review-20260926.geojson`). For each
   entrance you confirm: `python -m edwait.entrances set SLUG --lat .. --lon ..
   --label ".." --source-url <https imagery link> --method imagery_review`.
3. **Decide Leake's status (step 3b).** Either accept the federal evidence (CMS: critical
   access hospital with emergency services; 42 CFR 485.618(a): emergency services
   "available on a 24-hours a day basis") as meeting the 24/7 rule, or phone Baptist
   Leake (601-267-1100). Note that CAH rules allow an on-call practitioner to arrive
   within 30 minutes, which may affect how its wait compares. On approval Claude sets
   `active_status` and records the evidence.
4. **Cloudflare account (step 3c).** Create or choose a Free-plan account and review
   its terms; the gateway (step 5, done locally) cannot deploy without it. Steps:
   `docs/m2-operations.md#cloudflare-gateway` ("Deployment").
5. **Send the metric inquiry (step 4).** Review and send the draft in
   `docs/m2-metric-inquiry-2026-09-26.md`, or tell Claude to change it.
6. **Live rush-hour run (step 6).** On Monday 2026-09-28 between 12:00 and 14:00 UTC
   (7–9 AM Chicago), run the two commands in
   [m2-validation](m2-validation.md#traffic-profiles-and-rush-hour--2026-09-26-utc)
   (54 requests), or ask Claude to then. Claude can also set up a one-off scheduled
   task for it if you approve that.
7. **Security observation (not a step).** CloudTrail records this machine's AWS CLI
   calls as the root user. AWS recommends against root access keys; consider an IAM
   user or role with only the permissions these scripts need, then removing the root keys.

## Log

- 2026-09-26 00:05 UTC — Run started on branch `next-steps-2026-09-26`. Read the
  full development plan. Workflow history: all 47 EventBridge `workflow_dispatch`
  runs from 2026-09-24 01:17 through 2026-09-25 23:17 UTC succeeded; the backup
  cron ran 5 times a day, 3–6 hours apart. Alarm `dashboard-dispatch-failed` is
  `OK`; its only subscription (email) is `PendingConfirmation`.
- 2026-09-26 00:07 UTC — Step 1. CloudTrail shows the `Subscribe` call at
  2026-09-24 00:24:56 UTC and no `ConfirmSubscription`. AWS documents confirmation
  tokens as valid for two days, so the original link was about to expire. Re-issued
  `Subscribe` for the same topic and existing email endpoint (returns
  `pending confirmation`; no duplicate subscription). Blocked on the user's click.
  Step 2 is blocked on step 1. (Superseded at 00:37 UTC: the re-send did not keep
  the subscription alive; see below.)
- 2026-09-26 00:12 UTC — Steps 3–4. Entrance tooling runs; review GeoJSON exported.
  Leake: re-fetched official location, services and emergency-list pages (no 24/7
  wording; not listed); CMS Provider Data query (dataset `xubh-q36u`) and 42 CFR
  485.618 (via Cornell LII; eCFR blocked automated access) recorded as supporting
  evidence; registry not changed pending the user's decision. One read-only API
  request showed no timestamp or cache headers. Drafted the metric inquiry; the
  site's 911 and triage wording it cites was confirmed in `dashboard/index.qmd`.
- 2026-09-26 00:30 UTC — Step 5 checkpoint. Design: the Worker proxies the S3 site
  (same origin for page and API) and reads destinations from the published
  `travel.json`, which now carries each facility's `arrival_point` (additive), so the
  page and gateway always compare the same set and registry changes need no Worker
  redeploy. TomTom calls, the usage ledger and the cooldown live in one SQLite
  Durable Object (30 s CPU per call on Free) rather than the 10 ms Worker. Fixed a
  limiter flaw found by tests (timers can fire early; grants are now serialized and
  anchored to the clock). Installed pinned wrangler 4.141.0 in `gateway/` (Git-ignored
  `node_modules`); dry-run bundle 16.75 KiB. Local prepare/render from read-only S3
  history, then 11/11 workerd checks passed: pass-through and cache headers, status,
  18 adult / 4 child sets equal to the page's, provider starts ≥250.1 ms apart,
  serialization, ledger exhaustion and persistence across restart, 15.1 s deadline,
  cooldown persistence, unconfigured state. Full suites: 84 Python, 60 JS passed.
- 2026-09-26 00:45 UTC — Step 5 done (local). Browser: the page served through the
  mock-backed gateway enabled Compare and returned 18 labeled rows (DOM click; the
  pane was not drawing, so coordinate clicks failed), no console errors. Live: reserved
  18 requests in `.cache/tomtom-usage.sqlite3`, then one comparison from downtown
  Memphis through workerd returned 18/18 routes in 4.6 s at 00:32 UTC (drive
  9.8–219.2 min, no reported delay on a Friday evening); TomTom accepted the Worker's
  `Z` timestamps. Page privacy line now names the Cloudflare gateway. Plan, M2
  operations (gateway section with the owner's deployment steps), S3 reference,
  README and a Leake addendum in m2-destinations updated.
- 2026-09-26 00:38 UTC — Step 1 correction. The topic now lists no subscriptions
  (attributes: 0 confirmed, 0 pending). CloudTrail shows only the two `Subscribe`
  calls (2026-09-24 00:24:56 and my 2026-09-26 00:07:18) and no confirm or
  unsubscribe, so SNS removed the unconfirmed subscription about two days after
  creation; re-sending did not extend it. Tried to restore the original subscription
  from CloudTrail's `Subscribe` parameters: SNS rejected the value (`InvalidParameter`)
  because CloudTrail stores the endpoint redacted (8-character placeholder). Nothing
  was created. Not guessing the address; queued for the user. Observation for the
  user: this machine's AWS CLI calls appear in CloudTrail as the **root** identity.
- 2026-09-26 00:45 UTC — Step 6. TomTom docs: `live` = historical profiles plus
  current jams; the delay field counts jams only (zero in `historical` mode), which
  explains all-zero delays so far. Added `--traffic`/`--departure` to
  `scripts/check_routes.py` and `scripts/compare_routes.py`. Ran historical profiles
  for Monday 03:00/08:00/17:00 CDT (162 requests, reserved in the local ledger, all
  within tolerance). Peak vs 03:00: 08:00 median +4.3 min (max +8.4, ratio ≤1.19);
  17:00 median +4.5 (max +8.1, ratio ≤1.21). Summary committed as
  `docs/m2-traffic-profile-2026-09-26.json`. Live peak run is time-gated to Monday.
