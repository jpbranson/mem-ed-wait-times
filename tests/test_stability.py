from datetime import timedelta
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from edwait.analysis import BaselineIndex
from edwait.areas import areas
from edwait.data import History, registry, timestamp
from edwait.prepare import build_comparisons
from edwait.stability import POLICY, reference_window, summarize, window_points
from edwait.travel import build_travel
from tests.fakes import record

NOW = timestamp("2026-09-14T17:00:00Z")
START = timestamp("2026-09-04T05:00:00Z")  # Chicago midnight; ten full local days before NOW


def sawtooth(skip=()):
    # Rises 5 minutes per slot for seven slots, then drops 35: changes are not sorted in time.
    rows = [record(batch=(START + timedelta(minutes=15*i)).isoformat(),
                   observed=(START + timedelta(minutes=15*i)).isoformat(), wait=(i % 8) * 5)
            for i in range(960) if i not in skip]
    # Today's reading must never describe its own reference window.
    rows.append(record(batch=NOW.isoformat(), observed=NOW.isoformat(), wait=99999))
    return rows


def stability(rows):
    start, end = reference_window(NOW, POLICY["lookback_days"])
    return summarize(window_points(BaselineIndex(rows), "memphis", start, end))


class StabilityTests(unittest.TestCase):
    def test_sorted_magnitudes_and_signed_shares_per_horizon(self):
        by_horizon = {row["horizon_minutes"]: row for row in stability(sawtooth())}
        fifteen, thirty = by_horizon[15], by_horizon[30]
        self.assertEqual((fifteen["pairs"], fifteen["days"]), (959, 10))
        self.assertEqual((fifteen["median_abs_change"], fifteen["p90_abs_change"]), (5, 35))
        self.assertEqual(fifteen["rise_share"], 0)
        self.assertAlmostEqual(fifteen["fall_share"], 119 / 959)  # drops after slots 7, 15, ..., 951
        # Two slots apart: +10 six times per cycle, -30 twice; +10 counts as a meaningful rise.
        self.assertEqual((thirty["median_abs_change"], thirty["p90_abs_change"]), (10, 30))
        self.assertAlmostEqual(thirty["rise_share"] + thirty["fall_share"], 1)
        self.assertAlmostEqual(thirty["fall_share"], 240 / 958, places=2)

    def test_gaps_are_not_bridged_and_sparse_history_is_unsupported(self):
        self.assertEqual(stability(sawtooth(skip={400}))[0]["pairs"], 957)
        sparse = stability(sawtooth(skip=set(range(96, 960))))
        self.assertTrue(all(row["median_abs_change"] is None and row["rise_share"] is None for row in sparse))

    def test_travel_movement_uses_sorted_magnitudes(self):
        # Regression: M2's 90th percentile was read from chronological order.
        memphis = next(f for f in build_travel(History(records=sawtooth()), NOW)["facilities"] if f["slug"] == "memphis")
        self.assertEqual([m["absolute_change_p90"] for m in memphis["movement"]][:2], [35, 30])

    def test_comparison_artifact_carries_schema_valid_stability(self):
        artifact = build_comparisons(History(records=sawtooth()), NOW, facilities=[{"slug": "memphis"}])
        self.assertEqual(artifact["stability"]["method_version"], "wait-stability-v1")
        self.assertEqual(artifact["stability"]["source_end"], "2026-09-14T05:00:00+00:00")
        self.assertEqual(artifact["facilities"][0]["stability"][0]["p90_abs_change"], 35)
        schema = json.loads(Path("docs/comparisons.schema.json").read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(artifact)
        artifact["facilities"][0]["stability"][0]["rise_share"] = 1.5
        self.assertTrue(list(validator.iter_errors(artifact)))
        del artifact["facilities"][0]["stability"]
        self.assertTrue(list(validator.iter_errors(artifact)))


class AreaTests(unittest.TestCase):
    def test_areas_reuse_m3_groups_and_registry_states(self):
        result = {a["label"]: a for a in areas(registry())}
        self.assertEqual(list(result)[0], "All hospitals")
        self.assertEqual(len(result["All hospitals"]["slugs"]), 20)
        self.assertEqual(set(result["Memphis area"]["slugs"]),
                         {"arlington", "childrens", "collierville", "memphis", "tipton", "crittenden", "desoto"})
        self.assertEqual(result["Booneville / North Mississippi / Union County"]["slugs"],
                         ["booneville", "north-mississippi", "union-county"])
        self.assertEqual({k: len(result[k]["slugs"]) for k in ("Tennessee", "Arkansas", "Mississippi")},
                         {"Tennessee": 7, "Arkansas": 2, "Mississippi": 11})
        self.assertEqual(len(result), 6, "two-hospital neighbor pairs are not summarized as areas")
        self.assertEqual(len({a["key"] for a in result.values()}), 6)


if __name__ == "__main__":
    unittest.main()
