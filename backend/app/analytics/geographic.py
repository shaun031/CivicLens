import math
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal


def cell_key(row, grid):
    size = Decimal(str(grid))

    def axis(value, maximum):
        index = int((Decimal(str(value)) / size).to_integral_value(rounding=ROUND_FLOOR))
        return min(index, math.ceil(maximum / grid) - 1)

    return axis(row["latitude"], 90), axis(row["longitude"], 180)


def within(row, bounds):
    if bounds is None:
        return True
    s, w, n, e = bounds
    return s <= row["latitude"] <= n and w <= row["longitude"] <= e


def hotspots(incidents, reports, grid, bounds):
    cells = {}
    counts = defaultdict(int)
    for report in reports:
        if within(report, bounds):
            counts[cell_key(report, grid)] += 1
    for row in incidents:
        if not within(row, bounds):
            continue
        key = cell_key(row, grid)
        if key not in cells:
            lat, lon = key
            cells[key] = {
                "cell": f"{lat}:{lon}",
                "south": max(-90, round(lat * grid, 7)),
                "west": max(-180, round(lon * grid, 7)),
                "north": min(90, round((lat + 1) * grid, 7)),
                "east": min(180, round((lon + 1) * grid, 7)),
                "incidentCount": 0,
                "activeIncidents": 0,
                "criticalIncidents": 0,
                "overdueIncidents": 0,
                "scores": [],
                "reportCount": counts[key],
            }
        cell = cells[key]
        cell["incidentCount"] += 1
        cell["activeIncidents"] += row["status"] == "OPEN"
        cell["criticalIncidents"] += row["band"] == "CRITICAL"
        cell["overdueIncidents"] += row["overdue"]
        if row["score"] is not None:
            cell["scores"].append(row["score"])
    # Report-only cells are included: unlinked reports must not disappear from the volume layer.
    for key, count in counts.items():
        if key not in cells:
            lat, lon = key
            cells[key] = {
                "cell": f"{lat}:{lon}",
                "south": max(-90, round(lat * grid, 7)),
                "west": max(-180, round(lon * grid, 7)),
                "north": min(90, round((lat + 1) * grid, 7)),
                "east": min(180, round((lon + 1) * grid, 7)),
                "incidentCount": 0,
                "activeIncidents": 0,
                "criticalIncidents": 0,
                "overdueIncidents": 0,
                "scores": [],
                "reportCount": count,
            }
    result = []
    for cell in cells.values():
        scores = cell.pop("scores")
        result.append(
            cell
            | {
                "averageCalculatedScore": sum(scores) / len(scores) if scores else None,
                "scoreSampleSize": len(scores),
            }
        )
    return sorted(result, key=lambda c: (-c["incidentCount"], c["cell"]))
