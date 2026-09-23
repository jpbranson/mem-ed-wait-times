"""M2 destination gates and descriptive movement in published waits, not forecasts."""

from collections import Counter
from datetime import date, datetime, time, timedelta
import math

from edwait.analysis import BaselineIndex, ZONE, expected_slots, quantile
from edwait.data import METRIC, registry, utc

POLICY = {"lookback_days": 28, "horizons_minutes": [15, 30, 60, 120],
          "minimum_days": 8, "minimum_pairs": 64, "minimum_day_coverage": .75,
          "gap_seconds": 1200, "horizon_tolerance_seconds": 450,
          "quantile": .9, "meaningful_minutes": 10, "route_ttl_seconds": 300,
          "context_ttl_seconds": 7200, "verification_days": 90}


def coordinate(value, limit):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= limit


def eligibility(facility, age_group, now):
    """Only trusted registry metadata can enable a destination; campus points cannot."""
    if age_group not in ("adult", "child"):
        return "Choose an age group"
    if facility.get("active_status") != "active":
        return "Active emergency service unverified"
    if not isinstance(facility.get("service_applicability"), list) or "general_emergency" not in facility["service_applicability"]:
        return "Emergency service applicability unverified"
    if not isinstance(facility.get("age_applicability"), list) or age_group not in facility["age_applicability"]:
        return "Age applicability unverified or unsuitable"
    try:
        verified = date.fromisoformat(facility["travel_verified_on"])
        age = (utc(now).astimezone(ZONE).date() - verified).days
        if not 0 <= age <= POLICY["verification_days"]:
            return "Destination verification expired"
    except (ValueError, TypeError, KeyError):
        return "Destination verification missing"
    entrance = facility.get("emergency_entrance")
    if not isinstance(entrance, dict) or not coordinate(entrance.get("latitude"), 90) or not coordinate(entrance.get("longitude"), 180):
        return "Emergency entrance coordinates unverified"
    if not entrance.get("label") or not str(entrance.get("source_url", "")).startswith("https://"):
        return "Emergency entrance evidence missing"
    return None


def build_travel(history, now, facilities=None):
    now = utc(now)
    facilities = registry() if facilities is None else facilities
    day = now.astimezone(ZONE).date()
    end = utc(datetime.combine(day, time.min, ZONE))
    start = utc(datetime.combine(day - timedelta(days=POLICY["lookback_days"]), time.min, ZONE))
    # Reuse M1's validated, latest-per-UTC-slot representation.
    index = BaselineIndex(history.records)
    entries = []
    for facility in facilities:
        points = [p for p in index.by_facility[facility["slug"]] if start <= p[0] < end and p[1] >= 0]
        counts = Counter(p[2] for p in points)
        covered = {d for d, count in counts.items() if count >= POLICY["minimum_day_coverage"] * expected_slots(d, 12, 12, 900)}
        movement = []
        for horizon in POLICY["horizons_minutes"]:
            steps = horizon // 15
            changes, days = [], set()
            for i in range(len(points) - steps):
                a, b = points[i], points[i + steps]
                if a[2] not in covered or b[2] not in covered:
                    continue
                if abs((b[0] - a[0]).total_seconds() - horizon * 60) > POLICY["horizon_tolerance_seconds"]:
                    continue
                if any((points[j + 1][0] - points[j][0]).total_seconds() > POLICY["gap_seconds"] for j in range(i, i + steps)):
                    continue
                changes.append(abs(b[1] - a[1]))
                days.add(a[2])
            supported = len(changes) >= POLICY["minimum_pairs"] and len(days) >= POLICY["minimum_days"]
            movement.append({"horizon_minutes": horizon, "pairs": len(changes), "days": len(days),
                             "absolute_change_p90": quantile(changes, .9) if supported else None})
        reasons = {group: eligibility(facility, group, now) for group in ("adult", "child")}
        entries.append({"slug": facility["slug"], "display_name": facility["display_name"],
                        "eligibility": reasons, "movement": movement})
    return {"schema_version": 1, "method_version": "travel-wait-v1", "metric": METRIC,
            "generated_at": now.isoformat(), "source_start": start.isoformat(), "source_end": end.isoformat(),
            "policy": POLICY.copy(), "recommendations_enabled": False,
            "recommendation_blockers": ["Current wait metric interpretation is unverified", "Traffic uncertainty is not calibrated"],
            "facilities": entries}
