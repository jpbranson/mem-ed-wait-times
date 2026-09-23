import gzip
import os
from datetime import datetime, timedelta, timezone

import boto3

from edwait.data import list_objects, source_fingerprint

DATASET = "ed_wait"


def compact(bucket, day, s3=None):
    s3 = s3 or boto3.client("s3")
    src = f"raw/{DATASET}/dt={day:%Y-%m-%d}/"
    dst = f"compacted/{DATASET}/dt={day:%Y-%m-%d}/data.jsonl.gz"

    lines = []
    objects = [o for o in list_objects(s3, bucket, src) if o["Key"].endswith(".jsonl")]
    for obj in objects:
        body = s3.get_object(Bucket=bucket, Key=obj["Key"], IfMatch=obj["ETag"])["Body"].read()
        lines.extend(body.decode("utf-8").splitlines())

    if not lines:
        return None

    s3.put_object(
        Bucket=bucket,
        Key=dst,
        Body=gzip.compress(("\n".join(lines) + "\n").encode("utf-8")),
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
        Metadata={"source-fingerprint": source_fingerprint(objects),
                  "source-object-count": str(len(objects)),
                  "compacted-at": datetime.now(timezone.utc).isoformat()},
    )
    return dst, len(lines)


def lambda_handler(event, context):
    if event.get("date"):
        day = datetime.strptime(event["date"], "%Y-%m-%d").date()
    else:
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
    result = compact(os.environ["BUCKET"], day)
    if result is None:
        raise RuntimeError(f"No raw objects found for {day}")
    dst, count = result
    return {"key": dst, "records": count}
