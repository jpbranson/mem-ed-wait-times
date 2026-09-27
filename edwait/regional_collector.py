"""Collect public ER wait ranges and check-in slots around Memphis.

Run ``python -m edwait.regional_collector --output batch.json`` for a local
read-only collection. The separate Lambda handler writes to BUCKET, never to
the Baptist wait history or latest.json. Dated source research and the record
contract are in docs/regional-collector.md.
"""

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import boto3
import requests

LOGGER = logging.getLogger(__name__)
# Lambda leaves the root logger at WARNING; keep the run summary in CloudWatch.
LOGGER.setLevel(logging.INFO)
# Identify the project so site operators can see who is calling and reach the maintainer.
USER_AGENT = ("mem-ed-wait-times/1.0 (+https://github.com/jpbranson/mem-ed-wait-times; "
              "public ER information collector)")
METHODIST_URL = "https://mychart.methodisthealth.org/MyChart/Scheduling/OnMyWay"
METHODIST_API = METHODIST_URL + "/GetOnMyWayDepartmentData"
INQUICKER_URL = "https://southern-checkin.inquicker.com"
INQUICKER_API = "https://apiv4.inquicker.com/v4/southern-checkin.inquicker.com"
# Anonymous public application key from the site's JS bundle, not an account
# credential. Only exchange it for an ephemeral token; never persist that token.
INQUICKER_PUBLIC_KEY = "935412a0255fa01a36766c351d70583006f39056"
FORREST_URL = "https://forrestcitymedicalcenter.com/er/"
# ER department names. The same MyChart listing includes Minor Medical Centers
# (urgent care), which must never match.
METHODIST = {
    "methodist-university": "Methodist University Emergency Department",
    "methodist-north": "Methodist North Emergency",
    "methodist-south": "Methodist South Emergency",
    "methodist-germantown": "Methodist Germantown Emergency",
    "methodist-olive-branch": "Methodist Olive Branch Emergency",
}
# Permalink and InQuicker facility ID (observed 2026-09-27). Every run checks both
# against the facility included in the schedules response.
SAINT_FRANCIS = {
    "saint-francis-memphis": ("saint-francis-hospital", "953125689"),
    "saint-francis-bartlett": ("saint-francis-hospital-bartlett", "953125690"),
}
EXPECTED = {**{f: ["estimated_wait_range"] for f in METHODIST},
            **{f: ["arrival_slots"] for f in SAINT_FRANCIS},
            "forrest-city": ["published_wait"]}
TIMEOUT = (3, 10)
# Saint Francis evidence keeps only the slot fields the parser reads.
SLOT_FIELDS = ("schedule-id", "appointment-type-id", "times", "next-time")
WIDGET_CHARS = 200


class DeadlineError(Exception):
    """Reserve time for diagnostics and storage before the Lambda deadline."""


class SourceError(ValueError):
    """A failed source check. Its message is a fixed phrase from this module, so the
    attempt summary can store it; exception text that might quote a source is never stored."""


COLLECTION_ERRORS = (requests.RequestException, ValueError, TypeError, KeyError, DeadlineError)


class PublicHTML(HTMLParser):
    """Read public inputs and visible text without executing page scripts."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.inputs, self.text, self.wait_text = {}, [], []
        self._hidden, self._wait_depth = 0, 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and "name" in attrs:
            self.inputs[attrs["name"]] = attrs.get("value")
        if tag in ("script", "style"):
            self._hidden += 1
        if tag == "h4" and "wait-time-menu" in attrs.get("class", "").split():
            self._wait_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._hidden = max(0, self._hidden - 1)
        if tag == "h4":
            self._wait_depth = max(0, self._wait_depth - 1)

    def handle_data(self, data):
        if not self._hidden:
            self.text.append(data)
            if self._wait_depth:
                self.wait_text.append(data)


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    if not isinstance(value, str):
        raise SourceError("timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SourceError("invalid timestamp") from None
    if parsed.tzinfo is None:
        raise SourceError("timestamp needs an offset")
    return parsed.astimezone(timezone.utc)


def nonnegative_int(value):
    return type(value) is int and value >= 0


def object_value(value):
    if not isinstance(value, dict):
        raise SourceError("expected a JSON object")
    return value


def json_body(response):
    def reject_constant(value):
        raise SourceError("nonfinite source number")
    try:
        return response.json(parse_constant=reject_constant)
    except SourceError:
        raise
    except ValueError:
        # requests' decode error is also a RequestException: a bad body, not a failed request.
        raise SourceError("invalid JSON") from None


def request(session, method, url, context=None, **kwargs):
    if context and context.get_remaining_time_in_millis() < 23000:
        raise DeadlineError()
    response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response


def observation(facility, metric, batch_id, source_url, endpoint,
                *, value=None, source_value=None, status="available", reason=None):
    # collect() fills latency_ms with the facility's measured fetch time.
    return {"schema_version": 1, "facility": facility, "metric": metric,
            "batch_id": batch_id, "observed_at": utcnow().isoformat(),
            "source_url": source_url, "source_endpoint": endpoint,
            "latency_ms": None, "status": status, "reason": reason,
            "value": value, "source_value": source_value}


def methodist_payload(session, context=None):
    html = request(session, "GET", METHODIST_URL, context).text
    token = PublicHTML(html).inputs.get("__RequestVerificationToken")
    start = html.find('{"WorkflowSettings"')
    if not token or start < 0:
        raise SourceError("public MyChart bootstrap missing")
    try:
        initial, _ = json.JSONDecoder().raw_decode(html[start:])
    except ValueError:
        raise SourceError("invalid MyChart bootstrap") from None
    reasons = [r for r in initial["ReasonsForVisit"] if object_value(r).get("Title") == "Urgent Visit"]
    if len(reasons) != 1:
        raise SourceError("ambiguous reason for visit")
    # This endpoint only reads department information. Do not call scheduling,
    # registration, patient-intake, or reservation endpoints.
    return json_body(request(session, "POST", METHODIST_API, context, data={
        "rfvId": reasons[0]["Id"], "displayGroupIds": "", "searchCoordinates": "null",
        "__RequestVerificationToken": token}))


def parse_methodist(payload, facility, batch_id):
    departments = payload["OnMyWayDepartments"]
    if not isinstance(departments, list) or not all(isinstance(d, dict) for d in departments):
        raise SourceError("invalid department list")
    matches = [d for d in departments if d.get("Name") == METHODIST[facility]
               and d.get("IsEDDep") is True and d.get("IsASAP") is True]
    if len(matches) != 1:
        raise SourceError("missing or duplicate ER department")
    dep = matches[0]
    if not {"CanShowWaitInfo", "WaitTime", "WaitTimeLower", "MaxValueHit"} <= dep.keys():
        raise SourceError("missing wait fields")
    if type(dep["CanShowWaitInfo"]) is not bool:
        raise SourceError("invalid wait visibility flag")
    raw = {k: dep.get(k) for k in ("Name", "WaitTime", "WaitTimeLower", "MaxValueHit",
                                  "CanShowWaitInfo", "WaitTimeDisplayString")}
    options = {"source_value": raw}
    upper, lower = dep.get("WaitTime"), dep.get("WaitTimeLower")
    if dep.get("CanShowWaitInfo") is not True or upper is None:
        options.update(status="unavailable", reason="wait_not_displayed")
    elif not nonnegative_int(upper) or lower is not None and (
            not nonnegative_int(lower) or lower > upper):
        options.update(status="invalid", reason="invalid_wait_bounds")
    elif type(dep.get("MaxValueHit")) not in (bool, type(None)):
        options.update(status="invalid", reason="invalid_cap_flag")
    else:
        # The site shows equal or absent bounds as one value; MaxValueHit means "or more".
        lower = upper if lower is None else lower
        capped = dep.get("MaxValueHit") is True and lower == upper
        options["value"] = {"lower_minutes": lower, "upper_minutes": None if capped else upper,
                            "lower_bound_only": capped}
    return observation(facility, "estimated_wait_range", batch_id, METHODIST_URL,
                       METHODIST_API, **options)


def inquicker_token(session, context=None):
    token = request(session, "GET", INQUICKER_API + "/token", context,
                    params={"api_key": INQUICKER_PUBLIC_KEY, "locale": "en-US"}).text.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise SourceError("invalid anonymous token response")
    return token


def data_list(payload):
    if (not isinstance(payload, dict) or not isinstance(payload.get("data"), list)
            or not all(isinstance(row, dict) for row in payload["data"])):
        raise SourceError("invalid public API envelope")
    return payload["data"]


def select_schedules(payload, facility_id, permalink):
    rows = data_list(payload)
    count = object_value(payload.get("meta")).get("record-count")
    if type(count) is not int or count != len(rows):
        raise SourceError("incomplete schedule listing")
    # include=facility returns the facility itself; confirm it is this hospital's ER.
    included = [object_value(item) for item in payload.get("included") or []]
    facilities = [item for item in included if item.get("type") == "facilities"]
    if (len(facilities) != 1 or facilities[0].get("id") != facility_id
            or object_value(facilities[0].get("attributes")).get("permalink") != permalink
            or facilities[0]["attributes"].get("facility-type") != "Emergencydepartment"):
        raise SourceError("missing or unexpected emergency facility")
    result = []
    for row in rows:
        attrs = object_value(row["attributes"])
        if object_value(attrs.get("service")).get("permalink") != "emergency-room":
            continue
        if (row["relationships"]["facility"]["data"]["id"] != facility_id
                or attrs.get("active") is not True or attrs.get("hidden") is not False
                or attrs.get("appointment-types") != []):
            raise SourceError("unexpected ER schedule scope")
        result.append(row["id"])
    if not result or len(set(result)) != len(result):
        raise SourceError("missing or duplicate ER schedules")
    return result


def parse_slots(payload, schedule_ids, start, end):
    if not isinstance(payload, list):
        raise SourceError("invalid slot response")
    seen, slots, beyond, next_times = set(), set(), set(), []
    for row in payload:
        if not isinstance(row, dict):
            raise SourceError("invalid slot row")
        schedule = row["schedule-id"]
        if schedule not in schedule_ids or schedule in seen or row.get("appointment-type-id") != "":
            raise SourceError("unexpected slot schedule or appointment type")
        seen.add(schedule)
        times = row["times"]
        if not isinstance(times, list):
            raise SourceError("invalid slot list")
        for value in times:
            instant = aware(value)
            if instant < start:
                raise SourceError("expired slot")
            # max_days=1 can return slots past the requested window: count them (they can
            # set next_available_at) rather than failing the facility or listing them.
            (slots if instant < end else beyond).add(instant.isoformat())
        next_time = row["next-time"]
        if next_time is not None:
            instant = aware(next_time)
            if instant < start:
                raise SourceError("expired next slot")
            # The API may return its next-time beyond the requested slot window.
            next_times.append(instant)
    if seen != set(schedule_ids):
        raise SourceError("incomplete slot response")
    ordered = sorted(slots)
    candidates = next_times + [aware(t) for t in ordered + sorted(beyond)]
    return {"next_available_at": min(candidates).isoformat() if candidates else None,
            "available_slots": ordered, "slots_beyond_window": len(beyond),
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "timezone": "America/Chicago", "schedule_ids": sorted(schedule_ids)}


def fetch_saint_francis(session, token, facility, batch_id, context=None):
    permalink, facility_id = SAINT_FRANCIS[facility]
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.api+json"}
    payload = json_body(request(session, "GET", INQUICKER_API + "/schedules", context, headers=headers,
                                params={"filter[facility_id]": facility_id, "filter[active]": "true",
                                        "filter[hidden]": "false", "filter[context]": "patient",
                                        "include": "facility", "page[size]": 100}))
    schedules = select_schedules(payload, facility_id, permalink)
    start = utcnow().replace(microsecond=0)
    end = start + timedelta(days=1)
    endpoint = INQUICKER_API + "/available-appointment-times"
    payload = json_body(request(session, "GET", endpoint, context, headers=headers, params={
        "schedule_ids[]": schedules, "max_days": 1, "from": start.isoformat(),
        "to": end.isoformat(), "context": "patient"}))
    # Check-in slots are projected times subject to triage, not waits: keep absolute
    # timestamps and never convert time until a slot into a wait.
    value = parse_slots(payload, schedules, start, end)
    available = value["next_available_at"] is not None
    evidence = [{k: row.get(k) for k in SLOT_FIELDS} for row in payload]
    return observation(facility, "arrival_slots", batch_id,
                       f"{INQUICKER_URL}/facility/{permalink}?service=10", endpoint,
                       value=value, source_value=evidence,
                       status="available" if available else "unavailable",
                       reason=None if available else "no_slots_returned")


def parse_forrest(html, batch_id):
    page = PublicHTML(html)
    if "Forrest City Medical Center" not in " ".join(" ".join(page.text).split()):
        raise SourceError("unexpected Forrest City page")
    widget = " ".join(" ".join(page.wait_text).split())
    matches = re.findall(r"Current\s+ER\s+Wait\s+Time:\s*([+-]?\d+)\s+Minutes", widget, re.I)
    raw = list(dict.fromkeys(matches))
    # Trimmed public text is kept even when nothing matches, so a wording change is visible.
    options = {"source_value": {"widget_text": widget[:WIDGET_CHARS], "matches": raw},
               "status": "invalid", "reason": "missing_or_conflicting_widget"}
    if len(raw) == 1:
        minutes = int(raw[0])
        # The widget has shown -1: negative values are invalid evidence, never a wait.
        options["reason"] = "negative_wait_sentinel"
        if minutes >= 0:
            options.update(value={"minutes": minutes}, status="available", reason=None)
    return observation("forrest-city", "published_wait", batch_id, FORREST_URL, FORREST_URL, **options)


def diagnose(error):
    """Attempt fields for a failed fetch. Details are fixed phrases, never source text."""
    status = None
    if isinstance(error, DeadlineError):
        code, detail = "collection_deadline", None
    elif isinstance(error, requests.RequestException):
        code = "request_failed"
        if isinstance(error, requests.HTTPError):
            detail = "http_error"
            status = error.response.status_code if error.response is not None else None
        elif isinstance(error, requests.Timeout):
            detail = "timeout"
        elif isinstance(error, requests.ConnectionError):
            detail = "connection_error"
        else:
            detail = "request_error"
    else:
        code = "invalid_response"
        if isinstance(error, SourceError):
            detail = str(error)
        elif isinstance(error, KeyError) and error.args and isinstance(error.args[0], str):
            detail = "missing field " + error.args[0]  # keys are literals in this module
        else:
            detail = "unexpected value type" if isinstance(error, TypeError) else "invalid value"
    return {"error_code": code, "error_detail": detail, "http_status": status}


def collect(batch_dt=None, context=None):
    run_started = time.monotonic()
    batch_dt = batch_dt or utcnow()
    if batch_dt.tzinfo is None:
        raise ValueError("batch timestamp needs an offset")
    batch_id = batch_dt.astimezone(timezone.utc).isoformat()
    records, attempts = [], {}

    def capture(facility, fetch, attempted=None, shared_ms=0):
        # Latency covers this facility's fetch and parsing plus any fetch it shares.
        attempted = attempted or utcnow().isoformat()
        started = time.monotonic()
        failure = {"error_code": None, "error_detail": None, "http_status": None}
        try:
            rows = fetch()
        except COLLECTION_ERRORS as exc:
            rows, failure = [], diagnose(exc)
        latency = shared_ms + round((time.monotonic() - started) * 1000)
        invalid = [r for r in rows if r["status"] == "invalid"]
        if invalid:
            failure.update(error_code="invalid_source_value",
                           error_detail=", ".join(sorted({r["reason"] for r in invalid})))
        for row in rows:
            row["latency_ms"] = latency
        records.extend(rows)
        state = "failed" if len(invalid) == len(rows) else "partial" if invalid else "success"
        attempts[facility] = {"attempted_at": attempted, "state": state, **failure,
                              "expected_metrics": EXPECTED[facility],
                              "collected_metrics": [r["metric"] for r in rows]}

    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        methodist_attempted, started = utcnow().isoformat(), time.monotonic()
        try:
            methodist, methodist_error = methodist_payload(session, context), None
        except COLLECTION_ERRORS as exc:
            methodist, methodist_error = None, exc
        bootstrap_ms = round((time.monotonic() - started) * 1000)
        for facility in METHODIST:
            def fetch_methodist(facility=facility):
                if methodist_error is not None:
                    raise methodist_error
                return [parse_methodist(methodist, facility, batch_id)]
            capture(facility, fetch_methodist, methodist_attempted, bootstrap_ms)

        try:
            token, token_error = inquicker_token(session, context), None
        except COLLECTION_ERRORS as exc:
            token, token_error = None, exc
        for facility in SAINT_FRANCIS:
            def fetch_slots(facility=facility):
                if token_error is not None:
                    raise token_error
                return [fetch_saint_francis(session, token, facility, batch_id, context)]
            capture(facility, fetch_slots)

        def fetch_forrest():
            return [parse_forrest(request(session, "GET", FORREST_URL, context).text, batch_id)]
        capture("forrest-city", fetch_forrest)

    summary = {"schema_version": 1, "batch_id": batch_id, "generated_at": utcnow().isoformat(),
               "duration_ms": round((time.monotonic() - run_started) * 1000),
               "expected_facilities": len(EXPECTED), "records": len(records),
               **{state: sum(a["state"] == state for a in attempts.values())
                  for state in ("success", "partial", "failed")}, "attempts": attempts}
    return records, summary


def store_batch(s3, bucket, records, summary):
    batch_dt = aware(summary["batch_id"])
    suffix = f"dt={batch_dt:%Y-%m-%d}/{batch_dt:%Y%m%dT%H%M%S%fZ}"
    key = "raw/er_publications/" + suffix + ".jsonl"
    if records:
        body = "".join(json.dumps(r, allow_nan=False) + "\n" for r in records)
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode(), ContentType="application/x-ndjson")
    s3.put_object(Bucket=bucket, Key="operations/er_publications/" + suffix + ".json",
                  Body=json.dumps(summary, allow_nan=False).encode(), ContentType="application/json")
    return key if records else None


def lambda_handler(event, context):
    bucket = os.environ["BUCKET"]
    records, summary = collect(context=context)
    key = store_batch(boto3.client("s3"), bucket, records, summary)
    LOGGER.info("regional_collection_summary %s", json.dumps({k: v for k, v in summary.items() if k != "attempts"}))
    for facility, attempt in summary["attempts"].items():
        if attempt["state"] != "success":
            LOGGER.warning("regional_facility_%s facility=%s code=%s detail=%s http_status=%s",
                           attempt["state"], facility, attempt["error_code"], attempt["error_detail"],
                           attempt["http_status"])
    if not summary["success"] and not summary["partial"]:
        raise RuntimeError("All regional facilities failed; diagnostics stored")
    return {"key": key, **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write one JSON batch locally; default: stdout")
    args = parser.parse_args()
    if args.output:
        # Create the folder before any network request, not after them.
        args.output.parent.mkdir(parents=True, exist_ok=True)
    records, summary = collect()
    body = json.dumps({"summary": summary, "observations": records}, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 1 if summary["failed"] or summary["partial"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
