# M2 local validation — 2026-09-14

Status: **local prototype validated; M2 acceptance remains incomplete**. The
checks below occurred on 2026-09-14, without production deployment, account
creation, billing configuration, or preferred hospital recommendations.
The static interface was subsequently published with M0/M1 on 2026-09-22;
the routing gateway remains local-only and real destinations remain excluded.
[Release evidence](aws-deployment-2026-09-22.md), [operations and policy](m2-operations.md).

## Origin selection follow-up — 2026-09-14

The user reported that Use my location did not work. The button had shared
Compare's context/destination gate, leaving it disabled for all unverified
facilities. GPS, manual input and the new map now work independently; only route
submission requires eligibility. GPS progress and errors have their own status.

**49 Python and 33 JavaScript tests passed at this checkpoint.** Eight new checks in
[origin.test.mjs](../tests/origin.test.mjs) cover the mounted controls before age
selection/with failed context, successful GPS, permission denial, timeout (including
a browser that never calls back), insecure context, invalid/partial coordinates,
zero coordinates, map/keyboard/manual synchronization, map startup failure, and
Clear/page exit. Late GPS cannot overwrite a newer origin, and late map startup
cannot restore a cleared selection. The mounted integration verifies that only
Compare sends an origin and that selecting another point aborts an in-flight route.
The pinned map style's label checks enforce Inter and a minimum 16 CSS px.

Quarto rendered all five cells and copied the map style/renderer/worker assets.
Chrome loaded actual OpenFreeMap map data in the localhost preview with no key,
browser location permission, or TomTom request. At desktop width 1,703 px, map
clicks and pin dragging changed both input coordinates. Clear removed the pin,
blanked inputs, and left GPS enabled. The dark style was adjusted after visual
review to make roads and labels more legible.

At a 390 px viewport override (375 px document), the 340 px map and controls fit
without horizontal overflow. Visible travel text used Inter with a 16 px minimum;
map label sizes are fixed at 16/18/20 px. Arrow-key panning followed by Use map
center changed the selected longitude, and a map click also worked at this width.
No console errors/warnings were observed during the review. Temporary selections
were cleared and the native viewport restored. All 20 lines and the seven-day
opening chart remain intact. **GPS success/error validation used simulated
positions; the user's actual device location was not read.** Existing source
artifacts were reused; no new historical replay, route validation or deployment.

Provider policy, privacy, bundled sources, and remaining M2 gates are in
[operations](m2-operations.md#origin-map-and-location-controls). Map display is
free and independent of the TomTom allowance; real routing remains gated.

## TomTom follow-up — 2026-09-14

The current adapter uses TomTom Orbis Routing v3, superseding the initial OSRM
prototype below. **49 Python and 25 JavaScript tests passed**. The new
[routing tests](../tests/test_routing.py) use synthetic entrances and mocked
responses shaped to the [official v3 contract](https://docs.tomtom.com/routing-api/documentation/tomtom-orbis-maps/v3/calculate-route).
No TomTom key is configured; **no live TomTom request or traffic accuracy check
was performed**. The earlier OSRM connectivity result does not validate TomTom.

Automated checks cover individual POST requests, header-only key transmission,
common departure time and live traffic mode, endpoint geometry checks, seconds
and meters, nullable/zero delay, and the new [response schema](routes.schema.json).
The total uses TomTom's duration once; delay is informational. Invalid summaries,
partial failures, timeouts, authentication failures and 429 responses fail safely
without provider text or secrets reaching the browser. Old OSRM responses are
rejected. There are no automatic retries or silent provider fallbacks.

Budget tests verify complete-comparison reservations, persistence across Router
instances, atomic concurrent reservations through separate SQLite connections,
rolling-window boundaries and clock rollback, configured limits, and corrupt-file
failure. Only date/count values are stored. HTTP integration covers same-origin
POST, body limits, no-store responses, sanitized setup/quota status codes, no
origin in responses, and no application request logs. Existing M0/M1 tests and
the AWS CLI `data/*` protection dry run also pass.

The free allowance and prepaid-credit stop behavior were checked on TomTom's
[pricing page](https://docs.tomtom.com/pricing) on this date. No account, payment
method, prepaid credit, or public service was created. Usage guards and the
remaining activation work are documented in [M2 operations](m2-operations.md).

Quarto rendered all five cells successfully and the local review server was
restarted with the TomTom adapter. Chrome confirmed the opening seven-day chart
still selects all 20 hospitals, the updated TomTom attribution/privacy/coverage
text is visible, both age groups retain the empty-destination gate, and the
fictional example still shows 92/60/88-minute totals. No real origin was sent.
Desktop (1,703 px) and mobile (390 px override; 375 px document) checks found no
horizontal overflow. Visible travel text used Inter at a minimum 16 CSS px,
including the expanded coverage disclosure. No browser console errors were
observed. The viewport and initial page controls were restored afterward.
The build reused the dated M1/M2 artifacts below; no new historical replay or
production deployment was performed for this adapter change.

## Initial OSRM prototype — historical evidence

The following checks predate the TomTom change on the same day. They describe
the earlier adapter and the shared data/UI prototype, not live TomTom validation.

### Automated and provider checks

- All 42 Python and 23 JavaScript tests passed. The M2 additions are in
  [Python tests](../tests/test_travel.py) and [browser logic tests](../tests/travel.test.mjs).
  Existing M0/M1 checks, including the AWS CLI `data/*` protection dry run, passed.
- Tests cover fractional-minute arithmetic and zero waits; closest by road;
  missing closest waits; partial, malformed, timed-out and failed routes; invalid
  origins and client-supplied destinations; unsupported ages and unknown/expired
  verification; empty eligibility; stale waits/routes/context and future clocks;
  insufficient history and unsupported horizons; and an uncertain benefit.
- Same-origin HTTP integration verifies POST/body bounds, cross-origin rejection,
  no-store responses, no application location logging, and no origin in responses.
  Provider mocks verify a single bounded matrix, rate limiting, road snap limits,
  seconds/meters, no fallback speeds, and sanitized failures. Browser logic tests
  verify that Clear invalidates late responses and that denied/unavailable GPS
  offers manual entry. No actual user location or browser location permission was used.
- One read-only connectivity request to the free public FOSSGIS matrix endpoint
  used two public map points, `(-90.05,35.15)` and `(-90.04,35.14)`. It returned
  `Ok`, 171.9 seconds and 2,058 meters, with 4.54/3.86-meter road snapping.
  These are **not verified hospital entrances**. This establishes connectivity
  and units, not suitability, traffic accuracy, or regional route validation.

### Historical context

The live read-only preparation produced both artifacts at
`2026-09-14T18:11:24.567087+00:00`. `comparisons.json` contained all 20 facilities
and 13,440 historical chart points. Both complete generated artifacts passed
their JSON schemas, and Quarto successfully rendered all five cells.

The M2 reference spans 2026-08-17 00:00 through 2026-09-14 00:00 America/Chicago,
excluding September 14. All 20 facilities had supported summaries at all four
horizons. The [machine-readable evidence](m2-replay-evidence.json) preserves the
artifact hash, exact source dates, policy, support counts and selected results.

90th percentile absolute change in published minutes, rounded here to one decimal:

| Facility | 15 min | 30 min | 60 min | 120 min |
| --- | ---: | ---: | ---: | ---: |
| Memphis | 87.0 | 173.7 | 192.3 | 106.3 |
| Crittenden | 3.6 | 11.0 | 16.0 | 10.0 |
| DeSoto | 5.2 | 6.0 | 15.9 | 36.4 |

Each selected summary uses 28 contributing days; valid pairs range from 2,672 to
2,687. These overlapping, all-hour historical changes are descriptive and are
not calibrated error bounds. Changes need not increase monotonically with the
horizon: a published series can return toward an earlier value. Selecting the
next available horizon does not establish a conservative bound for an intervening
drive time. The provisional movement screen cannot establish clinical benefit or
traffic uncertainty; recommendations remain disabled even when it is passed.

### Browser review

Chrome reviewed the local server at desktop width 1,703 px and 390/320 px viewport
overrides (375/305 px document widths). The page kept all 20 lines and the seven-day
default. The top plot remained immediately adjacent to its legend. M2 controls
and bars reflowed without page overflow; visible M2 text measured at least 16 px
and used Inter. Example bars separately show driving and published wait, with
total, collection age, extra driving and arithmetic differences.

Adult and child selections both showed that emergency destinations await
verification, with GPS/Compare disabled. View example displayed fictional
hospitals A/B/C with 92/60/88-minute sums; B had 13 extra driving minutes and a
32-minute lower arithmetic estimate. Clear emptied manual test coordinates.
The example used no live provider request and did not replace real facility data.
Native viewport settings were restored after the review. The final rendered page
showed the revised provider-transmission disclosure, blank origin inputs and
disabled real routing. No browser console errors were observed.

## Traffic profiles and rush hour — 2026-09-26 UTC

TomTom's v3 `live` mode estimates durations from historical speed profiles plus
current jams and closures; `historical` mode uses the profiles only and always
reports zero `trafficDelayDurationInSeconds`, which counts jams relative to free
flow ([v3 contract](https://docs.tomtom.com/routing-api/documentation/tomtom-orbis-maps/v3/calculate-route)).
Typical rush-hour slowing therefore appears in the duration, not the delay field.
That explains the zero delays on every route in the overnight 2026-09-23 run and
in a Friday-evening gateway check (2026-09-26 00:32 UTC). Neither establishes
live-jam coverage.

`scripts/check_routes.py` gained `--traffic` and `--departure` options, and
`scripts/compare_routes.py` compares saved runs route by route. Three runs used
`--traffic historical` for Monday 2026-09-28 at 03:00, 08:00 and 17:00 Chicago
time: three public city-center origins times 18 adult destinations, 162 requests
reserved in the local ledger. All 162 ended within tolerance (at most 61 m).
Compared with 03:00 on the same 54 routes:

| Departure (CDT) | Extra minutes: median / 90th pct / max | Ratio: median / max | Largest origin effect |
| --- | --- | --- | --- |
| 08:00 | 4.3 / 6.9 / 8.4 | 1.04 / 1.19 | Jackson median +5.0 min |
| 17:00 | 4.5 / 6.2 / 8.1 | 1.03 / 1.21 | Memphis median +5.0 min, ratio up to 1.21 |

The 2026-09-23 overnight live run agreed with the 03:00 profile within about
±5 minutes (median −1.3). TomTom's typical profiles thus add about 3–8 minutes
at weekday peaks on these routes; incidents, weather and heavier jams can add
more, and profiles say nothing about live coverage. Aggregate results:
[m2-traffic-profile-2026-09-26.json](m2-traffic-profile-2026-09-26.json); the
per-route files (no geometry) are in the Git-ignored `.cache/`.

**Still required:** a `live` run during an actual weekday peak (next: Monday
2026-09-28, 12:00–14:00 or 21:00–23:00 UTC), compared with the profile for the
same hour to measure jam delay and reported-delay coverage:

```powershell
.venv\Scripts\python.exe scripts/check_routes.py --output .cache/route-validation-20260928-am.json
.venv\Scripts\python.exe scripts/compare_routes.py .cache/route-profile-20260928T0800-0500.json .cache/route-validation-20260928-am.json
```

## Outstanding evidence and release work

All 20 real registry entries remain travel-ineligible. The pages reviewed on
2026-09-14 remain dated source evidence: the
[Baptist emergency page](https://www.baptistonline.org/services/emergency) supports
the directory and triage guidance but did not establish the API's `CV_ED_Wait`
averaging, refresh or sentinel semantics. The
[DeSoto services page](https://www.baptistonline.org/locations/desoto/services)
describes emergency care across ages; the
[Crittenden location page](https://www.baptistonline.org/locations/crittenden)
describes emergency services and campus access. Neither supplies all the
verified entrance, age, operational and metric evidence needed by this prototype.
Coarse campus geotags and older campus maps were not promoted into ED destinations.

Configure a free TomTom key locally and validate actual v3 responses. Complete
destination/metric verification and representative route/threshold
evaluation, then select a free public gateway with aggregate provider limits and
review the full provider terms. Static S3 hosting cannot serve the local POST
endpoint. These remain M2 work; test fixtures and one connectivity check do not
satisfy them. No forecast or measured patient time-savings claim has been made.
