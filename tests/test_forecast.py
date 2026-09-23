import unittest
from datetime import timedelta

from edwait.data import timestamp
from edwait.forecast import grid, metrics, predictions, replay
from tests.fakes import record


def observation(at, value, metric="CV_ED_Wait"):
    return record(observed=at, batch=at, wait=value, metric=metric)


class ForecastTests(unittest.TestCase):
    def test_slot_boundary_ties_zero_negative_and_metric(self):
        rows = [observation("2026-09-01T00:00:00Z", 0), observation("2026-09-01T00:14:59Z", 5),
                observation("2026-09-01T00:14:59Z", 7), observation("2026-09-01T00:15:00Z", 0),
                observation("2026-09-01T00:29:00Z", -1), observation("2026-09-01T00:14:00Z", 99, "OTHER")]
        a, counts = grid(rows, "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")
        b, _ = grid(list(reversed(rows)), "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z")
        self.assertEqual(a, b)
        self.assertEqual([r["wait_minutes"] for _, r in sorted(a["memphis"].items())], [7, 0])
        self.assertEqual(counts["negative_records_excluded"], 1)

    def test_missing_and_delayed_availability(self):
        origin = int(timestamp("2026-09-02T00:00:00Z").timestamp())
        slots = {origin: {"wait_minutes": 0}, origin - 900: {"wait_minutes": 20}}
        self.assertEqual(predictions(slots, origin, 15, 10)["carry_forward"], 0)
        self.assertEqual(predictions(slots, origin, 15, 10, 1)["carry_forward"], 20)
        self.assertTrue(all(v is None for v in predictions(slots, origin + 900, 15, 10).values()))
        self.assertIsNone(predictions(slots, origin, 15, 10)["daily_naive"])

    def test_future_mutation_does_not_change_forecasts_across_midnight(self):
        start = timestamp("2026-08-01T00:00:00Z")
        rows = [observation((start + timedelta(minutes=15 * i + 1)).isoformat(), i % 70) for i in range(36 * 96)]
        payload = {"start": "2026-08-01T00:00:00Z", "end": "2026-09-06T00:00:00Z", "records": rows}
        _, before = replay(payload, "2026-09-05T04:00:00Z", "2026-09-05T08:00:00Z")
        for row in rows:
            if timestamp(row["observed_at"]) >= timestamp("2026-09-05T04:00:00Z"):
                row["wait_minutes"] = 9000
        _, after = replay(payload, "2026-09-05T04:00:00Z", "2026-09-05T08:00:00Z")
        self.assertEqual([r["predictions"] for r in before if r["origin"].endswith("04:00:00+00:00")],
                         [r["predictions"] for r in after if r["origin"].endswith("04:00:00+00:00")])
        self.assertTrue(all(timestamp(r["target"]) < timestamp("2026-09-05T08:00:00Z") for r in after))

    def test_dst_utc_slots_are_distinct(self):
        rows = [observation("2026-11-01T06:05:00Z", 10), observation("2026-11-01T07:05:00Z", 20)]
        slots, _ = grid(rows, "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z")
        self.assertEqual(len(slots["memphis"]), 2)
        self.assertEqual(max(slots["memphis"]) - min(slots["memphis"]), 3600)

    def test_missing_targets_and_abstention_denominators(self):
        rows = [{"origin": "2026-09-01T00:00:00Z", "actual": actual, "predictions": {"carry_forward": pred}}
                for actual, pred in ((0, 2), (None, 5), (4, None))]
        result = metrics(rows, "carry_forward")
        self.assertEqual((result["targets"], result["missing_targets"], result["scored"], result["abstentions_with_target"]), (2, 1, 1, 1))
        self.assertEqual(result["mae"], 2)


if __name__ == "__main__":
    unittest.main()
