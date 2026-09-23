# M2 readiness follow-up — 2026-09-23 UTC

M2 remains in progress. Local TomTom connectivity is now validated; real hospital
route acceptance and public deployment are not complete. No registry eligibility
or recommendation gate was relaxed.

## Live provider check

The user configured `TOMTOM_API_KEY` in Git-ignored `.env.local`.
`scripts/check_tomtom.py` explicitly reads that key and reserves one request in
the existing persistent `.cache/tomtom-usage.sqlite3` counter. It does not print
or store the key, response geometry, or origin in its output. The review server
still requires an environment variable; it does not automatically load this file.

At **04:41:15 UTC**, one v3 POST between the fixed public downtown Memphis road
points used in prior diagnostics returned HTTP 200: **252 seconds**, **2,047
meters**, and **0 seconds reported traffic delay**, with live traffic requested.
The existing parser accepted the route fields and endpoint-distance checks.
Elapsed request/check time was 0.354 seconds. These points are not hospital
entrances or a user's location. Zero delay does not prove road-level live coverage
or travel-time accuracy. Sanitized evidence is `.cache/tomtom-live-check.json`.

Re-run explicitly with:

```powershell
.venv\Scripts\python.exe scripts/check_tomtom.py
```

The [current pricing page](https://docs.tomtom.com/pricing) lists 20,000 free monthly
Routing requests; the [platform FAQ](https://docs.tomtom.com/platform/documentation/status-and-support/faqs)
says exceeded limits return HTTP 429. Account plan/prepaid-credit settings were
not inspected. Keep the free-plan provider stop and shared app budget; do not
enable prepaid credit or paid fallback. Full account/terms review remains a gate.

## Destination evidence reviewed

| Facility | Current official evidence | Still needed before a real comparison |
| --- | --- | --- |
| Memphis | [Service page](https://www.baptistonline.org/locations/memphis/services) describes a continuously open ER at 6019 Walnut Grove Road | Exact vehicle arrival coordinates/entrance evidence; explicit supported age groups |
| DeSoto | [Service page](https://www.baptistonline.org/locations/desoto/services) describes around-the-clock general emergency care for children, adults and older patients | Exact general-ER arrival coordinates, distinguished from the separate obstetrics ER |
| Crittenden | [Location page](https://www.baptistonline.org/locations/crittenden) describes 24/7 emergency care and the shared outpatient/ER entry vestibule | Exact arrival coordinates tied to that entrance; explicit supported age groups |
| Children's | [Location page](https://www.baptistonline.org/locations/childrens) describes a 24/7 pediatric ER and after-hours access | Exact pediatric-ER arrival coordinates and whole-group age applicability; outpatient ages alone do not establish ER limits |

The reviewed pages did not establish every required destination field. Campus
addresses and map markers are not substituted for verified emergency entrances.
All 20 registry destinations remain excluded. This table records partial research,
not a complete operational/suitability verification.

The [current emergency information](https://www.baptistonline.org/services/emergency)
describes triage and variable waits; the location pages link approximate waits to
that information. They do not establish the current `CV_ED_Wait` averaging window,
update cadence, or zero/sentinel behavior. The 2017 Tipton explanation remains
historical evidence, not a current cross-facility contract. No provider was contacted.

Required provider questions are concrete: what event starts/ends the measured
wait; which patients and averaging window are included; when values update; what
zero/negative/missing values mean; and whether definitions differ by facility.
Destination confirmation must identify the public vehicle arrival point, general
ER versus specialty entrance, supported age range, and date of verification.

## Free public hosting decision

Selected design target: **Cloudflare Workers Free with one SQLite-backed Durable
Object** for shared reservations and rate enforcement. Cloudflare documents
[Free-plan Durable Objects](https://developers.cloudflare.com/changelog/post/2025-04-07-durable-objects-free-tier/)
and [included quotas](https://developers.cloudflare.com/workers/platform/pricing/).
This is a design selection, not a configured account or deployed service.

Use a free `workers.dev` origin serving the static dashboard through the existing
public S3 assets and handling `/api/routes` at the same origin. Retain no-store
latest/route responses. The original S3 URL remains a static dashboard. One shared
object must reserve the full comparison before outbound calls, preserve the
rolling date/count budget across deploys, serialize comparisons, and enforce the
existing rate/deadline limits. Store the key as a Worker secret; never retain
origins, route geometry, or body/header-bearing access/error logs. New location
processing through Cloudflare must be disclosed and its provider privacy handling
reviewed before launch. Do not infer app privacy from disabled app logging alone.

Activation requires account access and confirmed Free-plan settings, an implemented
and load-tested gateway within [Worker limits](https://developers.cloudflare.com/workers/platform/limits/),
destination/metric evidence, provider terms review, representative regional routes,
and the existing uncertainty/failure tests. No Cloudflare resources, billing, DNS,
public routing service, or data contracts were changed in this follow-up.
