import copy
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from jsonschema import Draft202012Validator, FormatChecker

from edwait import regional_collector as collector
from tests.fakes import MemoryS3


FIXTURES = Path(__file__).parent / "fixtures" / "regional"
BATCH = "2026-09-27T14:42:00+00:00"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class RegionalCollectorTests(unittest.TestCase):
    def setUp(self):
        self.methodist = fixture("methodist.json")
        self.start = collector.aware(BATCH)
        self.end = self.start + timedelta(days=1)
        self.forrest = (FIXTURES / "forrest.html").read_text(encoding="utf-8")

    def methodist_record(self):
        return collector.parse_methodist(self.methodist, "methodist-university", BATCH, 32)

    def university(self):
        return next(d for d in self.methodist["OnMyWayDepartments"]
                    if d["Name"] == collector.METHODIST["methodist-university"])

    def saint_francis_row(self, times):
        facility = {"data": [{"id": "953125689", "attributes": {
            "permalink": "saint-francis-hospital", "facility-type": "Emergencydepartment"}}]}
        session = Mock()
        responses = [Mock(), Mock(), Mock()]
        for response, payload in zip(responses, [facility, fixture("saint-francis-hospital-schedules.json"), times]):
            response.json.return_value = payload
        session.request.side_effect = responses
        with patch.object(collector, "utcnow", return_value=self.start):
            return collector.fetch_saint_francis(session, "ephemeral", "saint-francis-memphis", BATCH), session

    def test_live_methodist_fixture_preserves_ranges_and_excludes_urgent_care(self):
        expected = [(5, 20), (55, 115), (60, 105), (10, 25), (15, 30)]
        for slug, bounds in zip(collector.METHODIST, expected):
            record = collector.parse_methodist(self.methodist, slug, BATCH, 32)
            self.assertEqual(record["status"], "available")
            self.assertEqual((record["value"]["lower_minutes"], record["value"]["upper_minutes"]), bounds)
            self.assertNotIn("wait_minutes", record)
        self.university()["IsEDDep"] = False
        with self.assertRaises(ValueError):
            self.methodist_record()

    def test_methodist_hidden_null_negative_decimal_bool_and_reversed_bounds(self):
        for fields, status in [({"CanShowWaitInfo": False}, "unavailable"),
                               ({"WaitTime": None}, "unavailable"),
                               ({"WaitTime": -1}, "invalid"), ({"WaitTime": True}, "invalid"),
                               ({"WaitTime": 2.5}, "invalid"), ({"WaitTimeLower": 21}, "invalid"),
                               ({"MaxValueHit": "false"}, "invalid")]:
            with self.subTest(fields=fields):
                self.methodist = fixture("methodist.json")
                self.university().update(fields)
                record = self.methodist_record()
                self.assertEqual(record["status"], status)
                self.assertIsNone(record["value"])

    def test_methodist_zero_single_and_capped_bound(self):
        self.university().update(WaitTime=0, WaitTimeLower=None)
        self.assertEqual(self.methodist_record()["value"],
                         {"lower_minutes": 0, "upper_minutes": 0, "lower_bound_only": False})
        self.university().update(WaitTime=120, MaxValueHit=True)
        self.assertEqual(self.methodist_record()["value"],
                         {"lower_minutes": 120, "upper_minutes": None, "lower_bound_only": True})
        # Match the site's formatter: distinct bounds remain a range.
        self.university()["WaitTimeLower"] = 60
        self.assertEqual(self.methodist_record()["value"]["upper_minutes"], 120)

    def test_methodist_missing_duplicate_and_bad_department_are_rejected(self):
        self.methodist["OnMyWayDepartments"].append(copy.deepcopy(self.university()))
        with self.assertRaises(ValueError):
            self.methodist_record()
        for payload in ({}, {"OnMyWayDepartments": []}, {"OnMyWayDepartments": [None]}):
            with self.assertRaises((ValueError, KeyError)):
                collector.parse_methodist(payload, "methodist-university", BATCH, 0)

    def test_missing_contract_fields_and_nonfinite_json_fail_clearly(self):
        del self.university()["CanShowWaitInfo"]
        with self.assertRaises(ValueError):
            self.methodist_record()
        response = requests.Response()
        response._content = b'{"WaitTime": NaN}'
        with self.assertRaises(ValueError):
            collector.json_body(response)
        schedules = fixture("saint-francis-hospital-schedules.json")
        schedules["meta"] = None
        with self.assertRaises(ValueError):
            collector.select_schedules(schedules, "953125689")

    def test_one_changed_methodist_department_does_not_drop_other_hospitals(self):
        self.university()["CanShowWaitInfo"] = None
        with patch.object(collector, "methodist_payload", return_value=self.methodist), \
             patch.object(collector, "inquicker_token", side_effect=requests.Timeout()), \
             patch.object(collector, "request", side_effect=requests.HTTPError()):
            records, summary = collector.collect(self.start)
        self.assertEqual(len(records), 4)
        self.assertEqual(summary["success"], 4)
        self.assertEqual(summary["attempts"]["methodist-university"]["error_code"], "invalid_response")

    def test_methodist_bootstrap_uses_fresh_session_token_and_read_only_post(self):
        session = Mock()
        page = Mock(text='<input value="fresh-token" name="__RequestVerificationToken">'
                    '<script>{"WorkflowSettings":{},"ReasonsForVisit":[{"Title":"Urgent Visit","Id":"fresh-id"}]}</script>')
        response = Mock()
        response.json.return_value = self.methodist
        session.request.side_effect = [page, response]
        self.assertEqual(collector.methodist_payload(session), self.methodist)
        call = session.request.call_args
        self.assertEqual(call.args, ("POST", collector.METHODIST_API))
        self.assertEqual(call.kwargs["data"]["__RequestVerificationToken"], "fresh-token")
        self.assertEqual(call.kwargs["data"]["rfvId"], "fresh-id")
        self.assertEqual(call.kwargs["timeout"], (3, 10))

    def test_inquicker_fixtures_match_facility_and_emergency_service(self):
        for name, facility, schedule in [("saint-francis-hospital", "953125689", "17"),
                                         ("saint-francis-hospital-bartlett", "953125690", "18")]:
            schedules = fixture(name + "-schedules.json")
            self.assertEqual(collector.select_schedules(schedules, facility), [schedule])
            slots = collector.parse_slots(fixture(name + "-times.json"), [schedule], self.start, self.end)
            self.assertEqual(slots["next_available_at"], "2026-09-27T15:30:00+00:00")
            self.assertTrue(slots["available_slots"])
            self.assertEqual(slots["timezone"], "America/Chicago")
            with self.assertRaises(ValueError):
                collector.select_schedules(schedules, "wrong-facility")
            schedules["meta"]["record-count"] = 2
            with self.assertRaises(ValueError):
                collector.select_schedules(schedules, facility)

    def test_inquicker_no_slots_is_explicit_and_next_time_can_be_outside_window(self):
        payload = [{"schedule-id": "17", "appointment-type-id": "", "times": [], "next-time": None}]
        empty = collector.parse_slots(payload, ["17"], self.start, self.end)
        self.assertIsNone(empty["next_available_at"])
        self.assertEqual((empty["available_slots"], empty["slots_beyond_window"]), ([], 0))
        payload[0]["next-time"] = (self.end + timedelta(days=1)).isoformat()
        self.assertEqual(collector.parse_slots(payload, ["17"], self.start, self.end)["next_available_at"],
                         "2026-09-29T14:42:00+00:00")

    def test_inquicker_slots_after_the_window_are_counted_not_failed(self):
        payload = fixture("saint-francis-hospital-times.json")
        later = [(self.end + timedelta(minutes=m)).isoformat() for m in (0, 15, 15)]
        payload[0]["times"] += later
        value = collector.parse_slots(payload, ["17"], self.start, self.end)
        self.assertEqual(value["slots_beyond_window"], 2)
        self.assertTrue(all(collector.aware(t) < self.end for t in value["available_slots"]))
        payload[0].update({"times": later[:1], "next-time": None})
        value = collector.parse_slots(payload, ["17"], self.start, self.end)
        self.assertEqual((value["available_slots"], value["slots_beyond_window"]), ([], 1))
        self.assertEqual(value["next_available_at"], self.end.isoformat())

    def test_saint_francis_evidence_keeps_only_parsed_slot_fields(self):
        times = fixture("saint-francis-hospital-times.json")
        times[0]["links"] = {"self": "https://example.invalid/unexpected"}
        row, _ = self.saint_francis_row(times)
        self.assertEqual([set(r) for r in row["source_value"]], [set(collector.SLOT_FIELDS)])
        self.assertEqual(row["source_value"][0]["times"], fixture("saint-francis-hospital-times.json")[0]["times"])

    def test_saint_francis_fetch_reads_verified_facility_schedule_and_slots_without_booking(self):
        for times, state in [(fixture("saint-francis-hospital-times.json"), "available"),
                             ([{"schedule-id": "17", "appointment-type-id": "", "times": [], "next-time": None}], "unavailable")]:
            row, session = self.saint_francis_row(times)
            self.assertEqual(row["status"], state)
            calls = session.request.call_args_list
            self.assertEqual([c.args[0] for c in calls], ["GET"] * 3)
            # Relationship data is only returned when explicitly included.
            self.assertEqual(calls[1].kwargs["params"]["include"], "facility")
            self.assertEqual(calls[2].kwargs["params"]["schedule_ids[]"], ["17"])
            self.assertNotIn("ephemeral", json.dumps(row))

    def test_partial_forrest_result_is_reported_as_partial(self):
        response = Mock(text=self.forrest)
        with patch.object(collector, "methodist_payload", return_value=self.methodist), \
             patch.object(collector, "inquicker_token", side_effect=requests.Timeout()), \
             patch.object(collector, "request", return_value=response):
            records, summary = collector.collect(self.start)
        self.assertEqual(summary["attempts"]["forrest-city"]["state"], "partial")
        self.assertEqual(summary["attempts"]["forrest-city"]["error_detail"], "negative_wait_sentinel")
        self.assertEqual(summary["partial"], 1)
        self.assertEqual(len(records), 7)

    def test_inquicker_wrong_missing_duplicate_past_and_naive_slots_are_rejected(self):
        payload = fixture("saint-francis-hospital-times.json")
        for bad in ({}, [], [None], payload + payload):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                collector.parse_slots(bad, ["17"], self.start, self.end)
        for field, value in [("schedule-id", "18"), ("times", None),
                             ("times", ["2026-09-27T10:30:00"]),
                             ("next-time", "2026-09-26T10:30:00-05:00"),
                             ("times", ["2026-09-26T10:30:00-05:00"]),
                             ("appointment-type-id", "unexpected")]:
            bad = copy.deepcopy(payload)
            bad[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                collector.parse_slots(bad, ["17"], self.start, self.end)

    def test_forrest_negative_widget_keeps_pledge_separate_and_does_not_invent_zero(self):
        wait, pledge = collector.parse_forrest(self.forrest, BATCH, 100)
        self.assertEqual(wait["status"], "invalid")
        self.assertEqual(wait["reason"], "negative_wait_sentinel")
        self.assertEqual(wait["source_value"],
                         {"widget_text": "Current ER Wait Time: -1 Minutes Learn More", "matches": ["-1"]})
        self.assertIsNone(wait["value"])
        self.assertEqual(pledge["metric"], "initial_assessment_target")
        self.assertEqual(pledge["value"], {"minutes": 30})
        for minutes in (0, 13):
            wait, _ = collector.parse_forrest(self.forrest.replace("<span>-1", f"<span>{minutes}"), BATCH, 1)
            self.assertEqual(wait["value"], {"minutes": minutes})
        wait, _ = collector.parse_forrest(self.forrest.replace("wait-time-menu", "changed"), BATCH, 1)
        self.assertEqual(wait["status"], "invalid")
        with self.assertRaises(ValueError):
            collector.parse_forrest("<h1>Access denied</h1>", BATCH, 1)

    def test_forrest_conflicting_widgets_and_script_text_are_not_trusted(self):
        html = self.forrest + '<h4 class="wait-time-menu">Current ER Wait Time: 20 Minutes</h4>'
        self.assertEqual(collector.parse_forrest(html, BATCH, 0)[0]["status"], "invalid")
        html = self.forrest.replace('<h1>30-Minute ER Pledge</h1>', '<script>30-Minute ER Pledge</script>')
        self.assertEqual(collector.parse_forrest(html, BATCH, 0)[1]["status"], "invalid")

    def test_forrest_keeps_trimmed_text_when_the_wording_changes(self):
        html = self.forrest.replace("Minutes", "Mins").replace("30-Minute ER Pledge", "30 Minute E.R. Pledge")
        wait, pledge = collector.parse_forrest(html, BATCH, 1)
        self.assertEqual((wait["status"], pledge["status"]), ("invalid", "invalid"))
        self.assertEqual(wait["source_value"], {"widget_text": "Current ER Wait Time: -1 Mins Learn More", "matches": []})
        self.assertEqual(pledge["source_value"]["matches"], [])
        self.assertTrue(any("30 Minute E.R. Pledge" in s for s in pledge["source_value"]["pledge_snippets"]))
        wait, _ = collector.parse_forrest(self.forrest.replace("Learn More", "x" * 500), BATCH, 1)
        self.assertEqual(len(wait["source_value"]["widget_text"]), collector.WIDGET_CHARS)

    def test_partial_outage_preserves_other_facilities_and_records_all_attempts(self):
        with patch.object(collector, "methodist_payload", return_value=self.methodist), \
             patch.object(collector, "inquicker_token", side_effect=requests.Timeout()), \
             patch.object(collector, "request", side_effect=requests.HTTPError()):
            records, summary = collector.collect(self.start)
        self.assertEqual(len(records), 5)
        self.assertEqual(summary["success"], 5)
        self.assertEqual(summary["failed"], 3)
        self.assertEqual(set(summary["attempts"]), set(collector.EXPECTED))
        self.assertEqual(summary["attempts"]["forrest-city"]["error_code"], "request_failed")
        self.assertEqual(summary["attempts"]["forrest-city"]["error_detail"], "http_error")
        self.assertEqual(summary["attempts"]["saint-francis-bartlett"]["error_detail"], "timeout")
        self.assertIsNone(summary["attempts"]["methodist-north"]["error_detail"])
        self.assertIsInstance(summary["duration_ms"], int)

    def test_attempts_record_http_status_and_the_failed_check_but_no_source_text(self):
        blocked = requests.HTTPError(response=Mock(status_code=403))
        with patch.object(collector, "methodist_payload",
                          side_effect=collector.SourceError("ambiguous reason for visit")), \
             patch.object(collector, "inquicker_token", side_effect=requests.ConnectTimeout()), \
             patch.object(collector, "request", side_effect=blocked):
            _, summary = collector.collect(self.start)
        attempts = summary["attempts"]
        self.assertEqual({k: attempts["forrest-city"][k] for k in ("error_code", "error_detail", "http_status")},
                         {"error_code": "request_failed", "error_detail": "http_error", "http_status": 403})
        self.assertEqual((attempts["saint-francis-memphis"]["error_detail"],
                          attempts["saint-francis-memphis"]["http_status"]), ("timeout", None))
        self.assertEqual((attempts["methodist-north"]["error_code"], attempts["methodist-north"]["error_detail"]),
                         ("invalid_response", "ambiguous reason for visit"))
        # A non-JSON body is an invalid response, not a failed request.
        response = requests.Response()
        response._content = b"<html>Access denied</html>"
        with self.assertRaises(collector.SourceError) as caught:
            collector.json_body(response)
        self.assertEqual((collector.error_code(caught.exception), str(caught.exception)),
                         ("invalid_response", "invalid JSON"))
        self.assertEqual(collector.error_detail(KeyError("next-time")), "missing field next-time")
        self.assertEqual(collector.error_detail(ValueError("Invalid isoformat string: 'source text'")),
                         "invalid value")
        with self.assertRaises(collector.SourceError) as caught:
            collector.aware("source text")
        self.assertEqual(str(caught.exception), "invalid timestamp")

    def test_latency_counts_http_time_only(self):
        spent = []
        with patch.object(collector.time, "monotonic", side_effect=[10.0, 10.25]):
            collector.request(Mock(), "GET", collector.FORREST_URL, spent=spent)
        self.assertEqual(spent, [0.25])

    def test_deadline_skips_network_and_reports_all_facilities(self):
        context = Mock()
        context.get_remaining_time_in_millis.return_value = 22000
        with patch.object(collector.requests, "Session") as session:
            records, summary = collector.collect(self.start, context)
        session.return_value.__enter__.return_value.request.assert_not_called()
        # Sites can see who is calling and how to reach the project.
        session.return_value.__enter__.return_value.headers.update.assert_called_once_with(
            {"User-Agent": collector.USER_AGENT})
        self.assertIn("+https://github.com/jpbranson/mem-ed-wait-times", collector.USER_AGENT)
        self.assertEqual(records, [])
        self.assertEqual(summary["failed"], 8)
        self.assertEqual({a["error_code"] for a in summary["attempts"].values()}, {"collection_deadline"})

    def test_storage_is_separate_and_retains_invalid_evidence(self):
        s3 = MemoryS3()
        records = collector.parse_forrest(self.forrest, BATCH, 10)
        key = collector.store_batch(s3, "data", records, {"batch_id": BATCH})
        self.assertTrue(key.startswith("raw/er_publications/dt=2026-09-27/"))
        stored = [json.loads(line) for line in s3.objects["data", key]["Body"].splitlines()]
        self.assertEqual(stored, records)
        self.assertEqual(len(s3.objects), 2)
        self.assertFalse(any("ed_wait/" in key or "latest.json" in key for _, key in s3.objects))

    def test_all_failed_lambda_writes_diagnostics_before_raising(self):
        s3 = MemoryS3()
        attempt = {"state": "failed", "error_code": "request_failed", "error_detail": "http_error", "http_status": 403}
        summary = {"batch_id": BATCH, "success": 0, "partial": 0, "failed": 8, "attempts": {"forrest-city": attempt}}
        with patch.object(collector, "collect", return_value=([], summary)), \
             patch.object(collector.boto3, "client", return_value=s3), \
             patch.dict(os.environ, {"BUCKET": "data"}), \
             self.assertLogs(collector.LOGGER, "INFO") as logs:
            with self.assertRaisesRegex(RuntimeError, "diagnostics stored"):
                collector.lambda_handler({}, None)
        self.assertEqual(len(s3.objects), 1)
        self.assertTrue(next(iter(s3.objects))[1].startswith("operations/er_publications/"))
        self.assertIn("regional_collection_summary", logs.output[0])
        self.assertIn("regional_facility_failed facility=forrest-city code=request_failed "
                      "detail=http_error http_status=403", logs.output[1])
        # Lambda leaves the root logger at WARNING; the module logger must still emit INFO.
        self.assertEqual(collector.LOGGER.level, logging.INFO)

    def test_cli_creates_the_output_folder_before_collecting(self):
        summary = {"batch_id": BATCH, "success": 8, "partial": 0, "failed": 0}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "new", "batch.json")

            def fake_collect():
                self.assertTrue(target.parent.is_dir())
                return [], summary
            with patch.object(collector, "collect", side_effect=fake_collect), \
                 patch.object(sys, "argv", ["regional_collector", "--output", str(target)]):
                self.assertEqual(collector.main(), 0)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")),
                             {"summary": summary, "observations": []})

    def all_record_kinds(self):
        """Every status each parser can produce, built from the captured fixtures."""
        records = [collector.parse_methodist(self.methodist, slug, BATCH, 32) for slug in collector.METHODIST]
        for fields in ({"CanShowWaitInfo": False}, {"WaitTime": -1}, {"MaxValueHit": "false"},
                       {"WaitTime": 0, "WaitTimeLower": None},
                       {"WaitTime": 120, "WaitTimeLower": None, "MaxValueHit": True}):
            self.methodist = fixture("methodist.json")
            self.university().update(fields)
            records.append(self.methodist_record())
        empty = {"schedule-id": "17", "appointment-type-id": "", "times": [], "next-time": None}
        for times in (fixture("saint-francis-hospital-times.json"), [empty],
                      [{**empty, "next-time": (self.end + timedelta(days=1)).isoformat()}],
                      [{**empty, "times": [(self.end + timedelta(hours=1)).isoformat()]}]):
            records.append(self.saint_francis_row(times)[0])
        for html in (self.forrest, self.forrest.replace("<span>-1", "<span>0"),
                     self.forrest.replace("wait-time-menu", "changed").replace("30-Minute ER Pledge", "Our promise")):
            records.extend(collector.parse_forrest(html, BATCH, 1))
        return records

    def test_schema_accepts_every_record_kind_and_rejects_fake_waits(self):
        schema = json.loads(Path("docs/er-publication.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        records = self.all_record_kinds()
        self.assertEqual({(r["metric"], r["status"]) for r in records}, {
            ("estimated_wait_range", "available"), ("estimated_wait_range", "unavailable"),
            ("estimated_wait_range", "invalid"), ("arrival_slots", "available"), ("arrival_slots", "unavailable"),
            ("published_wait", "available"), ("published_wait", "invalid"),
            ("initial_assessment_target", "available"), ("initial_assessment_target", "invalid")})
        for record in records:
            with self.subTest(metric=record["metric"], status=record["status"], reason=record["reason"]):
                validator.validate(record)
        bad = copy.deepcopy(records[0]); bad["wait_minutes"] = 10
        self.assertTrue(list(validator.iter_errors(bad)))
        wait = next(r for r in records if r["metric"] == "published_wait")
        bad = copy.deepcopy(wait); bad["value"] = {"minutes": -1}
        self.assertTrue(list(validator.iter_errors(bad)))
        closed = next(r for r in records if r["metric"] == "arrival_slots" and r["status"] == "unavailable")
        bad = copy.deepcopy(closed); bad["value"]["slots_beyond_window"] = 1
        self.assertTrue(list(validator.iter_errors(bad)))


if __name__ == "__main__":
    unittest.main()
