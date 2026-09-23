"""Render the saved development benchmarks into a dated report and static figures."""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.forecast import MODELS, HORIZONS


def save_svg(figure, path):
    figure.savefig(path, metadata={"Date": None})
    # Matplotlib writes trailing spaces in path data; normalize for clean diffs.
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--study", type=Path, default=Path("build/m5-study"))
    parser.add_argument("--output", type=Path, default=Path("docs/m5-validation.md"))
    args = parser.parse_args()
    report = json.loads((args.study / "benchmarks-delay0.json").read_text())
    delayed = json.loads((args.study / "benchmarks-delay1.json").read_text())
    manifest = json.loads((args.study / "manifest.json").read_text())
    rows = json.loads((args.study / "origins-delay0.json").read_text())
    summary = report["summary"]
    figures = args.output.parent / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    colors = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")
    labels = ("Latest reading", "Daily naive (UTC)", "Weekly naive (UTC)", "M1 median")
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "edwait-m5-benchmarks-v1"})
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    for ax, facility in zip(axes, ("memphis", "desoto", "crittenden")):
        relevant = sorted((r for r in summary if r["facility"] == facility), key=lambda r:r["horizon_minutes"])
        for model, label, color in zip(MODELS, labels, colors):
            ax.plot(HORIZONS, [r["models"][model]["matched"]["mae"] for r in relevant], marker="o", label=label, color=color)
        ax.set(title=facility.title(), xlabel="Forecast horizon (minutes)", ylabel="Mean absolute error (minutes)")
        ax.set_xticks(HORIZONS)
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=10)
    fig.suptitle("Published-wait benchmarks · development data only\n26 August–8 September 2026 UTC · matched hourly origins")
    fig.savefig(figures / "m5-benchmark-errors.png", dpi=160)
    save_svg(fig, figures / "m5-benchmark-errors.svg")
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), layout="constrained", sharex=True)
    for ax, facility in zip(axes, ("memphis", "desoto", "crittenden")):
        sample = [r for r in rows if r["facility"] == facility and r["horizon_minutes"] == 60 and r["target"].startswith("2026-09-08")]
        dates = [datetime.fromisoformat(r["target"]) for r in sample]
        ax.plot(dates, [r["actual"] for r in sample], label="Observed target", color="#222222", linewidth=2)
        for model, label, color in zip(MODELS, labels, colors):
            ax.plot(dates, [r["predictions"][model] for r in sample], label=label, color=color, linestyle="--", alpha=.8)
        ax.set(title=facility.title(), ylabel="Published minutes")
        ax.grid(alpha=.2)
    axes[0].legend(ncol=3, fontsize=10)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[-1].set_xlabel("Target-slot end, 8 September 2026 UTC")
    fig.suptitle("60-minute-ahead benchmark replay · development example\nNo prediction intervals fitted; lines connect hourly scored targets")
    fig.savefig(figures / "m5-benchmark-replay.png", dpi=160)
    save_svg(fig, figures / "m5-benchmark-replay.svg")
    plt.close(fig)
    winners = Counter(r["development_winner"] for r in summary)
    delayed_winners = Counter(r["development_winner"] for r in delayed["summary"])
    lines = ["# M5 benchmark checkpoint — 2026-09-23 UTC", "",
             "Status: implemented and locally validated offline; M5 remains in progress. No public forecasts.", "",
             "## Inputs and reproducibility", "",
             f"Frozen snapshot: {manifest['records']:,} observations across {len(manifest['source']['partitions'])} UTC partitions, "
             "29 July through 22 September 2026. M0 selected one partition source; no raw/compacted concatenation.", "",
             f"SHA-256: `{manifest['snapshot_sha256']}`. Rejections: {manifest['source']['rejected_records']}; "
             f"logical duplicates: {manifest['source']['duplicate_records']}; grid collisions resolved: {report['grid'].get('slot_collisions',0)}; "
             f"negative records excluded: {report['grid'].get('negative_records_excluded',0)}.", "",
             "[Frozen protocol](m5-study-protocol.md) defines slot/availability rules, chronological phases, "
             "benchmarks, and provisional model-release gates. [Manifest](m5-study-manifest.json) records source, dependencies and hashes. "
             "Detailed inputs and origin-level results are local ignored artifacts; the snapshot hash identifies the exact input.", "",
             "```powershell", ".venv\\Scripts\\python.exe scripts/m1_snapshot.py --start 2026-07-29T00:00:00Z --end 2026-09-23T00:00:00Z --output .cache/m5-history-20260923.json",
             ".venv\\Scripts\\python.exe scripts/m5_benchmarks.py .cache/m5-history-20260923.json --freeze-only",
             ".venv\\Scripts\\python.exe scripts/m5_benchmarks.py .cache/m5-history-20260923.json",
             ".venv\\Scripts\\python.exe scripts/m5_benchmarks.py .cache/m5-history-20260923.json --delay-slots 1",
             ".venv\\Scripts\\python.exe scripts/m5_report.py", "```", "",
             "A fresh S3 read may have a different hash if late data arrives; preserve the frozen snapshot to reproduce these exact scores. "
             "Install `requirements-analysis.txt` separately; deployment does not install modeling/plotting packages.", "",
             "## Development results", "",
             f"Scored {len(rows):,} facility/origin/horizon rows for 26 August–8 September UTC. "
             f"Lowest matched-origin MAE: carry-forward {winners['carry_forward']}/80; M1 median {winners['m1_median']}/80. "
             "Neither seasonal-naive benchmark led a combination. Ties prefer the simpler model. "
             "These are development rankings, not evidence of final-test forecast skill.", "",
             f"The 15-minute availability-delay sensitivity produced carry-forward {delayed_winners['carry_forward']}/80 "
             f"and M1 median {delayed_winners['m1_median']}/80 winners. Runtime was {report['runtime_seconds']:.1f}s "
             f"and {delayed['runtime_seconds']:.1f}s respectively on this workstation.", "",
             "![Matched-origin errors](figures/m5-benchmark-errors.png)", "",
             "Table cells show the winning baseline and its MAE in minutes. CF = latest reading; M1 = local-time median.", "",
             "| Facility | 15 min | 30 min | 60 min | 120 min |", "| --- | --- | --- | --- | --- |"]
    for facility in sorted({r["facility"] for r in summary}):
        values = []
        for horizon in HORIZONS:
            r = next(r for r in summary if r["facility"] == facility and r["horizon_minutes"] == horizon)
            winner = r["development_winner"]
            values.append(f"{'CF' if winner == 'carry_forward' else 'M1'} · {r['models'][winner]['matched']['mae']:.2f}")
        lines.append("| " + facility + " | " + " | ".join(values) + " |")
    lines.extend(["", "[All aggregate metrics](m5-benchmark-results.json) include each model's own and matched-origin MAE, RMSE, bias, "
                  "support/abstention counts, zero-target errors, and past-threshold spike errors. "
                  "Do not treat the matched subset as the entire feed or the many overlapping forecast errors as independent.", "",
                  "![60-minute benchmark replay](figures/m5-benchmark-replay.png)", "",
                  "## Validation and remaining work", "",
                  "Focused tests cover future-data mutation across local midnight, exact UTC slot boundaries, deterministic collisions, "
                  "metric separation, zero/negative/missing values, delayed availability, DST repeated hours and error denominators. "
                  "No future filling, synthetic validation targets or random split is used.", "",
                  "This checkpoint evaluates simple benchmarks. A subsequent [ARIMA development pilot](m5-arima-validation.md) "
                  "evaluates two nonseasonal candidates; seasonal diagnostics, interval calibration and final holdout scoring remain pending. "
                  "The snapshot contains the later periods, but the evaluation only scores development. "
                  "Ingestion/publication timestamps are unavailable: `observed_at` and a one-slot delay are sensitivity assumptions. "
                  "Per-facility/horizon release decisions remain **disabled** until the full protocol passes. "
                  "No forecast record/storage contract or production deployment changed.", ""])
    args.output.write_text("\n".join(lines), encoding="utf-8")
    (args.output.parent / "m5-study-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    (args.output.parent / "m5-benchmark-results.json").write_text(json.dumps({"development": report, "delayed_availability": delayed}, indent=2)+"\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
