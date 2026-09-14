import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
import boto3
import os
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_URL = "https://sites.bmhcc.org/api/waittimes/waittimes.php"
DATASET = "ed_wait"
BUCKET = os.environ["BUCKET"]
s3 = boto3.client("s3")

FACILITIES = [
    "arlington",
    "childrens",
    "collierville",
    "huntingdon",
    "memphis",
    "tipton",
    "union-city",
    "crittenden",
    "nea",
    "anderson",
    "baptist-medical-center-attala",
    "booneville",
    "calhoun",
    "desoto",
    "golden-triangle",
    "baptist-medical-center-leake",
    "north-mississippi",
    "union-county",
    "baptist-medical-center-yazoo",
    "baptist-medical-center"
]



def build_key(batch_dt):
    return (
        f"raw/{DATASET}/"
        f"dt={batch_dt:%Y-%m-%d}/"
        f"{batch_dt:%Y%m%dT%H%M%SZ}.jsonl"
    )

def fetch_facility(session, fac, batch_id):
    resp = session.get(BASE_URL, params={"fac": fac}, timeout=10)
    resp.raise_for_status()
    observed_at = datetime.now(timezone.utc).isoformat()

    return [
        {
            "facility": fac,
            "metric": key,
            "wait_minutes": int(value),
            "observed_at": observed_at,
            "batch_id": batch_id,
            "latency_ms": round(resp.elapsed.total_seconds() * 1000),
        }
        for key, value in resp.json().items()
    ]



def collect(batch_dt):
    batch_id = batch_dt.isoformat()
    records = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        for fac in FACILITIES:
            try:
                records.extend(fetch_facility(session, fac, batch_id))
            except Exception as exc:
                logger.warning("%s failed: %s", fac, exc)
            time.sleep(0.5)
    return records


def to_jsonl(records):
    return "\n".join(json.dumps(r) for r in records) + "\n"

def write_local(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_jsonl(records), encoding="utf-8", newline="\n")

def write_s3(records, bucket, key):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=to_jsonl(records).encode("utf-8"),
        ContentType="application/x-ndjson",
    )


def lambda_handler(event, context):
    batch_dt = datetime.now(timezone.utc)
    records = collect(batch_dt)

    if not records:
        raise RuntimeError("No records collected - refusing to write empty batch")

    key = build_key(batch_dt)
    write_s3(records, BUCKET, key)

    logger.info("Wrote %d records to %s", len(records), key)
    return {"records": len(records), "key": key}


if __name__ == "__main__":
    print(lambda_handler({}, None))
