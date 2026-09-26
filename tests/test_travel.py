from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from edwait.data import History, registry, timestamp
from edwait.travel import arrival, build_travel, eligibility
from tests.fakes import record

NOW = timestamp("2026-09-14T17:00:00Z")


class TravelTests(unittest.TestCase):
    def test_verified_age_service_arrival_and_date_are_all_required(self):
        f = deepcopy(registry()[0])
        campus = {"latitude": 35.14, "longitude": -90.04, "label": "Synthetic campus", "source_url": "https://example.com/campus"}
        entrance = {"latitude": 35.1405, "longitude": -90.0405, "label": "Synthetic entrance", "source_url": "https://example.com/fixture",
                    "method": "imagery_review", "reviewed_on": "2026-09-13"}
        f.update(active_status="active", service_applicability=["general_emergency"],
                 age_applicability=["adult"], travel_verified_on="2026-09-14", campus_point=campus, emergency_entrance=entrance)
        self.assertIsNone(eligibility(f, "adult", NOW))
        self.assertEqual(arrival(f), (entrance, "entrance"))
        self.assertIsNotNone(eligibility(f, "child", NOW))
        for patch in ({"active_status": "unknown"}, {"service_applicability": None},
                      {"service_applicability": "general_emergency"}, {"age_applicability": "adult"},
                      {"travel_verified_on": "2026-01-01"}, {"travel_verified_on": "2026-09-15"},
                      {"travel_verified_on": "garbage"}, {"emergency_entrance": None, "campus_point": None}):
            self.assertIsNotNone(eligibility({**f, **patch}, "adult", NOW))
        # Without a reviewed entrance, the labeled campus point is the routing fallback.
        fallback = {**f, "emergency_entrance": None}
        self.assertIsNone(eligibility(fallback, "adult", NOW))
        self.assertEqual(arrival(fallback), (campus, "campus"))
        self.assertEqual(eligibility({**fallback, "campus_point": {**campus, "source_url": "http://x"}}, "adult", NOW), "Arrival location unavailable")
        # A defective entrance blocks the destination rather than silently using the campus.
        for bad, reason in (({"method": "guess"}, "incomplete"), ({"reviewed_on": "2026-09-15"}, "incomplete"),
                            ({"reviewed_on": None}, "incomplete"), ({"label": ""}, "incomplete"),
                            ({"latitude": 35.16}, "too far")):
            self.assertIn(reason, eligibility({**f, "emergency_entrance": {**entrance, **bad}}, "adult", NOW))

    def test_real_registry_uses_labeled_campus_fallback_only_where_evidence_allows(self):
        later = timestamp("2026-09-24T17:00:00Z")
        facilities = {f["slug"]: f for f in registry()}
        adult = {slug for slug, f in facilities.items() if eligibility(f, "adult", later) is None}
        child = {slug for slug, f in facilities.items() if eligibility(f, "child", later) is None}
        self.assertEqual(len(adult), 18)
        self.assertEqual(child, {"childrens", "anderson", "desoto", "baptist-medical-center"})
        self.assertEqual(eligibility(facilities["baptist-medical-center-leake"], "adult", later), "Active emergency service unverified")
        self.assertTrue(all(arrival(facilities[s])[1] == "campus" for s in adult | child))
        # Attribute evidence expires after the 90-day recheck interval.
        self.assertTrue(all(eligibility(f, "adult", timestamp("2026-12-23T17:00:00Z")) for f in facilities.values()))

    def test_past_only_horizon_arithmetic_support_schema_and_no_origin(self):
        start = timestamp("2026-09-04T05:00:00Z")
        rows = [record(batch=(start + timedelta(minutes=15*i)).isoformat(),
                       observed=(start + timedelta(minutes=15*i)).isoformat(), wait=i) for i in range(960)]
        rows.append(record(batch=NOW.isoformat(), observed=NOW.isoformat(), wait=99999))
        context = build_travel(History(records=rows), NOW)
        memphis = next(f for f in context["facilities"] if f["slug"] == "memphis")
        self.assertEqual([m["absolute_change_p90"] for m in memphis["movement"]], [1, 2, 4, 8])
        # The gateway routes to exactly the published arrival point for each facility.
        facilities = {f["slug"]: f for f in registry()}
        for entry in context["facilities"]:
            point, kind = arrival(facilities[entry["slug"]])
            self.assertEqual(entry["arrival"], kind)
            self.assertEqual(entry["arrival_point"], {"latitude": point["latitude"], "longitude": point["longitude"]})
        self.assertEqual(memphis["movement"][0]["pairs"], 959)
        self.assertEqual(memphis["movement"][0]["days"], 10)
        schema = json.loads(Path("docs/travel.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(context)
        mismatched = deepcopy(context)
        mismatched["facilities"][0]["arrival"] = None
        self.assertTrue(list(validator.iter_errors(mismatched)))
        mismatched["facilities"][0]["arrival_point"] = None
        validator.validate(mismatched)
        context["origin"] = {"latitude": 35.15, "longitude": -90.05}
        self.assertTrue(list(validator.iter_errors(context)))
        self.assertFalse(context["recommendations_enabled"])

    def test_sparse_days_and_gaps_do_not_create_movement_support(self):
        start = timestamp("2026-09-01T05:00:00Z")
        rows = [record(batch=(start + timedelta(days=i, minutes=j*15)).isoformat(),
                       observed=(start + timedelta(days=i, minutes=j*15)).isoformat(), wait=j*100)
                for i in range(10) for j in range(12)]
        context = build_travel(History(records=rows), NOW)
        self.assertTrue(all(m["absolute_change_p90"] is None for f in context["facilities"] for m in f["movement"]))
        self.assertTrue(all(m["pairs"] == 0 for f in context["facilities"] for m in f["movement"]))


if __name__ == "__main__":
    unittest.main()
