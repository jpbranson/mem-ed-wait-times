# Flight log: next-steps run (2026-09-26 UTC)

Working record for the next steps listed at 2026-09-26 00:00 UTC from the
[development plan](development-plan.md), worked one by one at the user's request.
It records what was done, what is blocked, and where to resume after an
interruption. The development plan remains the authoritative status document.

Branch: `next-steps-2026-09-26`, from `main` at `eb4e7fb`. Nothing on this branch
is pushed or deployed unless an entry below says so.

## Resume here

Next action: step 1 — re-check the SNS subscription, then continue down the table.

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
| 1 | Confirm the `dashboard-dispatch-alerts` SNS email subscription | Human | Blocked (human) | Original link (sent 2026-09-24 00:24:56 UTC) expired after two days. Fresh confirmation requested 2026-09-26 00:07:18 UTC, valid until about 2026-09-28 00:07 UTC. Still one subscription, `PendingConfirmation` |
| 2 | Remove the backup GitHub `schedule:` trigger | Claude, after step 1 | Blocked on step 1 | Observation gate met: 47/47 hourly dispatches succeeded, 2026-09-24 01:17 to 2026-09-25 23:17 UTC. Re-check the subscription between steps; do this as soon as it is confirmed |
| 3a | Review ER entrances from imagery | Human | Blocked (human) | Tooling checked: `python -m edwait.entrances list` prints aerial links for all 20 (all still `campus`); review file `.cache/entrance-review-20260926.geojson` (Git-ignored) |
| 3b | Verify Leake's active emergency status | Human; Claude researched | Blocked (human decision) | Official pages unchanged (Level IV ER, live wait shown, no 24/7 wording, absent from the emergency list). CMS lists CCN 251315 as a critical access hospital with emergency services; 42 CFR 485.618(a) requires 24-hour availability. Registry unchanged |
| 3c | Cloudflare account and terms for the gateway | Human | Blocked (human) | Claude cannot create accounts or accept terms |
| 4 | Establish what `CV_ED_Wait` measures | Human or Baptist; Claude drafted the inquiry | Blocked (human) | Draft in [m2-metric-inquiry-2026-09-26.md](m2-metric-inquiry-2026-09-26.md), not sent. API response has no timestamp or caching headers |
| 5 | Build the Cloudflare routing gateway locally | Claude | Not started | |
| 6 | Test routes at rush hour | Claude; weekday peak only | Not started | |
| 7 | Draft the meaningful-difference (benefit) rule | Claude | Not started | |
| 8 | M4 historical-alternatives replay | Blocked on M2 | Not started | |
| 9 | M3 map view and replay controls | Claude | Not started | |
| 10 | 2026-10-15 checkpoint: M3 rerun, M5 holdout decision and new study, M4 re-test | Time-gated | Not started | |

## Human review queue

1. **Confirm the alarm email.** Open "AWS Notification - Subscription Confirmation"
   (sent 2026-09-26 00:07 UTC) and click the link before about 2026-09-28 00:07 UTC.
   Until then the `dashboard-dispatch-failed` alarm reaches no one, and step 2 waits.
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
   its terms; the gateway (step 5) cannot deploy without it.
5. **Send the metric inquiry (step 4).** Review and send the draft in
   `docs/m2-metric-inquiry-2026-09-26.md`, or tell Claude to change it.

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
  Step 2 is blocked on step 1.
- 2026-09-26 00:12 UTC — Steps 3–4. Entrance tooling runs; review GeoJSON exported.
  Leake: re-fetched official location, services and emergency-list pages (no 24/7
  wording; not listed); CMS Provider Data query (dataset `xubh-q36u`) and 42 CFR
  485.618 (via Cornell LII; eCFR blocked automated access) recorded as supporting
  evidence; registry not changed pending the user's decision. One read-only API
  request showed no timestamp or cache headers. Drafted the metric inquiry; the
  site's 911 and triage wording it cites was confirmed in `dashboard/index.qmd`.
