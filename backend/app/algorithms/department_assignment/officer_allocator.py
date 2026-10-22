import math
from itertools import islice


def validate_weights(weights):
    if len(weights) != 4 or any(
        type(w) not in (float, int) or not math.isfinite(w) or not 0 < w <= 100 for w in weights
    ):
        raise ValueError("Four finite workload weights in (0,100] are required")
    if list(weights) != sorted(weights):
        raise ValueError("Workload weights must not decrease with priority")
    return dict(zip(("LOW", "MEDIUM", "HIGH", "CRITICAL"), weights, strict=True))


def recommend(officers, incoming_units, latitude, longitude):
    from app.algorithms.department_assignment.routing_engine import covered

    ranked, excluded = [], []
    for officer in officers:
        reasons = []
        if not officer["eligibleAccount"] or not officer["active"]:
            reasons.append("Inactive, unverified, non-officer account or membership")
        if officer["availability"] != "AVAILABLE":
            reasons.append("Not available for a new assignment")
        if not covered(officer["areas"], latitude, longitude):
            reasons.append("Outside officer service area")
        capacity = officer["capacity"]
        if capacity is not None and officer["workload"] + incoming_units > capacity:
            reasons.append("Insufficient configured weighted capacity")
        if reasons:
            excluded.append({"officerId": officer["officerId"], "reasons": reasons})
            continue
        utilization = officer["workload"] / capacity if capacity else None
        ranked.append(
            officer
            | {
                "utilization": utilization,
                "projectedWorkload": officer["workload"] + incoming_units,
                "explanation": "Global weighted workload / capacity; stable user-ID tie-break."
                if capacity
                else "Capacity unknown: manual approval only; compare weighted workload.",
            }
        )
    ranked.sort(
        key=lambda o: (
            o["capacity"] is None,
            o["utilization"] if o["utilization"] is not None else o["workload"],
            o["officerId"],
        )
    )
    return {"ranked": ranked, "excluded": excluded}


def rebalance_analysis(officers, incidents):
    """Bounded advisory moves only; never transfer in-progress work or invent capacity."""
    eligible = {
        o["officerId"]: o
        for o in officers
        if o["active"]
        and o["eligibleAccount"]
        and o["availability"] == "AVAILABLE"
        and o["capacity"] is not None
    }
    proposals = []
    unstarted = (i for i in incidents if i["status"] == "OFFICER_ASSIGNED")
    for incident in islice(unstarted, 50):
        source = eligible.get(incident["officerId"])
        if not source or incident["status"] != "OFFICER_ASSIGNED":
            continue
        units = incident["units"]
        targets = recommend(
            [o for key, o in eligible.items() if key != source["officerId"]],
            units,
            incident["latitude"],
            incident["longitude"],
        )["ranked"]
        for target in targets:
            before = (
                source["workload"] / source["capacity"] - target["workload"] / target["capacity"]
            )
            after = abs(
                (source["workload"] - units) / source["capacity"]
                - (target["workload"] + units) / target["capacity"]
            )
            if before >= 0.5 and before - after >= 0.1:
                proposals.append(
                    {
                        "incidentId": incident["incidentId"],
                        "fromOfficerId": source["officerId"],
                        "toOfficerId": target["officerId"],
                        "reason": "Unstarted work could reduce normalized workload imbalance; "
                        "manual confirmation and fresh capacity checks required.",
                        "estimatedUtilizationGapBefore": round(before, 4),
                        "estimatedUtilizationGapAfter": round(after, 4),
                    }
                )
                break
        if len(proposals) >= 20:
            break
    return {
        "proposals": proposals,
        "automaticTransfers": False,
        "message": "No automatic redistribution. Suggestions are not completion-time predictions.",
    }
