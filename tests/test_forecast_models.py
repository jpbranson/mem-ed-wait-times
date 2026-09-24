import unittest

import numpy as np

from edwait.data import timestamp
from edwait.forecast_models import (GATES, Profile, attach_intervals, evaluate, fourier, replay_candidates, trim)

DAY = 86400


class State:
    def __init__(self, values):
        self.last = values[-1]
    def extend(self, values, exog=None):
        return State(values)
    def forecast(self, steps, exog=None):
        return np.repeat(self.last, steps)


def fake(values, order, exog=None):
    return State(values)


def history(origin, value=10, days=28):
    return {s: {"wait_minutes": value} for s in range(origin - days * DAY, origin + DAY, 900)}


class CandidateTests(unittest.TestCase):
    def test_trim_drops_partial_start_but_not_recent_gaps(self):
        values = np.ones(2688)
        values[:12] = np.nan
        kept, start = trim(values)
        self.assertEqual((len(kept), start), (2676, 12))
        values = np.ones(2688)
        values[-100:-90] = np.nan
        self.assertIsNone(trim(values)[0])
        values = np.zeros(2688)
        values[-1] = np.nan
        self.assertIsNone(trim(values)[0])

    def test_fourier_uses_local_clock_across_dst(self):
        before = int(timestamp("2026-10-31T17:15:00Z").timestamp())  # 12:00-12:15 CDT
        after = int(timestamp("2026-11-02T18:15:00Z").timestamp())   # 12:00-12:15 CST
        np.testing.assert_allclose(fourier([before]), fourier([after]))

    def test_future_mutation_and_delay_use_only_available_slots(self):
        origin = DAY * 40
        slots = history(origin)
        for s in range(origin + 900, origin + DAY, 900):
            slots[s] = {"wait_minutes": 500}
        rows, fits = replay_candidates(slots, origin, origin + 3600, fitter=fake)
        at_origin = [r["prediction"] for r in rows if r["origin"] == origin]
        self.assertTrue(all(p == 10 for p in at_origin))
        self.assertTrue(all(f["status"] == "ok" for f in fits))
        slots[origin] = {"wait_minutes": 40}
        rows, _ = replay_candidates(slots, origin, origin + 3600, fitter=fake, delay_slots=1)
        self.assertTrue(all(r["prediction"] == 10 for r in rows if r["origin"] == origin))

    def test_profile_persistence_and_nonnegative(self):
        origin = DAY * 40
        labels = np.arange(origin - 28 * DAY + 900, origin + 1, 900)
        values = np.array([20.0 + (i % 8) for i in range(len(labels))])
        profile = Profile(values, labels)
        self.assertTrue(all(0 <= b <= 1 for b in profile.beta.values()))
        profile.beta[1] = 1.0
        self.assertEqual(profile.forecast(origin, -1000, 1), 0.0)

    def test_failed_fit_and_missing_origin_abstain(self):
        origin = DAY * 40
        def failed(values, order, exog=None):
            raise ValueError("nonconvergent_fit")
        rows, fits = replay_candidates(history(origin), origin, origin + 3600, fitter=failed)
        arima = [r for r in rows if r["model"].startswith("arima")]
        self.assertTrue(arima and all(r["prediction"] is None for r in arima))
        self.assertEqual({f["status"] for f in fits if f["model"].startswith("arima")}, {"fit_failed"})
        slots = history(origin)
        del slots[origin]
        rows, fits = replay_candidates(slots, origin, origin + 3600, fitter=fake)
        self.assertTrue(all(r["prediction"] is None for r in rows))

    def test_intervals_use_only_passed_targets(self):
        rows = []
        for i in range(200):
            origin = i * 3600
            rows.append({"facility": "x", "horizon_minutes": 60, "origin_ts": origin, "target_ts": origin + 3600,
                         "actual": 10 + (i % 5), "predictions": {"m": 10}})
        rows[-1]["actual"] = 9000
        attach_intervals(rows, ("m",))
        self.assertIsNone(rows[70]["intervals"]["m"])
        self.assertLess(rows[-1]["intervals"]["m"]["95"][1], 100)
        low, high = rows[150]["intervals"]["m"]["80"]
        self.assertTrue(10 <= low <= high <= 14)

    def test_gates_require_every_check(self):
        rows = []
        for i in range(7 * 24):
            actual = 50 + (i % 3)
            miss80, miss95 = i % 20 < 4, i % 20 == 0  # about 21% and 5% outside
            rows.append({"origin": f"2026-09-{10 + i // 24:02d}T00:00:00+00:00", "actual": actual,
                         "predictions": {"b": actual + 10, "c": actual + 1},
                         "intervals": {"c": {"80": [actual + 1, actual + 2] if miss80 else [actual - 1, actual + 2],
                                             "95": [actual + 1, actual + 3] if miss95 else [actual - 2, actual + 3]}}})
        result = evaluate(rows, "b", "c", 0.0, 1.0)
        self.assertTrue(result["passes"], result["checks"])
        self.assertEqual(result["gain_interval"], evaluate(rows, "b", "c", 0.0, 1.0)["gain_interval"])
        self.assertFalse(evaluate(rows, "b", "c", 0.02, 1.0)["passes"])
        self.assertFalse(evaluate(rows[:100], "b", "c", 0.0, 1.0)["checks"]["support"])
        self.assertFalse(evaluate(rows, "b", "c", 0.0, GATES["maximum_update_seconds"] + 1)["passes"])


if __name__ == "__main__":
    unittest.main()
