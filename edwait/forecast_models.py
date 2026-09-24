"""M5 v2 development candidates, empirical intervals and release gates (offline only)."""

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from math import pi, sqrt
from statistics import mean
import random
import warnings

import numpy as np

from edwait.analysis import ZONE
from edwait.forecast import CADENCE, HORIZONS

SIMPLE = ("carry_forward", "daily_naive", "weekly_naive", "m1_median")
CANDIDATES = ("arima_100", "arima_110", "arima_100_fourier", "profile_ar")
ORDERS = {"arima_100": (1, 0, 0), "arima_110": (1, 1, 0), "arima_100_fourier": (1, 0, 0)}
STEPS = max(HORIZONS) // 15
SPEC = {"version": "m5-candidates-v2", "candidates": list(CANDIDATES),
        "orders": {k: list(v) for k, v in ORDERS.items()},
        "training_slots": 28 * 96, "minimum_training_slots": 14 * 96,
        "minimum_coverage": .95, "maximum_missing_run": 4,
        "support_trim": "drop slots through the last missing run longer than the limit, then apply the support rule",
        "fourier": "local America/Chicago time of slot midpoint; daily harmonics k=1,2; constant",
        "profile_ar": "median by local hour and weekday/weekend over the trimmed window (fallback: window median "
                      "when a cell has fewer than 8 values); per-step least-squares persistence through zero, clipped to [0, 1]",
        "refit_seconds": 86400, "origins_seconds": 3600, "max_iterations": 100,
        "negative_forecasts": "clip to zero", "missing_training": "no imputation",
        "intervals": {"levels": [80, 95], "method": "empirical quantiles of the same model's own errors for targets "
                      "observed by the origin, previous 7 days", "window_seconds": 7 * 86400, "minimum_errors": 72,
                      "lower_bound": "clip to zero"}}
GATES = {"minimum_matched": 150, "minimum_days": 6, "minimum_gain_minutes": 1.0, "minimum_gain_fraction": .05,
         "rmse_no_worse": True, "bootstrap": {"blocks": "UTC origin day", "resamples": 2000, "seed": 20260924,
                                              "interval": .95, "require_lower_above_zero": True},
         "minimum_availability": .95, "maximum_fit_failure": .01, "interval_tolerance": .05,
         "maximum_update_seconds": 600}


def trim(values):
    """Keep only the trailing part after the last long outage; return None if unsupported."""
    finite = np.isfinite(values)
    start, run = 0, 0
    for i, present in enumerate(finite):
        run = 0 if present else run + 1
        if run > SPEC["maximum_missing_run"]:
            start = i + 1
    kept = values[start:]
    present = np.isfinite(kept)
    if (present.sum() < SPEC["minimum_training_slots"] or present.mean() < SPEC["minimum_coverage"]
            or not present[-1]):
        return None, start
    return kept, start


def local_parts(slots):
    """Local hour fraction and weekend flag for each slot midpoint (label minus 7.5 minutes)."""
    hours, weekend = [], []
    for s in slots:
        local = datetime.fromtimestamp(int(s) - CADENCE // 2, timezone.utc).astimezone(ZONE)
        hours.append(local.hour + local.minute / 60)
        weekend.append(local.weekday() >= 5)
    return np.array(hours), np.array(weekend)


def fourier(slots):
    hours, _ = local_parts(slots)
    angle = 2 * pi * hours / 24
    return np.column_stack([f(k * angle) for k in (1, 2) for f in (np.sin, np.cos)])


def fit_arima(values, order, exog=None):
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ARIMA(values, exog=exog, order=order, trend="c" if order[1] == 0 else "n").fit(
            method_kwargs={"maxiter": SPEC["max_iterations"]})
    if not fitted.mle_retvals.get("converged", False):
        raise ValueError("nonconvergent_fit")
    return fitted


class Profile:
    """Direct persistence of deviations from a local hour/day-type median profile."""

    def __init__(self, values, slots):
        hours, weekend = local_parts(slots)
        keys = list(zip(hours.astype(int), weekend))
        present = np.isfinite(values)
        cells = defaultdict(list)
        for key, value, ok in zip(keys, values, present):
            if ok:
                cells[key].append(value)
        overall = float(np.median(values[present]))
        self.cells = {k: float(np.median(v)) if len(v) >= 8 else overall for k, v in cells.items()}
        self.overall = overall
        deviation = values - np.array([self.cells.get(k, overall) for k in keys])
        self.beta = {}
        for step in range(1, STEPS + 2):
            a, b = deviation[:-step], deviation[step:]
            ok = np.isfinite(a) & np.isfinite(b)
            denominator = float(np.sum(a[ok] ** 2))
            beta = float(np.sum(a[ok] * b[ok]) / denominator) if denominator else 0.0
            self.beta[step] = min(1.0, max(0.0, beta))

    def usual(self, slot):
        hours, weekend = local_parts([slot])
        return self.cells.get((int(hours[0]), bool(weekend[0])), self.overall)

    def forecast(self, slot, value, step):
        return max(0.0, self.usual(slot + step * CADENCE) + self.beta[step] * (value - self.usual(slot)))


def series(slots, first, last):
    labels = np.arange(first, last + 1, CADENCE)
    return labels, np.array([slots.get(int(s), {}).get("wait_minutes", np.nan) for s in labels], dtype=float)


def replay_candidates(slots, start, end, *, delay_slots=0, fitter=fit_arima, clock=None):
    """Daily fits at UTC midnight; hourly origins use only slots at or before origin - delay."""
    from time import perf_counter
    clock = clock or perf_counter
    delay = delay_slots * CADENCE
    output, fits = [], []
    for model in CANDIDATES:
        day = start
        while day < end:
            cutoff = day - delay
            labels, raw = series(slots, cutoff - (SPEC["training_slots"] - 1) * CADENCE, cutoff)
            values, offset = trim(raw)
            state, status, began = None, "insufficient_history", clock()
            if values is not None:
                kept = labels[offset:]
                try:
                    if model == "profile_ar":
                        state = Profile(values, kept)
                    else:
                        state = fitter(values, ORDERS[model], fourier(kept) if model == "arima_100_fourier" else None)
                    status = "ok"
                except (ValueError, np.linalg.LinAlgError):
                    status = "fit_failed"
            fits.append({"model": model, "day": datetime.fromtimestamp(day, timezone.utc).isoformat(),
                         "status": status, "seconds": clock() - began})
            for origin in range(day, min(day + 86400, end), 3600):
                available = origin - delay
                if origin > day and state is not None and model != "profile_ar":
                    new_labels, arrived = series(slots, available - 3 * CADENCE, available)
                    try:
                        state = state.extend(arrived, exog=fourier(new_labels) if model == "arima_100_fourier" else None)
                    except (ValueError, np.linalg.LinAlgError):
                        state = None
                # Do not bridge a new long outage after a daily ARIMA fit.
                if model != "profile_ar" and not any(slots.get(s) is not None for s in range(available - 3 * CADENCE, available + 1, CADENCE)):
                    state = None
                forecast = None
                current = slots.get(available)
                if state is not None and current is not None:
                    try:
                        if model == "profile_ar":
                            forecast = np.array([state.forecast(available, current["wait_minutes"], k)
                                                 for k in range(1, STEPS + 1 + delay_slots)])
                        else:
                            future = np.arange(available + CADENCE, available + (STEPS + delay_slots + 1) * CADENCE, CADENCE)
                            candidate = np.asarray(state.forecast(steps=STEPS + delay_slots,
                                                   exog=fourier(future) if model == "arima_100_fourier" else None), dtype=float)
                            if np.all(np.isfinite(candidate)):
                                forecast = np.maximum(candidate, 0)
                    except (ValueError, np.linalg.LinAlgError):
                        forecast = None
                for horizon in HORIZONS:
                    if origin + horizon * 60 < end:
                        step = horizon // 15 + delay_slots
                        output.append({"model": model, "origin": origin, "horizon_minutes": horizon,
                                       "prediction": float(forecast[step - 1]) if forecast is not None else None})
            day += 86400
    return output, fits


def attach_intervals(rows, models):
    """Add past-only empirical intervals; errors count only once their target slot has passed."""
    window, minimum = SPEC["intervals"]["window_seconds"], SPEC["intervals"]["minimum_errors"]
    groups = defaultdict(list)
    for row in rows:
        groups[row["facility"], row["horizon_minutes"]].append(row)
    for group in groups.values():
        group.sort(key=lambda r: r["origin_ts"])
        for model in models:
            history = sorted((r["target_ts"], r["actual"] - r["predictions"][model]) for r in group
                             if r["actual"] is not None and r["predictions"].get(model) is not None)
            times = [t for t, _ in history]
            for row in group:
                row.setdefault("intervals", {})[model] = None
                if row["predictions"].get(model) is None:
                    continue
                errors = [e for _, e in history[bisect_right(times, row["origin_ts"] - window):bisect_right(times, row["origin_ts"])]]
                if len(errors) < minimum:
                    continue
                point = row["predictions"][model]
                bands = {}
                for level in SPEC["intervals"]["levels"]:
                    tail = (1 - level / 100) / 2
                    lo, hi = np.quantile(errors, [tail, 1 - tail])
                    bands[str(level)] = [max(0.0, point + float(lo)), max(0.0, point + float(hi))]
                row["intervals"][model] = bands


def score(rows, model):
    supported = [r for r in rows if r["actual"] is not None and r["predictions"].get(model) is not None]
    errors = [r["predictions"][model] - r["actual"] for r in supported]
    targets = sum(r["actual"] is not None for r in rows)
    result = {"origins": len(rows), "targets": targets, "scored": len(errors),
              "availability_with_target": len(errors) / targets if targets else None,
              "days": len({r["origin"][:10] for r in supported}),
              "mae": mean(abs(e) for e in errors) if errors else None,
              "rmse": sqrt(mean(e * e for e in errors)) if errors else None,
              "bias": mean(errors) if errors else None}
    for level in SPEC["intervals"]["levels"]:
        banded = [r for r in supported if (r.get("intervals") or {}).get(model)]
        inside = [lo <= r["actual"] <= hi for r in banded for lo, hi in [r["intervals"][model][str(level)]]]
        widths = [r["intervals"][model][str(level)][1] - r["intervals"][model][str(level)][0] for r in banded]
        result[f"coverage_{level}"] = mean(inside) if inside else None
        result[f"width_{level}"] = float(np.median(widths)) if widths else None
        result[f"intervals_{level}"] = len(inside)
    return result


def bootstrap_gain(rows, benchmark, candidate):
    """Paired daily-block bootstrap of MAE gain (benchmark minus candidate)."""
    config = GATES["bootstrap"]
    days = defaultdict(list)
    for r in rows:
        days[r["origin"][:10]].append(abs(r["predictions"][benchmark] - r["actual"]) - abs(r["predictions"][candidate] - r["actual"]))
    blocks = list(days.values())
    if len(blocks) < 2:
        return None
    rng = random.Random(config["seed"])
    draws = []
    for _ in range(config["resamples"]):
        sample = [d for _ in blocks for d in rng.choice(blocks)]
        draws.append(mean(sample))
    tail = (1 - config["interval"]) / 2
    return [float(np.quantile(draws, tail)), float(np.quantile(draws, 1 - tail))]


def evaluate(rows, benchmark, candidate, fit_failure, update_seconds):
    """Apply every frozen gate to one facility/horizon; returns checks and the release decision."""
    matched = [r for r in rows if r["actual"] is not None and r["predictions"].get(benchmark) is not None
               and r["predictions"].get(candidate) is not None]
    b, c, own = score(matched, benchmark), score(matched, candidate), score(rows, candidate)
    gain = b["mae"] - c["mae"] if matched else None
    interval = bootstrap_gain(matched, benchmark, candidate) if matched else None
    tolerance = GATES["interval_tolerance"]
    checks = {
        "support": len(matched) >= GATES["minimum_matched"] and c["days"] >= GATES["minimum_days"],
        "gain": gain is not None and gain >= max(GATES["minimum_gain_minutes"], GATES["minimum_gain_fraction"] * b["mae"]),
        "rmse": bool(matched) and c["rmse"] <= b["rmse"],
        "bootstrap": interval is not None and interval[0] > 0,
        "availability": (own["availability_with_target"] or 0) >= GATES["minimum_availability"],
        "fit_failure": fit_failure <= GATES["maximum_fit_failure"],
        "coverage": all(own[f"coverage_{l}"] is not None and abs(own[f"coverage_{l}"] - l / 100) <= tolerance for l in (80, 95)),
        "runtime": update_seconds <= GATES["maximum_update_seconds"],
    }
    return {"benchmark": benchmark, "candidate": candidate, "matched": len(matched),
            "benchmark_scores": b, "candidate_matched": c, "candidate_own": own,
            "gain_minutes": gain, "gain_interval": interval, "checks": checks, "passes": all(checks.values())}
