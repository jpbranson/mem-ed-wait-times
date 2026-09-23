import unittest
from datetime import date, datetime, timedelta, timezone

from edwait.analysis import BaselineIndex, DEFAULT_POLICY, ZONE, expected_slots, quantile, percentile
from edwait.data import History
from edwait.prepare import build_comparisons


def row(at, value=20, facility="memphis", metric="CV_ED_Wait"):
    at = at.astimezone(timezone.utc)
    return {"facility": facility, "metric": metric, "wait_minutes": value,
            "observed_at": at.isoformat(), "batch_id": at.isoformat(), "latency_ms": 100}


def cohort(target=date(2026,9,14), hours=range(9,12), exclude=None, value=20):
    output=[]
    for delta in range(28,0,-1):
        day=target-timedelta(days=delta)
        for hour in hours:
            for minute in (0,15,30,45):
                if exclude and exclude(day,hour,minute):
                    continue
                output.append(row(datetime(day.year,day.month,day.day,hour,minute,tzinfo=ZONE),value))
    return output


class AnalysisTests(unittest.TestCase):
    def test_linear_quantiles_and_midrank_ties(self):
        self.assertEqual(quantile([0,10,20,30],.25),7.5)
        self.assertEqual(quantile([0,10,20,30],.5),15)
        self.assertEqual(quantile([0,10,20,30],.75),22.5)
        self.assertEqual(percentile([0,0,0,10],0),37.5)

    def test_same_day_and_future_values_cannot_leak_into_baseline(self):
        rows=cohort()
        target=datetime(2026,9,14,10,tzinfo=ZONE)
        before=BaselineIndex(rows).compare("memphis",target.isoformat(),100)
        after=BaselineIndex(rows+[row(target-timedelta(hours=1),9999),row(target,9999),row(target+timedelta(days=1),9999)]).compare("memphis",target.isoformat(),100)
        self.assertEqual(before,after)
        self.assertEqual(before["model"]["median"],20)
        self.assertEqual(before["delta"],80)
        self.assertEqual(before["percentile"],100)
        self.assertEqual(before["model"]["support"]["days"],20)
        self.assertEqual(before["model"]["reference_end_exclusive"],"2026-09-14")

    def test_sparse_days_do_not_count_as_adequate_support(self):
        rows=cohort(exclude=lambda day,hour,minute: minute!=0)
        model=BaselineIndex(rows).baseline("memphis",date(2026,9,14),10)
        self.assertEqual(model["state"],"insufficient_history")
        self.assertEqual(model["support"]["days"],0)
        self.assertIsNone(model["median"])

    def test_wider_hour_fallback_is_explicit(self):
        rows=cohort(hours=range(8,13),exclude=lambda day,hour,minute: hour==9)
        model=BaselineIndex(rows).baseline("memphis",date(2026,9,14),10)
        self.assertEqual(model["group"],"wider_hours")
        self.assertEqual(model["state"],"supported")
        self.assertEqual(model["support"]["coverage"],.8)

    def test_seven_weekend_days_use_broader_fallback_not_precise_weekend_reference(self):
        target=date(2026,9,12)
        missing_day=date(2026,9,5)
        rows=cohort(target,hours=range(8,13),exclude=lambda day,hour,minute:day==missing_day)
        model=BaselineIndex(rows).baseline("memphis",target,10)
        self.assertEqual(model["group"],"all_days")
        self.assertEqual(model["state"],"supported")
        self.assertEqual(model["support"]["days"],27)

    def test_zero_is_a_value_and_small_changes_do_not_trigger_unusualness(self):
        index=BaselineIndex(cohort(value=0))
        at="2026-09-14T15:00:00Z"
        self.assertEqual(index.compare("memphis",at,0)["percentile"],50)
        self.assertEqual(index.compare("memphis",at,5)["unusual"],"no_large_departure")
        self.assertEqual(index.compare("memphis",at,10)["unusual"],"above_usual")

    def test_duplicate_cadence_slots_and_other_metrics_do_not_inflate_support(self):
        rows=cohort()
        before=BaselineIndex(rows).baseline("memphis",date(2026,9,14),10)
        duplicates=[dict(r,batch_id=r["batch_id"],metric="OTHER",wait_minutes=1000) for r in rows]
        after=BaselineIndex(rows+rows+duplicates).baseline("memphis",date(2026,9,14),10)
        self.assertEqual(before,after)

    def test_dst_denominators_and_midnight_local_day(self):
        self.assertEqual(expected_slots(date(2026,3,8),2,1,900),8)
        self.assertEqual(expected_slots(date(2026,11,1),1,1,900),16)
        index=BaselineIndex([])
        result=index.compare("memphis","2026-09-14T00:01:00Z",10)
        self.assertEqual(result["model"]["reference_end_exclusive"],"2026-09-13")

    def test_trend_uses_past_reference_median_and_requires_gap_free_support(self):
        at=datetime(2026,9,14,15,tzinfo=timezone.utc)
        rows=[row(at-timedelta(minutes=m),v) for m,v in [(75,10),(60,20),(45,30)]]
        rows += [row(at,999),row(at+timedelta(minutes=30),999)]
        trend=BaselineIndex(rows).trend("memphis",at.isoformat(),40)
        self.assertEqual(trend,{"state":"rising","delta":20,"samples":3})
        self.assertEqual(BaselineIndex([rows[0],rows[2]]).trend("memphis",at.isoformat(),40)["state"],"insufficient_recent_history")

    def test_empty_and_future_history_cannot_manufacture_current_context(self):
        at=datetime(2026,9,14,15,tzinfo=timezone.utc)
        artifact=build_comparisons(History(records=[row(at+timedelta(days=1))]),at,
                                   facilities=[{"slug":"memphis"}])
        self.assertEqual(artifact["facilities"][0]["history"],[])
        self.assertEqual(artifact["source_range"],{"start":None,"end":None})
        self.assertEqual(artifact["facilities"][0]["models"]["2026-09-14"][10]["state"],"insufficient_history")


if __name__=="__main__":
    unittest.main()
