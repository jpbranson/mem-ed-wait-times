"""Latest artifact generation; collection failures never advance last_success."""

import json
from datetime import datetime, timezone

from edwait.data import METRIC, missing_object, timestamp, validate_record

LATEST_KEY = "data/latest.json"
DEFAULT_FRESHNESS = {"expected_collection_seconds": 900, "stale_after_seconds": 1800,
                     "refresh_seconds": 60, "request_timeout_seconds": 10}


def build_latest(previous, records, attempts, facilities, *, generated_at, freshness=None):
    previous = previous or {}
    if previous and (previous.get("schema_version") != 1 or previous.get("metric") != METRIC):
        raise ValueError("unsupported previous latest artifact")
    settings = dict(DEFAULT_FRESHNESS, **(freshness or {}))
    if any(type(v) is not int or v <= 0 for v in settings.values()):
        raise ValueError("freshness settings must be positive integers")
    old = {f["slug"]: f for f in previous.get("facilities", [])}
    readings = {}
    for row in records:
        validate_record(row)
        if row["metric"] == METRIC:
            current = readings.get(row["facility"])
            if current is None or timestamp(row["observed_at"]) > timestamp(current["observed_at"]):
                readings[row["facility"]] = row
    entries = []
    for facility in facilities:
        slug = facility["slug"]
        prior = old.get(slug, {})
        success = prior.get("last_success")
        if success is not None:
            validate_record(success)
            if success["facility"] != slug or success["metric"] != METRIC:
                raise ValueError("previous reading identity mismatch")
        new = readings.get(slug)
        if new and (success is None or timestamp(new["observed_at"]) > timestamp(success["observed_at"])):
            success = new
        attempt = prior.get("last_attempt")
        incoming = attempts.get(slug)
        if incoming and (attempt is None or timestamp(incoming["batch_id"]) > timestamp(attempt["batch_id"])):
            attempt = incoming
        state = "failed" if attempt and attempt["state"] == "failed" else ("reporting" if success else "missing")
        entries.append({"slug": slug, "display_name": facility["display_name"], "region": facility["region"],
                        "timezone": facility["timezone"], "last_success": success,
                        "last_attempt": attempt, "reporting_state": state})
    times = [timestamp(f["last_success"]["observed_at"]) for f in entries if f["last_success"]]
    return {"schema_version": 1, "method_version": "latest-v1", "metric": METRIC,
            "generated_at": generated_at, "freshness": settings,
            "source_range": {"start": min(times).isoformat() if times else None, "end": max(times).isoformat() if times else None},
            "coverage": {"configured": len(entries), "with_reading": len(times),
                         "failed_latest_attempt": sum(f["reporting_state"] == "failed" for f in entries),
                         "missing": sum(f["last_success"] is None for f in entries)},
            "facilities": entries}


def publish_latest(s3, bucket, records, attempts, facilities, *, freshness=None):
    """Conditional complete replacement; concurrent invocations merge on retry."""
    for _ in range(4):
        try:
            response = s3.get_object(Bucket=bucket, Key=LATEST_KEY)
            previous = json.loads(response["Body"].read())
            condition = {"IfMatch": response["ETag"]}
        except Exception as exc:
            if not missing_object(exc):
                raise
            previous, condition = None, {"IfNoneMatch": "*"}
        artifact = build_latest(previous, records, attempts, facilities,
                                generated_at=datetime.now(timezone.utc).isoformat(), freshness=freshness)
        try:
            s3.put_object(Bucket=bucket, Key=LATEST_KEY, Body=json.dumps(artifact, allow_nan=False).encode(),
                          ContentType="application/json", CacheControl="no-store, max-age=0", **condition)
            return artifact
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") not in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
                raise
    raise RuntimeError("latest publication conflicted repeatedly; previous artifact retained")
