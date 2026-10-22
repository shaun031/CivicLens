import hashlib
import json


def contains(area, latitude, longitude):
    """Inclusive non-wrapping WGS84 rectangles; coordinate accuracy is not verified."""
    return area["south"] <= latitude <= area["north"] and area["west"] <= longitude <= area["east"]


def covered(areas, latitude, longitude):
    return not areas or any(contains(area, latitude, longitude) for area in areas)


def route(category, latitude, longitude, departments, rules):
    version = hashlib.sha256(
        json.dumps([departments, rules], sort_keys=True, allow_nan=False).encode()
    ).hexdigest()[:16]
    active = {d["id"]: d for d in departments if d["active"]}
    matching = [r for r in rules if r["active"] and r["category"] == category]
    candidates = []
    for rule in matching:
        department = active.get(rule["departmentId"])
        if department and covered(department["areas"], latitude, longitude):
            candidates.append((rule["precedence"], department["id"]))
    candidates.sort()
    best = sorted({d for p, d in candidates if p == candidates[0][0]}) if candidates else []
    if len(best) == 1 and category != "OTHER":
        department = active[best[0]]
        mode = "RECTANGLE_COVERAGE" if department["areas"] else "CATEGORY_DEMONSTRATION"
        return {
            "departmentId": best[0],
            "review": False,
            "mode": mode,
            "ruleVersion": version,
            "explanation": [
                f"Category {category}; lowest configured precedence wins.",
                f"Coverage mode: {mode}; coordinate accuracy is unverified.",
            ],
        }
    fallback = next(
        (
            d
            for d in active.values()
            if d["code"] == "GENERAL_REVIEW" and covered(d["areas"], latitude, longitude)
        ),
        None,
    )
    return {
        "departmentId": fallback["id"] if fallback else None,
        "review": True,
        "mode": "REVIEW",
        "ruleVersion": version,
        "explanation": [
            "Ambiguous, unclassified, inactive or uncovered responsibility; "
            "administrator review required. No out-of-jurisdiction assignment."
        ],
    }
