"""Run M5 v2 candidates by phase; calibration/holdout require the committed freeze record."""

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
from edwait.forecast import grid, replay
from edwait.forecast_models import CANDIDATES, GATES, SIMPLE, SPEC, attach_intervals, evaluate, replay_candidates, score

# Each phase starts its replay 7 days early so intervals have past errors; only [score, end) is scored.
PHASES = {"development": ("2026-08-19T00:00:00Z", "2026-08-26T00:00:00Z", "2026-09-09T00:00:00Z"),
          "calibration": ("2026-09-02T00:00:00Z", "2026-09-09T00:00:00Z", "2026-09-16T00:00:00Z"),
          "holdout": ("2026-09-09T00:00:00Z", "2026-09-16T00:00:00Z", "2026-09-23T00:00:00Z")}
FREEZE = Path("docs/m5-freeze.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def worker(job):
    facility, slots, start, end, delay = job
    rows, fits = replay_candidates(slots, start, end, delay_slots=delay)
    return facility, rows, fits


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("--phase", choices=PHASES, default="development")
    parser.add_argument("--delay-slots", type=int, choices=(0, 1), default=0)
    parser.add_argument("--study", type=Path, default=Path("build/m5-study-v2"))
    parser.add_argument("--confirm-holdout", action="store_true", help="required once; the holdout is scored only after freeze and calibration")
    args = parser.parse_args()
    body = Path(args.snapshot).read_bytes()
    manifest = json.loads(Path("docs/m5-study-manifest.json").read_text())
    if hashlib.sha256(body).hexdigest() != manifest["snapshot_sha256"]:
        raise ValueError("Snapshot differs from the frozen M5 input")
    code = {p: digest(p) for p in ("edwait/forecast.py", "edwait/forecast_models.py", "scripts/m5_candidates.py")}
    spec = {"specification": SPEC, "gates": GATES, "snapshot_sha256": manifest["snapshot_sha256"], "code_sha256": code}
    args.study.mkdir(parents=True, exist_ok=True)
    spec_path = args.study / "spec.json"
    canonical = json.dumps(spec, indent=2)
    if spec_path.exists() and spec_path.read_text() != canonical:
        raise ValueError("Specification or code changed; use a separate study directory")
    spec_path.write_text(canonical, encoding="utf-8")
    freeze = None
    if args.phase != "development":
        freeze = json.loads(FREEZE.read_text())
        if freeze["spec_sha256"] != hashlib.sha256(canonical.encode()).hexdigest():
            raise ValueError("Frozen selection does not match this specification and code")
    if args.phase == "holdout" and not (args.confirm_holdout and (args.study / "calibration-delay0.json").exists()):
        raise ValueError("Holdout requires a scored calibration phase and --confirm-holdout")
    warm, begin, end = PHASES[args.phase]
    payload = json.loads(body)
    slots, _ = grid(payload["records"], payload["start"], payload["end"])
    started = perf_counter()
    _, rows = replay(payload, warm, end, delay_slots=args.delay_slots)
    by_key = {(r["facility"], int(timestamp(r["origin"]).timestamp()), r["horizon_minutes"]): r for r in rows}
    for r in rows:
        r["origin_ts"], r["target_ts"] = int(timestamp(r["origin"]).timestamp()), int(timestamp(r["target"]).timestamp())
    first, last = (int(timestamp(t).timestamp()) for t in (warm, end))
    fits = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs = [(f, s, first, last, args.delay_slots) for f, s in sorted(slots.items())]
        for facility, predictions, attempts in pool.map(worker, jobs):
            for p in predictions:
                by_key[facility, p["origin"], p["horizon_minutes"]]["predictions"][p["model"]] = p["prediction"]
            fits.extend({"facility": facility, **a} for a in attempts)
    attach_intervals(rows, (*SIMPLE, *CANDIDATES))
    scored = [r for r in rows if r["origin_ts"] >= int(timestamp(begin).timestamp())]
    scored_fits = [f for f in fits if f["day"] >= timestamp(begin).isoformat()]
    daily = defaultdict(float)
    for f in scored_fits:
        daily[f["day"]] += f["seconds"]
    update_seconds = max(daily.values()) if daily else 0.0
    failures = defaultdict(Counter)
    for f in scored_fits:
        failures[f["facility"], f["model"]][f["status"]] += 1
    groups = defaultdict(list)
    for r in scored:
        groups[r["facility"], r["horizon_minutes"]].append(r)
    names = (*SIMPLE, *CANDIDATES)
    summary = []
    selections = {(s["facility"], s["horizon_minutes"]): s for s in freeze["selections"]} if freeze else {}
    for (facility, horizon), group in sorted(groups.items()):
        matched = [r for r in group if r["actual"] is not None and all(r["predictions"].get(m) is not None for m in names)]
        scores = {m: {"all": score(group, m), "matched": score(matched, m)} for m in names}
        if freeze:
            benchmark, candidate = selections[facility, horizon]["benchmark"], selections[facility, horizon]["candidate"]
        else:
            rank = lambda pool: min(pool, key=lambda m: (scores[m]["matched"]["mae"] if scores[m]["matched"]["mae"] is not None else float("inf"), names.index(m)))
            benchmark, candidate = rank(SIMPLE), rank(CANDIDATES)
        counts = failures[facility, candidate]
        failure = counts["fit_failed"] / sum(counts.values()) if counts else 0.0
        summary.append({"facility": facility, "horizon_minutes": horizon, "models": scores,
                        "decision": evaluate(group, benchmark, candidate, failure, update_seconds)})
    report = {"phase": args.phase, "delay_slots": args.delay_slots, "window": {"warm_up": warm, "scored": begin, "end": end},
              "spec_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "frozen": freeze is not None,
              "runtime_seconds": perf_counter() - started, "maximum_daily_fit_seconds": update_seconds,
              "fit_counts": {m: dict(Counter(f["status"] for f in scored_fits if f["model"] == m)) for m in CANDIDATES},
              "fit_seconds": {m: sum(f["seconds"] for f in scored_fits if f["model"] == m) for m in CANDIDATES},
              "summary": summary, "public_release": False}
    suffix = f"{args.phase}-delay{args.delay_slots}"
    (args.study / f"{suffix}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.study / f"{suffix}-origins.json").write_text(json.dumps(scored), encoding="utf-8")
    print(json.dumps({"phase": args.phase, "delay": args.delay_slots, "rows": len(scored), "runtime_seconds": round(report["runtime_seconds"], 1),
                      "fit_counts": report["fit_counts"], "passes": sum(s["decision"]["passes"] for s in summary),
                      "candidates": dict(Counter(s["decision"]["candidate"] for s in summary)),
                      "benchmarks": dict(Counter(s["decision"]["benchmark"] for s in summary))}))


if __name__ == "__main__":
    main()
