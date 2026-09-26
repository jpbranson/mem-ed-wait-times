# M2 destination evidence — 2026-09-23 UTC

M2 remains in progress. This record documents the destination research that the
registry's travel gates require, and the user's later decision the same day to
route to labeled campus centers until emergency entrances are reviewed. No
recommendation gate was relaxed and no public routing service exists.

## Method

For each of the 20 registry facilities, official Baptist pages were fetched on
2026-09-23 and quoted for three attributes:

- **Active status**: current official text stating a 24/7 (or always-open)
  emergency department.
- **Service**: a general emergency department, distinguished from separate
  obstetric/maternity emergency units and noting freestanding or pediatric-only ERs.
- **Age groups**: `adult` from a general community ER description; `child` only
  where official text says the ER treats children, pediatric patients or all ages.
  Staff pediatric credentials, hospital-wide pediatric services or outpatient age
  ranges were not treated as ER age applicability.

Emergency entrances were searched in official location/services text and in
OpenStreetMap through the Overpass API (data as of 2026-09-22T08:45Z), using
small bounding boxes around each campus for `entrance=*`, `emergency=*`,
ambulance and "Emergency"-named features. Campus polygons/POIs were recorded as
references only. Research was performed by delegated agents; seven key quotes (Anderson and
Mississippi Baptist all-ages text, Children's, Memphis and Arlington status,
Collierville parking, Leake) were re-fetched and confirmed at about 07:15 UTC.
Quotes are summarized below, and the registry stores each
facility's source URL, address, OpenStreetMap campus reference and notes in
`destination_evidence`.

## Result

| Facility | Active 24/7 ER | Age groups | Notes |
| --- | --- | --- | --- |
| Memphis | Yes | adult | Separate Children's pediatric ER and Women's maternity triage on campus |
| Children's | Yes | child | Pediatric-only 10-bay ER; no ER upper age limit published |
| Collierville | Yes | adult | Official: emergency parking on the north side (not a coordinate) |
| Arlington | Yes | adult | Freestanding ER, a department of Baptist Memphis |
| Tipton | Yes | adult | |
| Carroll County (`huntingdon`) | Yes | adult | Location URL is `/locations/carroll-county` |
| Union City | Yes | adult | Hospital at 1201 Bishop St; services page lists the ED at 1202 |
| Crittenden | Yes | adult | ER shares a vestibule with the main outpatient entrance |
| NEA Baptist | Yes | adult | Official ZIP differs between pages (72405/72401) |
| DeSoto | Yes | adult, child | "children, adults and elderly patients"; separate obstetrics ER in the Women's Pavilion |
| Anderson | Yes | adult, child | "patients of all ages"; primary pediatric trauma center; Anderson-South has no ER |
| Attala | Yes | adult | Page carries stale copied content |
| Booneville | Yes | adult | Official address inconsistent (Hospital St / Hospital Drive) |
| Calhoun | Yes | adult | Page's embedded coordinates ~3 km from the campus |
| Golden Triangle | Yes | adult | 38-bed ER |
| Leake | **Unverified** | adult | Current pages say Level IV ED but not 24/7; 24-hour wording only in 2024 news; page structured data lists `openingHours: 24/7` for the location, not specifically the ER; absent from the emergency services list |
| North Mississippi | Yes | adult | One unconfirmed OSM node named "Emergency Room Entrance" (amenity=hospital, no entrance tag); not used |
| Union County | Yes | adult | Separate obstetric ED on campus |
| Yazoo | Yes | adult | |
| Mississippi Baptist | Yes | adult, child | "patients of all ages"; separate OB emergency department; official URL `/locations/jackson` |

**Emergency entrances: none verified.** No official page gives entrance
coordinates, and OpenStreetMap has no emergency-entrance element at any campus.
The North Mississippi volunteer node was not used as an entrance.

The registry sets `active_status`, `service_applicability`, `age_applicability`
and `travel_verified_on: 2026-09-23` from this research. `travel_verified_on` dates
the attribute evidence; it starts the existing 90-day re-verification window.
`emergency_entrance` stays `null` and `coordinates` stays unset.

## Campus-center fallback (user decision, 2026-09-23)

After reviewing the options above, the user chose to proceed with arrival points
labeled "ER entrance unconfirmed" and to add entrance points from satellite
imagery later. Implementation:

- Each facility has a `campus_point`: the center of its OpenStreetMap hospital
  element (Overpass data 2026-09-22T08:45:51Z), with the element URL as source and
  the label "Hospital campus center · ER entrance unconfirmed". Union City uses its
  hospital multipolygon relation 21370174; Children's and Arlington use their POI nodes.
- `edwait.travel.arrival()` routes to a reviewed `emergency_entrance` when present,
  otherwise to `campus_point`. A defective entrance blocks the destination instead
  of silently falling back. `travel.json` now reports each facility's `arrival`
  (`entrance`, `campus` or `null`) and adds the recommendation blocker "Some arrival
  points are campus locations; ER entrances unconfirmed".
- The page counts campus arrivals in its status ("18 eligible destinations · all to
  campus center, ER entrance unconfirmed"), labels each bar and row "Drive to campus
  center · ER entrance unconfirmed", and explains the fallback in the disclosure.
- Route endpoints must land within 300 m of a campus point (150 m for a reviewed
  entrance).

Eligibility on 2026-09-23: **18 adult destinations** (all active general ERs except
Children's) and **4 child destinations** (Children's, Anderson, DeSoto, Mississippi
Baptist). Leake stays excluded until its 24/7 status is confirmed.

### Live route validation

`scripts/check_routes.py` sent 54 budgeted TomTom v3 requests at 07:36:56 UTC, one
from each of three fixed public city-center points (downtown Memphis, Jackson and
Tupelo; not user locations) to every adult destination. **54/54 returned HTTP 200**
with parseable summaries. Route ends were a median 26 m and at most 61 m (NEA)
from the campus points, well inside the 300 m tolerance. Examples: downtown Memphis
to Crittenden 10 min, Baptist Memphis 17 min, DeSoto 17 min; downtown Jackson to
Mississippi Baptist 7 min; downtown Tupelo to Union County 27 min. No route reported
traffic delay at this overnight hour, which does not establish live-traffic coverage.
Sanitized evidence without geometry: `.cache/route-validation-20260923.json`.

An end-to-end local Compare through the review server from downtown Memphis
returned 18 labeled rows with drive, published wait and differences, and no
recommendation.

## Adding reviewed entrances

`python -m edwait.entrances` maintains entrance points:

- `list` prints each facility's arrival kind, address, offset and OpenStreetMap and
  aerial-imagery links for review.
- `geojson review.geojson` exports campus/entrance points for any GeoJSON viewer.
- `set SLUG --lat --lon --label --source-url [--method imagery_review] [--reviewed-on]
  [--note] [--dry-run]` validates with the same rule eligibility uses (HTTPS source,
  label, method in `official_source`/`imagery_review`/`site_visit`, non-future review
  date, within 1,000 m of the campus center) and writes the registry.
- `clear SLUG` reverts to the campus fallback.

A reviewed entrance immediately replaces the campus point and the "unconfirmed"
labels for that facility after the next preparation/render.

## Routing availability gate

Separately, the browser now asks `GET /api/routes/status` before enabling Compare.
Static S3 hosting has no such endpoint, so even a future eligible destination
cannot cause the public page to post a user's coordinates to S3. The local review
server answers from its configured key; a future public gateway must implement the
same probe. Tests cover the probe, the S3 error case and the local server response.

## Leake recheck — 2026-09-26 UTC

Official pages were re-fetched; the evidence is unchanged. The
[location page](https://www.baptistonline.org/locations/leake) describes a Level IV
emergency department and showed a live ER wait; the
[services page](https://www.baptistonline.org/locations/leake/services) gives no ER
hours; the [emergency services list](https://www.baptistonline.org/services/emergency)
still names 19 locations without Leake.

Supporting federal evidence, not an official Baptist statement:

- CMS Provider Data, Hospital General Information (dataset `xubh-q36u`, queried
  2026-09-26): BAPTIST MEDICAL CENTER-LEAKE, CCN 251315, type "Critical Access
  Hospitals", emergency services "Yes".
- [42 CFR 485.618](https://www.law.cornell.edu/cfr/text/42/485.618) requires a
  critical access hospital's emergency services to be available 24 hours a day,
  with a practitioner on call and on site within 30 minutes (60 in frontier areas).

The registry is unchanged: `active_status` stays `unknown` until the user decides
whether this evidence meets the 24/7 rule or confirms by phone (601-267-1100).
The on-call allowance may matter when comparing its published wait.

## Remaining decisions

1. **Entrance evidence.** Resolved for now by the labeled campus fallback; the user
   will add imagery-reviewed entrances with `python -m edwait.entrances`.
2. **Children at general hospitals.** Only Anderson, DeSoto and Mississippi Baptist
   state that their general ER treats children. Others likely treat children (EMTALA obliges screening), but
   the registry records only explicit evidence.

Metric semantics (`CV_ED_Wait` averaging window, update cadence and zero meaning)
remain unconfirmed and continue to block recommendations regardless of entrances.
