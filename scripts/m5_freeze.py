"""Freeze development selections, shortlist and release rule before later phases are scored."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path("build/m5-study-v2")
OUTPUT = Path("docs/m5-freeze.json")
RULE = ("A facility/horizon may display a model forecast only if it was shortlisted by passing every gate on "
        "development (no delay), then passes every gate again with the frozen benchmark/candidate on calibration "
        "and on the final holdout (no delay), and on the holdout with a one-slot availability delay still meets "
        "the minimum MAE gain. Everything else stays disabled. Development scores are selection evidence only.")


def main():
    if OUTPUT.exists():
        raise SystemExit(f"{OUTPUT} already exists; a freeze is never rewritten")
    spec_text = (STUDY / "spec.json").read_text()
    report = json.loads((STUDY / "development-delay0.json").read_text())
    if report["spec_sha256"] != hashlib.sha256(spec_text.encode()).hexdigest():
        raise SystemExit("Development report does not match the current specification")
    selections = [{"facility": s["facility"], "horizon_minutes": s["horizon_minutes"],
                   "benchmark": s["decision"]["benchmark"], "candidate": s["decision"]["candidate"],
                   "shortlisted": s["decision"]["passes"]} for s in report["summary"]]
    freeze = {"frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "spec_sha256": report["spec_sha256"], "specification": json.loads(spec_text),
              "selection_source": "development-delay0 (2026-08-26 to 2026-09-09 UTC, matched origins)",
              "release_rule": RULE, "calibration_scored": False, "holdout_scored": False,
              "shortlist": [f"{s['facility']}@{s['horizon_minutes']}" for s in selections if s["shortlisted"]],
              "selections": selections}
    OUTPUT.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"shortlist": freeze["shortlist"], "spec_sha256": freeze["spec_sha256"]}))


if __name__ == "__main__":
    main()
