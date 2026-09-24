"""Seasonal/persistence diagnostics on M5 data before calibration (never reads later phases)."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.analysis import ZONE
from edwait.data import timestamp
from edwait.forecast import CADENCE, grid

END = "2026-09-09T00:00:00Z"


def correlation(x, lag):
    a, b = x[:-lag], x[lag:]
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 50 else None


def explained(values, keys):
    resid = values.copy()
    for key in np.unique(keys):
        resid[keys == key] -= values[keys == key].mean()
    return float(1 - np.var(resid) / np.var(values)) if np.var(values) else None


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".cache/m5-history-20260923.json")
    body = path.read_bytes()
    manifest = json.loads(Path("docs/m5-study-manifest.json").read_text())
    if hashlib.sha256(body).hexdigest() != manifest["snapshot_sha256"]:
        raise ValueError("Snapshot differs from the frozen M5 input")
    payload = json.loads(body)
    slots, _ = grid(payload["records"], payload["start"], END)
    labels = np.arange(int(timestamp(payload["start"]).timestamp()) + CADENCE, int(timestamp(END).timestamp()) + 1, CADENCE)
    local = [datetime.fromtimestamp(int(s) - CADENCE // 2, timezone.utc).astimezone(ZONE) for s in labels]
    hour = np.array([t.hour for t in local])
    weekend = np.array([t.weekday() >= 5 for t in local])
    result = {"end_exclusive": END, "facilities": {}}
    for facility in sorted(slots):
        x = np.array([slots[facility].get(int(s), {}).get("wait_minutes", np.nan) for s in labels], dtype=float)
        ok = np.isfinite(x)
        weeks = [float(np.nanmedian(x[i:i + 672])) for i in range(0, len(x), 672)]
        result["facilities"][facility] = {
            "coverage": float(ok.mean()), "zero_share": float(np.mean(x[ok] == 0)),
            "mean": float(x[ok].mean()), "sd": float(x[ok].std()),
            "autocorrelation": {str(lag): correlation(x, lag) for lag in (1, 4, 8, 96, 672)},
            "differenced_lag96": correlation(np.diff(x), 96),
            "variance_explained_local_hour": explained(x[ok], hour[ok]),
            "variance_explained_hour_daytype": explained(x[ok], (hour * 2 + weekend)[ok]),
            "weekly_medians": weeks}
    out = Path("build/m5-study-v2/diagnostics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
