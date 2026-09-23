"""Read a dated, validated M0 history snapshot for reproducible offline replay."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boto3
from botocore.config import Config
from edwait.data import timestamp
from edwait.snapshot import load_window

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    s3 = boto3.client("s3", region_name="us-east-1", config=Config(max_pool_connections=10))
    history = load_window(s3, "mem-ed-wait-times", timestamp(args.start), timestamp(args.end))
    payload = {"bucket": "mem-ed-wait-times", "start": args.start, "end": args.end, **asdict(history)}
    body = json.dumps(payload, sort_keys=True).encode()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    print(json.dumps({"records": len(history.records), "partitions": len(history.partitions),
                      "rejected": history.rejected_records, "duplicates": history.duplicate_records,
                      "sha256": hashlib.sha256(body).hexdigest()}))
