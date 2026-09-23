"""Explicitly invoked live check of routes to every eligible registry destination.

Origins are fixed public city-center road points, never a user's location. Each
request is reserved in the persistent local budget first. Output keeps timing,
distance and how far the route ends from the arrival point; no geometry is stored.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.data import registry
from edwait.routing import ARRIVAL_TOLERANCE_METERS, ENDPOINT, USER_AGENT, RequestBudget, RoutingError, separation
from edwait.travel import arrival, eligibility
from scripts.check_tomtom import read_key

ORIGINS = {"downtown-memphis": [-90.0490, 35.1495], "downtown-jackson": [-90.1848, 32.2988],
           "downtown-tupelo": [-88.7034, 34.2576]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--output", type=Path, default=Path(".cache/route-validation.json"))
    args = parser.parse_args()
    key = read_key(args.env_file)
    if not key:
        print(json.dumps({"status": "routing_not_configured"}))
        return 2
    now = datetime.now(timezone.utc)
    targets = [f for f in registry() if eligibility(f, "adult", now) is None]
    results = []
    try:
        RequestBudget().reserve(len(targets) * len(ORIGINS), now)
    except RoutingError as error:
        print(json.dumps({"status": str(error)}))
        return 1
    for name, origin in ORIGINS.items():
        for facility in targets:
            point, kind = arrival(facility)
            destination = [point["longitude"], point["latitude"]]
            row = {"origin": name, "slug": facility["slug"], "arrival": kind}
            try:
                response = requests.post(ENDPOINT, json={
                    "routePlanningLocations": {"origin": {"type": "Point", "coordinates": origin},
                                               "destination": {"type": "Point", "coordinates": destination}},
                    "traffic": "live", "departureDateTime": datetime.now(timezone.utc).isoformat(), "routeType": "fast",
                    "travelMode": "car", "maxPathAlternativeRoutes": 0},
                    headers={"TomTom-Api-Key": key, "TomTom-Api-Version": "3", "Attributes": "routes.summary,routes.legs.path",
                             "Content-Type": "application/json", "User-Agent": USER_AGENT}, timeout=(2, 8), allow_redirects=False)
                row["http_status"] = response.status_code
                if response.status_code == 200:
                    route = response.json()["routes"][0]
                    path = route["legs"][0]["path"]["coordinates"]
                    row.update(seconds=route["summary"]["travelDurationInSeconds"], meters=route["summary"]["lengthInMeters"],
                               traffic_delay_seconds=route["summary"].get("trafficDelayDurationInSeconds"),
                               end_offset_m=round(separation(path[-1], destination)),
                               within_tolerance=separation(path[-1], destination) <= ARRIVAL_TOLERANCE_METERS[kind])
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
                row["error"] = type(error).__name__
            results.append(row)
            time.sleep(.3)
    ok = [r for r in results if r.get("within_tolerance")]
    summary = {"checked_at": now.isoformat(), "requests": len(results), "passed": len(ok),
               "max_end_offset_m": max((r["end_offset_m"] for r in results if "end_offset_m" in r), default=None),
               "status": "passed" if len(ok) == len(results) else "partial"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "routes": results}, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    for r in results:
        print(json.dumps(r))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
