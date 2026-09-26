from datetime import datetime, timedelta, timezone
import unittest

from edwait.benefit import (POLICY, analyze, claims, confirmation_outcome, horizon_for, opportunities, profile,
                            select, summary)
from edwait.data import timestamp
from tests.fakes import record

DAY = "2026-09-13"
SCREEN = {h: 5 for h in (15, 30, 60, 120)}


def routes(**minutes):
    return [{"origin": "o", "slug": slug, "seconds": {k: m * 60 for k in ("night", "am", "pm")}} for slug, m in minutes.items()]


def row(D, A, day=DAY, p=5, A60=None, stress=None):
    return {"D": D, "A": A, "day": day, "p90_c": p, "p90_a": p, "A60": A60, "A_stress": stress}


class BenefitRuleTests(unittest.TestCase):
    def test_profiles_follow_local_weekday_peaks(self):
        cases = {"2026-09-14T12:30:00Z": "am", "2026-09-14T14:59:00Z": "am", "2026-09-14T15:00:00Z": "night",
                 "2026-09-14T21:00:00Z": "pm", "2026-09-12T12:30:00Z": "night", "2026-09-14T17:00:00Z": "night"}
        for at, expected in cases.items():
            self.assertEqual(profile(timestamp(at)), expected, at)
        self.assertEqual([horizon_for(m) for m in (7, 15, 16, 61, 120, 121)], [15, 15, 30, 120, 120, None])

    def test_opportunity_arithmetic_uses_readings_at_each_arrival(self):
        slot = int(timestamp("2026-09-13T08:00:00Z").timestamp()) // 900  # Saturday: night profile
        readings = {"c": {slot: 100, slot + 1: 90}, "a": {slot: 50, slot + 2: 80}}
        screen = {"c": {datetime(2026, 9, 13).date(): SCREEN}, "a": {datetime(2026, 9, 13).date(): SCREEN}}
        start, end = timestamp("2026-09-13T08:00:00Z"), timestamp("2026-09-13T08:15:00Z")
        [r] = opportunities(readings, screen, routes(c=10, a=20), start, end, timestamp("2026-09-16T00:00:00Z"))
        self.assertEqual((r["closest"], r["alternative"], r["profile"]), ("c", "a", "night"))
        self.assertEqual(r["D"], (10 + 100) - (20 + 50))
        self.assertEqual(r["A"], (10 + 90) - (20 + 80))  # Advantage gone at arrival: does not hold.
        self.assertIsNone(r["A60"])  # No readings an hour after arrival.
        self.assertAlmostEqual(r["A_stress"], (10 + 90) - (24 + 80))
        # Missing current or arrival readings, long drives and post-holdout arrivals create no row.
        for patch in ({"a": {slot + 2: 80}}, {"a": {slot: 50}}, {"c": {slot + 1: 90}}):
            self.assertEqual(opportunities({**readings, **patch}, screen, routes(c=10, a=20), start, end,
                                           timestamp("2026-09-16T00:00:00Z")), [])
        self.assertEqual(opportunities(readings, screen, routes(c=10, a=121), start, end, timestamp("2026-09-16T00:00:00Z")), [])
        self.assertEqual(opportunities(readings, screen, routes(c=10, a=20), start, end, timestamp("2026-09-13T08:20:00Z")), [])
        unsupported = {**screen, "a": {datetime(2026, 9, 13).date(): {**SCREEN, 30: None}}}
        self.assertEqual(opportunities(readings, unsupported, routes(c=10, a=20), start, end, timestamp("2026-09-16T00:00:00Z")), [])

    def test_rules_claims_precision_and_secondary_outcomes(self):
        rows = [row(5, 1, A60=1), row(15, -1, A60=-3), row(25, 5, stress=-1), row(50, 10, stress=2)]
        counts = {name: len(claims(rows, [name, kind, value])) for name, kind, value in POLICY["rules"]}
        self.assertEqual(counts, {"F0": 4, "F10": 3, "F20": 2, "F30": 1, "F45": 1, "F60": 0, "S1": 2, "S0.5": 2})
        result = summary(rows, ["F10", "fixed", 10], [DAY])
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertEqual((result["claims"], result["claim_days"], result["median_A"]), (3, 1, 5))
        self.assertEqual(result["later"], {"n": 1, "precision": 0.0})
        self.assertEqual(result["stress"], {"n": 2, "precision": 0.5})
        self.assertIsNone(summary([], ["F10", "fixed", 10], [])["precision"])

    def test_bootstrap_is_seeded_and_bounded(self):
        rows = [row(20, 5 if i % 5 else -1, day=f"2026-09-{i % 9 + 1:02d}") for i in range(60)]
        days = sorted({r["day"] for r in rows})
        first = summary(rows, ["F10", "fixed", 10], days, POLICY["bootstrap"])["precision_interval"]
        self.assertEqual(first, summary(rows, ["F10", "fixed", 10], days, POLICY["bootstrap"])["precision_interval"])
        self.assertTrue(0 <= first[0] <= 0.8 <= first[1] <= 1)
        held = [row(20, 5, day=d) for d in days]
        self.assertEqual(summary(held, ["F10", "fixed", 10], days, POLICY["bootstrap"])["precision_interval"], [1, 1])

    def test_selection_and_confirmation_gates(self):
        def result(claims, precision, lower, days=6):
            return {"claims": claims, "claim_days": days, "precision": precision, "precision_interval": [lower, 1]}
        results = {"F10": result(100, .92, .85), "F20": result(60, .95, .9), "S1": result(100, .93, .86), "F0": result(400, .6, .5)}
        self.assertEqual(select(results), "F10")  # Tie on claims: the fixed rule wins.
        self.assertEqual(select({**results, "F10": result(100, .92, .79)}), "S1")
        self.assertEqual(select({**results, "F10": result(100, .92, .85, days=4), "S1": result(49, .99, .95)}), "F20")
        self.assertIsNone(select({"F0": result(400, .6, .5)}))
        gates = {"claims": 20, "claim_days": 3}
        self.assertEqual(confirmation_outcome({**gates, "precision": .9}), "confirmed")
        self.assertEqual(confirmation_outcome({**gates, "precision": .89}), "failed")
        self.assertEqual(confirmation_outcome({**gates, "claims": 19, "precision": 1}), "inconclusive")
        self.assertEqual(confirmation_outcome({**gates, "claim_days": 2, "precision": 1}), "inconclusive")

    def test_analysis_never_reads_the_m5_holdout(self):
        start = timestamp("2026-08-20T05:00:00Z")
        records = []
        for i in range(27 * 96):
            at = start + timedelta(minutes=15 * i)
            for slug, wait in (("memphis", 100), ("desoto", 50)):
                records.append(record(facility=slug, wait=wait, batch=at.isoformat(), observed=(at + timedelta(seconds=5)).isoformat()))
        # Post-holdout readings that would flip every late outcome if they were read.
        for i in range(8):
            at = timestamp("2026-09-16T00:00:00Z") + timedelta(minutes=15 * i)
            records.append(record(facility="desoto", wait=500, batch=at.isoformat(), observed=(at + timedelta(seconds=5)).isoformat()))
        policy = {**POLICY, "periods": {"discovery": ["2026-09-05T00:00:00Z", "2026-09-10T00:00:00Z"],
                                        "confirmation": ["2026-09-10T00:00:00Z", "2026-09-16T00:00:00Z"]}}
        report = analyze({"records": records}, {"routes": routes(memphis=10, desoto=20)}, policy)
        self.assertLess(report["latest_batch_used"], "2026-09-16T00:00:00")
        self.assertEqual(report["records_used"], len(records) - 8 - sum(
            1 for r in records[:-8] if r["batch_id"] >= "2026-09-16T00:00:00"))
        discovery, confirmation = report["periods"]["discovery"]["rules"], report["periods"]["confirmation"]["rules"]
        self.assertEqual(discovery["F30"]["precision"], 1.0)
        self.assertEqual(discovery["F45"]["claims"], 0)
        self.assertEqual(confirmation["F30"]["claims"], confirmation["F0"]["claims"])
        self.assertTrue(all(r["precision"] in (1.0, None) for r in confirmation.values()))
        self.assertEqual(report["selected_rule"], "F30")  # Equal claims: fixed, then the larger threshold.
        self.assertEqual(report["confirmation_outcome"], "confirmed")


if __name__ == "__main__":
    unittest.main()
