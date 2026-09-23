import unittest

import numpy as np

from edwait.forecast_arima import replay_facility, supported


class State:
    def __init__(self, values):
        self.last = values[-1]
    def extend(self, values):
        return State(values)
    def forecast(self, steps):
        return np.repeat(self.last, steps)


class ArimaReplayTests(unittest.TestCase):
    def test_support_gaps_and_zero(self):
        self.assertTrue(supported(np.zeros(2688)))
        self.assertFalse(supported(np.zeros(20)))
        values = np.ones(2688)
        values[100:105] = np.nan
        self.assertFalse(supported(values))

    def test_daily_fit_never_sees_future_and_hourly_updates_only_arrivals(self):
        origin = 86400 * 30
        slots = {i: {"wait_minutes": 1} for i in range(origin - 28 * 86400, origin + 9000, 900)}
        for i in range(origin + 900, origin + 9000, 900):
            slots[i] = {"wait_minutes": 100}
        inputs = []
        def fit(values, order):
            inputs.append(values.copy())
            return State(values)
        rows, _ = replay_facility(slots, origin, origin + 10800, fitter=fit)
        self.assertTrue(all(np.all(v == 1) for v in inputs))
        self.assertTrue(all(r["prediction"] == 1 for r in rows if r["origin"] == origin))
        self.assertTrue(all(r["prediction"] == 100 for r in rows if r["origin"] == origin + 3600))

    def test_failed_fit_abstains(self):
        origin = 86400 * 30
        slots = {i: {"wait_minutes": 0} for i in range(origin - 28 * 86400, origin + 3600, 900)}
        def failed(values, order):
            raise ValueError("nonconvergent_fit")
        rows, fits = replay_facility(slots, origin, origin + 3600, fitter=failed)
        self.assertTrue(all(r["prediction"] is None for r in rows))
        self.assertTrue(all(r["status"] == "fit_failed" for r in fits))


if __name__ == "__main__":
    unittest.main()
