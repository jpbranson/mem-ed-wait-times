"""Run the frozen M3 relationship protocol on M5's snapshot; no public artifact."""

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edwait.data import registry, short_name
from edwait.relationships import POLICY, analyze


def digest(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def figures(report, facilities, directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from scripts.m5_report import save_svg

    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "edwait-m3-relationships-v1"})
    order = [f["slug"] for f in facilities]
    labels = [short_name(f) for f in facilities]
    fig, axes = plt.subplots(1, 2, figsize=(17, 8), layout="constrained")
    for ax, period, title in zip(axes, ("discovery", "confirmation"), ("Discovery · supported 19 Aug–1 Sep", "Confirmation · 2–15 Sep")):
        matrix = [[float("nan")] * len(order) for _ in order]
        for pair in report["pairs"]:
            value = (pair[f"{period}_co_deviation"] or {}).get("r")
            i, j = order.index(pair["a"]), order.index(pair["b"])
            matrix[i][j] = matrix[j][i] = float("nan") if value is None else value
        image = ax.imshow(matrix, cmap="RdBu_r", norm=TwoSlopeNorm(0, -0.6, 0.6))
        ax.set_xticks(range(len(order)), labels, rotation=90, fontsize=10)
        ax.set_yticks(range(len(order)), labels if ax is axes[0] else [], fontsize=10)
        ax.set_title(title)
    fig.colorbar(image, ax=axes, shrink=0.7, label="Spearman ρ of hourly difference from usual")
    fig.suptitle("Same-time co-deviation of published waits · associations only, not patient movement")
    fig.savefig(directory / "m3-co-deviation.png", dpi=140)
    save_svg(fig, directory / "m3-co-deviation.svg")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained", sharey=True)
    for ax, family, title in zip(axes, ("co_deviation", "same_time_change"), ("Difference from usual", "Hour-over-hour change")):
        for period, color in (("discovery", "#0072B2"), ("confirmation", "#D55E00")):
            points = [(p["distance_km"], p[f"{period}_{family}"]["r"]) for p in report["pairs"]
                      if p[f"{period}_{family}"] and p[f"{period}_{family}"]["r"] is not None]
            ax.scatter(*zip(*points), s=18, alpha=0.7, color=color, label=period.title())
        ax.axvline(report["policy"]["neighbor_km"], color="#555555", linestyle="--", linewidth=1)
        ax.axhline(0, color="#999999", linewidth=0.8)
        ax.set(title=title, xlabel="Campus distance (km, straight line)")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Same-time Spearman ρ")
    axes[0].legend(fontsize=10)
    fig.suptitle("Pair association by campus distance · dashed line marks the 50 km neighbor rule")
    fig.savefig(directory / "m3-distance.png", dpi=140)
    save_svg(fig, directory / "m3-distance.svg")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot")
    parser.add_argument("--output", type=Path, default=Path("build/m3-study"))
    parser.add_argument("--results", type=Path, default=Path("docs/m3-relationship-results.json"))
    parser.add_argument("--figures", type=Path, default=Path("docs/figures"))
    args = parser.parse_args()
    body = Path(args.snapshot).read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    if sha != POLICY["snapshot_sha256"]:
        raise ValueError(f"snapshot {sha} is not the protocol's frozen input")
    payload = json.loads(body)
    facilities = registry()
    started = perf_counter()
    report, tests = analyze(payload, facilities)
    report.update({"snapshot_sha256": sha, "records": len(payload["records"]),
                   "protocol_sha256": digest("docs/m3-relationship-protocol.md"),
                   "code_sha256": digest("edwait/relationships.py"), "python": platform.python_version(),
                   "runtime_seconds": perf_counter() - started, "generated_at": datetime.now(timezone.utc).isoformat()})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "tests.json").write_text(json.dumps(tests), encoding="utf-8")
    args.results.write_text(json.dumps(report, indent=1), encoding="utf-8")
    figures(report, facilities, args.figures)
    labels = {}
    for c in report["candidates"]:
        labels[c["label"]] = labels.get(c["label"], 0) + 1
    print(json.dumps({"tests": report["tests"], "candidates": len(report["candidates"]), "labels": labels,
                      "runtime_seconds": round(report["runtime_seconds"], 1)}))


if __name__ == "__main__":
    main()
