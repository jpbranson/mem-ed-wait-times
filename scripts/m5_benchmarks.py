"""Freeze input/policy provenance and score only M5's development interval."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.forecast import replay

POLICY = {"version": "m5-benchmarks-v1", "cadence_seconds": 900,
          "origin_frequency_seconds": 3600, "horizons_minutes": [15, 30, 60, 120],
          "development_start": "2026-08-26T00:00:00Z", "development_end": "2026-09-09T00:00:00Z",
          "calibration_end": "2026-09-16T00:00:00Z", "holdout_end": "2026-09-23T00:00:00Z",
          "availability": "observed_at proxy; completed UTC slots", "holdout_scored": False}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("--output", default="build/m5-study")
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--delay-slots", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    body = Path(args.snapshot).read_bytes()
    payload = json.loads(body)
    manifest = {"snapshot_sha256": hashlib.sha256(body).hexdigest(), "policy": POLICY,
                "source": {k: payload[k] for k in ("bucket", "start", "end", "partitions", "rejected_records", "duplicate_records", "conflicting_duplicates")},
                "records": len(payload["records"]), "python": platform.python_version(),
                "dependencies": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "statsmodels", "matplotlib")},
                "protocol_sha256": hashlib.sha256(Path("docs/m5-study-protocol.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                "code_sha256": hashlib.sha256(Path("edwait/forecast.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text())
        if any(prior[k] != value for k, value in manifest.items()):
            raise ValueError("Manifest differs: use a new output directory for a changed study")
    else:
        manifest_path.write_text(json.dumps({**manifest, "frozen_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    if args.freeze_only:
        print(json.dumps({"manifest": str(manifest_path), "sha256": manifest["snapshot_sha256"], "records": manifest["records"]}))
        return
    started = perf_counter()
    report, rows = replay(payload, POLICY["development_start"], POLICY["development_end"], delay_slots=args.delay_slots)
    report.update({"policy": POLICY, "snapshot_sha256": manifest["snapshot_sha256"], "delay_slots": args.delay_slots,
                   "runtime_seconds": perf_counter() - started, "generated_at": datetime.now(timezone.utc).isoformat()})
    suffix = f"delay{args.delay_slots}"
    (out / f"benchmarks-{suffix}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / f"origins-{suffix}.json").write_text(json.dumps(rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "runtime_seconds": report["runtime_seconds"], "winners": dict(Counter(r["development_winner"] for r in report["summary"])), "grid": report["grid"]}))


if __name__ == "__main__":
    main()
