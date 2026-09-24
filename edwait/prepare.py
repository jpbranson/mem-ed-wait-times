"""Build website-owned M1 and M2 context from one history read before Quarto."""

import argparse
import json
import os
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from edwait.analysis import BaselineIndex, METHOD_VERSION, ZONE, quantile
from edwait.data import History, METRIC, coverage, registry, timestamp, utc
from edwait.snapshot import load_window
from edwait import stability
from edwait.travel import build_travel


def build_comparisons(history, now, facilities=None, policy=None):
    now = utc(now)
    facilities = facilities or registry()
    rows = [r for r in history.records if timestamp(r["observed_at"]) <= now]
    index = BaselineIndex(rows, policy)
    local_day = now.astimezone(ZONE).date()
    history_start = now - timedelta(days=7)
    stability_start, stability_end = stability.reference_window(now, stability.POLICY["lookback_days"])
    entries, latency = [], []
    for facility in facilities:
        slug = facility["slug"]
        timings = sorted(r["latency_ms"] for r in rows if r["facility"] == slug and r["metric"] == METRIC and timestamp(r["observed_at"]) >= history_start)
        latency.append({"slug": slug, "samples": len(timings), "median_ms": quantile(timings, .5) if timings else None,
                        "p95_ms": quantile(timings, .95) if timings else None})
        # Daily reference cuts guarantee no same-day readings can enter a model.
        # Yesterday covers retained observations just across local midnight.
        models = {str(day): [index.baseline(slug, day, hour) for hour in range(24)]
                  for day in (local_day - timedelta(days=1), local_day)}
        points = []
        for at, value, _, _ in index.by_facility[slug]:
            if not history_start <= at <= now:
                continue
            result = index.compare(slug, at.isoformat(), value)
            model = result["model"]
            # Compact fixed-width tuples; the schema documents the column order.
            points.append([at.isoformat(), value, model["median"], model["low"], model["high"], result["delta"],
                           result["percentile"], model["support"]["days"], model["support"]["coverage"], model["group"]])
        entries.append({"slug": slug, "models": models, "history": points,
                        "stability": stability.summarize(stability.window_points(index, slug, stability_start, stability_end))})
    observed = [timestamp(r["observed_at"]) for r in rows]
    return {"schema_version": 1, "method_version": METHOD_VERSION, "metric": METRIC,
            "generated_at": now.isoformat(), "local_timezone": str(ZONE),
            "valid_until": utc(datetime.combine(local_day + timedelta(days=1), time.min, ZONE)).isoformat(),
            "history_start": history_start.isoformat(), "policy": index.policy,
            "source_range": {"start": min(observed).isoformat() if observed else None,
                             "end": max(observed).isoformat() if observed else None},
            "stability": {"method_version": stability.METHOD_VERSION, "policy": stability.POLICY.copy(),
                          "source_start": stability_start.isoformat(), "source_end": stability_end.isoformat()},
            "coverage": coverage(replace(history, records=rows), [f["slug"] for f in facilities]), "latency": latency, "facilities": entries}


def write_artifact(artifact, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic local replacement, then S3's complete object replacement on sync.
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(artifact, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", help="Explicit dated local snapshot for replay/preview only")
    parser.add_argument("--now", help="Explicit timezone-aware cutoff (required with --snapshot)")
    parser.add_argument("--output", default="dashboard/comparisons.json")
    parser.add_argument("--travel-output", default="dashboard/travel.json")
    args = parser.parse_args()
    if args.snapshot and not args.now:
        parser.error("--snapshot requires an explicit --now; dated history must not masquerade as live")
    now = timestamp(args.now) if args.now else datetime.now(timezone.utc)
    if args.snapshot:
        source = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        history = History(**{k: source[k] for k in History.__dataclass_fields__})
    else:
        import boto3
        from botocore.config import Config
        # Seven display days plus the model lookback, padded one UTC partition
        # for local-day and batch/observation midnight differences.
        from edwait.analysis import DEFAULT_POLICY
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=DEFAULT_POLICY["lookback_days"] + 8)
        s3 = boto3.client("s3", config=Config(max_pool_connections=10))
        history = load_window(s3, os.environ.get("BUCKET", "mem-ed-wait-times"), start, now)
    artifact = build_comparisons(history, now)
    travel = build_travel(history, now)
    write_artifact(artifact, args.output)
    write_artifact(travel, args.travel_output)
    print(json.dumps({"output": args.output, "facilities": len(artifact["facilities"]),
                      "historical_points": sum(len(f["history"]) for f in artifact["facilities"]),
                      "generated_at": artifact["generated_at"], "travel_output": args.travel_output}))


if __name__ == "__main__":
    main()
