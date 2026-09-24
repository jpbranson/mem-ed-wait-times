"""Offline M3 associations among published readings; never patient movement."""

import random
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from itertools import combinations
from math import asin, atanh, cos, erfc, radians, sin, sqrt
from statistics import mean, median

from edwait.analysis import BaselineIndex, ZONE
from edwait.data import timestamp
from edwait.forecast import grid

BIN = 3600
POLICY = {
    "version": "m3-relationships-v1",
    "snapshot_sha256": "efda699fb411e72c49374024e847834bfd225f580789d6140034e235234588ed",
    "discovery": ["2026-08-12T00:00:00Z", "2026-09-02T00:00:00Z"],
    "confirmation": ["2026-09-02T00:00:00Z", "2026-09-16T00:00:00Z"],
    "reserved_unread": ["2026-09-16T00:00:00Z", "2026-09-23T00:00:00Z"],
    "bin_seconds": BIN, "minimum_slots_per_bin": 2, "neighbor_km": 50, "far_km": 150,
    "lags_hours": [1, 2, 3], "minimum_bins": 168, "minimum_days": 7, "minimum_day_bins": 12,
    "minimum_others": 5, "fdr_q": 0.10, "robust_p": 0.05, "discovery_effect": 0.20,
    "confirmation_effect": 0.10, "zero_heavy_share": 0.10, "episode_minutes": 10,
    "bootstrap_resamples": 1000, "bootstrap_seed": 20260924,
}
FAMILIES = ("co_deviation", "same_time_change", "lagged_change")


def distance_km(a, b):
    """Great-circle distance between campus points, not road travel time."""
    lat1, lat2 = radians(a["latitude"]), radians(b["latitude"])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(radians(b["longitude"] - a["longitude"]) / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def neighbors(facilities, km):
    """Pair distances and connected components of pairs within `km`."""
    points = [f for f in facilities if f.get("campus_point")]
    distances = {(a["slug"], b["slug"]): distance_km(a["campus_point"], b["campus_point"])
                 for a, b in combinations(points, 2)}
    parent = {f["slug"]: f["slug"] for f in points}
    def root(slug):
        while parent[slug] != slug:
            slug = parent[slug]
        return slug
    for (a, b), d in distances.items():
        if d <= km:
            parent[root(b)] = root(a)
    groups = defaultdict(list)
    for f in points:
        groups[root(f["slug"])].append(f["slug"])
    return distances, [g for g in groups.values() if len(g) > 1]


def deviations(payload, start, end, minimum_slots=2):
    """Hourly median difference from M1's past-only usual median, per facility.

    Each Chicago day's reference uses only slots before that day's local
    midnight, exactly as M1 compares a live reading. Unsupported slots and bins
    with fewer than `minimum_slots` supported slots stay missing.
    """
    start, end = timestamp(start), timestamp(end)
    slots, _ = grid(payload["records"], payload["start"], payload["end"])
    rows = sorted((timestamp(r["observed_at"]), r) for values in slots.values() for r in values.values())
    times = [at for at, _ in rows]
    bins, readings = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    day = start.astimezone(ZONE).date()
    while (midnight := datetime.combine(day, time.min, ZONE).astimezone(timezone.utc)) < end:
        following = datetime.combine(day + timedelta(days=1), time.min, ZONE).astimezone(timezone.utc)
        index = BaselineIndex(r for _, r in rows[bisect_left(times, midnight - timedelta(days=30)):bisect_left(times, midnight)])
        for at, row in rows[bisect_left(times, max(start, midnight)):bisect_left(times, min(end, following))]:
            readings[row["facility"]].append(row["wait_minutes"])
            usual = index.baseline(row["facility"], day, at.astimezone(ZONE).hour)["median"]
            if usual is not None:
                bins[row["facility"]][int(at.timestamp()) // BIN * BIN].append(row["wait_minutes"] - usual)
        day += timedelta(days=1)
    series = {f: {t: median(v) for t, v in values.items() if len(v) >= minimum_slots} for f, values in bins.items()}
    zero_share = {f: sum(v == 0 for v in values) / len(values) for f, values in readings.items()}
    return series, zero_share


def changes(series):
    return {f: {t: v - values[t - BIN] for t, v in values.items() if t - BIN in values} for f, values in series.items()}


def demeaned(series):
    """Remove each facility's within-period mean by Chicago hour of day."""
    hour = lambda t: datetime.fromtimestamp(t, timezone.utc).astimezone(ZONE).hour
    result = {}
    for facility, values in series.items():
        groups = defaultdict(list)
        for t, v in values.items():
            groups[hour(t)].append(v)
        means = {h: mean(v) for h, v in groups.items()}
        result[facility] = {t: v - means[hour(t)] for t, v in values.items()}
    return result


def ranks(values):
    """Average ranks, so tied readings (including repeated zeros) share rank mass."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2
        i = j + 1
    return result


def pearson(x, y):
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return sxy / sqrt(sxx * syy) if sxx and syy else None


def lag1(times, values):
    """Lag-one autocorrelation over consecutive hourly bins present in `times`."""
    index = dict(zip(times, values))
    pairs = [(v, index[t + BIN]) for t, v in index.items() if t + BIN in index]
    return (pearson(*zip(*pairs)) or 0.0) if len(pairs) > 2 else 0.0


def p_value(r, n_eff, controls=0):
    dof = n_eff - 3 - controls
    if r is None or dof <= 0:
        return None
    return erfc(abs(atanh(max(-0.999999, min(0.999999, r)))) * sqrt(dof) / sqrt(2))


def correlate(triples, controls=None):
    """Spearman correlation with an autocorrelation-adjusted p-value.

    `triples` are (leader time, leader value, follower value). The effective
    sample size n(1 - ra*rb)/(1 + ra*rb) follows Bretherton et al. (1999),
    capped at n. With `controls`, returns the partial correlation given them.
    """
    if controls is not None:
        keep = [i for i, c in enumerate(controls) if c is not None]
        triples, controls = [triples[i] for i in keep], [controls[i] for i in keep]
    n = len(triples)
    if n < 4:
        return {"r": None, "n": n, "n_eff": None, "p": None}
    times = [t for t, _, _ in triples]
    ra, rb = ranks([a for _, a, _ in triples]), ranks([b for _, _, b in triples])
    r = pearson(ra, rb)
    product = lag1(times, ra) * lag1(times, rb)
    n_eff = min(n, n * (1 - product) / (1 + product)) if product > -1 else n
    if controls is not None and r is not None:
        rc = ranks(controls)
        rac, rbc = pearson(ra, rc), pearson(rb, rc)
        if rac is None or rbc is None or abs(rac) >= 1 or abs(rbc) >= 1:
            r = None
        else:
            r = (r - rac * rbc) / sqrt((1 - rac ** 2) * (1 - rbc ** 2))
    return {"r": r, "n": n, "n_eff": n_eff, "p": p_value(r, n_eff, 1 if controls is not None else 0)}


def aligned(leader, follower, lag):
    step = lag * BIN
    return [(t, v, follower[t + step]) for t, v in sorted(leader.items()) if t + step in follower]


def others_median(series, pair, minimum):
    """Median of every other facility per bin: the system-wide swing for a pair."""
    by_time = defaultdict(list)
    for facility, values in series.items():
        if facility not in pair:
            for t, v in values.items():
                by_time[t].append(v)
    return {t: median(v) for t, v in by_time.items() if len(v) >= minimum}


def benjamini_hochberg(pvalues):
    """Adjusted q-values; None entries stay None and do not count as tests."""
    indexed = sorted((p, i) for i, p in enumerate(pvalues) if p is not None)
    q, running = [None] * len(pvalues), 1.0
    for rank in range(len(indexed), 0, -1):
        p, i = indexed[rank - 1]
        running = min(running, p * len(indexed) / rank)
        q[i] = running
    return q


def pair_test(kinds, leader, follower, lag, policy):
    """One test with its support, system-wide-swing and residual-hour checks."""
    series, adjusted = kinds
    triples = aligned(series[leader], series[follower], lag)
    days = defaultdict(int)
    for t, _, _ in triples:
        days[t // 86400] += 1
    support = {"n": len(triples), "days": sum(n >= policy["minimum_day_bins"] for n in days.values())}
    if support["n"] < policy["minimum_bins"] or support["days"] < policy["minimum_days"]:
        return {**support, "state": "insufficient_support", "r": None, "p": None}
    main = correlate(triples)
    swing = others_median(series, (leader, follower), policy["minimum_others"])
    partial = correlate(triples, [swing.get(t + lag * BIN) for t, _, _ in triples])
    residual = correlate(aligned(adjusted[leader], adjusted[follower], lag))
    return {**support, "state": "tested", "r": main["r"], "n_eff": main["n_eff"], "p": main["p"],
            "system_wide": {"r": partial["r"], "p": partial["p"], "n": partial["n"]},
            "residual_hour": {"r": residual["r"], "p": residual["p"]}}


def period_tests(series, facilities, policy):
    """Every pair's co-deviation, same-time change and lagged-change tests."""
    level = (series, demeaned(series))
    delta = changes(series)
    delta = (delta, demeaned(delta))
    slugs = [f for f in facilities if f in series]
    tests = []
    for a, b in combinations(slugs, 2):
        tests.append({"family": "co_deviation", "leader": a, "follower": b, "lag_hours": 0, **pair_test(level, a, b, 0, policy)})
        tests.append({"family": "same_time_change", "leader": a, "follower": b, "lag_hours": 0, **pair_test(delta, a, b, 0, policy)})
        for lag in policy["lags_hours"]:
            for x, y in ((a, b), (b, a)):
                tests.append({"family": "lagged_change", "leader": x, "follower": y, "lag_hours": lag, **pair_test(delta, x, y, lag, policy)})
    for family in FAMILIES:
        members = [t for t in tests if t["family"] == family]
        for test, q in zip(members, benjamini_hochberg([t["p"] for t in members])):
            test["q"] = q
    reverse = {(t["leader"], t["follower"], t["lag_hours"]): t for t in tests if t["family"] == "lagged_change"}
    for test in tests:
        if test["family"] == "lagged_change":
            other = reverse[test["follower"], test["leader"], test["lag_hours"]]
            test["reverse_r"] = other["r"]
    return tests


def robust(test, sign, policy):
    checks = (test.get("system_wide") or {}, test.get("residual_hour") or {})
    return all(c.get("r") is not None and c["p"] is not None and c["r"] * sign > 0 and c["p"] < policy["robust_p"] for c in checks)


def dominant(test):
    return test["family"] != "lagged_change" or (test["reverse_r"] is not None and abs(test["r"]) > abs(test["reverse_r"]))


def candidate(test, policy):
    if test["r"] is None or test["q"] is None:
        return False
    sign = 1 if test["r"] > 0 else -1
    return (test["q"] <= policy["fdr_q"] and abs(test["r"]) >= policy["discovery_effect"]
            and robust(test, sign, policy) and dominant(test))


def key(test):
    return test["family"], test["leader"], test["follower"], test["lag_hours"]


def confirm(candidates, later, policy):
    """Re-test only discovery candidates in the later period, with BH across them."""
    later = {key(t): t for t in later}
    retests = [later[key(t)] for t in candidates]
    qvalues = benjamini_hochberg([t["p"] for t in retests])
    results = []
    for first, second, q in zip(candidates, retests, qvalues):
        sign = 1 if first["r"] > 0 else -1
        confirmed = (q is not None and q <= policy["fdr_q"] and second["r"] is not None
                     and second["r"] * sign >= policy["confirmation_effect"]
                     and robust(second, sign, policy) and dominant(second))
        results.append({"key": key(first), "confirmation_q": q, "confirmed": confirmed})
    return results


def bootstrap(triples, resamples, rng):
    """Percentile 95% interval from paired UTC-day block resampling."""
    days = defaultdict(list)
    for triple in triples:
        days[triple[0] // 86400].append(triple)
    blocks = list(days.values())
    values = []
    for _ in range(resamples):
        sample = [t for _ in blocks for t in rng.choice(blocks)]
        r = pearson(ranks([a for _, a, _ in sample]), ranks([b for _, _, b in sample]))
        if r is not None:
            values.append(r)
    values.sort()
    if len(values) < 20:
        return None
    return [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]


def episodes(a, b, threshold, limit=5):
    """Longest runs of consecutive bins with both facilities above usual."""
    hits = sorted(t for t, v in a.items() if v >= threshold and b.get(t, float("-inf")) >= threshold)
    runs, current = [], []
    for t in hits:
        if current and t != current[-1] + BIN:
            runs.append(current)
            current = []
        current.append(t)
    if current:
        runs.append(current)
    runs.sort(key=lambda run: (-len(run), run[0]))
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")
    return [{"start": iso(run[0]), "end": iso(run[-1] + BIN), "hours": len(run),
             "median_above_usual": [median(a[t] for t in run), median(b[t] for t in run)]}
            for run in runs[:limit]]


def band(distance, policy):
    if distance <= policy["neighbor_km"]:
        return "neighbor"
    return "regional" if distance <= policy["far_km"] else "distant"


def analyze(payload, facilities, policy=POLICY):
    """Run discovery on all pairs, then confirmation on candidates only."""
    order = [f["slug"] for f in facilities]
    distances, groups = neighbors(facilities, policy["neighbor_km"])
    def distance(a, b):
        return distances.get((a, b), distances.get((b, a)))
    periods, tests = {}, {}
    for name in ("discovery", "confirmation"):
        series, zero_share = deviations(payload, *policy[name], policy["minimum_slots_per_bin"])
        tests[name] = period_tests(series, order, policy)
        periods[name] = {"series": series, "zero_share": zero_share}
    candidates = [t for t in tests["discovery"] if candidate(t, policy)]
    outcomes = {r["key"]: r for r in confirm(candidates, tests["confirmation"], policy)}
    zero_heavy = {f for p in periods.values() for f, share in p["zero_share"].items() if share > policy["zero_heavy_share"]}
    rng = random.Random(policy["bootstrap_seed"])
    later = {key(t): t for t in tests["confirmation"]}
    results = []
    for test in candidates:
        pair = (test["leader"], test["follower"])
        outcome = outcomes[key(test)]
        label = "exploratory" if zero_heavy & set(pair) else ("confirmed" if outcome["confirmed"] else "not_supported")
        intervals = {}
        for name in ("discovery", "confirmation"):
            source = periods[name]["series"] if test["family"] == "co_deviation" else changes(periods[name]["series"])
            triples = aligned(source[pair[0]], source[pair[1]], test["lag_hours"])
            intervals[name] = bootstrap(triples, policy["bootstrap_resamples"], rng) if triples else None
        both = {**periods["discovery"]["series"][pair[0]], **periods["confirmation"]["series"][pair[0]]}, \
               {**periods["discovery"]["series"][pair[1]], **periods["confirmation"]["series"][pair[1]]}
        results.append({"family": test["family"], "leader": pair[0], "follower": pair[1], "lag_hours": test["lag_hours"],
                        "distance_km": distance(*pair), "band": band(distance(*pair), policy), "label": label,
                        "discovery": test, "confirmation": later[key(test)], "confirmation_q": outcome["confirmation_q"],
                        "bootstrap_95": intervals,
                        "episodes": episodes(*both, policy["episode_minutes"]) if label == "confirmed" else []})
    summary = {}
    for name, period in tests.items():
        summary[name] = {}
        for family in ("co_deviation", "same_time_change"):
            for group in ("neighbor", "regional", "distant"):
                values = [t["r"] for t in period if t["family"] == family and t["r"] is not None
                          and band(distance(t["leader"], t["follower"]), policy) == group]
                summary[name][f"{family}:{group}"] = {
                    "pairs": len(values), "median_r": median(values) if values else None,
                    "positive_share": sum(v > 0 for v in values) / len(values) if values else None,
                    "significant": sum(1 for t in period if t["family"] == family and t["q"] is not None and t["q"] <= policy["fdr_q"]
                                       and band(distance(t["leader"], t["follower"]), policy) == group)}
    support = {name: {f: {"bins": len(p["series"].get(f, {})), "zero_share": p["zero_share"].get(f),
                          "lag1_deviation": lag1(sorted(p["series"].get(f, {})), [v for _, v in sorted(p["series"].get(f, {}).items())])}
                      for f in order} for name, p in periods.items()}
    pairs = [{"a": a, "b": b, "distance_km": distance(a, b), "band": band(distance(a, b), policy),
              **{f"{name}_{family}": next(({"r": t["r"], "q": t["q"], "n": t["n"]} for t in tests[name]
                                          if t["family"] == family and t["leader"] == a and t["follower"] == b), None)
                 for name in tests for family in ("co_deviation", "same_time_change")}}
             for a, b in combinations(order, 2)]
    tested = {name: {family: sum(t["family"] == family and t["p"] is not None for t in period) for family in FAMILIES}
              for name, period in tests.items()}
    return {"policy": policy, "neighbor_groups": groups, "support": support, "tests": tested,
            "band_summary": summary, "candidates": results, "pairs": pairs}, tests
