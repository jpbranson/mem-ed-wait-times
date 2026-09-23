"""Validated, provenance-preserving historical reads using UTC batch boundaries."""

import gzip
import hashlib
import json
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
LOCAL_TIMEZONE = "America/Chicago"
METRIC = "CV_ED_Wait"
FIELDS = {"facility", "metric", "wait_minutes", "observed_at", "batch_id", "latency_ms"}


def timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("expected a timezone-aware ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp has no timezone")
    return result.astimezone(UTC)


def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("explicit timezone required")
    return value.astimezone(UTC)


def local_time(value):
    return timestamp(value).astimezone(ZoneInfo(LOCAL_TIMEZONE))


def validate_record(row):
    if not isinstance(row, dict) or set(row) != FIELDS:
        raise ValueError("expected exactly the six observation fields")
    for name in ("facility", "metric"):
        if not isinstance(row[name], str) or not row[name].strip():
            raise ValueError(f"invalid {name}")
    for name in ("wait_minutes", "latency_ms"):
        if type(row[name]) is not int:
            raise ValueError(f"{name} must be an integer")
    if row["latency_ms"] < 0:
        raise ValueError("negative latency")
    if timestamp(row["observed_at"]) < timestamp(row["batch_id"]):
        raise ValueError("observation predates batch")
    return row


def registry():
    return json.loads(Path(__file__).with_name("facilities.json").read_text(encoding="utf-8"))["facilities"]


def list_objects(s3, bucket, prefix):
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    return sorted((o for p in pages for o in p.get("Contents", [])), key=lambda o: o["Key"])


def source_fingerprint(objects):
    manifest = [{k: o[k] for k in ("Key", "ETag", "Size")} for o in sorted(objects, key=lambda o: o["Key"])]
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def missing_object(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound")


@dataclass
class History:
    records: list = field(default_factory=list)
    partitions: list = field(default_factory=list)
    rejected_records: int = 0
    duplicate_records: int = 0
    conflicting_duplicates: int = 0
    issues: list = field(default_factory=list)

    def reject(self, key, line, reason):
        self.rejected_records += 1
        if len(self.issues) < 25:
            self.issues.append({"key": key, "line": line, "reason": str(reason)})


def load_history(s3, bucket, start, end, *, metric=METRIC, now=None):
    """Read [start,end) by batch_id, not observed_at, converting bounds to UTC.

    Cross-midnight observations stay with their batch. metric=None returns all
    metrics, still deduplicated independently. Original records are never edited.
    S3 failures abort the read; malformed objects/lines are counted and excluded.
    """
    start, end = utc(start), utc(end)
    now = utc(now or datetime.now(UTC))
    if start >= end or end > now:
        raise ValueError("require start < end <= now")
    result, candidates = History(), {}
    day = start.date()
    while day <= (end - timedelta(microseconds=1)).date():
        raw = [o for o in list_objects(s3, bucket, f"raw/ed_wait/dt={day}/") if o["Key"].endswith(".jsonl")]
        key = f"compacted/ed_wait/dt={day}/data.jsonl.gz"
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if not missing_object(exc):
                raise
            head = None
        matched = bool(raw and head and day < now.date() and
                       head.get("Metadata", {}).get("source-fingerprint") == source_fingerprint(raw))
        if matched:
            selected, source, completeness = [{"Key": key, "ETag": head["ETag"]}], "compacted", "snapshot_matches_raw"
        elif raw:
            selected, source = raw, "raw"
            completeness = "open_day" if day >= now.date() else "raw_snapshot"
        elif head:
            selected, source, completeness = [{"Key": key, "ETag": head["ETag"]}], "compacted", "unverified_no_raw"
        else:
            selected, source, completeness = [], "missing", "missing"
        result.partitions.append({"date": str(day), "source": source, "completeness": completeness, "objects": len(selected)})
        for obj in selected:
            body = s3.get_object(Bucket=bucket, Key=obj["Key"], IfMatch=obj["ETag"])["Body"].read()
            try:
                if obj["Key"].endswith(".gz"):
                    body = gzip.decompress(body)
                lines = body.decode("utf-8").splitlines()
            except (OSError, EOFError, UnicodeError, zlib.error) as exc:
                result.reject(obj["Key"], None, exc)
                continue
            for line_number, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    row = validate_record(json.loads(line))
                    batch, observed = timestamp(row["batch_id"]), timestamp(row["observed_at"])
                    if batch.date() != day or observed > now:
                        raise ValueError("wrong partition or future observation")
                except (ValueError, TypeError) as exc:
                    result.reject(obj["Key"], line_number, exc)
                    continue
                if not start <= batch < end or (metric is not None and row["metric"] != metric):
                    continue
                logical_key = (batch, row["facility"], row["metric"])
                # Latest observation wins; ties use lexical source key, then line.
                rank = (observed, obj["Key"], line_number)
                if logical_key in candidates:
                    result.duplicate_records += 1
                    if candidates[logical_key][1] != row:
                        result.conflicting_duplicates += 1
                if logical_key not in candidates or rank > candidates[logical_key][0]:
                    candidates[logical_key] = (rank, row)
        day += timedelta(days=1)
    result.records = sorted((value[1] for value in candidates.values()),
                            key=lambda r: (timestamp(r["observed_at"]), r["facility"], r["metric"], timestamp(r["batch_id"])))
    return result


def coverage(history, facilities, *, metric=METRIC, gap_seconds=1200):
    """Coverage relative to observed batches; never asserts scheduled completeness."""
    rows = [r for r in history.records if r["metric"] == metric]
    batches = sorted({timestamp(r["batch_id"]) for r in rows})
    counts = Counter(r["facility"] for r in rows)
    expected = set(facilities)
    return {
        "metric": metric, "observations": len(rows), "observed_batches": len(batches),
        "missing_facility_observations": sum(len(batches) - counts[f] for f in expected),
        "facilities": {f: {"observations": counts[f], "missing_in_observed_batches": len(batches) - counts[f]} for f in sorted(expected)},
        "unknown_facilities": sorted(set(counts) - expected),
        "collection_gaps": [{"from": a.isoformat(), "to": b.isoformat(), "seconds": (b - a).total_seconds()}
                            for a, b in zip(batches, batches[1:]) if (b - a).total_seconds() > gap_seconds],
        "rejected_records": history.rejected_records, "duplicate_records": history.duplicate_records,
        "conflicting_duplicates": history.conflicting_duplicates, "partitions": history.partitions,
    }
