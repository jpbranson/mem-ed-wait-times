import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from edwait.data import registry, timestamp
from edwait.latest import build_latest, publish_latest
from tests.fakes import MemoryS3, attempt, record

spec = importlib.util.spec_from_file_location("collector", "mem-ed-lambda.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class LatestTests(unittest.TestCase):
    def setUp(self):
        self.facilities = [f for f in registry() if f["slug"] in ("memphis", "desoto")]
        self.generated = "2026-09-14T01:00:00Z"

    def build(self, previous=None, rows=None, attempts=None):
        return build_latest(previous, rows or [], attempts or {}, self.facilities, generated_at=self.generated)

    def test_partial_failure_retains_success_and_separate_attempt(self):
        before = self.build(rows=[record()], attempts={"memphis": attempt()})
        after = self.build(before, attempts={"memphis": attempt("2026-09-14T00:15:00Z", "failed"), "desoto": attempt(state="failed")})
        item = next(f for f in after["facilities"] if f["slug"] == "memphis")
        self.assertEqual(item["last_success"], record())
        self.assertEqual(item["reporting_state"], "failed")
        self.assertEqual(after["coverage"]["failed_latest_attempt"], 2)
        self.assertEqual(after["coverage"]["missing"], 1)

    def test_old_batch_does_not_roll_back_new_success_or_failure(self):
        newer = record(wait=50, batch="2026-09-14T00:15:00Z", observed="2026-09-14T00:16:00Z")
        previous = self.build(rows=[newer], attempts={"memphis": attempt("2026-09-14T00:30:00Z", "failed")})
        after = self.build(previous, [record()], {"memphis": attempt()})
        self.assertEqual(after["facilities"][0]["last_success"], newer)
        self.assertEqual(after["facilities"][0]["reporting_state"], "failed")

    def test_equal_zero_is_success_not_feed_failure_and_other_metric_is_excluded(self):
        after = self.build(rows=[record(wait=0), record(wait=123, metric="OTHER")], attempts={"memphis": attempt()})
        self.assertEqual(after["facilities"][0]["last_success"]["wait_minutes"], 0)
        self.assertEqual(after["facilities"][0]["reporting_state"], "reporting")

    def test_conditional_publication_retry_cache_and_failed_write_retention(self):
        s3 = MemoryS3()
        s3.conflict_once = True
        publish_latest(s3, "web", [record()], {"memphis": attempt()}, self.facilities)
        before = s3.objects["web", "data/latest.json"]["Body"]
        self.assertIn("no-store", s3.objects["web", "data/latest.json"]["CacheControl"])
        s3.fail_put = "latest.json"
        with self.assertRaises(Exception):
            publish_latest(s3, "web", [], {"memphis": attempt(state="failed")}, self.facilities)
        self.assertEqual(s3.objects["web", "data/latest.json"]["Body"], before)

    def test_corrupt_previous_artifact_is_not_treated_as_absent(self):
        s3 = MemoryS3()
        s3.put_object(Bucket="web", Key="data/latest.json", Body=b"corrupt")
        with self.assertRaises(ValueError):
            publish_latest(s3, "web", [record()], {}, self.facilities)
        self.assertEqual(s3.objects["web", "data/latest.json"]["Body"], b"corrupt")

    def test_all_failed_collection_publishes_attempts_before_raising(self):
        s3 = MemoryS3()
        attempts = {f: attempt(state="failed") for f in collector.FACILITIES}
        with patch.object(collector.boto3, "client", return_value=s3), patch.object(collector, "collect", return_value=([], attempts)), patch.dict(os.environ, {"BUCKET": "raw", "LATEST_BUCKET": "web"}):
            with self.assertRaisesRegex(RuntimeError, "failure artifact published"):
                collector.lambda_handler({}, None)
        self.assertEqual(s3.json("web", "data/latest.json")["coverage"]["failed_latest_attempt"], 20)
        self.assertTrue(any(k.startswith("operations/collection/") for b, k in s3.objects))
        self.assertFalse(any(k.startswith("raw/") for b, k in s3.objects))

    def test_collector_deadline_records_unattempted_facilities(self):
        context = Mock()
        context.get_remaining_time_in_millis.return_value = 20000
        with patch.object(collector, "fetch_facility") as fetch:
            records, attempts = collector.collect(timestamp("2026-09-14T00:00:00Z"), context)
        fetch.assert_not_called()
        self.assertEqual(records, [])
        self.assertEqual(len(attempts), 20)
        self.assertEqual({a["error_code"] for a in attempts.values()}, {"collection_deadline"})

    def test_successful_handler_preserves_raw_then_publishes_operations_and_latest(self):
        s3 = MemoryS3()
        attempts = {f: attempt(state="failed") for f in collector.FACILITIES}
        attempts["memphis"] = attempt()
        with patch.object(collector.boto3, "client", return_value=s3), patch.object(collector, "collect", return_value=([record()], attempts)), patch.dict(os.environ, {"BUCKET": "raw", "LATEST_BUCKET": "web"}):
            result = collector.lambda_handler({}, None)
        self.assertEqual(result["records"], 1)
        keys = list(s3.objects)
        self.assertTrue(keys[0][1].startswith("raw/ed_wait/"))
        self.assertEqual(json.loads(s3.objects[keys[0]]["Body"]), record())
        self.assertTrue(keys[1][1].startswith("operations/collection/"))
        self.assertEqual(keys[2], ("web", "data/latest.json"))
        self.assertEqual(s3.json("web", "data/latest.json")["coverage"]["failed_latest_attempt"], 19)

    def test_expected_metric_absence_and_request_failure_are_separate(self):
        import requests
        with patch.object(collector, "FACILITIES", ["memphis", "desoto"]), patch.object(collector.time, "sleep"), patch.object(collector, "fetch_facility", side_effect=[[record(metric="OTHER")], requests.Timeout()]):
            records, attempts = collector.collect(timestamp("2026-09-13T23:59:00Z"))
        self.assertEqual(len(records), 1)
        self.assertEqual(attempts["memphis"]["error_code"], "expected_metric_missing")
        self.assertEqual(attempts["desoto"]["error_code"], "request_failed")

    def test_upstream_validation_does_not_truncate_decimals_or_accept_empty(self):
        session = Mock()
        response = session.get.return_value
        response.elapsed.total_seconds.return_value = 0.2
        for bad in ({}, [], {"CV_ED_Wait": 1.5}, {"CV_ED_Wait": True}, {"CV_ED_Wait": None}):
            response.json.return_value = bad
            with self.assertRaises(ValueError):
                collector.fetch_facility(session, "memphis", "2026-09-13T00:00:00Z")
        response.json.return_value = {"CV_ED_Wait": "0"}
        self.assertEqual(collector.fetch_facility(session, "memphis", "2026-09-13T00:00:00Z")[0]["wait_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
