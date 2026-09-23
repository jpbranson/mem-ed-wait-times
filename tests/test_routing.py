import contextlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock

from jsonschema import Draft202012Validator, FormatChecker
import requests

from edwait.data import registry, timestamp
from edwait.routing import ENDPOINT, RequestBudget, Router, RoutingError, parse_route
from edwait.serve import ReviewHandler, ThreadingHTTPServer

NOW = timestamp("2026-09-14T17:00:00Z")
ORIGIN = {"latitude": 35.15, "longitude": -90.05, "age_group": "adult"}
KEY = "test-only-key-must-not-escape"


def destinations():
    # These coordinates/verification are synthetic test data, never real destinations.
    facilities = deepcopy(registry()[:2])
    for i, f in enumerate(facilities):
        f.update(active_status="active", service_applicability=["general_emergency"],
                 age_applicability=["adult"], travel_verified_on="2026-09-14",
                 campus_point={"latitude": 35.14, "longitude": -90.04 - i * .01,
                               "label": "Synthetic campus", "source_url": "https://example.com/campus"},
                 emergency_entrance={"latitude": 35.14, "longitude": -90.04 - i * .01,
                                     "label": "Synthetic entrance", "source_url": "https://example.com/fixture",
                                     "method": "imagery_review", "reviewed_on": "2026-09-14"})
    return facilities


def payload(origin=None, destination=None):
    return {"routes": [{"summary": {"lengthInMeters": 2058, "travelDurationInSeconds": 600,
                                    "trafficDelayDurationInSeconds": 60},
                        "legs": [{"path": {"type": "LineString", "coordinates": [origin or [-90.05, 35.15], destination or [-90.04, 35.14]]}}]}]}


def responder(url, **kwargs):
    points = kwargs["json"]["routePlanningLocations"]
    return Mock(status_code=200, json=lambda: payload(points["origin"]["coordinates"], points["destination"]["coordinates"]))


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "usage.sqlite3"
        self.clock = Clock()
        self.requester = Mock(side_effect=responder)
        self.budget = RequestBudget(self.path, limit=20)

    def router(self, **kwargs):
        return Router(**{**dict(requester=self.requester, clock=self.clock, now=lambda: NOW,
                                api_key=KEY, budget=self.budget, sleeper=self.clock.sleep), **kwargs})

    def test_individual_post_routes_live_traffic_header_secret_and_response_schema(self):
        result = self.router().matrix(ORIGIN, destinations())
        self.assertEqual(self.requester.call_count, 2)
        for args, kwargs in self.requester.call_args_list:
            self.assertEqual(args, (ENDPOINT,))
            self.assertNotIn(KEY, args[0])
            self.assertNotIn("35.15", args[0])
            self.assertEqual(kwargs["headers"]["TomTom-Api-Key"], KEY)
            self.assertEqual(kwargs["headers"]["TomTom-Api-Version"], "3")
            body = kwargs["json"]
            self.assertEqual(body["traffic"], "live")
            self.assertEqual(body["departureDateTime"], NOW.isoformat())
            self.assertEqual(body["routeType"], "fast")
            self.assertEqual(body["travelMode"], "car")
            self.assertEqual(body["routePlanningLocations"]["origin"]["coordinates"], [-90.05, 35.15])
            self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(result["routes"][0]["seconds"], 600)  # Includes the delay: never add it twice.
        self.assertEqual(result["routes"][0]["traffic_delay_seconds"], 60)
        self.assertEqual(result["generated_at"], NOW.isoformat())
        self.assertNotIn(KEY, json.dumps(result))
        self.assertNotIn("coordinates", json.dumps(result))
        schema = json.loads(Path("docs/routes.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(result)
        result["origin"] = ORIGIN
        self.assertTrue(list(validator.iter_errors(result)))

    def test_invalid_input_empty_eligibility_and_missing_key_do_not_spend_budget(self):
        router = self.router()
        for patch in ({"latitude": True}, {"latitude": 91}, {"longitude": float("nan")},
                      {"age_group": "unknown"}, {"destinations": [ORIGIN]}):
            with self.assertRaises(RoutingError):
                router.matrix({**ORIGIN, **patch}, destinations())
        with self.assertRaisesRegex(RoutingError, "no_verified_destinations"):
            router.matrix(ORIGIN, registry())
        with self.assertRaisesRegex(RoutingError, "routing_not_configured"):
            self.router(api_key="").matrix(ORIGIN, destinations())
        self.requester.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_provider_failure_keeps_partial_coverage_and_never_retries(self):
        def partial(url, **kwargs):
            if kwargs["json"]["routePlanningLocations"]["destination"]["coordinates"][0] == -90.04:
                raise requests.Timeout(KEY + " secret origin")
            return responder(url, **kwargs)
        self.requester.side_effect = partial
        result = self.router().matrix(ORIGIN, destinations())
        self.assertEqual([r["status"] for r in result["routes"]], ["unavailable", "ok"])
        self.assertEqual(result["routes"][0]["seconds"], None)
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(self.requester.call_count, 2)

    def test_access_quota_and_service_errors_are_sanitized_and_cool_down(self):
        for status, code in ((401, "routing_access_denied"), (403, "routing_access_denied"), (429, "provider_limit_reached"), (500, "routing_unavailable")):
            with self.subTest(status=status):
                self.requester.return_value = Mock(status_code=status, json=lambda: {"key": KEY})
                self.requester.side_effect = None
                router = self.router()
                with self.assertRaisesRegex(RoutingError, "^" + code + "$"):
                    router.matrix(ORIGIN, destinations())
                if status != 500:
                    before = self.requester.call_count
                    with self.assertRaisesRegex(RoutingError, "provider_limit_reached"):
                        router.matrix(ORIGIN, destinations())
                    self.assertEqual(self.requester.call_count, before)

    def test_missing_or_zero_delay_is_not_fabricated_traffic_coverage(self):
        for delay in (None, 0):
            data = payload()
            data["routes"][0]["summary"].pop("trafficDelayDurationInSeconds")
            if delay == 0:
                data["routes"][0]["summary"]["trafficDelayDurationInSeconds"] = 0
            route = parse_route(data, "test", [-90.05, 35.15], [-90.04, 35.14])
            self.assertEqual(route["traffic_delay_seconds"], delay)
            self.assertEqual(route["seconds"], 600)

    def test_bad_summaries_and_wrong_road_endpoints_fail_closed(self):
        for field in ("travelDurationInSeconds", "lengthInMeters", "trafficDelayDurationInSeconds"):
            for value in (-1, float("nan"), True):
                data = payload()
                data["routes"][0]["summary"][field] = value
                with self.assertRaises(ValueError):
                    parse_route(data, "test", [-90.05, 35.15], [-90.04, 35.14])
        for data in (payload(origin=[0, 0]), payload(destination=[0, 0])):
            with self.assertRaises(ValueError):
                parse_route(data, "test", [-90.05, 35.15], [-90.04, 35.14])
        self.requester.side_effect = lambda *a, **k: Mock(status_code=200, json=lambda: {"routes": []})
        with self.assertRaisesRegex(RoutingError, "routing_unavailable"):
            self.router().matrix(ORIGIN, destinations())

    def test_budget_persists_across_restarts_reserves_entire_comparison_and_has_no_locations(self):
        budget = RequestBudget(self.path, limit=3)
        self.router(budget=budget).matrix(ORIGIN, destinations())
        with self.assertRaisesRegex(RoutingError, "request_budget_exhausted"):
            self.router(budget=RequestBudget(self.path, limit=3)).matrix(ORIGIN, destinations())
        self.assertEqual(self.requester.call_count, 2)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT * FROM requests").fetchall(), [("2026-09-14", 2)])
        self.assertNotIn(KEY.encode(), self.path.read_bytes())
        self.assertNotIn(b"35.15", self.path.read_bytes())

    def test_budget_rolls_conservatively_and_corruption_never_resets_it(self):
        budget = RequestBudget(self.path, limit=2)
        budget.reserve(2, NOW)
        with self.assertRaisesRegex(RoutingError, "request_budget_exhausted"):
            budget.reserve(1, NOW + timedelta(days=31))
        budget.reserve(2, NOW + timedelta(days=32))
        with self.assertRaisesRegex(RoutingError, "request_budget_exhausted"):
            budget.reserve(1, NOW)  # Clock rollback must not erase newer reservations.
        self.path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(RoutingError, "request_budget_unavailable"):
            budget.reserve(1, NOW)
        self.assertEqual(self.path.read_bytes(), b"corrupt")
        with self.assertRaises(ValueError):
            RequestBudget(self.path, limit=20001)

    def test_budget_reservation_is_atomic_across_independent_instances(self):
        def reserve(_):
            try:
                RequestBudget(self.path, limit=3).reserve(2, NOW)
                return True
            except RoutingError as e:
                self.assertEqual(str(e), "request_budget_exhausted")
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reserve, range(2))), [False, True])

    def test_request_deadline_and_single_comparison_gate(self):
        router = self.router()
        router.lock.acquire()
        try:
            with self.assertRaisesRegex(RoutingError, "rate_limited"):
                router.matrix(ORIGIN, destinations())
        finally:
            router.lock.release()
        def expired(*args, **kwargs):
            self.clock.value += 16
            return responder(*args, **kwargs)
        self.requester.side_effect = expired
        with self.assertRaisesRegex(RoutingError, "routing_unavailable"):
            router.matrix(ORIGIN, destinations())

    def test_local_gateway_roundtrip_privacy_cross_origin_errors_and_body_bounds(self):
        router = self.router()
        class Handler(ReviewHandler):
            pass
        # Route the HTTP boundary through the actual adapter with synthetic facilities.
        Handler.router = Mock(matrix=lambda data: router.matrix(data, destinations()))
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                response = requests.post(origin + "/api/routes", json=ORIGIN, headers={"Origin": origin}, timeout=3)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["provider"], "tomtom")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertNotIn(KEY, response.text + output.getvalue())
            self.assertNotIn("35.15", response.text + output.getvalue())
            self.assertEqual(requests.post(origin + "/api/routes", json=ORIGIN, headers={"Origin": "https://evil.example"}, timeout=3).status_code, 403)
            self.assertEqual(requests.post(origin + "/api/routes", data="x"*513, headers={"Origin": origin,"Content-Type":"application/json"}, timeout=3).status_code, 400)
            Handler.router = Mock(api_key=KEY)
            status = requests.get(origin + "/api/routes/status", timeout=3)
            self.assertEqual(status.json(), {"schema_version": 1, "available": True})
            self.assertEqual(status.headers["Cache-Control"], "no-store")
            self.assertNotIn(KEY, status.text)
            Handler.router = Mock(api_key="")
            self.assertEqual(requests.get(origin + "/api/routes/status", timeout=3).json()["available"], False)
            Handler.router = Mock()
            for code, status in (("routing_not_configured", 503), ("provider_limit_reached", 429), ("request_budget_exhausted", 429)):
                Handler.router.matrix.side_effect = RoutingError(code)
                response = requests.post(origin + "/api/routes", json=ORIGIN, headers={"Origin": origin}, timeout=3)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"error": code})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()


class ArrivalToleranceTests(unittest.TestCase):
    def test_campus_fallback_allows_wider_road_snap_than_a_reviewed_entrance(self):
        # About 250 m north of the target: plausible for a large campus, not for an entrance.
        data = payload(destination=[-90.04, 35.14225])
        self.assertEqual(parse_route(data, "campus", [-90.05, 35.15], [-90.04, 35.14], 300)["status"], "ok")
        with self.assertRaises(ValueError):
            parse_route(data, "entrance", [-90.05, 35.15], [-90.04, 35.14])

    def test_router_targets_campus_point_when_no_entrance_is_reviewed(self):
        requester = Mock(side_effect=responder)
        with tempfile.TemporaryDirectory() as folder:
            router = Router(requester=requester, now=lambda: NOW, api_key=KEY, budget=RequestBudget(Path(folder) / "u.sqlite3", limit=5))
            facilities = destinations()[:1]
            facilities[0]["emergency_entrance"] = None
            facilities[0]["campus_point"] = {"latitude": 35.13, "longitude": -90.02, "label": "Synthetic campus", "source_url": "https://example.com/campus"}
            result = router.matrix(ORIGIN, facilities)
        self.assertEqual(result["routes"][0]["status"], "ok")
        body = requester.call_args.kwargs["json"]
        self.assertEqual(body["routePlanningLocations"]["destination"]["coordinates"], [-90.02, 35.13])
