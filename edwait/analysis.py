"""Past-only facility self-comparisons; these are published readings, not patients."""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from functools import lru_cache
from statistics import median
from zoneinfo import ZoneInfo

from edwait.data import LOCAL_TIMEZONE, METRIC, timestamp, utc, validate_record

ZONE = ZoneInfo(LOCAL_TIMEZONE)
METHOD_VERSION = "self-comparison-v1"
DEFAULT_POLICY = {
    "lookback_days": 28, "hour_radius": 1, "fallback_hour_radius": 2,
    "minimum_days": 8, "minimum_samples": 64, "minimum_coverage": 0.75,
    "minimum_day_coverage": 0.75, "band_low": 0.25, "band_high": 0.75,
    "unusual_low": 10, "unusual_high": 90, "meaningful_minutes": 10,
    "trend_minutes": 60, "trend_tolerance_minutes": 20, "trend_minimum_samples": 2,
    "cadence_seconds": 900, "gap_seconds": 1200,
}


@lru_cache(maxsize=16384)
def expected_slots(day, hour, radius, cadence):
    hours = {(hour + offset) % 24 for offset in range(-radius, radius + 1)}
    cursor = utc(datetime.combine(day, time.min, ZONE))
    end = utc(datetime.combine(day + timedelta(days=1), time.min, ZONE))
    count = 0
    while cursor < end:
        count += cursor.astimezone(ZONE).hour in hours
        cursor += timedelta(seconds=cadence)
    return count


def quantile(values, p):
    """Linear interpolation at (n - 1) * p, matching the documented method."""
    position = (len(values) - 1) * p
    left = int(position)
    right = min(left + 1, len(values) - 1)
    return values[left] + (values[right] - values[left]) * (position - left)


def percentile(values, value):
    """Midrank percentile: ties receive half their mass, including repeated zeros."""
    return 100 * (bisect_left(values, value) + bisect_right(values, value)) / (2 * len(values))


class BaselineIndex:
    def __init__(self, records, policy=None):
        self.policy = dict(DEFAULT_POLICY, **(policy or {}))
        self.by_facility = defaultdict(list)
        self.by_hour = defaultdict(list)
        self.models = {}
        slots = {}
        for row in records:
            validate_record(row)
            if row["metric"] != METRIC:
                continue
            at = timestamp(row["observed_at"])
            # One deterministic contribution per UTC 15-minute slot, so retries
            # or a denser feed do not over-weight a day. Original rows stay intact.
            slot = (row["facility"], int(at.timestamp()) // self.policy["cadence_seconds"])
            rank = (at, timestamp(row["batch_id"]), row["wait_minutes"])
            if slot not in slots or rank > slots[slot][0]:
                slots[slot] = (rank, row)
        for (facility, _), (rank, row) in sorted(slots.items()):
            at = rank[0]
            local = at.astimezone(ZONE)
            point = (at, row["wait_minutes"], local.date(), local.hour)
            self.by_facility[facility].append(point)
            self.by_hour[facility, local.date(), local.hour].append(point)
        for points in self.by_facility.values():
            points.sort()

    def _sample(self, facility, target_day, hour, radius, same_day_type):
        policy = self.policy
        hours = {(hour + offset) % 24 for offset in range(-radius, radius + 1)}
        eligible, contributing, observed_slots, total_expected = [], [], 0, 0
        values = []
        for delta in range(policy["lookback_days"], 0, -1):
            day = target_day - timedelta(days=delta)
            if same_day_type and (day.weekday() >= 5) != (target_day.weekday() >= 5):
                continue
            eligible.append(day)
            # Count actual UTC slots through local midnight-to-midnight: DST's
            # missing/repeated hour affects the denominator, never guessed as 24h.
            expected = expected_slots(day, hour, radius, policy["cadence_seconds"])
            points = [p for h in hours for p in self.by_hour.get((facility, day, h), [])]
            observed_slots += len(points)
            total_expected += expected
            # A thin fragment cannot make a day count as adequate support.
            if expected and len(points) / expected >= policy["minimum_day_coverage"]:
                contributing.append(day)
                values.extend(p[1] for p in points)
        values.sort()
        return values, {"days": len(contributing), "eligible_days": len(eligible),
                        "samples": len(values), "observed_slots": observed_slots,
                        "expected_slots": total_expected,
                        "coverage": observed_slots / total_expected if total_expected else 0}

    def baseline(self, facility, target_day, hour):
        cache_key = facility, target_day, hour
        if cache_key in self.models:
            return self.models[cache_key]
        policy = self.policy
        groups = [("weekday_weekend", policy["hour_radius"], True),
                  ("wider_hours", policy["fallback_hour_radius"], True),
                  ("all_days", policy["fallback_hour_radius"], False)]
        for name, radius, same_type in groups:
            values, support = self._sample(facility, target_day, hour, radius, same_type)
            sufficient = (support["days"] >= policy["minimum_days"] and
                          support["samples"] >= policy["minimum_samples"] and
                          support["coverage"] >= policy["minimum_coverage"])
            if sufficient:
                break
        model = {"state": "supported" if sufficient else "insufficient_history",
                 "group": name, "hour_radius": radius, "support": support,
                 "reference_start": str(target_day - timedelta(days=policy["lookback_days"])),
                 "reference_end_exclusive": str(target_day),
                 "median": quantile(values, 0.5) if sufficient else None,
                 "low": quantile(values, policy["band_low"]) if sufficient else None,
                 "high": quantile(values, policy["band_high"]) if sufficient else None,
                 "distribution": [[value, count] for value, count in sorted(Counter(values).items())] if sufficient else []}
        self.models[cache_key] = model
        return model

    def compare(self, facility, observed_at, value):
        local = timestamp(observed_at).astimezone(ZONE)
        model = self.baseline(facility, local.date(), local.hour)
        if model["state"] != "supported":
            return {"model": model, "delta": None, "percentile": None, "unusual": "insufficient_history"}
        distribution = model["distribution"]
        count = sum(n for _, n in distribution)
        rank = 100 * sum(n * (1 if v < value else 0.5 if v == value else 0) for v, n in distribution) / count
        delta = value - model["median"]
        unusual = "above_usual" if rank >= self.policy["unusual_high"] and delta >= self.policy["meaningful_minutes"] else (
            "below_usual" if rank <= self.policy["unusual_low"] and delta <= -self.policy["meaningful_minutes"] else "no_large_departure")
        return {"model": model, "delta": delta, "percentile": rank, "unusual": unusual}

    def trend(self, facility, observed_at, value):
        at = timestamp(observed_at)
        policy = self.policy
        low = at - timedelta(minutes=policy["trend_minutes"] + policy["trend_tolerance_minutes"])
        high = at - timedelta(minutes=policy["trend_minutes"] - policy["trend_tolerance_minutes"])
        series = self.by_facility[facility]
        points = series[bisect_left(series, (low,)):bisect_left(series, (min(high, at) + timedelta(microseconds=1),))]
        if len(points) < policy["trend_minimum_samples"] or any((b[0] - a[0]).total_seconds() > policy["gap_seconds"] for a, b in zip(points, points[1:])):
            return {"state": "insufficient_recent_history", "delta": None, "samples": len(points)}
        change = value - median(p[1] for p in points)
        direction = "rising" if change >= policy["meaningful_minutes"] else "falling" if change <= -policy["meaningful_minutes"] else "little_change"
        return {"state": direction, "delta": change, "samples": len(points)}
