"""Bounded parallel partition reads using M0's source selection and validation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from edwait.data import History, load_history, timestamp, utc


def load_window(s3, bucket, start, end, workers=8):
    start, end = utc(start), utc(end)
    if start >= end or end > datetime.now(timezone.utc):
        raise ValueError("require start < end <= current UTC time")
    windows = []
    cursor = start
    while cursor < end:
        stop = min(end, cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        windows.append((cursor, stop))
        cursor = stop
    result = History()
    def read(window):
        return load_history(s3, bucket, *window, now=end)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(read, windows):
            result.records.extend(part.records)
            result.partitions.extend(part.partitions)
            result.rejected_records += part.rejected_records
            result.duplicate_records += part.duplicate_records
            result.conflicting_duplicates += part.conflicting_duplicates
            result.issues.extend(part.issues[:max(0, 25 - len(result.issues))])
    result.records.sort(key=lambda r: (timestamp(r["observed_at"]), r["facility"], r["metric"]))
    return result
