"""Compare saved check_routes.py outputs against a baseline run, route by route.

Reads only the sanitized JSON files (timing, distance, delay; no geometry) and sends
nothing to TomTom. Pairs are matched on (origin, destination) and only routes that
ended within tolerance in both runs are compared.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.analysis import quantile


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = {(r["origin"], r["slug"]): r for r in data["routes"] if r.get("within_tolerance")}
    return data["summary"], rows


def spread(values):
    values = sorted(values)
    return {"median": round(quantile(values, .5), 2), "p90": round(quantile(values, .9), 2),
            "min": round(values[0], 2), "max": round(values[-1], 2)} if values else None


def compare(base, rows):
    pairs = [(base[k], rows[k]) for k in sorted(base.keys() & rows.keys())]
    extra = [(after["seconds"] - before["seconds"]) / 60 for before, after in pairs]
    ratio = [after["seconds"] / before["seconds"] for before, after in pairs if before["seconds"]]
    delays = [r["traffic_delay_seconds"] for _, r in pairs]
    return {"pairs": len(pairs), "extra_minutes": spread(extra), "ratio": spread(ratio),
            "reported_delay_routes": sum(1 for d in delays if d), "unknown_delay_routes": sum(1 for d in delays if d is None),
            "max_reported_delay_minutes": round(max((d or 0) for d in delays) / 60, 2) if delays else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("others", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base_summary, base = load(args.baseline)
    keep = ("checked_at", "traffic", "departure", "requests", "passed")
    report = {"baseline": {"file": args.baseline.name, **{k: base_summary.get(k) for k in keep}}, "comparisons": []}
    for path in args.others:
        summary, rows = load(path)
        entry = {"file": path.name, **{k: summary.get(k) for k in keep}, "all": compare(base, rows), "by_origin": {}}
        for origin in sorted({o for o, _ in base}):
            entry["by_origin"][origin] = compare({k: v for k, v in base.items() if k[0] == origin},
                                                 {k: v for k, v in rows.items() if k[0] == origin})
        report["comparisons"].append(entry)
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
