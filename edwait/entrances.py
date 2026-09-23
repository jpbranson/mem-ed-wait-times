"""Record reviewed emergency-entrance points in the facility registry.

A reviewed entrance replaces a facility's labeled campus fallback for routing.
Typical imagery workflow:

    python -m edwait.entrances list                 # links for review
    python -m edwait.entrances geojson review.geojson
    python -m edwait.entrances set memphis --lat 35.12901 --lon -89.86185 \
        --label "Emergency department ambulance/walk-in entrance, Walnut Grove Rd side" \
        --source-url "https://www.openstreetmap.org/?mlat=35.12901&mlon=-89.86185#map=19/35.12901/-89.86185" \
        --method imagery_review --note "Canopy and ER signage visible in current aerial imagery"
    python -m edwait.entrances clear memphis        # revert to the campus fallback
"""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from edwait.analysis import ZONE
from edwait.travel import ENTRANCE_METHODS, MAX_ENTRANCE_OFFSET_METERS, entrance_problem, meters_between

REGISTRY = Path(__file__).with_name("facilities.json")


def today():
    return datetime.now(timezone.utc).astimezone(ZONE).date()


def find(registry, slug):
    for facility in registry["facilities"]:
        if facility["slug"] == slug:
            return facility
    raise ValueError(f"Unknown facility slug: {slug}")


def set_entrance(registry, slug, *, latitude, longitude, label, source_url, method,
                 reviewed_on=None, note=None, on=None):
    """Validate with the same rule eligibility uses, then store; raises ValueError."""
    facility = find(registry, slug)
    now = on or today()
    entrance = {"latitude": latitude, "longitude": longitude, "label": label.strip(),
                "source_url": source_url.strip(), "method": method,
                "reviewed_on": (reviewed_on or now).isoformat()}
    if note:
        entrance["note"] = note.strip()
    problem = entrance_problem(entrance, facility.get("campus_point"), now)
    if problem:
        raise ValueError(f"{slug}: {problem}")
    facility["emergency_entrance"] = entrance
    return facility


def clear_entrance(registry, slug):
    facility = find(registry, slug)
    facility["emergency_entrance"] = None
    return facility


def review_rows(registry):
    rows = []
    for f in registry["facilities"]:
        entrance, campus = f.get("emergency_entrance"), f.get("campus_point")
        point = entrance or campus
        rows.append({"slug": f["slug"], "name": f["display_name"],
                     "arrival": "entrance" if entrance else "campus" if campus else "none",
                     "address": f.get("destination_evidence", {}).get("address"),
                     "offset_m": round(meters_between(entrance, campus)) if entrance and campus else None,
                     "osm": f"https://www.openstreetmap.org/?mlat={point['latitude']}&mlon={point['longitude']}#map=19/{point['latitude']}/{point['longitude']}" if point else None,
                     "aerial": f"https://www.google.com/maps/@{point['latitude']},{point['longitude']},150m/data=!3m1!1e3" if point else None})
    return rows


def geojson(registry):
    """Campus and entrance points for review in any GeoJSON viewer; no user data."""
    features = []
    for f in registry["facilities"]:
        for kind in ("campus_point", "emergency_entrance"):
            point = f.get(kind)
            if point:
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [point["longitude"], point["latitude"]]},
                                 "properties": {"slug": f["slug"], "name": f["display_name"], "kind": kind, "label": point["label"],
                                                "source_url": point["source_url"]}})
    return {"type": "FeatureCollection", "features": features}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show arrival kind and review links for every facility")
    export = commands.add_parser("geojson", help="write campus/entrance points as GeoJSON")
    export.add_argument("output", type=Path)
    setter = commands.add_parser("set", help="record a reviewed entrance")
    setter.add_argument("slug")
    setter.add_argument("--lat", type=float, required=True)
    setter.add_argument("--lon", type=float, required=True)
    setter.add_argument("--label", required=True, help="where vehicles arrive, e.g. street side and signage")
    setter.add_argument("--source-url", required=True, help="HTTPS link to the reviewed imagery/map view or official source")
    setter.add_argument("--method", choices=ENTRANCE_METHODS, default="imagery_review")
    setter.add_argument("--reviewed-on", type=date.fromisoformat, help="default: today in America/Chicago")
    setter.add_argument("--note")
    setter.add_argument("--dry-run", action="store_true")
    clearer = commands.add_parser("clear", help="remove an entrance, reverting to the campus fallback")
    clearer.add_argument("slug")
    args = parser.parse_args(argv)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    if args.command == "list":
        for row in review_rows(registry):
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if args.command == "geojson":
        args.output.write_text(json.dumps(geojson(registry), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    try:
        if args.command == "set":
            facility = set_entrance(registry, args.slug, latitude=args.lat, longitude=args.lon, label=args.label,
                                    source_url=args.source_url, method=args.method, reviewed_on=args.reviewed_on, note=args.note)
            offset = meters_between(facility["emergency_entrance"], facility["campus_point"]) if facility.get("campus_point") else None
            print(json.dumps({"slug": args.slug, "emergency_entrance": facility["emergency_entrance"],
                              "meters_from_campus_center": round(offset) if offset is not None else None,
                              "limit_meters": MAX_ENTRANCE_OFFSET_METERS}, indent=2, ensure_ascii=False))
        else:
            clear_entrance(registry, args.slug)
            print(f"{args.slug}: entrance cleared; routing uses the labeled campus point")
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")
    if getattr(args, "dry_run", False):
        print("Dry run: registry not written")
        return 0
    args.registry.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
