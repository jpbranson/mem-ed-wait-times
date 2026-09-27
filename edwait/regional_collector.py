"""Collect public ER ranges, check-in slots and timing targets around Memphis.

Run ``python -m edwait.regional_collector --output batch.json`` for a local
read-only collection. The separate Lambda handler writes to BUCKET, never to
the Baptist wait history or latest.json. See docs/regional-collector.md.
"""

# Research from this chat, checked 2026-09-27 (historical findings, not live data):
#
# Five Methodist ERs publish estimated wait ranges: University, North, South,
# Le Bonheur Germantown, and Olive Branch. Germantown's estimate excludes the
# children's ED. The public MyChart listing also contains Minor Medical Centers;
# those are urgent care and must not be mistaken for the five ERs.
# https://www.methodisthealth.org/articles/emergency-care-information
# https://mychart.methodisthealth.org/MyChart/Scheduling/OnMyWay
# The anonymous page supplies a session-specific reason-for-visit ID and CSRF
# token. Its read-only GetOnMyWayDepartmentData POST returns WaitTime (upper),
# WaitTimeLower, CanShowWaitInfo, IsEDDep and IsASAP. The site's formatter renders
# equal/absent lower bounds as one value; MaxValueHit then means "or more".
# Live examples during verification: University 5-20, Germantown 10-25,
# South 60-105, North 55-115, Olive Branch 15-30 minutes. Do not reuse these.
#
# Saint Francis Memphis (5959 Park Ave) and Bartlett (2986 Kate Bond Rd) offer
# InQuicker arrival/check-in slots, NOT a measured wait or guaranteed appointment.
# Memphis explicitly calls these projected treatment times, subject to triage.
# https://www.saintfrancishealthsystem.com/services/emergency-room/emergency-room-locations
# https://southern-checkin.inquicker.com/facility/saint-francis-hospital?service=10
# https://southern-checkin.inquicker.com/facility/saint-francis-hospital-bartlett?service=10
# The public application obtains an anonymous token using its bundled public
# client key, then reads facilities, schedules, and available-appointment-times.
# Observed facility IDs: 953125689 / 953125690; schedule IDs: 17 / 18. Resolve
# these at collection time. UI service-line 10 is NOT API ER service ID 36;
# verify service permalink emergency-room and the schedule's facility relation.
# Both returned next-time 2026-09-27T10:30:00-05:00 during verification. Store
# absolute timestamps and the query window, never minutes-until-slot as ER wait.
#
# Forrest City Medical Center (Forrest City, AR; near the search's 50-mile radius
# boundary) publishes a numeric ER widget and a 30-minute initial-assessment
# pledge. The pledge is a service target, not a current wait measurement.
# https://forrestcitymedicalcenter.com/er/
# https://forrestcitymedicalcenter.com/er-30-minute-pledge/
# Earlier checks showed inconsistent 0 / -1 widget values; the browser showed
# -1 again on 2026-09-27. Direct requests returned HTTP 403 during implementation.
# A later full collector run succeeded at 14:54 UTC: the widget returned 11
# minutes, while the pledge remained 30. Both successful and failing states were
# observed; the 403 is not a permanent policy claim and 11 is not a fallback.
# Preserve negative values only as invalid source evidence; never report -1 as
# a wait. Zero remains published zero with unverified meaning. Access failures
# must not be replaced by cached research values or the pledge.
#
# These eight publishers are separate from the eight map-only nonpublishers
# added earlier (Regional One, Le Bonheur Children's, Memphis VA, Highland Hills,
# Alliance, CrossRidge, SMC Regional, Lauderdale). They are also separate from
# the existing 20 Baptist CV_ED_Wait facilities. No clinical equivalence between
# these providers' measures has been established.

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
METHODIST = {
    "methodist-university": "Methodist University Emergency Department",
    "methodist-north": "Methodist North Emergency",
    "methodist-south": "Methodist South Emergency",
    "methodist-germantown": "Methodist Germantown Emergency",
    "methodist-olive-branch": "Methodist Olive Branch Emergency",
}
SAINT_FRANCIS = {
    "saint-francis-memphis": "saint-francis-hospital",
    "saint-francis-bartlett": "saint-francis-hospital-bartlett",
}
EXPECTED = {**{f: ["estimated_wait_range"] for f in METHODIST},
            **{f: ["arrival_slots"] for f in SAINT_FRANCIS},
            "forrest-city": ["published_wait", "initial_assessment_target"]}
TIMEOUT = (3, 10)
# Saint Francis evidence keeps only the slot fields the parser reads.
SLOT_FIELDS = ("schedule-id", "appointment-type-id", "times", "next-time")
WIDGET_CHARS, PLEDGE_CONTEXT, PLEDGE_SNIPPETS = 200, 60, 3


class DeadlineError(Exception):
    """Reserve time for diagnostics and storage before the Lambda deadline."""


class SourceError(ValueError):
    """A failed source check. Its message is a fixed phrase from this module, so the
    attempt summary can store it; exception text that might quote a source is never stored."""


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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def request(session, method, url, context=None, spent=None, **kwargs):
    if context and context.get_remaining_time_in_millis() < 23000:
        raise DeadlineError()
    started = time.monotonic()
    response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    if spent is not None:
        # HTTP time only: requests reads the body before returning; parsing is excluded.
        spent.append(time.monotonic() - started)
    response.raise_for_status()
    return response


def observation(facility, metric, batch_id, source_url, endpoint, latency_ms,
                *, value=None, source_value=None, status="available", reason=None):
    return {"schema_version": 1, "facility": facility, "metric": metric,
            "batch_id": batch_id, "observed_at": utcnow().isoformat(),
            "source_url": source_url, "source_endpoint": endpoint,
            "latency_ms": latency_ms, "status": status, "reason": reason,
            "value": value, "source_value": source_value}


def methodist_payload(session, context=None, spent=None):
    html = request(session, "GET", METHODIST_URL, context, spent=spent).text
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
    return json_body(request(session, "POST", METHODIST_API, context, spent=spent, data={
        "rfvId": reasons[0]["Id"], "displayGroupIds": "", "searchCoordinates": "null",
        "__RequestVerificationToken": token}))


def parse_methodist(payload, facility, batch_id, latency_ms):
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
        lower = upper if lower is None else lower
        capped = dep.get("MaxValueHit") is True and lower == upper
        options["value"] = {"lower_minutes": lower, "upper_minutes": None if capped else upper,
                            "lower_bound_only": capped}
    return observation(facility, "estimated_wait_range", batch_id, METHODIST_URL,
                       METHODIST_API, latency_ms, **options)


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


def select_schedules(payload, facility_id):
    rows = data_list(payload)
    count = object_value(payload.get("meta")).get("record-count")
    if type(count) is not int or count != len(rows):
        raise SourceError("incomplete schedule listing")
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
    spent = []
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.api+json"}
    permalink = SAINT_FRANCIS[facility]
    payload = json_body(request(session, "GET", INQUICKER_API + "/facilities", context, spent=spent,
                      headers=headers, params={"filter[permalink]": permalink}))
    matches = [r for r in data_list(payload) if object_value(r["attributes"]).get("permalink") == permalink
               and r["attributes"].get("facility-type") == "Emergencydepartment"]
    if len(matches) != 1:
        raise SourceError("missing or duplicate emergency facility")
    facility_id = matches[0]["id"]
    payload = json_body(request(session, "GET", INQUICKER_API + "/schedules", context, spent=spent,
                      headers=headers,
                      params={"filter[facility_id]": facility_id, "filter[active]": "true",
                              "filter[hidden]": "false", "filter[context]": "patient",
                              "include": "facility", "page[size]": 100}))
    schedules = select_schedules(payload, facility_id)
    start = utcnow().replace(microsecond=0)
    end = start + timedelta(days=1)
    endpoint = INQUICKER_API + "/available-appointment-times"
    payload = json_body(request(session, "GET", endpoint, context, spent=spent, headers=headers, params={
        "schedule_ids[]": schedules, "max_days": 1, "from": start.isoformat(),
        "to": end.isoformat(), "context": "patient"}))
    value = parse_slots(payload, schedules, start, end)
    available = value["next_available_at"] is not None
    evidence = [{k: row.get(k) for k in SLOT_FIELDS} for row in payload]
    return observation(facility, "arrival_slots", batch_id,
                       f"{INQUICKER_URL}/facility/{permalink}?service=10", endpoint,
                       round(sum(spent) * 1000), value=value,
                       source_value=evidence, status="available" if available else "unavailable",
                       reason=None if available else "no_slots_returned")


def parse_forrest(html, batch_id, latency_ms):
    page = PublicHTML(html)
    text = " ".join(" ".join(page.text).split())
    if "Forrest City Medical Center" not in text:
        raise SourceError("unexpected Forrest City page")
    records = []
    widget = " ".join(" ".join(page.wait_text).split())
    matches = re.findall(r"Current\s+ER\s+Wait\s+Time:\s*([+-]?\d+)\s+Minutes", widget, re.I)
    raw = list(dict.fromkeys(matches))
    # Trimmed public text is kept even when nothing matches, so a wording change is visible.
    options = {"source_value": {"widget_text": widget[:WIDGET_CHARS], "matches": raw},
               "status": "invalid", "reason": "missing_or_conflicting_widget"}
    if len(raw) == 1:
        minutes = int(raw[0])
        options["reason"] = "negative_wait_sentinel"
        if minutes >= 0:
            options.update(value={"minutes": minutes}, status="available", reason=None)
    records.append(observation("forrest-city", "published_wait", batch_id, FORREST_URL,
                               FORREST_URL, latency_ms, **options))
    pledges = set(re.findall(r"(\d+)[\s\-\u2011\u2013]+Minute\s+ER\s+Pledge", text, re.I))
    snippets = [text[max(0, m.start() - PLEDGE_CONTEXT):m.end() + PLEDGE_CONTEXT].strip()
                for m in re.finditer("pledge", text, re.I)]
    options = {"source_value": {"pledge_snippets": list(dict.fromkeys(snippets))[:PLEDGE_SNIPPETS],
                                "matches": sorted(pledges)},
               "status": "invalid", "reason": "missing_or_conflicting_pledge"}
    if len(pledges) == 1:
        options.update(value={"minutes": int(next(iter(pledges)))}, status="available", reason=None)
    records.append(observation("forrest-city", "initial_assessment_target", batch_id, FORREST_URL,
                               FORREST_URL, latency_ms, **options))
    return records


def error_code(error):
    if isinstance(error, DeadlineError):
        return "collection_deadline"
    if isinstance(error, requests.RequestException):
        return "request_failed"
    return "invalid_response"


def error_detail(error):
    """A short, fixed description for the attempt summary; never text from a source."""
    if isinstance(error, DeadlineError):
        return None
    if isinstance(error, requests.HTTPError):
        return "http_error"
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, requests.ConnectionError):
        return "connection_error"
    if isinstance(error, requests.RequestException):
        return "request_error"
    if isinstance(error, SourceError):
        return str(error)
    if isinstance(error, KeyError) and error.args and isinstance(error.args[0], str):
        return "missing field " + error.args[0]  # keys are literals in this module
    return "unexpected value type" if isinstance(error, TypeError) else "invalid value"


def http_status(error):
    response = getattr(error, "response", None)
    return response.status_code if isinstance(error, requests.HTTPError) and response is not None else None


def collect(batch_dt=None, context=None):
    run_started = time.monotonic()
    batch_dt = batch_dt or utcnow()
    if batch_dt.tzinfo is None:
        raise ValueError("batch timestamp needs an offset")
    batch_id = batch_dt.astimezone(timezone.utc).isoformat()
    records, attempts = [], {}

    def capture(facility, fetch, attempted=None):
        attempted = attempted or utcnow().isoformat()
        detail = status = None
        try:
            rows = fetch()
            invalid = [r for r in rows if r["status"] == "invalid"]
            state = "failed" if len(invalid) == len(rows) else "partial" if invalid else "success"
            code = "invalid_source_value" if invalid else None
            detail = ", ".join(sorted({r["reason"] for r in invalid})) or None
            records.extend(rows)
        except (requests.RequestException, ValueError, TypeError, KeyError, DeadlineError) as exc:
            rows, state, code = [], "failed", error_code(exc)
            detail, status = error_detail(exc), http_status(exc)
        attempts[facility] = {"attempted_at": attempted, "state": state, "error_code": code,
                              "error_detail": detail, "http_status": status,
                              "expected_metrics": EXPECTED[facility],
                              "collected_metrics": [r["metric"] for r in rows]}

    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        spent = []
        methodist_attempted = utcnow().isoformat()
        try:
            methodist = methodist_payload(session, context, spent)
            methodist_error = None
        except (requests.RequestException, ValueError, TypeError, KeyError, DeadlineError) as exc:
            methodist, methodist_error = None, exc
        elapsed = round(sum(spent) * 1000)
        for facility in METHODIST:
            def fetch_methodist(facility=facility):
                if methodist_error is not None:
                    raise methodist_error
                return [parse_methodist(methodist, facility, batch_id, elapsed)]
            capture(facility, fetch_methodist, methodist_attempted)

        try:
            token, token_error = inquicker_token(session, context), None
        except (requests.RequestException, ValueError, TypeError, KeyError, DeadlineError) as exc:
            token, token_error = None, exc
        for facility in SAINT_FRANCIS:
            def fetch_slots(facility=facility):
                if token_error is not None:
                    raise token_error
                return [fetch_saint_francis(session, token, facility, batch_id, context)]
            capture(facility, fetch_slots)

        def fetch_forrest():
            spent = []
            response = request(session, "GET", FORREST_URL, context, spent=spent)
            return parse_forrest(response.text, batch_id, round(sum(spent) * 1000))
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
