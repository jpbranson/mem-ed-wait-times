"""How far published readings historically moved over fixed horizons (M4 wait
stability, shared with M2's movement screen). Past-only and descriptive: not a
forecast, prediction interval, or individual patient's wait uncertainty."""

from collections import Counter
from datetime import datetime, time, timedelta

from edwait.analysis import ZONE, expected_slots, quantile
from edwait.data import utc

METHOD_VERSION = "wait-stability-v1"
POLICY = {"lookback_days": 28, "horizons_minutes": [15, 30, 60, 120],
          "minimum_days": 8, "minimum_pairs": 64, "minimum_day_coverage": .75,
          "gap_seconds": 1200, "horizon_tolerance_seconds": 450, "meaningful_minutes": 10}


def reference_window(now, lookback_days):
    """Complete previous local days, so today's readings never describe themselves."""
    day = utc(now).astimezone(ZONE).date()
    end = utc(datetime.combine(day, time.min, ZONE))
    return utc(datetime.combine(day - timedelta(days=lookback_days), time.min, ZONE)), end


def window_points(index, slug, start, end):
    """M1's latest-per-UTC-slot series; negative readings have no confirmed meaning."""
    return [p for p in index.by_facility[slug] if start <= p[0] < end and p[1] >= 0]


def horizon_changes(points, horizon, policy):
    """Signed changes between readings `horizon` minutes apart on adequately covered
    local days, never bridging a collection gap. Returns changes and origin days."""
    counts = Counter(p[2] for p in points)
    covered = {d for d, count in counts.items()
               if count >= policy["minimum_day_coverage"] * expected_slots(d, 12, 12, 900)}
    steps = horizon // 15
    changes, days = [], set()
    for i in range(len(points) - steps):
        a, b = points[i], points[i + steps]
        if a[2] not in covered or b[2] not in covered:
            continue
        if abs((b[0] - a[0]).total_seconds() - horizon * 60) > policy["horizon_tolerance_seconds"]:
            continue
        if any((points[j + 1][0] - points[j][0]).total_seconds() > policy["gap_seconds"] for j in range(i, i + steps)):
            continue
        changes.append(b[1] - a[1])
        days.add(a[2])
    return changes, days


def summarize(points, policy=POLICY):
    """Per horizon: overlapping pair support, median and 90th percentile absolute
    change, and the share of pairs rising or falling by the meaningful distance."""
    output = []
    for horizon in policy["horizons_minutes"]:
        changes, days = horizon_changes(points, horizon, policy)
        supported = len(changes) >= policy["minimum_pairs"] and len(days) >= policy["minimum_days"]
        sizes = sorted(abs(c) for c in changes)
        limit = policy["meaningful_minutes"]
        output.append({"horizon_minutes": horizon, "pairs": len(changes), "days": len(days),
                       "median_abs_change": quantile(sizes, .5) if supported else None,
                       "p90_abs_change": quantile(sizes, .9) if supported else None,
                       "rise_share": sum(c >= limit for c in changes) / len(changes) if supported else None,
                       "fall_share": sum(c <= -limit for c in changes) / len(changes) if supported else None})
    return output
