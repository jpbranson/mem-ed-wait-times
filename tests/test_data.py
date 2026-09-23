import gzip
import json
import unittest
from datetime import date, datetime, timezone

from edwait.data import coverage, load_history, local_time, registry, timestamp, validate_record
from lambda_function import compact
from tests.fakes import MemoryS3, record


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.s3 = MemoryS3()
        self.start = timestamp("2026-09-13T00:00:00Z")
        self.end = timestamp("2026-09-14T01:00:00Z")

    def raw(self, rows, key="raw/ed_wait/dt=2026-09-13/a.jsonl"):
        self.s3.put_object(Bucket="test", Key=key, Body=("\n".join(json.dumps(r) for r in rows) + "\n").encode())

    def load(self, **kwargs):
        return load_history(self.s3, "test", self.start, self.end, now=self.end, **kwargs)

    def test_overlap_reads_only_verified_compacted_snapshot(self):
        self.raw([record()])
        compact("test", date(2026, 9, 13), self.s3)
        self.s3.reads.clear()
        result = self.load()
        self.assertEqual(result.records, [record()])
        self.assertEqual(result.partitions[0]["source"], "compacted")
        self.assertFalse(any(k.startswith("raw/") for k in self.s3.reads))

    def test_partial_compaction_and_late_raw_fall_back_to_raw(self):
        self.raw([record()])
        compact("test", date(2026, 9, 13), self.s3)
        self.raw([record("desoto")], "raw/ed_wait/dt=2026-09-13/b.jsonl")
        self.s3.reads.clear()
        result = self.load()
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.partitions[0]["source"], "raw")
        self.assertFalse(any(k.endswith(".gz") for k in self.s3.reads))

    def test_legacy_compaction_is_unverified_and_never_mixed(self):
        key = "compacted/ed_wait/dt=2026-09-13/data.jsonl.gz"
        self.s3.put_object(Bucket="test", Key=key, Body=gzip.compress(json.dumps(record()).encode()))
        self.assertEqual(self.load().partitions[0]["completeness"], "unverified_no_raw")
        self.raw([record(wait=99)])
        self.assertEqual(self.load().records[0]["wait_minutes"], 99)

    def test_current_day_uses_raw_even_with_matching_compaction(self):
        row = record(batch="2026-09-14T00:00:00Z")
        self.raw([row], "raw/ed_wait/dt=2026-09-14/a.jsonl")
        compact("test", date(2026, 9, 14), self.s3)
        self.assertEqual(self.load().partitions[1]["completeness"], "open_day")

    def test_deduplication_ties_offsets_and_metric_separation(self):
        first = record(wait=10)
        same_key = record(wait=20, batch="2026-09-13T18:59:00-05:00")
        self.raw([first, first, same_key, record(wait=0, metric="OTHER")])
        self.raw([record(wait=40)], "raw/ed_wait/dt=2026-09-13/z.jsonl")
        result = self.load()
        self.assertEqual([r["wait_minutes"] for r in result.records], [40])
        self.assertEqual(result.duplicate_records, 3)
        self.assertEqual(result.conflicting_duplicates, 2)
        self.assertEqual(len(self.load(metric=None).records), 2)

    def test_utc_batch_bounds_preserve_midnight_observation(self):
        self.raw([record()])
        result = load_history(self.s3, "test", self.start, timestamp("2026-09-14T00:00:00Z"), now=self.end)
        self.assertEqual(result.records[0]["observed_at"], record()["observed_at"])
        self.assertEqual(local_time(record()["observed_at"]).date(), date(2026, 9, 13))
        self.assertEqual(local_time("2026-11-01T06:30:00Z").hour, 1)
        self.assertEqual(local_time("2026-11-01T07:30:00Z").hour, 1)
        self.assertNotEqual(local_time("2026-11-01T06:30:00Z").utcoffset(), local_time("2026-11-01T07:30:00Z").utcoffset())
        with self.assertRaises(ValueError):
            load_history(self.s3, "test", datetime(2026, 9, 13), self.end)

    def test_empty_input_and_missing_facilities(self):
        result = self.load()
        self.assertEqual(result.records, [])
        summary = coverage(result, ["memphis", "desoto"])
        self.assertEqual(summary["observed_batches"], 0)
        self.assertTrue(all(p["source"] == "missing" for p in summary["partitions"]))

    def test_malformed_records_wrong_partition_future_and_zero(self):
        self.raw([record(wait=0), record(wait=True), {"facility": "bad"},
                  record(batch="2026-09-12T00:00:00Z"), record(observed="2099-01-01T00:00:00Z")])
        self.s3.put_object(Bucket="test", Key="raw/ed_wait/dt=2026-09-13/b.jsonl", Body=b"not json\n\n")
        result = self.load()
        self.assertEqual(result.rejected_records, 5)
        self.assertEqual(result.records, [record(wait=0)])

    def test_gaps_and_missing_facilities_are_reported(self):
        self.raw([record(batch="2026-09-13T23:00:00Z"), record()])
        summary = coverage(self.load(), ["memphis", "desoto"])
        self.assertEqual(summary["missing_facility_observations"], 2)
        self.assertEqual(summary["collection_gaps"][0]["seconds"], 3540)

    def test_registry_preserves_all_twenty_slugs_and_evidence_backed_travel_fields(self):
        from edwait.travel import eligibility, point_problem
        facilities = registry()
        self.assertEqual(len({f["slug"] for f in facilities}), 20)
        self.assertIn("huntingdon", [f["slug"] for f in facilities])
        now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
        for f in facilities:
            self.assertIn(f["active_status"], ("active", "unknown"))
            self.assertIsNone(f["coordinates"])
            self.assertTrue(f["official_source_url"].startswith("https://www.baptistonline.org/"))
            evidence = f["destination_evidence"]
            self.assertTrue(evidence["status_source_url"].startswith("https://www.baptistonline.org/"))
            self.assertTrue(evidence["osm_campus_url"].startswith("https://www.openstreetmap.org/"))
            self.assertTrue(set(f["age_applicability"]) <= {"adult", "child"} and f["age_applicability"])
            # Campus points are sourced, labeled fallbacks, never recorded as entrances.
            self.assertIsNone(point_problem(f["campus_point"]))
            self.assertIn("ER entrance unconfirmed", f["campus_point"]["label"])
            self.assertTrue(f["campus_point"]["source_url"].startswith("https://www.openstreetmap.org/"))
            if f["emergency_entrance"] is not None:
                self.assertIsNone(eligibility(f, f["age_applicability"][0], now))
        by_slug = {f["slug"]: f for f in facilities}
        self.assertEqual(by_slug["childrens"]["age_applicability"], ["child"])
        self.assertIsNone(eligibility(by_slug["memphis"], "adult", now))
        self.assertEqual(eligibility(by_slug["memphis"], "child", now), "Age applicability unverified or unsuitable")

    def test_corrupt_compressed_object_is_explicitly_rejected(self):
        self.s3.put_object(Bucket="test", Key="compacted/ed_wait/dt=2026-09-13/data.jsonl.gz", Body=b"not gzip")
        result = self.load()
        self.assertEqual(result.records, [])
        self.assertEqual(result.rejected_records, 1)

    def test_storage_access_error_aborts_instead_of_appearing_empty(self):
        from unittest.mock import patch
        from tests.fakes import error
        with patch.object(self.s3, "head_object", side_effect=error("AccessDenied")):
            with self.assertRaises(Exception):
                self.load()


if __name__ == "__main__":
    unittest.main()
