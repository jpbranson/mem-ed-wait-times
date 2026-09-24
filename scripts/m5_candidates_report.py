"""Render the v2 development/calibration results into a dated report, aggregates and figures."""

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
from edwait.forecast_models import CANDIDATES, SIMPLE
from scripts.m5_report import save_svg

STUDY = Path("build/m5-study-v2")
DOCS = Path("docs")
BLUE, ORANGE, GREEN, INK, MUTED = "#0072B2", "#D55E00", "#009E73", "#222222", "#6b6b6b"
LABELS = {"carry_forward": "latest reading", "m1_median": "M1 median", "daily_naive": "daily naive",
          "weekly_naive": "weekly naive", "arima_100": "ARIMA(1,0,0)", "arima_110": "ARIMA(1,1,0)",
          "arima_100_fourier": "ARIMA(1,0,0)+Fourier", "profile_ar": "profile persistence"}


def load(name):
    path = STUDY / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def compact(report):
    """Aggregate metrics only; origin-level rows stay in ignored local files."""
    keep = ("scored", "targets", "availability_with_target", "days", "mae", "rmse", "bias",
            "coverage_80", "coverage_95", "width_80", "width_95")
    summary = []
    for s in report["summary"]:
        d = s["decision"]
        summary.append({"facility": s["facility"], "horizon_minutes": s["horizon_minutes"],
                        "models": {m: {"all": {f: v["all"][f] for f in keep},
                                       "matched": {f: v["matched"][f] for f in ("scored", "mae", "rmse", "bias")}} for m, v in s["models"].items()},
                        "decision": {k: d[k] for k in ("benchmark", "candidate", "matched", "gain_minutes", "gain_interval", "checks", "passes")}
                                    | {"candidate_own": {f: d["candidate_own"][f] for f in keep}}})
    return {k: v for k, v in report.items() if k != "summary"} | {"summary": summary}


def rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def key(s):
    return f"{s['facility']}@{s['horizon_minutes']}"


def main():
    freeze = json.loads((DOCS / "m5-freeze.json").read_text())
    shortlist = set(freeze["shortlist"])
    dev, dev1, cal = load("development-delay0"), load("development-delay1"), load("calibration-delay0")
    diagnostics = load("diagnostics")
    figures = DOCS / "figures"
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "edwait-m5-candidates-v2"})

    # 1. Selection regression: development gain against calibration gain for the frozen pairs.
    calibrated = {key(s): s["decision"] for s in cal["summary"]}
    fig, ax = plt.subplots(figsize=(9, 6.5), layout="constrained")
    for s in dev["summary"]:
        k, c = key(s), calibrated[key(s)]
        x, y = s["decision"]["gain_minutes"], c["gain_minutes"]
        if k in shortlist:
            style = dict(color=GREEN if c["passes"] else ORANGE, marker="o" if c["passes"] else "X", s=110, zorder=3,
                         edgecolors="white", linewidths=1.5)
            ax.scatter(x, y, **style)
            left = x < 2 and y > 1  # keeps nearby shortlisted labels apart
            ax.annotate(k.replace("@", " · ") + " min", (x, y), textcoords="offset points", xytext=(-10, 8) if left else (8, 8),
                        ha="right" if left else "left", fontsize=11, color=INK)
        else:
            ax.scatter(x, y, color=MUTED, marker=".", s=60, alpha=.6, zorder=2)
    ax.axhline(0, color=MUTED, linewidth=.8)
    ax.axvline(0, color=MUTED, linewidth=.8)
    ax.scatter([], [], color=GREEN, marker="o", s=90, label="Shortlisted · passed calibration")
    ax.scatter([], [], color=ORANGE, marker="X", s=90, label="Shortlisted · failed calibration")
    ax.scatter([], [], color=MUTED, marker=".", s=60, label="Not shortlisted (cannot qualify)")
    ax.legend(loc="upper left", fontsize=11, frameon=False)
    ax.set(xlabel="Development MAE gain vs strongest simple benchmark (minutes)",
           ylabel="Calibration MAE gain, same frozen pair (minutes)")
    ax.grid(alpha=.2)
    fig.suptitle("Development gains mostly did not repeat · 80 facility/horizon pairs\n"
                 "Development 26 Aug–8 Sep, calibration 9–15 Sep 2026 UTC; positive = candidate better")
    fig.savefig(figures / "m5-candidates-selection.png", dpi=160)
    save_svg(fig, figures / "m5-candidates-selection.svg")
    plt.close(fig)

    # 2. Interval coverage by model and phase, against nominal.
    models = (*SIMPLE, *CANDIDATES)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained", sharey=True)
    for ax, level in zip(axes, (80, 95)):
        for i, model in enumerate(models):
            for offset, report, color, marker, label in ((-.17, dev, BLUE, "o", "Development"), (.17, cal, ORANGE, "D", "Calibration")):
                values = [s["models"][model]["all"][f"coverage_{level}"] for s in report["summary"]]
                values = [v * 100 for v in values if v is not None]
                ax.scatter([v for v in values], [i + offset] * len(values), color=color, marker=marker, s=18, alpha=.45,
                           label=label if i == 0 else None, edgecolors="none")
        ax.axvspan(level - 5, level + 5, color=MUTED, alpha=.12, label="Gate: nominal ± 5 points")
        ax.axvline(level, color=INK, linewidth=1)
        ax.set(xlabel=f"Empirical {level}% interval coverage (%)", title=f"{level}% intervals")
        ax.set_yticks(range(len(models)), [LABELS[m] for m in models])
        ax.grid(axis="x", alpha=.2)
    axes[0].invert_yaxis()
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=11, frameon=False)
    fig.suptitle("Trailing seven-day empirical intervals · one dot per facility/horizon")
    fig.savefig(figures / "m5-candidates-coverage.png", dpi=160)
    save_svg(fig, figures / "m5-candidates-coverage.svg")
    plt.close(fig)

    # 3. Calibration backtest for the only shortlisted pair that passed.
    passed = [s for s in cal["summary"] if key(s) in shortlist and s["decision"]["passes"]]
    if passed:
        chosen = passed[0]
        rows = [r for r in json.loads((STUDY / "calibration-delay0-origins.json").read_text())
                if r["facility"] == chosen["facility"] and r["horizon_minutes"] == chosen["horizon_minutes"]
                and "2026-09-12" <= r["target"][:10] <= "2026-09-14"]
        rows.sort(key=lambda r: r["target"])
        bench, cand = chosen["decision"]["benchmark"], chosen["decision"]["candidate"]
        times = [datetime.fromisoformat(r["target"]) for r in rows]
        fig, ax = plt.subplots(figsize=(14, 6), layout="constrained")
        band = [(t, r["intervals"][cand]["80"]) for t, r in zip(times, rows) if (r.get("intervals") or {}).get(cand)]
        ax.fill_between([t for t, _ in band], [b[0] for _, b in band], [b[1] for _, b in band], color=ORANGE, alpha=.15,
                        step="mid", label=f"{LABELS[cand]} 80% interval", linewidth=0)
        ax.plot(times, [r["actual"] for r in rows], color=INK, linewidth=2, label="Observed published reading")
        ax.plot(times, [r["predictions"][bench] for r in rows], color=BLUE, linewidth=2, linestyle="--", label=f"{LABELS[bench]} (benchmark)")
        ax.plot(times, [r["predictions"][cand] for r in rows], color=ORANGE, linewidth=2, label=LABELS[cand])
        ax.set(ylabel="Published minutes", xlabel="Target time, 12–14 September 2026 UTC")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
        ax.grid(alpha=.2)
        fig.legend(*ax.get_legend_handles_labels(), loc="outside lower center", ncol=4, fontsize=11, frameon=False)
        fig.suptitle(f"{chosen['facility'].title()} · {chosen['horizon_minutes']}-minute-ahead calibration backtest\n"
                     "Hourly origins; lines connect scored targets; offline study, not a public forecast")
        fig.savefig(figures / "m5-candidates-backtest.png", dpi=160)
        save_svg(fig, figures / "m5-candidates-backtest.svg")
        plt.close(fig)

    # Report text.
    def fails(report):
        return Counter(k for s in report["summary"] for k, v in s["decision"]["checks"].items() if not v)
    def within(report, model, level):
        values = [s["models"][model]["all"][f"coverage_{level}"] for s in report["summary"]]
        return sum(v is not None and abs(v - level / 100) <= .05 for v in values)
    dev_passes = [key(s) for s in dev["summary"] if s["decision"]["passes"]]
    dev1_passes = [key(s) for s in dev1["summary"] if s["decision"]["passes"]]
    cal_pass = [key(s) for s in cal["summary"] if s["decision"]["passes"]]
    eligible = [k for k in cal_pass if k in shortlist]
    fits = sum(sum(v.values()) for v in dev["fit_counts"].values())
    ok = sum(v.get("ok", 0) for v in dev["fit_counts"].values())
    hours = [v["variance_explained_local_hour"] for v in diagnostics["facilities"].values()]
    lines = [
        "# M5 candidate study (v2) — development and calibration, 2026-09-24 UTC", "",
        "Status: offline only. Development and calibration scored with a frozen specification; the final holdout "
        "remains **unscored**. No public forecast, artifact or schema exists.", "",
        "This continues the [benchmark checkpoint](m5-validation.md) and [ARIMA pilot](m5-arima-validation.md) "
        "on the same frozen snapshot (`" + freeze["specification"]["snapshot_sha256"][:12] + "…`). The "
        "[protocol amendment](m5-study-protocol.md#amendment--2026-09-24-utc-before-calibration-scoring) "
        "records every choice made here, and the [freeze record](m5-freeze.json) fixes the "
        f"specification hash `{freeze['spec_sha256'][:12]}…`, each facility/horizon pair and the shortlist, "
        f"frozen at {freeze['frozen_at']} before calibration was scored.", "",
        "```powershell",
        ".venv\\Scripts\\python.exe scripts/m5_diagnostics.py .cache/m5-history-20260923.json",
        ".venv\\Scripts\\python.exe scripts/m5_candidates.py .cache/m5-history-20260923.json --phase development",
        ".venv\\Scripts\\python.exe scripts/m5_candidates.py .cache/m5-history-20260923.json --phase development --delay-slots 1",
        ".venv\\Scripts\\python.exe scripts/m5_freeze.py",
        ".venv\\Scripts\\python.exe scripts/m5_candidates.py .cache/m5-history-20260923.json --phase calibration",
        ".venv\\Scripts\\python.exe scripts/m5_candidates_report.py", "```", "",
        "The runner refuses calibration or holdout unless the freeze matches the specification and code hashes, "
        "and refuses the holdout without a scored calibration and `--confirm-holdout`.", "",
        "## Diagnostics (data before 9 September only)", "",
        f"Local hour of day explains {min(hours):.0%}–{max(hours):.0%} of each hospital's reading variance "
        f"({sum(h <= .105 for h in hours)} of 20 at or below about 10%; Memphis highest). One-day-lag autocorrelation "
        "is 0.02–0.52 and one-week-lag −0.01–0.40, and weekly medians move substantially (DeSoto 26→90 minutes). "
        "Readings are highly persistent over 15–30 minutes. A 96-slot seasonal ARIMA is therefore not justified; two bounded "
        "calendar candidates were added instead. Per-facility values are in the [aggregate results](m5-candidates-results.json).", "",
        "## Development (26 August–8 September UTC)", "",
        f"Cold start is fixed: {ok}/{fits} daily fits succeeded with no support abstentions or failures "
        "(v1: 40 abstentions, 92.8% availability). Where training windows are identical, v2 reproduces all 61,200 "
        "v1 ARIMA and benchmark forecasts exactly. The largest per-day sum of fit times for all 20 facilities and "
        f"four candidates was {dev['maximum_daily_fit_seconds']:.0f} s (including one-time library import), against the 600 s limit.", "",
        "Best candidate per pair: " + ", ".join(f"{LABELS[m]} {n}" for m, n in Counter(s['decision']['candidate'] for s in dev['summary']).most_common())
        + ". Strongest simple benchmark: " + ", ".join(f"{LABELS[m]} {n}" for m, n in Counter(s['decision']['benchmark'] for s in dev['summary']).most_common()) + ".", "",
        f"{len(dev_passes)}/80 pairs passed every gate on development and form the shortlist: "
        + ", ".join(k.replace("@", " ") + " min" for k in dev_passes) + ". Most failures were the minimum gain "
        f"({fails(dev)['gain']}/80) and bootstrap interval ({fails(dev)['bootstrap']}/80). These passes are "
        "selection-biased: each pair's best candidate was chosen on the same data.", "",
        f"With a one-slot (15-minute) availability delay, {len(dev1_passes)}/80 pairs passed, "
        + ", ".join(k.replace("@", " ") + " min" for k in dev1_passes) + ". Benchmark rankings were nearly unchanged.", "",
        "Intervals built from each model's trailing seven-day errors were close to nominal on development: "
        + "; ".join(f"{LABELS[m]} {within(dev, m, 80)}/80 (80%) and {within(dev, m, 95)}/80 (95%) within 5 points" for m in ("carry_forward", "arima_110", "arima_100_fourier", "profile_ar")) + ".", "",
        "## Calibration (9–15 September UTC, frozen pairs)", "",
        f"Candidates lowered MAE in {sum(s['decision']['gain_minutes'] > 0 for s in cal['summary'])}/80 pairs. "
        f"{len(cal_pass)}/80 passed every gate, but only {len(eligible)} of those was shortlisted: "
        + (", ".join(k.replace("@", " ") + " min" for k in eligible) or "none") + ". "
        "Under the frozen rule only shortlisted pairs can qualify.", "",
        "| Shortlisted pair | Frozen benchmark → candidate | Development gain | Calibration gain (95% block bootstrap) | 80% / 95% coverage | Calibration |",
        "| --- | --- | --- | --- | --- | --- |"]
    dev_by = {key(s): s["decision"] for s in dev["summary"]}
    for s in cal["summary"]:
        k = key(s)
        if k not in shortlist:
            continue
        d, o = s["decision"], s["decision"]["candidate_own"]
        failed = [c for c, v in d["checks"].items() if not v]
        lines.append(f"| {s['facility']} {s['horizon_minutes']} min | {LABELS[d['benchmark']]} → {LABELS[d['candidate']]} | "
                     f"{dev_by[k]['gain_minutes']:+.2f} | {d['gain_minutes']:+.2f} ({d['gain_interval'][0]:+.2f} to {d['gain_interval'][1]:+.2f}) | "
                     f"{o['coverage_80']:.0%} / {o['coverage_95']:.0%} | {'Pass' if d['passes'] else 'Fail: ' + ', '.join(failed)} |")
    others = [s for s in cal["summary"] if s["decision"]["passes"] and key(s) not in shortlist]
    lines += ["", "Gains are minutes of MAE reduction versus the frozen benchmark; positive favors the candidate.", "",
              "Not shortlisted but passing on calibration: "
              + ", ".join(f"{s['facility']} {s['horizon_minutes']} min ({LABELS[s['decision']['candidate']]}, {s['decision']['gain_minutes']:+.1f})" for s in others)
              + ". They cannot qualify in this study. Together with the development results, they suggest profile persistence "
              "may help at 60–120 minutes for the most variable hospitals. Testing that needs a new pre-registered study on data "
              "collected after 23 September.", "",
              f"Calibration interval coverage stayed near nominal (ARIMA(1,0,0)+Fourier {within(cal, 'arima_100_fourier', 80)}/80 and "
              f"{within(cal, 'arima_100_fourier', 95)}/80; profile persistence {within(cal, 'profile_ar', 80)}/80 and {within(cal, 'profile_ar', 95)}/80 within 5 points), "
              f"but {fails(cal)['coverage']} selected candidates missed the coverage gate at one or both levels. Maximum daily fit time was {cal['maximum_daily_fit_seconds']:.0f} s.", "",
              "![Development versus calibration gain](figures/m5-candidates-selection.png)", "",
              "![Interval coverage by model](figures/m5-candidates-coverage.png)", ""]
    if passed:
        lines += ["![Calibration backtest](figures/m5-candidates-backtest.png)", ""]
    lines += ["## Status and limits", "",
              f"Holdout-eligible: {', '.join(k.replace('@', ' ') + ' min' for k in eligible) or 'none'}. The final holdout "
              "(16–22 September UTC) is unscored. Scoring it is a one-time action; if this pair passes there, including the "
              "delayed-availability gain check, it becomes the only forecast eligible for display. Display would still require "
              "the plan's forecast artifact contract, chart validation and a deployed smoke check. A negative holdout result "
              "ends this study with forecasts disabled.", "",
              "Hourly origins give at most 168 targets per phase, and seven daily blocks make bootstrap intervals coarse. "
              "Overlapping multi-step errors are dependent. `observed_at` stands in for availability. "
              "Forecasts describe the published reading, not an individual patient's wait.", ""]
    (DOCS / "m5-candidates-validation.md").write_text("\n".join(lines), encoding="utf-8")
    results = {"freeze": {k: freeze[k] for k in ("frozen_at", "spec_sha256", "shortlist", "release_rule")},
               "diagnostics": diagnostics, "development": compact(dev), "development_delay1": compact(dev1),
               "calibration": compact(cal), "holdout": None, "public_release": False}
    (DOCS / "m5-candidates-results.json").write_text(json.dumps(rounded(results), indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"dev_passes": dev_passes, "calibration_passes": cal_pass, "eligible": eligible}))


if __name__ == "__main__":
    main()
