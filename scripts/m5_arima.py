"""Run the protocol's two ARIMA pilots on development data, with daily refits."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

# Bound numerical worker threads before importing NumPy/scipy in parent or child.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.data import timestamp
from edwait.forecast import grid, metrics, MODELS
from edwait.forecast_arima import CANDIDATES, SPEC, replay_facility


def worker(job):
    facility, slots, start, end = job
    started = perf_counter()
    rows, fits = replay_facility(slots, start, end)
    return facility, rows, fits, perf_counter() - started


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("--study", type=Path, default=Path("build/m5-study"))
    args = parser.parse_args()
    body = Path(args.snapshot).read_bytes()
    manifest = json.loads((args.study / "manifest.json").read_text())
    if hashlib.sha256(body).hexdigest() != manifest["snapshot_sha256"]:
        raise ValueError("Snapshot differs from frozen benchmark input")
    spec = {**SPEC, "snapshot_sha256": manifest["snapshot_sha256"],
            "code_sha256": hashlib.sha256(Path("edwait/forecast_arima.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    spec_path = args.study / "arima-spec.json"
    canonical = json.dumps(spec, indent=2)
    if spec_path.exists() and spec_path.read_text() != canonical:
        raise ValueError("ARIMA specification changed; use a separate study directory")
    spec_path.write_text(canonical, encoding="utf-8")
    payload = json.loads(body)
    slots, _ = grid(payload["records"], payload["start"], payload["end"])
    start, end = [int(timestamp(manifest["policy"][f"development_{k}"]).timestamp()) for k in ("start", "end")]
    baseline = json.loads((args.study / "origins-delay0.json").read_text())
    by_key = {(r["facility"], int(timestamp(r["origin"]).timestamp()), r["horizon_minutes"]): r for r in baseline}
    fits, runtimes = [], {}
    began = perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for facility, predictions, attempts, seconds in pool.map(worker, [(f, s, start, end) for f, s in sorted(slots.items())]):
            for row in predictions:
                by_key[facility, row["origin"], row["horizon_minutes"]]["predictions"][row["model"]] = row["prediction"]
            fits.extend({"facility": facility, **r} for r in attempts)
            runtimes[facility] = seconds
            print(json.dumps({"facility": facility, "seconds": round(seconds, 2), "fits": dict(Counter(r["status"] for r in attempts))}), flush=True)
    groups = defaultdict(list)
    for row in baseline:
        groups[row["facility"], row["horizon_minutes"]].append(row)
    summary = []
    model_names = (*MODELS, *CANDIDATES)
    for (facility, horizon), rows in sorted(groups.items()):
        matched = [r for r in rows if r["actual"] is not None and all(r["predictions"].get(m) is not None for m in model_names)]
        scores = {m: {"all": metrics(rows, m), "matched": metrics(matched, m)} for m in model_names}
        summary.append({"facility": facility, "horizon_minutes": horizon, "models": scores})
    report = {"specification": spec, "runtime_seconds": perf_counter() - began,
              "facility_runtimes": runtimes, "fit_counts": dict(Counter(r["status"] for r in fits)),
              "fits": fits, "summary": summary, "public_release": False}
    (args.study / "arima-development.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.study / "arima-origins.json").write_text(json.dumps(baseline), encoding="utf-8")
    print(json.dumps({"runtime_seconds": report["runtime_seconds"], "fit_counts": report["fit_counts"]}))


if __name__ == "__main__":
    main()
