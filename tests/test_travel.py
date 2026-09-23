from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from edwait.data import History, registry, timestamp
from edwait.travel import build_travel, eligibility
from tests.fakes import record

NOW = timestamp("2026-09-14T17:00:00Z")


class TravelTests(unittest.TestCase):
    def test_verified_age_service_entrance_and_date_are_all_required(self):
        f = deepcopy(registry()[0])
        f.update(active_status="active", service_applicability=["general_emergency"],
                 age_applicability=["adult"], travel_verified_on="2026-09-14",
                 emergency_entrance={"latitude": 35.14, "longitude": -90.04,
                                     "label": "Synthetic entrance", "source_url": "https://example.com/fixture"})
        self.assertIsNone(eligibility(f, "adult", NOW))
        self.assertIsNotNone(eligibility(f, "child", NOW))
        for patch in ({"active_status": "unknown"}, {"service_applicability": None},
                      {"service_applicability": "general_emergency"}, {"age_applicability": "adult"},
                      {"emergency_entrance": None}, {"travel_verified_on": "2026-01-01"},
                      {"travel_verified_on": "2026-09-15"}, {"travel_verified_on": "garbage"}):
            self.assertIsNotNone(eligibility({**f, **patch}, "adult", NOW))
        self.assertTrue(all(eligibility(f, "adult", NOW) for f in registry()))

    def test_past_only_horizon_arithmetic_support_schema_and_no_origin(self):
        start = timestamp("2026-09-04T05:00:00Z")
        rows = [record(batch=(start + timedelta(minutes=15*i)).isoformat(),
                       observed=(start + timedelta(minutes=15*i)).isoformat(), wait=i) for i in range(960)]
        rows.append(record(batch=NOW.isoformat(), observed=NOW.isoformat(), wait=99999))
        context = build_travel(History(records=rows), NOW)
        memphis = next(f for f in context["facilities"] if f["slug"] == "memphis")
        self.assertEqual([m["absolute_change_p90"] for m in memphis["movement"]], [1, 2, 4, 8])
        self.assertEqual(memphis["movement"][0]["pairs"], 959)
        self.assertEqual(memphis["movement"][0]["days"], 10)
        schema = json.loads(Path("docs/travel.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(context)
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
