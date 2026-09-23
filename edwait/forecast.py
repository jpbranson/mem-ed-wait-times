"""Offline M5 benchmarks; no production forecast artifacts or patient predictions."""

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from math import sqrt
from statistics import mean

from edwait.analysis import BaselineIndex, ZONE, quantile
from edwait.data import METRIC, timestamp, validate_record

CADENCE = 900
HORIZONS = (15, 30, 60, 120)
MODELS = ("carry_forward", "daily_naive", "weekly_naive", "m1_median")


def grid(records, start, end):
    """A slot labeled T contains observations in [T-15min,T); never at T."""
    start, end = timestamp(start), timestamp(end)
    slots, counts = defaultdict(dict), Counter()
    for row in records:
        validate_record(row)
        at = timestamp(row["observed_at"])
        if row["metric"] != METRIC or not start <= at < end:
            continue
        counts["input_records"] += 1
        if row["wait_minutes"] < 0:
            counts["negative_records_excluded"] += 1
            continue
        slot = (int(at.timestamp()) // CADENCE + 1) * CADENCE
        rank = (at, timestamp(row["batch_id"]), row["wait_minutes"])
        prior = slots[row["facility"]].get(slot)
        if prior:
            counts["slot_collisions"] += 1
        if prior is None or rank > prior[0]:
            slots[row["facility"]][slot] = (rank, row)
    return {f: {s: r for s, (_, r) in values.items()} for f, values in slots.items()}, dict(counts)


def predictions(slots, origin, horizon, m1_value, delay_slots=0):
    cutoff = origin - delay_slots * CADENCE
    # An empty most recent available slot is an abstention, never an imputation.
    current = slots.get(cutoff)
    if current is None:
        return dict.fromkeys(MODELS)
    result = {"carry_forward": current["wait_minutes"], "m1_median": m1_value}
    for name, period in (("daily_naive", 96), ("weekly_naive", 672)):
        source = origin + horizon * 60 - period * CADENCE
        row = slots.get(source) if source <= cutoff else None
        result[name] = row["wait_minutes"] if row else None
    return result


def metrics(rows, model):
    supported = [r for r in rows if r["actual"] is not None and r["predictions"][model] is not None]
    errors = [r["predictions"][model] - r["actual"] for r in supported]
    targets = sum(r["actual"] is not None for r in rows)
    return {"origins": len(rows), "targets": targets,
            "missing_targets": len(rows) - targets, "scored": len(errors),
            "abstentions_with_target": targets - len(errors),
            "availability_with_target": len(errors) / targets if targets else None,
            "days": len({r["origin"][:10] for r in supported}),
            "mae": mean(abs(e) for e in errors) if errors else None,
            "rmse": sqrt(mean(e * e for e in errors)) if errors else None,
            "bias": mean(errors) if errors else None}


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["facility"], row["horizon_minutes"]].append(row)
    reports = []
    for (facility, horizon), group in sorted(groups.items()):
        matched = [r for r in group if r["actual"] is not None and all(r["predictions"][m] is not None for m in MODELS)]
        report = {"facility": facility, "horizon_minutes": horizon, "models": {}}
        for model in MODELS:
            report["models"][model] = {
                "all": metrics(group, model), "matched": metrics(matched, model),
                "zero_targets": metrics([r for r in group if r["actual"] == 0], model),
                "spike_targets": metrics([r for r in group if r["spike"]], model),
            }
        eligible = [m for m in MODELS if report["models"][m]["matched"]["mae"] is not None]
        report["development_winner"] = min(eligible, key=lambda m: (report["models"][m]["matched"]["mae"], MODELS.index(m))) if eligible else None
        reports.append(report)
    return reports


def replay(payload, start, end, *, delay_slots=0):
    """Score hourly origins within a phase, excluding targets crossing its end."""
    start, end = timestamp(start), timestamp(end)
    source_start, source_end = timestamp(payload["start"]), timestamp(payload["end"])
    if not source_start <= start < end <= source_end or delay_slots not in (0, 1):
        raise ValueError("phase must be inside snapshot; delay must be 0 or 1 slot")
    if int(start.timestamp()) % 3600 or int(end.timestamp()) % 3600:
        raise ValueError("phase boundaries must be UTC hours")
    slots, counts = grid(payload["records"], payload["start"], payload["end"])
    # This cache is keyed by origin-local date, not target-local date. That
    # distinction prevents cross-midnight forecasts from using the future day.
    indexes, output = {}, []
    origin = start
    while origin < end:
        available = origin - timedelta(seconds=delay_slots * CADENCE)
        day = available.astimezone(ZONE).date()
        if day not in indexes:
            cutoff = datetime.combine(day, time.min, ZONE).astimezone(timezone.utc)
            lower = cutoff - timedelta(days=30)
            past = [r for values in slots.values() for r in values.values()
                    if lower <= timestamp(r["observed_at"]) < cutoff]
            indexes = {day: BaselineIndex(past)}
        index = indexes[day]
        origin_slot = int(origin.timestamp())
        for facility, values in sorted(slots.items()):
            past_values = sorted(r["wait_minutes"] for s, r in values.items()
                                 if origin_slot - 28 * 86400 < s <= int(available.timestamp()))
            p90 = quantile(past_values, .9) if len(past_values) >= 64 else None
            for horizon in HORIZONS:
                target = origin + timedelta(minutes=horizon)
                if target >= end:
                    continue
                local = target.astimezone(ZONE)
                m1 = index.baseline(facility, local.date(), local.hour)["median"]
                actual = values.get(int(target.timestamp()), {}).get("wait_minutes")
                output.append({"facility": facility, "origin": origin.isoformat(),
                               "target": target.isoformat(), "horizon_minutes": horizon,
                               "actual": actual, "spike": actual is not None and p90 is not None and actual > p90,
                               "predictions": predictions(values, origin_slot, horizon, m1, delay_slots)})
        origin += timedelta(hours=1)
    return {"grid": counts, "summary": summarize(output)}, output
