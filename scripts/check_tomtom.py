"""One explicitly invoked live routing contract probe; no hospital eligibility changes."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from time import perf_counter

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.routing import ENDPOINT, RequestBudget, RoutingError, USER_AGENT, parse_route


def read_key(env_file):
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key and env_file.exists():
        # Read only the requested key; never execute .env content or print values.
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "TOMTOM_API_KEY":
                key = value.strip().strip('"\'')
    return key


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--output", type=Path, default=Path(".cache/tomtom-live-check.json"))
    args = parser.parse_args()
    key = read_key(args.env_file)
    if not key:
        print(json.dumps({"status": "routing_not_configured"}))
        return 2
    now = datetime.now(timezone.utc)
    # Fixed public downtown Memphis road points. Neither is a hospital entrance
    # or a user's location. This probe cannot verify clinical destination metadata.
    origin, destination = [-90.05, 35.15], [-90.04, 35.14]
    evidence = {"checked_at": now.isoformat(), "purpose": "nonclinical_api_contract_probe",
                "provider": "tomtom", "api_version": 3, "traffic_requested": "live"}
    started = perf_counter()
    try:
        RequestBudget().reserve(1, now)
        response = requests.post(ENDPOINT, json={
            "routePlanningLocations": {"origin": {"type": "Point", "coordinates": origin},
                                       "destination": {"type": "Point", "coordinates": destination}},
            "traffic": "live", "departureDateTime": now.isoformat(), "routeType": "fast",
            "travelMode": "car", "maxPathAlternativeRoutes": 0},
            headers={"TomTom-Api-Key": key, "TomTom-Api-Version": "3",
                     "Attributes": "routes.summary,routes.legs.path", "Content-Type": "application/json",
                     "User-Agent": USER_AGENT}, timeout=(2, 5), allow_redirects=False)
        evidence["http_status"] = response.status_code
        if response.status_code == 200:
            evidence["route"] = parse_route(response.json(), "public-road-probe", origin, destination)
            evidence["status"] = "passed"
        else:
            evidence["status"] = "provider_rejected"
    except RoutingError as error:
        evidence["status"] = str(error)
    except requests.RequestException:
        evidence["status"] = "network_error"
    except (ValueError, KeyError, TypeError, IndexError):
        evidence["status"] = "response_contract_failed"
    evidence["elapsed_seconds"] = round(perf_counter() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
