---
type: Research Record
title: Memphis-area ERs without published wait information
description: Official evidence and map locations for eight Memphis-area ERs without published wait information, added as map-only directory records and released 2026-09-27.
tags: [map, facilities, directory]
status: stable
generated:
  by: claude-code/claude-opus-5-5
  at: 2026-10-05T03:16:22Z
sources:
- id: highland-hills-er
  resource: https://highlandhillsmc.com/er/
  title: Highland Hills Medical Center ER page
- id: highland-hills-home
  resource: https://highlandhillsmc.com/
  title: Highland Hills Medical Center home page
- id: regional-one
  resource: https://www.regionalonehealth.org/main-campus/regional-medical-center/
  title: Regional One Health – Regional Medical Center
- id: regional-one-services
  resource: https://www.regionalonehealth.org/medicine/
  title: Regional One Health medical services
- id: le-bonheur-er
  resource: https://www.lebonheur.org/your-visit/preparing-for-your-visit/emergency-room/
  title: Le Bonheur Children's Hospital emergency room
- id: memphis-va
  resource: https://www.va.gov/memphis-health-care/locations/lt-col-luke-weathers-jr-va-medical-center/
  title: Lt. Col. Luke Weathers, Jr. VA Medical Center facility page
- id: alliance-healthcare
  resource: https://www.alliancehcs.org/
  title: Alliance HealthCare System home page
- id: crossridge
  resource: https://www.stbernards.info/locations/profile/st-bernards-crossridge-community-hospital/
  title: St. Bernards CrossRidge Community Hospital location page
- id: smc-regional
  resource: https://www.mchsys.org/
  title: Mississippi County Hospital System (SMC Regional Medical Center)
- id: lauderdale-community
  resource: https://www.lauderdalehospital.org/getpage.php?name=Emergency_Services&sub=Services
  title: Lauderdale Community Hospital emergency services
- id: openstreetmap
  resource: https://www.openstreetmap.org/
  title: OpenStreetMap campus geometry (one way or relation per facility, linked in the table)
---

# Memphis-area ERs without published wait information

Reviewed: 2026-09-27. Published on 2026-09-27 by the 18:17 UTC build
([release](#validation-and-release)).

The user requested that ERs without published waits still appear on maps. These
eight additions follow the Memphis-area search, including communities roughly
within a 50-mile radius. This is a geographic radius, not a 50-mile driving limit;
Lauderdale Community Hospital is near the outer boundary. It is not a complete
regional ED inventory.

## Official evidence and map locations

No current public wait estimate, range or ER arrival scheduler was found on the
reviewed official pages below. The display label is **No published wait time**.
This is a dated search finding, not proof of permanent nonpublication or a
hospital-confirmed policy. Recheck official pages when refreshing this directory.

| Registry slug | Facility and city | Official emergency-service evidence | Campus coordinates and source | Qualification |
| --- | --- | --- | --- | --- |
| `highland-hills` | Highland Hills Medical Center · Senatobia, MS | [ER page](https://highlandhillsmc.com/er/), [24/7 service on home page](https://highlandhillsmc.com/) | 34.6246213, -89.9563835 · [OSM](https://www.openstreetmap.org/way/486893533) | General guidance that a visit may take several hours is not a live wait estimate |
| `regional-one` | Regional One Health – Regional Medical Center · Memphis, TN | [Regional Medical Center](https://www.regionalonehealth.org/main-campus/regional-medical-center/), [medical services](https://www.regionalonehealth.org/medicine/) | 35.1419953, -90.0305622 · [OSM](https://www.openstreetmap.org/relation/21086410) | ED and trauma center |
| `le-bonheur-childrens` | Le Bonheur Children's Hospital · Memphis, TN | [Emergency room](https://www.lebonheur.org/your-visit/preparing-for-your-visit/emergency-room/) | 35.1457333, -90.030748 · [OSM](https://www.openstreetmap.org/relation/21075529) | Pediatric ED; distinct from Baptist Children's Hospital |
| `memphis-va` | Lt. Col. Luke Weathers, Jr. VA Medical Center · Memphis, TN | [Facility page, Emergency care section](https://www.va.gov/memphis-health-care/locations/lt-col-luke-weathers-jr-va-medical-center/) explicitly lists 24/7 ER | 35.1430691, -90.0261207 · [OSM](https://www.openstreetmap.org/relation/21086412) | VA facility; eligibility requirements apply |
| `alliance-healthcare` | Alliance HealthCare System · Holly Springs, MS | [Hospital home page](https://www.alliancehcs.org/) lists 24/7 ER | 34.7867524, -89.4162494 · [OSM](https://www.openstreetmap.org/way/875017011) | General ED |
| `crossridge` | St. Bernards CrossRidge Community Hospital · Wynne, AR | [Hospital location page](https://www.stbernards.info/locations/profile/st-bernards-crossridge-community-hospital/) lists 24/7 emergency medicine | 35.2197151, -90.7863027 · [OSM](https://www.openstreetmap.org/way/452343585) | Do not attribute Jonesboro-specific timing claims on system pages to this campus |
| `smc-regional` | SMC Regional Medical Center · Osceola, AR | [Mississippi County Hospital System](https://www.mchsys.org/) identifies SMC as a rural emergency hospital with 24/7 emergency care | 35.6994888, -89.975748 · [OSM](https://www.openstreetmap.org/way/452144552) | Also known as South Mississippi County Regional Medical Center |
| `lauderdale-community` | Lauderdale Community Hospital · Ripley, TN | [Emergency services](https://www.lauderdalehospital.org/getpage.php?name=Emergency_Services&sub=Services) lists 24/7/365 ER | 35.7451256, -89.5498368 · [OSM](https://www.openstreetmap.org/way/496476114) | Near the radius boundary; driving distance is longer |

Coordinates are hospital-campus centers from an OpenStreetMap Overpass query,
with database timestamp `2026-09-27T14:04:06Z`; they are not verified emergency
entrances. Official addresses take precedence over OSM addresses: the VA's current
official address is 116 N Pauline Street (OSM lists its older name and Jefferson
Avenue campus address); Lauderdale's official address is 340 Asbury Avenue (OSM
lists 326). These discrepancies are retained in each record's evidence notes.

Delta Specialty is excluded until an active general ED can be verified: its old
acute-care material is insufficient. The planned Baptist Fayette ER is not an
operating destination. Methodist, Saint Francis and Forrest City are not marked
as nonpublishers: the search found wait ranges, arrival slots, or a timing widget
and pledge respectively, even where the timing's usability needs further review.

## Registry and publication behavior

The canonical [registry](../edwait/facilities.json) now contains 28 records:
20 existing Baptist collection records plus eight map-only listings.

- Every record has an explicit boolean `collection_enabled`. `registry()` returns
  only `true` records; `registry(include_map_only=True)` returns the full directory.
- Map-only records have `collection_enabled: false` and `wait_time_reporting`
  with `status: "not_published"`, `label`, `checked_on`, `source_urls`, and review
  `notes`. They also have an official URL, address, `map_note`, campus coordinates,
  and source dates. Age applicability remains unreviewed except the pediatric ED.
- `travel_verified_on` and `emergency_entrance` remain null. Map-only records are
  explicitly ineligible for the drive-plus-wait comparison even if accidentally
  passed to its eligibility check.
- The built HTML embeds these records in `map-only-facilities` and generates
  separate `map-area-groups` using the full directory. The normal `facility-registry`
  and analytical `area-groups` still contain only the original collection roster.
  Because 50 km neighbor groups chain through the added campuses, the map's
  Memphis-area view frames 17 campuses (the analytical view keeps 7), and the
  Booneville / North Mississippi / Union County view appears only in the M4 area
  picker, not the map's.
- Square map markers (□) show **No published wait time**. Selecting one shows the
  name, address, service note, review date and official website, without opening a
  wait chart. The square status stays constant during replay and when history is
  unavailable. Round markers keep their replay behavior, except that without
  history they now show "– no reading" instead of the last period's colors.

No placeholder wait observations, zero waits, scheduled collection attempts, or
failure records are created for these listings. Raw, compacted, latest,
comparison and travel artifact contracts remain unchanged, as does the
[six-field observation schema](ed-wait.schema.json). Adding the directory does
not change coverage denominators, analytical neighbor groups or route coverage;
only the map's own views regroup (above).

Cost assessment: eight small static records and map markers in the existing
page, with no new service, collection schedule, hospital API calls or route calls.
The incremental page payload is under 15 KB uncompressed, negligible beside the
existing roughly 5.5 MB page and within the project's current $5/month design.

## Validation and release

- 91 Python tests and 72 JavaScript tests passed on 2026-09-27 (before the regional
  collector's 19 Python tests were added; the full suite ran 111 with the release fix
  below and 117 at release), including collection
  roster separation, source/coordinate completeness, travel exclusion, generated
  HTML membership, map selection, missing history, and replay status separation.
- Quarto successfully rendered the dashboard using the existing cached history.
- Local browser review passed: 28 accessible map markers, eight distinct squares,
  dated labels and clickable facility details, and an unchanged wait-chart selection
  after selecting Highland Hills. The desktop view had no horizontal overflow or
  captured JavaScript errors. Cached history was visibly dated; live S3 refresh was
  not enabled for this review. The map's eight focused tests also passed after
  checking that lost history clears old period colors while preserving square status.
- Exact source diff and whitespace review passed.
- Released through the normal source flow: committed as `8dca952` and pushed to
  `main` with the documentation audit (`5738133`) at 18:12 UTC on 2026-09-27. The
  18:17 UTC hourly build (run 36340076534) passed 117 Python and 72 JavaScript tests and
  the exact public build/freshness check (20/20 current); an independent public check
  passed at 18:21 UTC. A browser check of the public page at 18:33 UTC found all 28
  markers, including the eight squares, and Highland Hills' details opened without
  changing the focus chart. Regional One, Le Bonheur Children's and the Memphis VA are
  400–500 m apart and stack at the default zoom until zoomed in; the user deferred a
  fix. No Lambda, schedule or gateway changed.
- Release fix (2026-09-27 documentation audit): `scripts/check_public.mjs` and
  `gateway/scripts/local-check.mjs` had counted all 28 records, so the public check
  failed against the 20-facility `latest.json` ("Invalid latest artifact") and the
  gateway harness stopped before starting. Both now keep `collection_enabled`
  records, and a test requires that of every Node script reading the registry. The
  read-only public check then passed (20/20) and the harness passed 13/13 mock
  checks. `python -m edwait.entrances list` still shows all 28 records.
