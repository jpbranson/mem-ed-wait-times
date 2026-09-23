"""Collect raw observations, retain attempt diagnostics, and publish freshness."""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import boto3
import requests

from edwait.data import METRIC, registry, validate_record
from edwait.latest import publish_latest

logger = logging.getLogger()
logger.setLevel(logging.INFO)
BASE_URL = "https://sites.bmhcc.org/api/waittimes/waittimes.php"
FACILITIES = [f["slug"] for f in registry()]


def build_key(batch_dt):
    return f"raw/ed_wait/dt={batch_dt:%Y-%m-%d}/{batch_dt:%Y%m%dT%H%M%SZ}.jsonl"


def fetch_facility(session, fac, batch_id):
    response = session.get(BASE_URL, params={"fac": fac}, timeout=(3, 7))
    response.raise_for_status()
    observed_at = datetime.now(timezone.utc).isoformat()
    payload = response.json()
    if not isinstance(payload, dict) or not payload:
        raise ValueError("empty or non-object response")
    records = []
    for key, value in payload.items():
        # Accept integer strings without silently truncating decimals or booleans.
        if not (type(value) is int or isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip())):
            raise ValueError("non-integer upstream metric")
        records.append(validate_record({"facility": fac, "metric": key, "wait_minutes": int(value),
                                        "observed_at": observed_at, "batch_id": batch_id,
                                        "latency_ms": round(response.elapsed.total_seconds() * 1000)}))
    return records


def collect(batch_dt, context=None):
    batch_id, records, attempts = batch_dt.isoformat(), [], {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        for fac in FACILITIES:
            attempt = {"batch_id": batch_id, "attempted_at": datetime.now(timezone.utc).isoformat(),
                       "state": "failed", "error_code": None}
            if context and context.get_remaining_time_in_millis() < 25000:
                attempt["error_code"] = "collection_deadline"
            else:
                try:
                    fetched = fetch_facility(session, fac, batch_id)
                    records.extend(fetched)
                    if any(r["metric"] == METRIC for r in fetched):
                        attempt["state"] = "success"
                    else:
                        attempt["error_code"] = "expected_metric_missing"
                except requests.RequestException:
                    attempt["error_code"] = "request_failed"
                except (ValueError, TypeError):
                    attempt["error_code"] = "invalid_response"
                time.sleep(0.5)
            attempts[fac] = attempt
            if attempt["state"] == "failed":
                logger.warning("facility_collection_failed facility=%s code=%s", fac, attempt["error_code"])
    return records, attempts


def to_jsonl(records):
    return "\n".join(json.dumps(r, allow_nan=False) for r in records) + "\n"


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    bucket = os.environ["BUCKET"]
    # Required at deployment: fail clearly instead of silently disabling live data.
    latest_bucket = os.environ["LATEST_BUCKET"]
    stale_after = int(os.environ.get("STALE_AFTER_SECONDS", "1800"))
    if stale_after <= 0:
        raise ValueError("STALE_AFTER_SECONDS must be positive")
    batch_dt = datetime.now(timezone.utc)
    records, attempts = collect(batch_dt, context)
    key = build_key(batch_dt)
    if records:
        s3.put_object(Bucket=bucket, Key=key, Body=to_jsonl(records).encode(), ContentType="application/x-ndjson")
    summary = {"schema_version": 1, "batch_id": batch_dt.isoformat(), "metric": METRIC,
               "generated_at": datetime.now(timezone.utc).isoformat(), "records": len(records),
               "expected_facilities": len(FACILITIES),
               "succeeded": sum(a["state"] == "success" for a in attempts.values()),
               "failed": sum(a["state"] == "failed" for a in attempts.values()), "attempts": attempts}
    s3.put_object(Bucket=bucket, Key=key.replace("raw/ed_wait/", "operations/collection/").replace(".jsonl", ".json"),
                  Body=json.dumps(summary).encode(), ContentType="application/json")
    logger.info("collection_summary %s", json.dumps({k: v for k, v in summary.items() if k != "attempts"}))
    artifact = publish_latest(s3, latest_bucket, records, attempts, registry(), freshness={"stale_after_seconds": stale_after})
    logger.info("latest_published coverage=%s", json.dumps(artifact["coverage"]))
    if not summary["succeeded"]:
        raise RuntimeError("No expected wait metrics collected; failure artifact published")
    return {"records": len(records), "key": key, "coverage": artifact["coverage"]}


if __name__ == "__main__":
    print(lambda_handler({}, None))
