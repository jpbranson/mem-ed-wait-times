"""Dated candidate selection and later-period replay, using only prior local days."""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.analysis import BaselineIndex, DEFAULT_POLICY
from edwait.data import timestamp


def summarize(rows):
    supported = [r for r in rows if r["delta"] is not None]
    return {"comparisons": len(rows), "supported": len(supported),
            "support_rate": len(supported) / len(rows) if rows else None,
            "median_absolute_deviation": median(abs(r["delta"]) for r in supported) if supported else None,
            "mean_absolute_deviation": mean(abs(r["delta"]) for r in supported) if supported else None,
            "typical_band_fraction": mean(r["low"] <= r["value"] <= r["high"] for r in supported) if supported else None,
            "unusual_fraction": mean(r["unusual"] in ("above_usual", "below_usual") for r in supported) if supported else None,
            "groups": dict(Counter(r["group"] for r in supported))}


def replay(payload):
    records = payload["records"]
    # At most one observation per facility per UTC hour limits repetitive scoring.
    # Selection and later inspection intervals were fixed before examining scores.
    sampled = {}
    for row in sorted(records, key=lambda r: timestamp(r["observed_at"])):
        key = row["facility"], row["observed_at"][:13]
        sampled.setdefault(key, row)
    targets = [r for r in sampled.values() if timestamp(r["observed_at"]) >= timestamp("2026-08-19T00:00:00Z")]
    reports, comparisons = [], {}
    for lookback in (28, 42):
        for radius in (1, 2):
            label = f"{lookback}d-radius{radius}"
            index = BaselineIndex(records, {"lookback_days": lookback, "hour_radius": radius})
            output = []
            for r in targets:
                result = index.compare(r["facility"], r["observed_at"], r["wait_minutes"])
                model = result["model"]
                output.append({"facility": r["facility"], "at": r["observed_at"], "value": r["wait_minutes"],
                               "median": model["median"], "low": model["low"], "high": model["high"],
                               "delta": result["delta"], "percentile": result["percentile"], "unusual": result["unusual"],
                               "group": model["group"], "support": model["support"]})
            selection = [r for r in output if timestamp(r["at"]) < timestamp("2026-09-07T00:00:00Z")]
            holdout = [r for r in output if timestamp(r["at"]) >= timestamp("2026-09-07T00:00:00Z")]
            reports.append({"candidate": label, "selection": summarize(selection), "later_period": summarize(holdout)})
            comparisons[label] = output
            print(label, json.dumps(reports[-1]), flush=True)
    # Common supported cases ensure missing baseline support cannot improve a score.
    common = set.intersection(*[{(r["facility"], r["at"]) for r in rows if r["delta"] is not None}
                               for rows in comparisons.values()])
    for report in reports:
        rows = [r for r in comparisons[report["candidate"]] if (r["facility"], r["at"]) in common and timestamp(r["at"]) < timestamp("2026-09-07T00:00:00Z")]
        report["common_selection"] = summarize(rows)
    trend_reports = []
    for minutes in (30, 60):
        for threshold in (5, 10):
            index = BaselineIndex(records, {"trend_minutes": minutes, "meaningful_minutes": threshold})
            counts = Counter()
            by_facility = defaultdict(list)
            for r in targets:
                result = index.trend(r["facility"], r["observed_at"], r["wait_minutes"])
                counts[result["state"]] += 1
                by_facility[r["facility"]].append((timestamp(r["observed_at"]), result["state"]))
            reversals, adjacent = 0, 0
            for points in by_facility.values():
                for (a, x), (b, y) in zip(points, points[1:]):
                    if (b - a).total_seconds() < 4500:
                        adjacent += 1
                        reversals += {x, y} == {"rising", "falling"}
            trend_reports.append({"minutes": minutes, "meaningful_minutes": threshold, "states": dict(counts),
                                  "opposite_direction_next_hour": reversals / adjacent if adjacent else None})
    return {"selection_start": "2026-08-19T00:00:00Z", "selection_end_exclusive": "2026-09-07T00:00:00Z",
            "later_start": "2026-09-07T00:00:00Z", "later_end_exclusive": payload["end"],
            "policy_except_candidates": DEFAULT_POLICY, "candidates": reports, "trend_candidates": trend_reports}, comparisons


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("--output", default=".cache/m1-replay.json")
    args = parser.parse_args()
    body = Path(args.snapshot).read_bytes()
    payload = json.loads(body)
    report, comparisons = replay(payload)
    report["source"] = {key: payload[key] for key in ("bucket", "start", "end", "partitions", "rejected_records", "duplicate_records")}
    report["source"]["records"] = len(payload["records"])
    report["source"]["snapshot_sha256"] = hashlib.sha256(body).hexdigest()
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    Path(args.output).with_name("m1-comparisons.json").write_text(json.dumps(comparisons), encoding="utf-8")
