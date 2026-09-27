import json
import unittest
from pathlib import Path

from edwait.data import registry, timestamp
from edwait.travel import eligibility, point_problem


class FacilityDirectoryTests(unittest.TestCase):
    def test_map_only_records_never_enter_default_collection_roster(self):
        full = registry(include_map_only=True)
        collected = registry()
        directory = [f for f in full if not f["collection_enabled"]]
        self.assertEqual(len(full), 28)
        self.assertEqual(len({f["slug"] for f in full}), 28)
        self.assertEqual(len(collected), 20)
        self.assertTrue(all(f["collection_enabled"] is True for f in collected))
        self.assertEqual({f["slug"] for f in directory}, {
            "highland-hills", "regional-one", "le-bonheur-childrens", "memphis-va",
            "alliance-healthcare", "crossridge", "smc-regional", "lauderdale-community"})
        self.assertFalse({f["slug"] for f in directory} & {f["slug"] for f in collected})
        # Every stored record must choose a roster explicitly; no accidental opt-in.
        stored = json.loads(Path("edwait/facilities.json").read_text(encoding="utf-8"))["facilities"]
        self.assertTrue(all(type(f["collection_enabled"]) is bool for f in stored))
        for facility in directory:
            with self.subTest(facility=facility["slug"]):
                status = facility["wait_time_reporting"]
                self.assertEqual(status["status"], "not_published")
                self.assertEqual(status["label"], "No published wait time")
                self.assertEqual(status["checked_on"], "2026-09-27")
                self.assertIn(facility["official_source_url"], status["source_urls"])
                self.assertIsNone(point_problem(facility["campus_point"]))
                self.assertTrue(facility["destination_evidence"]["address"])
                self.assertIsNone(facility["travel_verified_on"])
                self.assertNotIn("wait_minutes", facility)
                for age in ("adult", "child"):
                    self.assertEqual(eligibility(facility, age, timestamp("2026-09-27T12:00:00Z")),
                                     "No published wait time · map only")

    def test_node_scripts_reading_the_registry_expect_only_the_collection_roster(self):
        # Public latest/comparison/travel artifacts list 20 facilities; counting map-only
        # records made the workflow's public check fail after every sync.
        readers = {p.as_posix(): p.read_text(encoding="utf-8")
                   for p in [*Path("scripts").glob("*.mjs"), *Path("gateway/scripts").glob("*.mjs")]
                   if "facilities.json" in p.read_text(encoding="utf-8")}
        self.assertLessEqual({"scripts/check_public.mjs", "gateway/scripts/local-check.mjs"}, set(readers))
        for path, source in readers.items():
            with self.subTest(path=path):
                self.assertIn(".filter(f => f.collection_enabled === true)", source)


if __name__ == "__main__":
    unittest.main()
