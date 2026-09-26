"""M2 benefit-rule backtest (docs/m2-benefit-protocol.md): would an apparently lower
drive-plus-published-wait estimate still be lower with the published waits at
arrival? Offline and descriptive: published readings, not patient time, and no
recommendation is enabled by any result."""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import random

from edwait.analysis import ZONE, BaselineIndex, quantile
from edwait.data import timestamp
from edwait.stability import horizon_changes, reference_window, window_points
from edwait.travel import POLICY as TRAVEL_POLICY

POLICY = {
    "version": "m2-benefit-v1",
    "snapshot_sha256": "efda699fb411e72c49374024e847834bfd225f580789d6140034e235234588ed",
    # M5's final holdout starts here; nothing at or after it is read.
    "data_end": "2026-09-16T00:00:00Z",
    "periods": {"discovery": ["2026-08-08T00:00:00Z", "2026-09-02T00:00:00Z"],
                "confirmation": ["2026-09-02T00:00:00Z", "2026-09-16T00:00:00Z"]},
    "slot_seconds": 900, "evaluation_every_slots": 4, "max_drive_minutes": 120,
    "later_minutes": 60, "stress_ratio": 1.2,
    "rules": [["F0", "fixed", 0], ["F10", "fixed", 10], ["F20", "fixed", 20], ["F30", "fixed", 30],
              ["F45", "fixed", 45], ["F60", "fixed", 60], ["S1", "screen", 1.0], ["S0.5", "screen", 0.5]],
    "selection": {"minimum_claims": 50, "minimum_days": 5, "minimum_precision": .9, "minimum_lower_bound": .8},
    "confirmation": {"minimum_claims": 20, "minimum_days": 3, "minimum_precision": .9},
    "bootstrap": {"draws": 2000, "seed": 20260926},
}


def profile(departure):
    """Which typical-speed profile applies to a departure (local weekday peaks)."""
    local = departure.astimezone(ZONE)
    if local.weekday() < 5 and 6 <= local.hour < 10:
        return "am"
    if local.weekday() < 5 and 15 <= local.hour < 19:
        return "pm"
    return "night"


def horizon_for(drive_minutes):
    return next((h for h in TRAVEL_POLICY["horizons_minutes"] if h >= drive_minutes), None)


def slot_readings(index, slot_seconds=900):
    """Facility -> {UTC slot number: reading} from M1's latest reading per slot."""
    return {slug: {int(p[0].timestamp()) // slot_seconds: p[1] for p in points if p[1] >= 0}
            for slug, points in index.by_facility.items()}


def screens(index, slugs, days):
    """Facility -> local day -> {horizon: 90th percentile absolute change or None}, as
    travel.json would have published it that day (28 complete previous local days)."""
    output = defaultdict(dict)
    for slug in slugs:
        for day in days:
            start, end = reference_window(datetime.combine(day, time(12), ZONE), TRAVEL_POLICY["lookback_days"])
            points = window_points(index, slug, start, end)
            row = {}
            for horizon in TRAVEL_POLICY["horizons_minutes"]:
                changes, contributing = horizon_changes(points, horizon, TRAVEL_POLICY)
                supported = len(changes) >= TRAVEL_POLICY["minimum_pairs"] and len(contributing) >= TRAVEL_POLICY["minimum_days"]
                row[horizon] = quantile(sorted(abs(c) for c in changes), TRAVEL_POLICY["quantile"]) if supported else None
            output[slug][day] = row
    return output


def opportunities(readings, screen, routes, start, end, data_end, policy=POLICY):
    """One row per (origin, hourly slot, alternative) with both current readings,
    both screens supported and both arrival readings present."""
    size = policy["slot_seconds"]
    by_origin = defaultdict(list)
    for route in routes:
        by_origin[route["origin"]].append(route)
    limit = data_end.timestamp()

    def reading(slug, at):
        return readings.get(slug, {}).get(int(at.timestamp()) // size) if at.timestamp() < limit else None

    rows = []
    first, last = int(start.timestamp()) // size, int(end.timestamp()) // size
    for slot in range(first, last):
        if slot % policy["evaluation_every_slots"]:
            continue
        departure = datetime.fromtimestamp((slot + 1) * size, timezone.utc)
        kind, day = profile(departure), departure.astimezone(ZONE).date()
        for origin in sorted(by_origin):
            drives = {r["slug"]: r["seconds"][kind] / 60 for r in by_origin[origin]}
            closest = min(drives, key=lambda slug: (drives[slug], slug))
            d_c, w_c = drives[closest], readings.get(closest, {}).get(slot)
            h_c = horizon_for(d_c)
            p_c = screen.get(closest, {}).get(day, {}).get(h_c) if h_c else None
            if w_c is None or p_c is None:
                continue
            arrival_c = reading(closest, departure + timedelta(minutes=d_c))
            if arrival_c is None:
                continue
            later_c = reading(closest, departure + timedelta(minutes=d_c + policy["later_minutes"]))
            for alternative in sorted(drives):
                d_a = drives[alternative]
                if alternative == closest or d_a > policy["max_drive_minutes"]:
                    continue
                w_a, p_a = readings.get(alternative, {}).get(slot), screen.get(alternative, {}).get(day, {}).get(horizon_for(d_a))
                if w_a is None or p_a is None:
                    continue
                arrival_a = reading(alternative, departure + timedelta(minutes=d_a))
                if arrival_a is None:
                    continue
                later_a = reading(alternative, departure + timedelta(minutes=d_a + policy["later_minutes"]))
                stress_drive = d_a * policy["stress_ratio"]
                stress_a = reading(alternative, departure + timedelta(minutes=stress_drive))
                rows.append({
                    "origin": origin, "slot": slot, "day": day.isoformat(), "profile": kind,
                    "closest": closest, "alternative": alternative, "drive_c": d_c, "drive_a": d_a,
                    "p90_c": p_c, "p90_a": p_a,
                    "D": (d_c + w_c) - (d_a + w_a),
                    "A": (d_c + arrival_c) - (d_a + arrival_a),
                    "A60": (d_c + later_c) - (d_a + later_a) if later_c is not None and later_a is not None else None,
                    "A_stress": (d_c + arrival_c) - (stress_drive + stress_a) if stress_a is not None else None})
    return rows


def claims(rows, rule):
    name, kind, value = rule
    if kind == "fixed":
        return [r for r in rows if (r["D"] > 0 if value == 0 else r["D"] >= value)]
    return [r for r in rows if r["D"] > 10 + value * (r["p90_c"] + r["p90_a"])]


def interval(claimed, days, bootstrap):
    """Day-block bootstrap 95% interval for precision; resamples every period day."""
    per_day = defaultdict(lambda: [0, 0])
    for r in claimed:
        per_day[r["day"]][0] += 1
        per_day[r["day"]][1] += r["A"] > 0
    rng, estimates = random.Random(bootstrap["seed"]), []
    for _ in range(bootstrap["draws"]):
        total = held = 0
        for day in rng.choices(days, k=len(days)):
            total += per_day[day][0] if day in per_day else 0
            held += per_day[day][1] if day in per_day else 0
        if total:
            estimates.append(held / total)
    estimates.sort()
    return [quantile(estimates, .025), quantile(estimates, .975)] if estimates else None


def share(values):
    values = [v for v in values if v is not None]
    return {"n": len(values), "precision": sum(v > 0 for v in values) / len(values) if values else None}


def summary(rows, rule, days, bootstrap=None):
    claimed = claims(rows, rule)
    advantages = sorted(r["A"] for r in claimed)
    output = {"opportunities": len(rows), "claims": len(claimed), "claim_days": len({r["day"] for r in claimed}),
              "claim_rate": len(claimed) / len(rows) if rows else None,
              "precision": sum(a > 0 for a in advantages) / len(advantages) if advantages else None,
              "median_A": quantile(advantages, .5) if advantages else None,
              "p10_A": quantile(advantages, .1) if advantages else None,
              "later": share(r["A60"] for r in claimed), "stress": share(r["A_stress"] for r in claimed)}
    if bootstrap is not None:
        output["precision_interval"] = interval(claimed, days, bootstrap)
    return output


def select(results, policy=POLICY):
    """Most claims among rules meeting the discovery gates; ties prefer fixed rules,
    then the larger threshold. None when no rule qualifies."""
    gates, order = policy["selection"], {name: (kind != "fixed", -value) for name, kind, value in policy["rules"]}
    eligible = [name for name, s in results.items()
                if s["claims"] >= gates["minimum_claims"] and s["claim_days"] >= gates["minimum_days"]
                and s["precision"] >= gates["minimum_precision"] and s["precision_interval"]
                and s["precision_interval"][0] >= gates["minimum_lower_bound"]]
    return min(eligible, key=lambda name: (-results[name]["claims"], order[name])) if eligible else None


def confirmation_outcome(result, policy=POLICY):
    gates = policy["confirmation"]
    if result["claims"] < gates["minimum_claims"] or result["claim_days"] < gates["minimum_days"]:
        return "inconclusive"
    return "confirmed" if result["precision"] >= gates["minimum_precision"] else "failed"


def analyze(payload, profiles, policy=POLICY):
    end = timestamp(policy["data_end"])
    records = [r for r in payload["records"] if timestamp(r["batch_id"]) < end]
    index = BaselineIndex(records)
    readings = slot_readings(index, policy["slot_seconds"])
    routes = profiles["routes"]
    periods = {name: (timestamp(a), timestamp(b)) for name, (a, b) in policy["periods"].items()}
    first, last = min(a for a, _ in periods.values()), max(b for _, b in periods.values())
    days = sorted({(first + timedelta(hours=h)).astimezone(ZONE).date()
                   for h in range(int((last - first).total_seconds() // 3600) + 1)})
    screen = screens(index, sorted({r["slug"] for r in routes}), days)
    report = {"version": policy["version"], "records_used": len(records),
              "latest_batch_used": max(r["batch_id"] for r in records), "periods": {}}
    for name, (start, stop) in periods.items():
        rows = opportunities(readings, screen, routes, start, stop, end, policy)
        period_days = sorted({r["day"] for r in rows})
        results = {rule[0]: summary(rows, rule, period_days, policy["bootstrap"]) for rule in policy["rules"]}
        by_origin = {origin: {rule[0]: summary([r for r in rows if r["origin"] == origin], rule, period_days)
                              for rule in policy["rules"]}
                     for origin in sorted({r["origin"] for r in rows})}
        report["periods"][name] = {"opportunities": len(rows), "days": len(period_days),
                                   "closest": sorted({(r["origin"], r["closest"]) for r in rows}),
                                   "rules": results, "by_origin": by_origin}
    selected = select(report["periods"]["discovery"]["rules"], policy)
    report["selected_rule"] = selected
    report["confirmation_outcome"] = (confirmation_outcome(report["periods"]["confirmation"]["rules"][selected], policy)
                                      if selected else None)
    return report
