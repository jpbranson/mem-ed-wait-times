"""M2 destination gates and descriptive movement in published waits, not forecasts."""

from datetime import date
import math

from edwait.analysis import BaselineIndex, ZONE, quantile
from edwait.data import METRIC, registry, utc
from edwait.stability import horizon_changes, reference_window, window_points

POLICY = {"lookback_days": 28, "horizons_minutes": [15, 30, 60, 120],
          "minimum_days": 8, "minimum_pairs": 64, "minimum_day_coverage": .75,
          "gap_seconds": 1200, "horizon_tolerance_seconds": 450,
          "quantile": .9, "meaningful_minutes": 10, "route_ttl_seconds": 300,
          "context_ttl_seconds": 7200, "verification_days": 90}


# How an emergency entrance point was established; imagery review is the planned route.
ENTRANCE_METHODS = ("official_source", "imagery_review", "site_visit")
# A reviewed entrance must sit on or beside its campus; larger offsets suggest a typo.
MAX_ENTRANCE_OFFSET_METERS = 1000


def coordinate(value, limit):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= limit


def meters_between(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, h)))


def point_problem(point):
    """Shared shape check for campus and entrance points; returns a reason or None."""
    if not isinstance(point, dict) or not coordinate(point.get("latitude"), 90) or not coordinate(point.get("longitude"), 180):
        return "coordinates"
    if not point.get("label") or not str(point.get("source_url", "")).startswith("https://"):
        return "evidence"
    return None


def entrance_problem(entrance, campus, today):
    """Reason a reviewed entrance is unusable, or None. Never silently falls back to campus."""
    if point_problem(entrance) or entrance.get("method") not in ENTRANCE_METHODS:
        return "Emergency entrance evidence incomplete"
    try:
        reviewed = date.fromisoformat(entrance["reviewed_on"])
    except (ValueError, TypeError, KeyError):
        return "Emergency entrance evidence incomplete"
    if reviewed > today:
        return "Emergency entrance evidence incomplete"
    if point_problem(campus) is None and meters_between(entrance, campus) > MAX_ENTRANCE_OFFSET_METERS:
        return "Emergency entrance too far from campus"
    return None


def arrival(facility):
    """Routing target and its kind: a reviewed entrance wins; otherwise the labeled campus point."""
    if facility.get("emergency_entrance") is not None:
        return facility["emergency_entrance"], "entrance"
    campus = facility.get("campus_point")
    return (campus, "campus") if point_problem(campus) is None else (None, None)


def eligibility(facility, age_group, now):
    """Only trusted registry metadata can enable a destination. Campus points are an
    explicitly labeled fallback (user decision 2026-09-23) until an entrance is reviewed."""
    if age_group not in ("adult", "child"):
        return "Choose an age group"
    if facility.get("active_status") != "active":
        return "Active emergency service unverified"
    if not isinstance(facility.get("service_applicability"), list) or "general_emergency" not in facility["service_applicability"]:
        return "Emergency service applicability unverified"
    if not isinstance(facility.get("age_applicability"), list) or age_group not in facility["age_applicability"]:
        return "Age applicability unverified or unsuitable"
    today = utc(now).astimezone(ZONE).date()
    try:
        verified = date.fromisoformat(facility["travel_verified_on"])
        if not 0 <= (today - verified).days <= POLICY["verification_days"]:
            return "Destination verification expired"
    except (ValueError, TypeError, KeyError):
        return "Destination verification missing"
    if facility.get("emergency_entrance") is not None:
        return entrance_problem(facility["emergency_entrance"], facility.get("campus_point"), today)
    if point_problem(facility.get("campus_point")):
        return "Arrival location unavailable"
    return None


def build_travel(history, now, facilities=None):
    now = utc(now)
    facilities = registry() if facilities is None else facilities
    start, end = reference_window(now, POLICY["lookback_days"])
    # Reuse M1's validated, latest-per-UTC-slot representation.
    index = BaselineIndex(history.records)
    entries = []
    for facility in facilities:
        points = window_points(index, facility["slug"], start, end)
        movement = []
        for horizon in POLICY["horizons_minutes"]:
            changes, days = horizon_changes(points, horizon, POLICY)
            supported = len(changes) >= POLICY["minimum_pairs"] and len(days) >= POLICY["minimum_days"]
            movement.append({"horizon_minutes": horizon, "pairs": len(changes), "days": len(days),
                             "absolute_change_p90": quantile(sorted(abs(c) for c in changes), POLICY["quantile"]) if supported else None})
        reasons = {group: eligibility(facility, group, now) for group in ("adult", "child")}
        point, kind = arrival(facility)
        # The routing gateway reads its targets from this artifact, so the page and the
        # gateway always compare the same destinations. Hospital points only, never origins.
        entries.append({"slug": facility["slug"], "display_name": facility["display_name"],
                        "eligibility": reasons, "arrival": kind,
                        "arrival_point": None if point is None else {"latitude": point["latitude"], "longitude": point["longitude"]},
                        "movement": movement})
    return {"schema_version": 1, "method_version": "travel-wait-v1", "metric": METRIC,
            "generated_at": now.isoformat(), "source_start": start.isoformat(), "source_end": end.isoformat(),
            "policy": POLICY.copy(), "recommendations_enabled": False,
            "recommendation_blockers": ["Current wait metric interpretation is unverified", "Traffic uncertainty is not calibrated"] +
                                       (["Some arrival points are campus locations; ER entrances unconfirmed"]
                                        if any(e["arrival"] == "campus" and None in e["eligibility"].values() for e in entries) else []),
            "facilities": entries}
