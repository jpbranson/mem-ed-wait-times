# M2 destination evidence — 2026-09-23 UTC

M2 remains in progress. This record documents the destination research that the
registry's travel gates require. It changes registry metadata only; **no
destination became travel eligible** and no recommendation gate was relaxed.

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
Campus centers, address geocodes and the North Mississippi volunteer node were
not substituted, following the 2026-09-14 gate decision. Every facility therefore
remains excluded — 19 with "Emergency entrance coordinates unverified" and Leake
with "Active emergency service unverified".

The registry now sets `active_status`, `service_applicability`, `age_applicability`
and `travel_verified_on: 2026-09-23` from this research. `travel_verified_on` dates
the attribute evidence; it starts the existing 90-day re-verification window.
`emergency_entrance` stays `null` and `coordinates` stays unset.

## Routing availability gate

Separately, the browser now asks `GET /api/routes/status` before enabling Compare.
Static S3 hosting has no such endpoint, so even a future eligible destination
cannot cause the public page to post a user's coordinates to S3. The local review
server answers from its configured key; a future public gateway must implement the
same probe. Tests cover the probe, the S3 error case and the local server response.

## Decisions needed

1. **Entrance evidence.** Options: request vehicle-arrival points from Baptist,
   add reviewed entrance points from current imagery with a dated reviewer note,
   or explicitly accept campus points labeled "campus, ER entrance unconfirmed"
   (which would add a documented distance error to travel times). The current
   gate requires the first or second.
2. **Children at general hospitals.** Only Anderson, DeSoto and Mississippi Baptist
   state that their general ER treats children. Others likely treat children (EMTALA obliges screening), but
   the registry records only explicit evidence.

Metric semantics (`CV_ED_Wait` averaging window, update cadence and zero meaning)
remain unconfirmed and continue to block recommendations regardless of entrances.
