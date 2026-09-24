"""M4 area choices: all hospitals, M3's campus-center neighbor groups, and registry
states. Areas count facilities; they say nothing about occupancy or patient load."""

from edwait.data import short_name
from edwait.relationships import neighbors

# The same straight-line grouping M3 fixed before scoring; not travel time.
NEIGHBOR_KM = 50
MINIMUM_GROUP = 3


def areas(facilities):
    ordered = lambda members: [f["slug"] for f in facilities if f["slug"] in members]
    result = [{"key": "all", "label": "All hospitals", "basis": "All configured facilities",
               "slugs": ordered({f["slug"] for f in facilities})}]
    _, groups = neighbors(facilities, NEIGHBOR_KM)
    # Pairs are too small to summarize as an area; larger groups keep registry order.
    for group in sorted((g for g in groups if len(g) >= MINIMUM_GROUP), key=len, reverse=True):
        slugs = ordered(set(group))
        label = "Memphis area" if "memphis" in slugs else " / ".join(short_name(f) for f in facilities if f["slug"] in slugs)
        result.append({"key": "near-" + slugs[0], "label": label, "slugs": slugs,
                       "basis": f"Campus centers linked within {NEIGHBOR_KM} km (straight line)"})
    for region in dict.fromkeys(f["region"] for f in facilities if f.get("region")):
        result.append({"key": "region-" + region.lower().replace(" ", "-"), "label": region,
                       "basis": "Registry state", "slugs": ordered({f["slug"] for f in facilities if f.get("region") == region})})
    return result
