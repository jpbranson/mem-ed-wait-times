"""Run the M2 benefit-rule backtest (docs/m2-benefit-protocol.md) on the frozen snapshot.

Offline only: reads the snapshot and committed route profiles, never records at or
after M5's final holdout, and writes aggregate results. No public artifact changes.
"""

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.benefit import POLICY, analyze


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", nargs="?", default=".cache/m5-history-20260923.json")
    parser.add_argument("--profiles", type=Path, default=Path("docs/m2-route-profiles-2026-09-26.json"))
    parser.add_argument("--results", type=Path, default=Path("docs/m2-benefit-results.json"))
    args = parser.parse_args()
    body = Path(args.snapshot).read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    if sha != POLICY["snapshot_sha256"]:
        raise ValueError(f"snapshot {sha} is not the protocol's frozen input")
    started = perf_counter()
    report = analyze(json.loads(body), json.loads(args.profiles.read_text(encoding="utf-8")))
    report.update({"policy": POLICY, "snapshot_sha256": sha, "profiles_sha256": digest(args.profiles),
                   "protocol_sha256": digest("docs/m2-benefit-protocol.md"), "code_sha256": digest("edwait/benefit.py"),
                   "python": platform.python_version(), "runtime_seconds": round(perf_counter() - started, 1),
                   "generated_at": datetime.now(timezone.utc).isoformat()})
    args.results.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for name, period in report["periods"].items():
        print(f"{name}: {period['opportunities']} opportunities over {period['days']} days")
        for rule, s in period["rules"].items():
            bounds = s.get("precision_interval")
            print(f"  {rule:5} claims {s['claims']:5} days {s['claim_days']:3} precision "
                  f"{'-' if s['precision'] is None else f'{s['precision']:.3f}'} "
                  f"interval {bounds and [round(b, 3) for b in bounds]} median A {s['median_A']} p10 A {s['p10_A']}")
    print(json.dumps({"selected_rule": report["selected_rule"], "confirmation_outcome": report["confirmation_outcome"],
                      "runtime_seconds": report["runtime_seconds"]}))


if __name__ == "__main__":
    main()
