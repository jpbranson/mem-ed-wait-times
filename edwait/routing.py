"""TomTom individual routes, with live traffic requested and no location persistence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

import requests

from edwait.data import registry
from edwait.travel import POLICY, coordinate, eligibility

ENDPOINT = "https://api.tomtom.com/maps/orbis/routing/routes/calculate"
USER_AGENT = "mem-ed-wait-times/0.2 (TomTom Routing integration)"
DEFAULT_BUDGET_PATH = Path(__file__).resolve().parents[1] / ".cache" / "tomtom-usage.sqlite3"


class RoutingError(Exception):
    """Only bounded public codes, never keys, provider URLs, or response bodies."""


class RequestBudget:
    """Conservative reservations over 32 UTC dates; only date/count are persisted."""

    def __init__(self, path=DEFAULT_BUDGET_PATH, limit=20000):
        if type(limit) is not int or not 1 <= limit <= 20000:
            raise ValueError("TOMTOM_REQUEST_BUDGET must be between 1 and 20000")
        self.path, self.limit = Path(path), limit

    def reserve(self, count, now):
        # Includes 31 complete days and today, covering any monthly billing window.
        day = now.astimezone(timezone.utc).date()
        cutoff = (day - timedelta(days=31)).isoformat()
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=2)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS requests (day TEXT PRIMARY KEY, calls INTEGER NOT NULL CHECK(typeof(calls) = 'integer' AND calls >= 0))")
            used = connection.execute("SELECT COALESCE(SUM(calls), 0) FROM requests WHERE day >= ?", (cutoff,)).fetchone()[0]
            if used + count > self.limit:
                raise RoutingError("request_budget_exhausted")
            connection.execute("INSERT INTO requests VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls", (day.isoformat(), count))
            connection.commit()
        except (sqlite3.Error, OSError):
            raise RoutingError("request_budget_unavailable") from None
        finally:
            if connection is not None:
                connection.close()


def unavailable(slug):
    return {"slug": slug, "status": "unavailable", "seconds": None, "meters": None, "traffic_delay_seconds": None}


class Router:
    def __init__(self, requester=requests.post, clock=time.monotonic, now=lambda: datetime.now(timezone.utc),
                 api_key=None, budget=None, sleeper=time.sleep):
        self.requester, self.clock, self.now, self.sleep = requester, clock, now, sleeper
        self.api_key = os.environ.get("TOMTOM_API_KEY", "").strip() if api_key is None else api_key.strip()
        self.budget = budget if budget is not None else RequestBudget(limit=int(os.environ.get("TOMTOM_REQUEST_BUDGET", "20000")))
        self.lock, self.rate_lock = threading.Lock(), threading.Lock()
        self.next_request, self.blocked_until = float("-inf"), float("-inf")

    def _request_slot(self, deadline, stopped):
        with self.rate_lock:
            delay = max(0, self.next_request - self.clock())
            if stopped.is_set() or self.clock() + delay >= deadline:
                return False
            if delay:
                self.sleep(delay)
            if stopped.is_set():
                return False
            # Four starts per second across this Router; no route retries.
            self.next_request = self.clock() + .25
            return True

    def matrix(self, request, facilities=None):
        """Aggregate individual Routing API calls; never use TomTom's Matrix API."""
        if not isinstance(request, dict) or set(request) != {"latitude", "longitude", "age_group"}:
            raise RoutingError("invalid_origin")
        if not coordinate(request["latitude"], 90) or not coordinate(request["longitude"], 180):
            raise RoutingError("invalid_origin")
        group = request["age_group"]
        if group not in ("adult", "child"):
            raise RoutingError("invalid_age_group")
        now = self.now()
        facilities = registry() if facilities is None else facilities
        candidates = [f for f in facilities if eligibility(f, group, now) is None]
        if not candidates:
            raise RoutingError("no_verified_destinations")
        if len(candidates) > 20:
            raise RoutingError("too_many_destinations")
        if not self.api_key:
            raise RoutingError("routing_not_configured")
        if not self.lock.acquire(blocking=False):
            raise RoutingError("rate_limited")
        try:
            if self.clock() < self.blocked_until:
                raise RoutingError("provider_limit_reached")
            # Reserve the whole comparison atomically before any provider request.
            # Failures and skipped calls are not refunded: a timeout may be billed.
            self.budget.reserve(len(candidates), now)
            deadline = self.clock() + 15
            stopped = threading.Event()
            fatal_errors = []
            origin = [request["longitude"], request["latitude"]]

            def calculate(facility):
                slug = facility["slug"]
                if not self._request_slot(deadline, stopped):
                    return unavailable(slug)
                remaining = deadline - self.clock()
                if remaining <= .1:
                    return unavailable(slug)
                entrance = facility["emergency_entrance"]
                destination = [entrance["longitude"], entrance["latitude"]]
                body = {"routePlanningLocations": {"origin": {"type": "Point", "coordinates": origin},
                                                   "destination": {"type": "Point", "coordinates": destination}},
                        "traffic": "live", "departureDateTime": now.isoformat(), "routeType": "fast",
                        "travelMode": "car", "maxPathAlternativeRoutes": 0}
                try:
                    response = self.requester(ENDPOINT, json=body, headers={"TomTom-Api-Key": self.api_key,
                        "TomTom-Api-Version": "3", "Attributes": "routes.summary,routes.legs.path",
                        "Content-Type": "application/json", "User-Agent": USER_AGENT},
                        timeout=(min(2, remaining / 2), min(5, remaining / 2)), allow_redirects=False)
                    if response.status_code in (401, 403, 429):
                        fatal_errors.append("routing_access_denied" if response.status_code in (401, 403) else "provider_limit_reached")
                        stopped.set()
                        return unavailable(slug)
                    if response.status_code != 200:
                        return unavailable(slug)
                    result = parse_route(response.json(), slug, origin, destination)
                    return result if self.clock() <= deadline else unavailable(slug)
                except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
                    return unavailable(slug)

            with ThreadPoolExecutor(max_workers=4) as pool:
                routes = list(pool.map(calculate, candidates))
            if fatal_errors:
                # Stop this comparison and briefly block explicit retries after a
                # provider rate/quota/auth failure. No old or partial preferred claim.
                self.blocked_until = self.clock() + 60
                raise RoutingError("routing_access_denied" if "routing_access_denied" in fatal_errors else "provider_limit_reached")
            if not any(r["status"] == "ok" for r in routes):
                raise RoutingError("routing_unavailable")
            return {"schema_version": 2, "provider": "tomtom", "traffic_mode": "live",
                    "generated_at": now.isoformat(), "ttl_seconds": POLICY["route_ttl_seconds"],
                    "age_group": group, "routes": routes}
        finally:
            self.lock.release()


def nonnegative(value):
    return coordinate(value, 1e9) and value >= 0


def separation(a, b):
    if not isinstance(a, list) or len(a) != 2 or not coordinate(a[0], 180) or not coordinate(a[1], 90):
        raise ValueError("Invalid road endpoint")
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    h = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, h)))


def parse_route(payload, slug, origin, destination):
    route = payload["routes"][0]
    summary = route["summary"]
    seconds, meters = summary["travelDurationInSeconds"], summary["lengthInMeters"]
    delay = summary.get("trafficDelayDurationInSeconds")
    if not nonnegative(seconds) or not nonnegative(meters) or (delay is not None and (not nonnegative(delay) or delay > seconds)):
        raise ValueError("Invalid route summary")
    if len(route["legs"]) != 1:
        raise ValueError("Unexpected route legs")
    path = route["legs"][0]["path"]
    if path["type"] != "LineString" or not isinstance(path["coordinates"], list) or len(path["coordinates"]) < 2:
        raise ValueError("Missing route endpoints")
    if separation(path["coordinates"][0], origin) > 250 or separation(path["coordinates"][-1], destination) > 150:
        raise ValueError("Route ends too far from origin or verified entrance")
    # Keep only timing/distance data; geometry and origin never leave the adapter.
    # Zero/missing delay does not prove live traffic coverage on every road segment.
    return {"slug": slug, "status": "ok", "seconds": seconds, "meters": meters, "traffic_delay_seconds": delay}
