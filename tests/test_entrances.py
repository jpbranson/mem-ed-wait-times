from copy import deepcopy
from datetime import date
import json
import tempfile
from pathlib import Path
import unittest

from edwait.data import registry
from edwait.entrances import clear_entrance, geojson, main, review_rows, set_entrance

ON = date(2026, 9, 30)


def load():
    return {"facilities": deepcopy(registry())}


class EntranceToolTests(unittest.TestCase):
    def test_set_validates_with_the_eligibility_rule_and_clear_restores_campus(self):
        data = load()
        campus = next(f for f in data["facilities"] if f["slug"] == "memphis")["campus_point"]
        facility = set_entrance(data, "memphis", latitude=campus["latitude"] + .0004, longitude=campus["longitude"],
                                label="ER canopy, Walnut Grove Rd side", source_url="https://example.com/imagery",
                                method="imagery_review", note="Signage visible", on=ON)
        self.assertEqual(facility["emergency_entrance"]["reviewed_on"], "2026-09-30")
        self.assertEqual(facility["emergency_entrance"]["method"], "imagery_review")
        row = next(r for r in review_rows(data) if r["slug"] == "memphis")
        self.assertEqual(row["arrival"], "entrance")
        self.assertLess(row["offset_m"], 60)
        clear_entrance(data, "memphis")
        self.assertIsNone(facility["emergency_entrance"])

    def test_bad_entries_are_refused_without_changing_the_registry(self):
        data = load()
        before = deepcopy(data)
        cases = [dict(slug="nowhere"), dict(latitude=36.0), dict(source_url="http://insecure.example"),
                 dict(label=" "), dict(method="guess"), dict(reviewed_on=date(2026, 10, 1))]
        for case in cases:
            args = dict(slug="memphis", latitude=35.1286, longitude=-89.8610, label="ER entrance",
                        source_url="https://example.com/imagery", method="imagery_review", on=ON)
            args.update(case)
            slug = args.pop("slug")
            with self.subTest(case=case), self.assertRaises(ValueError):
                set_entrance(data, slug, **args)
        self.assertEqual(data, before)

    def test_cli_dry_run_list_and_geojson_write_nothing_unexpected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "facilities.json"
            path.write_text(json.dumps(load()), encoding="utf-8")
            original = path.read_text(encoding="utf-8")
            self.assertEqual(main(["--registry", str(path), "set", "tipton", "--lat", "35.5358", "--lon", "-89.6780",
                                   "--label", "ER entrance", "--source-url", "https://example.com/i", "--dry-run"]), 0)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(main(["--registry", str(path), "set", "tipton", "--lat", "35.5358", "--lon", "-89.6780",
                                   "--label", "ER entrance", "--source-url", "https://example.com/i"]), 0)
            saved = {f["slug"]: f for f in json.loads(path.read_text(encoding="utf-8"))["facilities"]}
            self.assertEqual(saved["tipton"]["emergency_entrance"]["label"], "ER entrance")
            output = Path(folder) / "review.geojson"
            main(["--registry", str(path), "geojson", str(output)])
            features = json.loads(output.read_text(encoding="utf-8"))["features"]
            self.assertEqual(sum(f["properties"]["kind"] == "campus_point" for f in features), 20)
            self.assertEqual(sum(f["properties"]["kind"] == "emergency_entrance" for f in features), 1)
        self.assertEqual(len(geojson(load())["features"]), 20)
