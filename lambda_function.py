import gzip
import os
from datetime import datetime, timedelta, timezone

import boto3

BUCKET = os.environ["BUCKET"]
DATASET = "ed_wait"
s3 = boto3.client("s3")


def list_keys(bucket, prefix):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def compact(bucket, day):
    src = f"raw/{DATASET}/dt={day:%Y-%m-%d}/"
    dst = f"compacted/{DATASET}/dt={day:%Y-%m-%d}/data.jsonl.gz"

    lines = []
    for key in sorted(list_keys(bucket, src)):
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        lines.extend(body.decode("utf-8").splitlines())

    if not lines:
        return None

    s3.put_object(
        Bucket=bucket,
        Key=dst,
        Body=gzip.compress(("\n".join(lines) + "\n").encode("utf-8")),
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
    )
    return dst, len(lines)


def lambda_handler(event, context):
    if event.get("date"):
        day = datetime.strptime(event["date"], "%Y-%m-%d").date()
    else:
        day = datetime.now(timezone.utc).date() - timedelta(days=1)
    result = compact(BUCKET, day)
    if result is None:
        raise RuntimeError(f"No raw objects found for {day}")
    dst, count = result
    return {"key": dst, "records": count}
