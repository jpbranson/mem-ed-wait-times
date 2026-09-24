import random
import unittest
from datetime import timedelta

from edwait.data import registry, timestamp
from edwait.relationships import (BIN, POLICY, benjamini_hochberg, candidate, confirm, correlate,
                                  deviations, episodes, neighbors, pair_test, period_tests, ranks)
from tests.fakes import record

START = 1_756_684_800  # 2025-09-01T00:00:00Z, an arbitrary hour boundary


def walk(rng, hours, step=5):
    value, values = 0.0, []
    for _ in range(hours):
        value = 0.9 * value + rng.gauss(0, step)
        values.append(value)
    return values


def hourly(values, offset=0):
    return {START + (i + offset) * BIN: v for i, v in enumerate(values)}


class RelationshipTests(unittest.TestCase):
    def test_neighbor_pairs_and_groups_come_from_campus_points(self):
        distances, groups = neighbors(registry(), 50)
        self.assertLess(distances["childrens", "memphis"], 1)
        self.assertEqual(sum(d <= 50 for d in distances.values()), 21)
        metro = next(g for g in groups if "memphis" in g)
        self.assertEqual(set(metro), {"arlington", "childrens", "collierville", "memphis", "tipton", "crittenden", "desoto"})
        self.assertNotIn("nea", {s for g in groups for s in g})

    def test_ranks_ties_and_benjamini_hochberg(self):
        self.assertEqual(ranks([0, 0, 5, 3]), [0.5, 0.5, 3, 2])
        self.assertEqual(benjamini_hochberg([0.01, None, 0.04, 0.03]), [0.03, None, 0.04, 0.04])

    def test_autocorrelation_shrinks_effective_sample_size(self):
        rng = random.Random(1)
        smooth = [(START + i * BIN, a, b) for i, (a, b) in enumerate(zip(walk(rng, 400), walk(rng, 400)))]
        noise = [(START + i * BIN, rng.random(), rng.random()) for i in range(400)]
        self.assertLess(correlate(smooth)["n_eff"], 150)
        self.assertGreater(correlate(noise)["n_eff"], 330)
        self.assertLessEqual(correlate(noise)["n_eff"], 400)

    def test_deviation_uses_only_earlier_local_days_and_needs_two_slots(self):
        start = timestamp("2026-08-01T05:00:00Z")  # Chicago midnight
        day = start + timedelta(days=21)
        def reading(at, wait):
            return record(observed=at.isoformat(), batch=at.isoformat(), wait=wait)
        rows = [reading(start + timedelta(minutes=15 * i + 1), 30) for i in range(21 * 96)]
        rows += [reading(day + timedelta(minutes=1), 90)]
        rows += [reading(day + timedelta(hours=2, minutes=15 * i + 1), 90) for i in range(8)]
        payload = {"start": "2026-08-01T00:00:00Z", "end": "2026-08-24T00:00:00Z", "records": rows}
        series, zero_share = deviations(payload, day.isoformat(), (day + timedelta(hours=4)).isoformat())
        bins = series["memphis"]
        # First hour has one slot (missing); later hours compare 90 with the earlier 30.
        self.assertNotIn(int(day.timestamp()), bins)
        self.assertEqual(bins[int(day.timestamp()) + 2 * BIN], 60)
        self.assertEqual(zero_share["memphis"], 0)

    def test_lead_detected_and_direction_dominates(self):
        rng = random.Random(7)
        base = walk(rng, 600)
        series = {"a": hourly(base), "b": hourly([v + rng.gauss(0, 1) for v in base], offset=2),
                  "c": hourly(walk(rng, 600))}
        for f in ("d", "e", "f", "g", "h"):
            series[f] = hourly(walk(rng, 600))
        tests = period_tests(series, list(series), POLICY)
        lead = next(t for t in tests if t["family"] == "lagged_change" and t["leader"] == "a" and t["follower"] == "b" and t["lag_hours"] == 2)
        self.assertGreater(lead["r"], 0.8)
        self.assertLess(abs(lead["reverse_r"]), 0.3)
        self.assertTrue(candidate(lead, POLICY))
        unrelated = next(t for t in tests if t["family"] == "co_deviation" and t["leader"] == "a" and t["follower"] == "c")
        self.assertFalse(candidate(unrelated, POLICY))

    def test_system_wide_swing_is_not_a_pair_relationship(self):
        rng = random.Random(3)
        common = walk(rng, 500, step=20)
        series = {f: hourly([c + rng.gauss(0, 2) for c in common]) for f in "abcdefgh"}
        pair = pair_test((series, series), "a", "b", 0, POLICY)
        self.assertGreater(pair["r"], 0.9)
        self.assertLess(abs(pair["system_wide"]["r"]), 0.3)
        self.assertFalse(candidate({**pair, "family": "co_deviation", "q": 0.001}, POLICY))

    def test_sparse_support_and_confirmation_sign(self):
        short = {"a": hourly(range(100)), "b": hourly(range(100))}
        self.assertEqual(pair_test((short, short), "a", "b", 0, POLICY)["state"], "insufficient_support")
        first = {"family": "co_deviation", "leader": "a", "follower": "b", "lag_hours": 0, "r": 0.5}
        robust = {"r": -0.5, "p": 0.001}
        later = {**first, "r": -0.5, "p": 0.001, "system_wide": robust, "residual_hour": robust}
        self.assertFalse(confirm([first], [later], POLICY)[0]["confirmed"])
        same = {**later, "r": 0.5, "system_wide": {"r": 0.4, "p": 0.001}, "residual_hour": {"r": 0.4, "p": 0.001}}
        self.assertTrue(confirm([first], [same], POLICY)[0]["confirmed"])

    def test_episodes_require_both_above_usual_in_consecutive_bins(self):
        a = hourly([15, 15, 15, 0, 15, 15])
        b = hourly([12, 12, 12, 30, 5, 12])
        found = episodes(a, b, 10)
        self.assertEqual([e["hours"] for e in found], [3, 1])
        self.assertEqual(found[0]["median_above_usual"], [15, 12])


if __name__ == "__main__":
    unittest.main()
