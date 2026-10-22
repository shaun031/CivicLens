"""Descriptive service indicators, not causal or protected-characteristic inference."""

import statistics
from collections import Counter, defaultdict

from app.analytics.geographic import cell_key

LIMITATIONS = [
    "Unadjusted: no population, road-length or asset-inventory denominators available",
    (
        "Reporting access and severity/department mix may differ; "
        "recorded incidents are not all defects"
    ),
    "A service-review flag is not evidence of discrimination, negligence or contractor fault",
    (
        "Creation-date cohort and current canonical membership; no "
        "officer penalties or priority changes"
    ),
]


def compare_areas(rows, intelligence, grid, minimum=10, ratio=2.0, rate_gap=0.2):
    grouped = defaultdict(list)
    for row in rows:
        grouped[cell_key(row, grid)].append(row)
    verified = {
        r["incident_id"]: r
        for r in intelligence["repairs"]
        if r["state"] == "VERIFIED_RESOLVED" and r["verified_at"]
    }
    confirmed = {
        r["new_incident_id"]
        for r in intelligence["recurrences"]
        if r["state"] == "CONFIRMED_RECURRENCE" and r["valid"]
    }
    potential = {
        r["new_incident_id"]
        for r in intelligence["recurrences"]
        if r["state"] == "POTENTIAL_RECURRENCE" and r["valid"]
    }

    def metrics(group):
        active = [r for r in group if r["status"] == "OPEN"]
        sla = [r for r in active if r["sla"]["RESOLUTION"] != "UNAVAILABLE"]
        responses = [r["workStartHours"] for r in group if r["workStartHours"] is not None]
        ages = [r["ageDays"] for r in active]
        resolved = sum(
            r["status"] == "RESOLVED"
            and r["incident_id"] in verified
            and r["resolved_at"] == verified[r["incident_id"]]["verified_at"]
            for r in group
        )
        return {
            "incidentCount": len(group),
            "activeIncidents": len(active),
            "activeBacklogRate": len(active) / len(group) if group else None,
            "medianWorkStartHours": statistics.median(responses) if responses else None,
            "responseObservations": len(responses),
            "missingWorkStart": len(group) - len(responses),
            "overdueIncidents": sum(r["overdue"] for r in sla),
            "slaObservations": len(sla),
            "overdueRate": sum(r["overdue"] for r in sla) / len(sla) if sla else None,
            "missingSla": len(active) - len(sla),
            "medianUnresolvedDays": statistics.median(ages) if ages else None,
            "verifiedResolutions": resolved,
            "verifiedResolutionRate": resolved / len(group) if group else None,
            "confirmedRecurrenceIncidents": sum(r["incident_id"] in confirmed for r in group),
            "potentialRecurrenceIncidents": sum(r["incident_id"] in potential for r in group),
            "priorityMix": dict(Counter(r["band"] for r in group)),
            "departmentMix": dict(Counter(r["department_id"] or "UNASSIGNED" for r in group)),
        }

    baseline = metrics(rows)
    areas = []
    for (lat, lon), group in sorted(grouped.items()):
        value = metrics(group)
        # Compare against other cells, not a baseline dominated by the tested cell itself.
        other_responses = [
            r["workStartHours"]
            for key, items in grouped.items()
            if key != (lat, lon)
            for r in items
            if r["workStartHours"] is not None
        ]
        other_sla = baseline["slaObservations"] - value["slaObservations"]
        other = {
            "incidentCount": baseline["incidentCount"] - value["incidentCount"],
            "responseObservations": len(other_responses),
            "medianWorkStartHours": statistics.median(other_responses) if other_responses else None,
            "slaObservations": other_sla,
            "overdueRate": (baseline["overdueIncidents"] - value["overdueIncidents"]) / other_sla
            if other_sla
            else None,
        }
        response_usable = (
            value["responseObservations"] >= minimum and other["responseObservations"] >= minimum
        )
        sla_usable = value["slaObservations"] >= minimum and other["slaObservations"] >= minimum
        flags = []
        if (
            response_usable
            and other["medianWorkStartHours"] > 0
            and value["medianWorkStartHours"] >= ratio * other["medianWorkStartHours"]
        ):
            flags.append("Recorded median work-start time exceeds comparison ratio")
        if sla_usable and value["overdueRate"] - other["overdueRate"] >= rate_gap:
            flags.append("Active known-SLA overdue fraction exceeds comparison difference")
        sufficient = value["incidentCount"] >= minimum and (response_usable or sla_usable)
        areas.append(
            {
                "areaId": f"grid:{grid}:{lat}:{lon}",
                "cell": f"{lat}:{lon}",
                "south": max(-90, lat * grid),
                "west": max(-180, lon * grid),
                "north": min(90, (lat + 1) * grid),
                "east": min(180, (lon + 1) * grid),
                **value,
                "status": "POTENTIAL_SERVICE_DISPARITY"
                if flags
                else "NO_FLAG"
                if sufficient
                else "INSUFFICIENT_DATA",
                "dataSufficient": sufficient,
                "flags": flags,
                "comparisonObservations": other["incidentCount"],
                "responseComparisonUsable": response_usable,
                "slaComparisonUsable": sla_usable,
            }
        )
    return {
        "areas": areas,
        "baseline": baseline,
        "minimumSampleSize": minimum,
        "thresholds": {"responseRatio": ratio, "overdueRateDifference": rate_gap},
        "grouping": f"Non-overlapping {grid}-degree grid cells",
        "normalization": "UNADJUSTED",
        "definitions": {
            "cohort": "Canonical incidents created within reporting window, current state",
            "response": (
                "Recorded WORK_START minus current SLA-cycle opening, hours; missing excluded"
            ),
            "overdueRate": "Overdue active incidents / active incidents with known resolution SLA",
            "backlogRate": (
                "Current OPEN canonical incidents / all canonical incidents in creation cohort"
            ),
            "verifiedResolutionRate": (
                "Current verified-resolved incidents / all canonical incidents in creation cohort"
            ),
            "recurrences": (
                "Distinct new canonical incidents with valid confirmed "
                "links, not proposed pair count"
            ),
            "baseline": (
                "All selected incidents; review comparisons use OTHER cells "
                "with sufficient observations"
            ),
        },
        "limitations": LIMITATIONS,
    }
