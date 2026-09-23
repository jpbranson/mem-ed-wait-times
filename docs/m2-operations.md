# M2 travel comparison: local operation and release gates

Updated 2026-09-23 UTC. M2 is implemented as a prototype and remains **in
progress**. The user supplied a local API key and one live v3 contract probe passed;
account/billing settings have not been audited and no production routing service
is configured. M0/M1 and M2's static interface were deployed on 2026-09-22;
the public routing endpoint remains unavailable and recommendations remain disabled.
Since 2026-09-23, 18 adult and 4 child destinations are eligible using labeled
campus centers (ER entrance unconfirmed); 54/54 live validation routes passed. See the [release record](aws-deployment-2026-09-22.md).
The [readiness follow-up](m2-readiness-2026-09-23.md) records the live check,
partial destination evidence, and selected free hosting design.

## TomTom provider and free usage

The user selected TomTom after reviewing traffic-aware providers and requires
the project to remain free. The adapter replaces the initial OSRM prototype with
TomTom Orbis Routing API v3. It sends individual route requests using
`POST https://api.tomtom.com/maps/orbis/routing/routes/calculate`, with the API key
in `TomTom-Api-Key`, version `3` in `TomTom-Api-Version`, and origin/destination
GeoJSON coordinates in the body. `Attributes: routes.summary,routes.legs.path`
requests timing and the geometry needed to check endpoints. It requests a fast
car route with `traffic: live` and a common departure time for the comparison.
Live traffic, where available, and historical traffic inform the estimate; this
does not establish live coverage on every segment. [Official v3 contract](https://docs.tomtom.com/routing-api/documentation/tomtom-orbis-maps/v3/calculate-route).

Pricing checked **2026-09-14**: standard Routing includes **20,000 requests per
month**, then **$1 per 1,000**. The free plan requires no card and stops at its
allowance unless prepaid credit has been added. Keep the account free, without
prepaid credit or automatic top-ups. This adapter does **not** use the separately
priced Matrix API. Recheck account terms before activation; no account, key, or
credit was configured during implementation. [TomTom pricing and FAQ](https://docs.tomtom.com/pricing).

Each explicit Compare action reserves one request per eligible destination, up
to 20 (1,000 full 20-destination comparisons per 20,000 requests). The local
SQLite counter at `.cache/tomtom-usage.sqlite3` atomically reserves the complete
comparison before sending requests and persists only UTC dates and counts.
It includes the preceding 31 dates plus today, conservatively covering a monthly
billing window. Failed and skipped requests are not refunded. Restarting the
server or changing the key does not reset usage. Missing configuration, an empty
candidate set, or invalid input spends no requests.

`TOMTOM_REQUEST_BUDGET` optionally lowers the default 20,000-request limit; only
integers from 1 through 20,000 are accepted. Exhaustion pauses estimates; unreadable
or corrupt counters fail closed. **Preserve this file**: deleting it resets local
accounting. The counter cannot see other applications' account usage or separate
ledgers, so it is an additional guard, not an account-wide billing guarantee.
Use a dedicated free account/project and retain the provider's free-plan stop.

One server accepts one comparison at a time, starts at most four provider calls
per second with four workers, and never automatically retries or refreshes routes.
New calls and accepted results stop after a 15-second comparison deadline;
individual connect/read timeouts are at most 2/5 seconds and the browser gives up
after 20 seconds. Authentication and provider-limit errors stop the comparison
and impose a 60-second cooldown. Failed or partial routes never become
straight-line estimates. Route endpoints must be within 250 meters of the origin
and 150 meters of a reviewed entrance or 300 meters of a campus center; geometry
is then discarded.

The static S3 website cannot run this gateway. Cloudflare Workers Free with one
SQLite Durable Object is the selected design target; no account or gateway has
been configured. Before public activation, implement durable shared accounting,
review the full provider license/privacy terms, and validate real routes. Do not
deploy independent public proxies with separate budgets or enable paid fallback.

## Preparation and local review

Use the [environment setup and build commands](m1-operations.md#environment-setup)
in M1 operations. The existing
`python -m edwait.prepare` command now reads history once and writes both ignored
`dashboard/comparisons.json` and `dashboard/travel.json`. Each file is replaced
atomically; there is no cross-file transaction. M1 and M2 validate and expire
their contexts independently. Quarto copies both artifacts and `travel.mjs`.

```powershell
# Build first using M1 operations. A key is optional for charts/map/example review.
.venv\Scripts\python.exe -m edwait.serve --live-s3
```

For local routing validation after verified destinations and a free-plan account
are available, stop the server and restart it with the key in its environment:

```powershell
# Enter the key locally; do not put it in source, command arguments, or chat.
$tomtomSecret = Read-Host 'TomTom API key' -AsSecureString
$env:TOMTOM_API_KEY = [System.Net.NetworkCredential]::new('', $tomtomSecret).Password
.venv\Scripts\python.exe -m edwait.serve --live-s3
```

Visit `http://127.0.0.1:8765/`. The checked-in review server binds only to loopback.
`--live-s3` reconstructs successful observations from the newest stored batch
using existing AWS read access. It does not consume deployed failure metadata or
retain earlier successes from other batches; this remains true after M0 rollout.
Omit the flag to serve local files only. See [local-preview behavior](m1-operations.md#local-preview)
for missing-data behavior and when to rebuild history.
The server is a local development tool, not a production server.
The server reads `TOMTOM_API_KEY` at startup; restart it after changing the key.
`.env` and `.env.local` are ignored by Git but are **not automatically loaded**.
The standalone `python scripts/check_tomtom.py` diagnostic explicitly loads
`.env.local` for one budgeted nonclinical API probe; it does not configure the server.
Without a key, the charts and fictional example still work; eligible route
requests return `routing_not_configured` without contacting TomTom. For a local
review with the key from `.env.local`, set `TOMTOM_API_KEY` in the server's
environment first. `python scripts/check_routes.py` explicitly loads `.env.local`
and sends 54 budgeted requests from three fixed public city centers to every adult
destination, recording timing, distance and endpoint offsets without geometry.

For an explicitly dated replay, set both output paths so live preview artifacts
are not overwritten:

```powershell
.venv\Scripts\python.exe -m edwait.prepare --snapshot .cache/m1-history.json --now 2026-09-14T00:00:00Z --output build/replay-comparisons.json --travel-output build/replay-travel.json
```

The page still opens with all 20 hospital lines and the seven-day window. Below
the M1 comparison, Drive + wait supports a clickable map, opt-in geolocation,
manual coordinates, adult/child selection, Compare, Clear, and an illustrative
example. Origin selection works before choosing an age and independently of
travel context, destination verification, or a TomTom key. GPS only runs after
clicking Use my location; Compare is a separate route transmission action. The
example contains fictional hospitals and fixed numbers, makes no route request,
and never overrides the real registry or live data.

## Origin map and location controls

The 2026-09-14 location fix separates GPS from the eligibility check that had
disabled it whenever no verified destinations were available. While finding a
location, the button shows progress and prevents duplicate clicks. Permission
denial, unavailable positioning, timeout, and insecure HTTP have distinct messages.
Geolocation requires browser permission and HTTPS or localhost. The browser has a
10-second request timeout, with a 12-second application deadline if it never calls
back. GPS error messages preserve map/manual entry as alternatives.

For the published site, use the [HTTPS dashboard URL](https://mem-ed-wait-times-dashboard.s3.us-east-1.amazonaws.com/index.html).
The HTTP S3 website endpoint is not a secure context for browser geolocation.
Serving over HTTPS permits the browser permission flow; actual device-location
behavior on the public site has not been newly validated. It does not enable
real routing or bypass destination verification.

Click or tap the map to place a pin; drag the pin to refine it. Coordinates and
the pin stay synchronized. GPS and completed manual edits center the map on the
selection. Keyboard users can pan with arrow keys, zoom with plus/minus, then
choose Use map center. Map panning alone does not change the selected origin.
Clear and page exit remove the pin, blank the inputs, reset the view to Memphis,
and invalidate late location/route callbacks. Origin edits cancel an in-flight
route comparison; a late GPS response cannot overwrite a newer map/manual choice.
Compare still requires an origin, age, valid context, verified destinations, and a
routing gateway that answers `GET /api/routes/status` with `available: true`.

Map display uses locally bundled **MapLibre GL JS 6.9.1** and a local adaptation
of **OpenFreeMap's Dark style**. Map code loads when its section nears the viewport,
so the opening all-hospital chart comes first. Font rendering uses the bundled
Inter font, with every map label at least 16 CSS px. The map has a 420 px desktop
height and 340 px mobile height, 44 px zoom controls, attribution, and an explicit
fallback when map initialization fails. It requires WebGL; GPS/manual selection
remain usable if rendering is unavailable. [MapLibre documentation](https://maplibre.org/maplibre-gl-js/docs/),
[bundled sources and notices](../dashboard/vendor/maplibre/NOTICE.txt).

OpenFreeMap's public map service was checked on **2026-09-14**: no account, API
key, paid tier, or map-view/request limit is needed. Its service is provided
without an availability guarantee. Map viewing uses no TomTom routing allowance.
Tiles and sprites are fetched directly from OpenFreeMap; the requested map area
and normal connection metadata reach that provider, including when the map moves
to a GPS origin. The selected point itself is not sent as a coordinate request
to OpenFreeMap, and no reverse geocoder is used. Ordinary browser tile caching
may occur; the app does not store the selected point or put it in the page URL.
The visible disclosure distinguishes map-area sharing from Compare's TomTom
transmission. [Service and attribution](https://openfreemap.org/),
[privacy](https://openfreemap.org/privacy/), [terms](https://openfreemap.org/tos/).

## Destination and privacy contracts

Since 2026-09-23 the registry records official status, service and age evidence
for each facility in `destination_evidence` (source URL, address, OpenStreetMap
campus reference, entrance search result and notes). By user decision the same day,
18 adult and 4 child destinations are eligible using labeled campus centers; Leake
stays excluded. [Evidence](m2-destinations-2026-09-23.md). A destination requires
reviewed evidence in [the registry](../edwait/facilities.json):

- `active_status: "active"` and `service_applicability: ["general_emergency"]`.
- `age_applicability` containing `"adult"` (18+) and/or `"child"` (under 18), only
  when that entire displayed age group is supported by current evidence.
- `travel_verified_on` as a nonfuture local ISO date at most 90 days old. This
  provisional recheck interval does not establish real-time operational status.
- An arrival point, chosen by `edwait.travel.arrival()`:
  - `emergency_entrance`, when present, always wins. It needs numeric
    `latitude`/`longitude`, a descriptive `label`, an HTTPS `source_url`, `method`
    (`official_source`, `imagery_review` or `site_visit`), a nonfuture `reviewed_on`
    date, and must lie within 1,000 m of the campus center. A defective entrance
    blocks the destination ("Emergency entrance evidence incomplete" or "too far
    from campus"); it never silently falls back.
  - Otherwise `campus_point`: an OpenStreetMap hospital-element center with HTTPS
    source and the label "Hospital campus center · ER entrance unconfirmed". The
    page labels these destinations everywhere and `travel.json` reports
    `arrival: "campus"` plus a recommendation blocker.

Route ends must land within 150 m of an entrance or 300 m of a campus center, or the
route is reported unavailable. `coordinates` remains unused. Keep unverified values
null; do not copy synthetic test metadata into the registry. These fields describe
general service applicability, not individual clinical suitability or diversion.

### Adding imagery-reviewed entrances

```powershell
.venv\Scripts\python.exe -m edwait.entrances list            # arrival kind + OSM/aerial links
.venv\Scripts\python.exe -m edwait.entrances geojson review.geojson
.venv\Scripts\python.exe -m edwait.entrances set memphis --lat 35.12901 --lon -89.86185 `
  --label "ER entrance canopy, Walnut Grove Rd side" `
  --source-url "https://www.openstreetmap.org/?mlat=35.12901&mlon=-89.86185#map=19/35.12901/-89.86185" `
  --method imagery_review --note "Canopy and ER signage visible" --dry-run
.venv\Scripts\python.exe -m edwait.entrances clear memphis    # back to the campus fallback
```

(The Memphis values above are placeholders, not a reviewed entrance.) Place the
point where a vehicle stops for the general ER, not an ambulance-only bay or a
separate obstetric/pediatric unit, and describe the evidence in `--label`/`--note`.
`set` validates with the same rule as eligibility before writing. After editing,
run the tests, `python -m edwait.prepare`, render, and optionally
`scripts/check_routes.py` (54 budgeted requests) to confirm road snapping. Commit
the registry change with the dated evidence.

Before enabling Compare, the page sends `GET /api/routes/status` (no origin or
body). The local server answers `{"schema_version": 1, "available": <key configured>}`
with `no-store`; static S3 returns an error, so the public page keeps Compare
disabled and never posts coordinates there. A future public gateway must answer
the same probe. The probe runs alongside the travel-context fetch and never delays it.

The local route endpoint accepts only `POST /api/routes`, with JSON keys `latitude`,
`longitude`, and `age_group`; it selects destinations from the trusted registry.
Requests must be same-origin, at most 512 bytes, with finite coordinates in range.
Client-supplied destinations are rejected. No CORS permission is granted.

The app's [response schema](routes.schema.json) requires `schema_version: 2`,
`provider: tomtom`, `traffic_mode: live`, `generated_at`, `ttl_seconds: 300`,
`age_group`, and `routes`. This app schema version is distinct from TomTom's
upstream API version 3. `generated_at` is the comparison request's start time,
not a provider traffic-observation timestamp. Routes expire five minutes from
that time. Each route has `slug`, `status: ok|unavailable`, `seconds`, `meters`,
and nullable `traffic_delay_seconds`; all three quantities are null when
unavailable. TomTom v3's `travelDurationInSeconds` already includes traffic delay.
The separately reported delay is informational and is **never added again**.
Zero delay and unknown delay remain distinct; neither proves live road coverage.
Errors contain a bounded code only. Origins, keys, geometry, and provider response
bodies/URLs are never returned. Old OSRM response contracts are rejected.

Selected origins stay in transient browser/request memory: no app cookies,
local/session storage, history URL, S3 object, analytics event, or application
request log. Map-area requests and browser tile caching are described above.
Clear, origin/age changes, and page exit invalidate pending routes and old results;
Clear and page exit also clear input coordinates and the map pin. Late geolocation and routing
callbacks cannot restore a cleared origin. Coordinates are sent to TomTom only
after Compare; provider handling is governed by [TomTom's privacy policy](https://www.tomtom.com/en_gb/privacy/).
This app cannot promise deletion from provider systems. A public gateway must
also exclude location/key-bearing access, error, and trace logs. The local usage
counter contains neither locations nor keys and is outside the served directory.

## Comparison and uncertainty policy

Only current M0 readings are summed. Zero stays zero; negative published values
remain visible in M0/M1 but cannot become travel/wait estimates. Closest means
the lowest road duration among verified candidates. A missing closest wait does
not substitute another hospital as closest. Any unknown route withholds closest
and all differences because the missing route could be shortest.

For each available row: total = drive + published wait; extra drive = drive minus
closest drive; difference = closest total minus row total. Positive differences
mean a lower arithmetic estimate, not measured patient time savings. Values are
sorted by drive time, with no preferred marker.

The [travel artifact](travel.schema.json) summarizes absolute published-wait
changes at 15/30/60/120-minute horizons across 28 prior complete local days. It
uses M1's validated latest-per-15-minute-slot records, excludes negative readings,
requires both endpoint days to have at least 75% slot coverage, and rejects
intermediate gaps over 20 minutes or horizon mismatch over 7.5 minutes. Support
requires 64 pairs and eight contributing origin days. Pairs overlap; they are not
independent observations. Zero values are preserved. The artifact expires after
two hours or a failed context refresh.

For a drive within 120 minutes, use the next available horizon at or above the
drive duration. Its 90th percentile absolute change is descriptive; it is neither
an arrival-time forecast nor a calibrated bound for that drive. The provisional
movement screen is strictly greater than 10 minutes plus the changes for both
the candidate and closest hospital. Missing support prevents passing the screen.
Even a passing result **cannot enable a recommendation**: metric semantics and
traffic uncertainty remain unverified. Code and schema enforce
`recommendations_enabled: false`. M5 now has an [offline development study](m5-validation.md);
it does not change this policy or provide arrival-time forecasts.

## Remaining M2 acceptance work

Local key configuration and one actual v3 response check are complete. Verify
account free-plan settings, emergency arrival points and applicability, confirm the
current wait API's clinical/averaging/update/zero-value contract, evaluate representative real routes
and threshold sensitivity, and settle a free public gateway's operational terms.
Then review the interpretation and presentation before enabling public use.
The local prototype and synthetic tests do not satisfy those evidence gates.
See [dated validation](m2-validation.md) and the [living plan](development-plan.md).
