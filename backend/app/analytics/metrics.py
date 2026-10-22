import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from app.services.sla_service import target_states


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def distribution(rows, key):
    return [
        {"label": str(k), "count": v}
        for k, v in sorted(Counter(r[key] for r in rows).items(), key=lambda pair: str(pair[0]))
    ]


def stats(values):
    return {
        "sampleSize": len(values),
        "meanHours": statistics.mean(values) if values else None,
        "medianHours": statistics.median(values) if values else None,
        "minimumHours": min(values) if values else None,
        "maximumHours": max(values) if values else None,
    }


def enrich(data, settings, config_version, now):
    """Read authoritative Phase8 scores/Phase9 weights; do not calculate a new priority."""
    weights = dict(
        zip(("LOW", "MEDIUM", "HIGH", "CRITICAL"), settings.workload_weights, strict=True)
    )
    members = defaultdict(list)
    histories = defaultdict(list)
    audit = defaultdict(list)
    for row in data["complaints"]:
        members[row["incident_id"]].append(row)
    for row in data["history"]:
        histories[row["entity_id"]].append(row | {"after": json.loads(row["after_state"])})
    for row in data["audit"]:
        audit[row["incident_id"]].append(row)
    result = []
    for source in data["incidents"]:
        row = source.copy()
        fresh = bool(
            row["calculated_at"]
            and row.get("has_priority_result")
            and row["priority_band"] in weights
            and not row["needs_recalculation"]
            and row["source_version"] == row["version"]
            and row["config_version"] == config_version
            and row["next_due"] > now.timestamp()
        )
        row.update(
            stale=not fresh,
            band=row["priority_band"] if fresh else "UNAVAILABLE",
            score=row["calculated_score"] if fresh else None,
            effectiveScore=row["effective_score"] if fresh else None,
            urgent=bool(row["urgent_hazard"]) if fresh else None,
            units=weights[row["priority_band"]] if fresh else weights["CRITICAL"],
        )
        row["members"] = members[row["incident_id"]]
        row["reportCount"] = len(row["members"])
        row["reporters"] = {r["citizen_id"] for r in row["members"]}
        row["assignment_status"] = row["assignment_status"] or "UNASSIGNED"
        baseline = stamp(row["opened_at"] or row["first_reported_at"])
        history = histories[row["incident_id"]]
        responses = [
            stamp(h["after"].get("assignedAt"))
            for h in history
            if h["kind"].startswith("ASSIGNMENT_")
            and h["after"].get("departmentId")
            and h["after"].get("status") != "NEEDS_REVIEW"
            and h["after"].get("assignedAt")
        ]
        responses = [at for at in responses if baseline <= at <= now]
        response = min(responses) if responses else None
        starts = [
            stamp(h["created_at"])
            for h in history
            if h["kind"] == "WORK_START" and baseline <= stamp(h["created_at"]) <= now
        ]
        row["responseHours"] = (response - baseline).total_seconds() / 3600 if response else None
        row["workStartHours"] = (min(starts) - baseline).total_seconds() / 3600 if starts else None
        transitions = [
            a
            for a in audit[row["incident_id"]]
            if a["next_status"] == "RESOLVED"
            and a["previous_status"] == "OPEN"
            and a["resolved_at"]
            and baseline <= stamp(a["resolved_at"]) <= now
        ]
        resolution = (
            stamp(row["resolved_at"])
            if row["status"] == "RESOLVED"
            and transitions
            and row["resolved_at"]
            and baseline <= stamp(row["resolved_at"]) <= now
            and any(stamp(a["resolved_at"]) == stamp(row["resolved_at"]) for a in transitions)
            else None
        )
        row["resolutionHours"] = (
            (resolution - baseline).total_seconds() / 3600 if resolution else None
        )
        row["recordedResolution"] = resolution is not None
        row["overdue"] = False
        row["approaching"] = False
        row["sla"] = {"RESPONSE": "UNAVAILABLE", "RESOLUTION": "UNAVAILABLE"}
        policies = [
            p
            for p in data["policies"]
            if fresh
            and p["priority_band"] == row["band"]
            and (not p["category"] or p["category"] == row["category"])
            and (not p["department_id"] or p["department_id"] == row["department_id"])
            and (not p["urgent"] or row["urgent"])
        ]
        policies.sort(
            key=lambda p: (
                -(bool(p["category"]) + bool(p["department_id"]) + p["urgent"]),
                p["policy_id"],
            )
        )
        if policies and (row["status"] == "OPEN" or resolution):
            assignment = {
                "departmentId": row["department_id"],
                "status": row["assignment_status"],
                "assignedAt": row["assigned_at"],
                "responseAt": response.isoformat() if response else None,
            }
            for milestone, deadline, reached, breached in target_states(
                baseline.isoformat(), assignment, policies[0], now
            ):
                # A recorded late response is measurable but noncompliant, not still pending.
                state = "MET" if reached else "MISSED" if breached else "PENDING"
                if milestone == "RESPONSE" and response:
                    state = "MET" if response <= deadline else "MISSED"
                if resolution and milestone == "RESOLUTION":
                    state = "MET" if resolution <= deadline else "MISSED"
                row["sla"][milestone] = state
                row["overdue"] |= row["status"] == "OPEN" and breached
                row["approaching"] |= (
                    row["status"] == "OPEN"
                    and not reached
                    and now < deadline <= now + timedelta(hours=24)
                )
        row["ageDays"] = max(0, (now - baseline).total_seconds() / 86400)
        result.append(row)
    return result


def compliance(rows, milestone):
    counts = Counter(row["sla"][milestone] for row in rows)
    denominator = counts["MET"] + counts["MISSED"]
    return {
        "met": counts["MET"],
        "missed": counts["MISSED"],
        "pending": counts["PENDING"],
        "unavailable": counts["UNAVAILABLE"],
        "denominator": denominator,
        "rate": counts["MET"] / denominator if denominator else None,
    }
