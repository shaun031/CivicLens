import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime

from app.analytics.geographic import hotspots, within
from app.analytics.metrics import compliance, distribution, enrich, stamp, stats
from app.analytics.trends import series
from app.models.incident import IncidentError
from app.utils.context_cursor import pack_cursor, unpack_cursor

VIEWS = (
    "overview",
    "complaint-trends",
    "incidents",
    "priorities",
    "departments",
    "officers",
    "sla",
    "backlog",
    "hotspots",
    "response-times",
)


class AnalyticsService:
    def __init__(self, repository, settings, priority_config, clock=None):
        self.repository, self.settings, self.priority_config = repository, settings, priority_config
        self.clock = clock or (lambda: datetime.now(UTC))

    def calculate(self, filters):
        now = self.clock()
        try:
            start, end = filters.window(self.settings.analytics_timezone, now)
        except ValueError as error:
            raise IncidentError(422, str(error)) from error
        areas = self.settings.analytics_service_areas
        if filters.area and filters.area not in areas:
            raise IncidentError(422, "Unknown configured service area")
        bounds = (
            [filters.south, filters.west, filters.north, filters.east]
            if filters.south is not None
            else None
        )
        data = self.repository.snapshot()
        if filters.department and str(filters.department) not in {
            d["id"] for d in data["departments"]
        }:
            raise IncidentError(422, "Department not found")
        all_incidents = enrich(data, self.settings, self.priority_config.version, now)

        def geography(row):
            return (
                (not areas or any(within(row, b) for b in areas.values()))
                and (not filters.area or within(row, areas[filters.area]))
                and within(row, bounds)
            )

        def matches(row):
            return (
                geography(row)
                and (not filters.category or row["category"] == filters.category)
                and (not filters.department or row["department_id"] == str(filters.department))
                and (not filters.priority or row["band"] == filters.priority)
                and (not filters.status or row["status"] == filters.status)
                and (not filters.assignment or row["assignment_status"] == filters.assignment)
                and (filters.urgent is None or row["urgent"] is filters.urgent)
            )

        incidents = [
            r for r in all_incidents if start <= stamp(r["created_at"]) < end and matches(r)
        ]
        # Incident attributes constrain reports, but do not impose incident-creation dates
        # to report submissions: each measure has its own documented creation-date cohort.
        matching_ids = {r["incident_id"] for r in all_incidents if matches(r)}
        operational = any(
            v is not None
            for v in (
                filters.department,
                filters.priority,
                filters.status,
                filters.assignment,
                filters.urgent,
            )
        )
        reports = [
            r
            for r in data["complaints"]
            if start <= stamp(r["created_at"]) < end
            and geography(r)
            and (not filters.category or r["category"] == filters.category)
            and (not operational or r["incident_id"] in matching_ids)
        ]
        active = [r for r in incidents if r["status"] == "OPEN"]
        ids = {r["incident_id"] for r in incidents}
        escalations = [
            r
            for r in data["escalations"]
            if r["incident_id"] in ids and start <= stamp(r["created_at"]) < end
        ]
        meta = {
            "calculatedAt": now.isoformat(),
            "reportingTimezone": self.settings.analytics_timezone,
            "scope": self.settings.analytics_scope,
            "window": {"startInclusive": start.isoformat(), "endExclusive": end.isoformat()},
            "filters": filters.model_dump(mode="json", exclude_none=True),
            "dataFreshness": {
                "mode": "PROJECTION"
                if data["meta"].get("cloudCalculatedAt")
                else "DIRECT_SNAPSHOT",
                "projectionCalculatedAt": data["meta"].get("cloudCalculatedAt"),
                "sourceRevision": data["meta"]["revision"],
                "projectionVersion": 1,
                "lastEventObservedAt": data["meta"].get("observed_at"),
                "stalePriorityCount": sum(r["stale"] for r in incidents),
                "stale": False,
            },
            "limitations": [
                "Creation-date cohorts; CURRENT membership/assignment, not historical snapshots",
                "Recorded resolution transitions are not Phase12 citizen repair verification",
                "Missing/stale priority is unavailable; workload charges maximum units",
            ],
        }
        return data, all_incidents, incidents, active, reports, escalations, meta, bounds

    @staticmethod
    def incident_public(row):
        return {
            "incidentId": row["incident_id"],
            "category": row["category"],
            "status": row["status"],
            "priority": row["band"],
            "urgentHazard": row["urgent"],
            "stale": row["stale"],
            "departmentId": row["department_id"],
            "assignmentStatus": row["assignment_status"],
            "reportCount": row["reportCount"],
            "uniqueReporters": len(row["reporters"]),
            "overdue": row["overdue"],
            "ageDays": row["ageDays"],
            "createdAt": row["created_at"],
        }

    def page(self, rows, filters, meta, route, key):
        context = {
            "route": route,
            "scope": self.settings.analytics_scope,
            "revision": meta["dataFreshness"]["sourceRevision"],
            "filters": filters.model_dump(mode="json", exclude={"cursor"}),
            "window": meta["window"],
        }
        after = unpack_cursor(filters.cursor, context, (1,)) if filters.cursor else None
        if after and not isinstance(after[0], str):
            raise IncidentError(400, "Invalid analytics keyset cursor")
        rows = sorted(rows, key=lambda r: str(r[key]))
        if after:
            rows = [r for r in rows if str(r[key]) > after[0]]
        selected = rows[: filters.limit]
        cursor = (
            pack_cursor(context, [str(selected[-1][key])]) if len(rows) > filters.limit else None
        )
        return {"items": selected, "nextCursor": cursor}

    def view(self, name, filters):
        if name not in VIEWS:
            raise IncidentError(404, "Analytics view not found")
        data, all_incidents, incidents, active, reports, escalations, meta, bounds = self.calculate(
            filters
        )
        calculated = stamp(meta["calculatedAt"])
        window = (stamp(meta["window"]["startInclusive"]), stamp(meta["window"]["endExclusive"]))
        ids = {r["incident_id"] for r in incidents}
        canonical_ids = {r["incident_id"] for r in all_incidents}
        history = [
            h | {"after": json.loads(h["after_state"])}
            for h in data["history"]
            if h["entity_id"] in ids
            and stamp(meta["window"]["startInclusive"])
            <= stamp(h["created_at"])
            < min(stamp(meta["window"]["endExclusive"]), calculated)
        ]
        eligible_officers = [
            o
            for o in data["officers"]
            if o["active"]
            and o["role"] == "OFFICER"
            and o["is_active"]
            and o["is_verified"]
            and o["department_id"] in {d["id"] for d in data["departments"] if d["active"]}
        ]
        if name == "overview":
            result = {
                "totalComplaints": len(reports),
                "totalIncidents": len(incidents),
                "activeIncidents": len(active),
                "resolvedIncidents": sum(r["recordedResolution"] for r in incidents),
                "recordedResolvedState": sum(r["status"] == "RESOLVED" for r in incidents),
                "unassignedIncidents": sum(not r["department_id"] for r in active),
                "criticalIncidents": sum(r["band"] == "CRITICAL" for r in active),
                "highPriorityIncidents": sum(r["band"] == "HIGH" for r in active),
                "overdueIncidents": sum(r["overdue"] for r in active),
                "activeDepartments": sum(
                    d["active"] and (not filters.department or d["id"] == str(filters.department))
                    for d in data["departments"]
                ),
                "availableOfficers": len(
                    {
                        o["officer_id"]
                        for o in eligible_officers
                        if o["availability"] == "AVAILABLE"
                        and (
                            not filters.department or o["department_id"] == str(filters.department)
                        )
                    }
                ),
                "uniqueReporters": len({r["citizen_id"] for r in reports}),
            }
            urgent = sorted(
                active,
                key=lambda r: (
                    not r["urgent"],
                    r["effectiveScore"] is None,
                    -(r["effectiveScore"] or 0),
                    -(r.get("unresolved_seconds") or 0),
                    r["incident_id"],
                ),
            )
            result["urgentQueue"] = [self.incident_public(r) for r in urgent[:10]]
            start, end = window
            result["priorityDistribution"] = distribution(active, "band")
            result["categoryDistribution"] = distribution(incidents, "category")
            result["complaintTrend"] = series(
                reports, start, end, self.settings.analytics_timezone, filters.grouping
            )
            result["incidentTrend"] = series(
                incidents, start, end, self.settings.analytics_timezone, filters.grouping
            )
            result["departmentOverview"] = [
                {"label": d["name"], "count": sum(r["department_id"] == d["id"] for r in active)}
                for d in data["departments"]
            ]
            result["geographicPreview"] = hotspots(incidents, [], filters.grid, None)[:10]
            result["geographicPreviewBasis"] = (
                "Top10 occupied cells; canonical incident counts only"
            )
            result["recentActivity"] = [
                {"incidentId": h["entity_id"], "kind": h["kind"], "at": h["created_at"]}
                for h in reversed(data["history"])
                if h["entity_id"] in ids and stamp(h["created_at"]) <= calculated
            ][:10]
        elif name == "complaint-trends":
            start, end = window
            initial = {}
            for h in data.get("membershipHistory", []):
                if stamp(h["created_at"]) <= calculated:
                    initial.setdefault(h["complaint_id"], h)
            initial_new = sum(
                initial.get(r["complaint_id"], {}).get("operation") == "INITIAL_ASSIGNMENT"
                for r in reports
            )
            initial_existing = sum(
                initial.get(r["complaint_id"], {}).get("operation")
                in ("AUTOMATIC_LINK", "MANUAL_LINK")
                for r in reports
            )
            result = {
                "total": len(reports),
                "series": series(
                    reports, start, end, self.settings.analytics_timezone, filters.grouping
                ),
                "byCategory": distribution(reports, "category"),
                "bySeverity": distribution(reports, "reported_severity"),
                "linkedCurrent": sum(r["incident_id"] in canonical_ids for r in reports),
                "historicalExistingVsNew": {
                    "initialSingletonReports": initial_new,
                    "initialExistingIncidentLinks": initial_existing,
                    "unknownInitialLinkage": len(reports) - initial_new - initial_existing,
                },
                "historicalLinkReason": (
                    "First recorded durable linkage, not membership at "
                    "submission or retrospective physical-defect identity"
                ),
            }
        elif name == "incidents":
            start, end = window
            result = {
                "total": len(incidents),
                "active": len(active),
                "resolved": sum(r["recordedResolution"] for r in incidents),
                "singleReport": sum(r["reportCount"] == 1 for r in incidents),
                "multiReport": sum(r["reportCount"] > 1 for r in incidents),
                "averageReports": sum(r["reportCount"] for r in incidents) / len(incidents)
                if incidents
                else None,
                "uniqueReporters": len(set().union(*(r["reporters"] for r in incidents)))
                if incidents
                else 0,
                "byCategory": distribution(incidents, "category"),
                "byStatus": distribution(incidents, "status"),
                "recordedStatusChanges": [
                    {
                        "at": h["created_at"],
                        "from": h["previous_status"],
                        "to": h["next_status"],
                        "operation": h["operation"],
                    }
                    for h in data["audit"]
                    if h["incident_id"] in ids
                    and h["previous_status"] != h["next_status"]
                    and start <= stamp(h["created_at"]) < min(end, calculated)
                ][-100:],
                "creationTrend": series(
                    incidents, start, end, self.settings.analytics_timezone, filters.grouping
                ),
                **self.page(
                    [self.incident_public(r) for r in incidents], filters, meta, name, "incidentId"
                ),
            }
        elif name == "priorities":
            scores = [r["score"] for r in active if r["score"] is not None]
            result = {
                "distribution": distribution(active, "band"),
                "verifiedUrgentHazards": sum(r["urgent"] is True for r in active),
                "requiringAssessment": sum(
                    r["stale"] or r["assessment_status"] != "VERIFIED" for r in active
                ),
                "provisional": sum(r["assessment_status"] == "PROVISIONAL" for r in active),
                "meanCalculatedScore": sum(scores) / len(scores) if scores else None,
                "medianCalculatedScore": statistics.median(scores) if scores else None,
                "sampleSize": len(scores),
                "byCategoryPriorities": self.cross(active, "category"),
                "byDepartmentPriorities": self.cross(active, "department_id"),
                "historicalPriorityTrend": [
                    {"at": h["created_at"], "kind": h["kind"], "priority": h["band"]}
                    for h in data.get("priorityHistory", [])
                    if h["incident_id"] in ids
                    and meta["window"]["startInclusive"]
                    <= stamp(h["created_at"]).isoformat()
                    < meta["window"]["endExclusive"]
                ][-100:],
                "historyReason": "Actual score events (last100), not historical citywide rankings",
            }
        elif name == "departments":
            rows = []
            for dept in data["departments"]:
                if filters.department and dept["id"] != str(filters.department):
                    continue
                cohort = [r for r in incidents if r["department_id"] == dept["id"]]
                opened = [r for r in cohort if r["status"] == "OPEN"]
                cohort_ids = {r["incident_id"] for r in cohort}
                events = [h for h in history if h["entity_id"] in cohort_ids]
                start, end = window
                rows.append(
                    {
                        "departmentId": dept["id"],
                        "name": dept["name"],
                        "active": bool(dept["active"]),
                        "activeIncidents": len(opened),
                        "assignedIncidents": sum(bool(r["officer_id"]) for r in opened),
                        "awaitingOfficer": sum(not r["officer_id"] for r in opened),
                        "inProgress": sum(r["assignment_status"] == "IN_PROGRESS" for r in opened),
                        "critical": sum(r["band"] == "CRITICAL" for r in opened),
                        "overdue": sum(r["overdue"] for r in opened),
                        "workloadUnits": sum(r["units"] for r in opened),
                        "availableOfficers": len(
                            {
                                o["officer_id"]
                                for o in eligible_officers
                                if o["department_id"] == dept["id"]
                                and o["availability"] == "AVAILABLE"
                            }
                        ),
                        "resolved": sum(r["recordedResolution"] for r in cohort),
                        "response": stats(
                            [r["responseHours"] for r in cohort if r["responseHours"] is not None]
                        ),
                        "responseCompliance": compliance(cohort, "RESPONSE"),
                        "priorities": distribution(opened, "band"),
                        "recordedWorkMilestones": len(
                            {
                                h["entity_id"]
                                for h in events
                                if h["kind"] in ("WORK_START", "WORK_PROGRESS")
                                and h["after"].get("percentage") == 100
                            }
                        ),
                        "recordedOperationsTrend": series(
                            [
                                {"created_at": h["created_at"], "category": h["kind"]}
                                for h in events
                            ],
                            start,
                            end,
                            self.settings.analytics_timezone,
                            filters.grouping,
                        ),
                    }
                )
            result = {
                "unallocatedActiveIncidents": sum(not r["department_id"] for r in active),
                **self.page(rows, filters, meta, name, "departmentId"),
            }
        elif name == "officers":
            rows = []
            for officer in eligible_officers:
                if filters.department and officer["department_id"] != str(filters.department):
                    continue
                if filters.availability and officer["availability"] != filters.availability:
                    continue
                selected = [
                    r
                    for r in active
                    if r["officer_id"] == officer["officer_id"]
                    and r["department_id"] == officer["department_id"]
                ]
                global_work = [
                    r
                    for r in all_incidents
                    if r["status"] == "OPEN" and r["officer_id"] == officer["officer_id"]
                ]
                units = sum(r["units"] for r in global_work)
                events = [
                    h
                    for h in history
                    if h["after"].get("officerId") == officer["officer_id"]
                    and h["after"].get("departmentId") == officer["department_id"]
                ]
                start, end = window
                if (
                    filters.minWorkload is not None
                    and units < filters.minWorkload
                    or filters.maxWorkload is not None
                    and units > filters.maxWorkload
                ):
                    continue
                rows.append(
                    {
                        "membershipId": officer["officer_id"] + ":" + officer["department_id"],
                        "officerId": officer["officer_id"],
                        "displayName": officer["display_name"],
                        "departmentId": officer["department_id"],
                        "availability": officer["availability"],
                        "assignedActiveIncidents": len(selected),
                        "globalActiveIncidents": len(global_work),
                        "globalPendingPriorities": sum(r["stale"] for r in global_work),
                        "inProgress": sum(
                            r["assignment_status"] == "IN_PROGRESS" for r in selected
                        ),
                        "weightedWorkload": units,
                        "selectedWorkload": sum(r["units"] for r in selected),
                        "capacity": officer["capacity"],
                        "utilization": units / officer["capacity"] if officer["capacity"] else None,
                        "highPriority": sum(r["band"] in ("HIGH", "CRITICAL") for r in selected),
                        "overdue": sum(r["overdue"] for r in selected),
                        "recordedWorkMilestones": len(
                            {
                                h["entity_id"]
                                for h in events
                                if h["kind"] in ("WORK_START", "WORK_PROGRESS")
                                and h.get("actor_id") == officer["officer_id"]
                                and h["after"].get("percentage") == 100
                            }
                        ),
                        "assignmentTrend": series(
                            [
                                {"created_at": h["created_at"], "category": h["kind"]}
                                for h in events
                                if h["kind"].startswith("ASSIGNMENT_")
                            ],
                            start,
                            end,
                            self.settings.analytics_timezone,
                            filters.grouping,
                        ),
                    }
                )
            result = {
                "basis": (
                    "Global Phase9 workload per officer; selected cohort separate; "
                    "membership rows are not additive"
                ),
                **self.page(rows, filters, meta, name, "membershipId"),
            }
        elif name == "sla":
            start, end = window
            result = {
                "overdueIncidents": sum(r["overdue"] for r in active),
                "approachingDeadline": sum(r["approaching"] for r in active),
                "escalationCount": len(escalations),
                "distinctEscalatedIncidents": len({e["incident_id"] for e in escalations}),
                "acknowledged": sum(e["status"] == "ACKNOWLEDGED" for e in escalations),
                "unacknowledged": sum(e["status"] == "OPEN" for e in escalations),
                "responseCompliance": compliance(incidents, "RESPONSE"),
                "resolutionCompliance": compliance(incidents, "RESOLUTION"),
                "overdueByDepartment": distribution(
                    [r for r in active if r["overdue"]], "department_id"
                ),
                "overdueByPriority": distribution([r for r in active if r["overdue"]], "band"),
                "denominator": (
                    "Current-cycle measurable MET+MISSED canonical outcomes; "
                    "pending and unavailable are separate"
                ),
                "demonstrationTargets": True,
                "escalationTrend": series(
                    [
                        {"created_at": e["created_at"], "category": e["milestone"]}
                        for e in escalations
                    ],
                    start,
                    end,
                    self.settings.analytics_timezone,
                    filters.grouping,
                ),
            }
        elif name == "backlog":
            groups = {
                "Unassigned": lambda r: not r["department_id"],
                "Assigned, not started": lambda r: (
                    r["assignment_status"] in ("DEPARTMENT_ASSIGNED", "OFFICER_ASSIGNED")
                ),
                "In progress": lambda r: r["assignment_status"] == "IN_PROGRESS",
                "Needs review": lambda r: r["assignment_status"] == "NEEDS_REVIEW",
                "Overdue": lambda r: r["overdue"],
                "Critical": lambda r: r["band"] == "CRITICAL",
                "Awaiting officer": lambda r: r["department_id"] and not r["officer_id"],
            }
            result = {
                "totalBacklog": len(active),
                "overlappingSubgroups": [
                    {"label": k, "count": sum(bool(fn(r)) for r in active)}
                    for k, fn in groups.items()
                ],
                "byDepartment": distribution(active, "department_id"),
                "byPriority": distribution(active, "band"),
                "aging": [
                    {"label": label, "count": sum(low <= r["ageDays"] < high for r in active)}
                    for label, low, high in (
                        ("0–7 days", 0, 7),
                        ("7–30 days", 7, 30),
                        ("30–90 days", 30, 90),
                        ("90+ days", 90, float("inf")),
                    )
                ],
                "historicalBacklog": None,
                "historyReason": "Current state does not reconstruct historical backlog",
            }
        elif name == "hotspots":
            if bounds is None:
                raise IncidentError(422, "Hotspots require explicit bounded viewport coordinates")
            cells = hotspots(incidents, reports, filters.grid, bounds)
            if len(cells) > 2000:
                raise IncidentError(
                    413, "Hotspot response exceeds2000 occupied cells; coarsen grid"
                )
            result = {
                "cells": cells,
                "gridDegrees": filters.grid,
                "incidentCount": len(incidents),
                "reportCount": len(reports),
                "interpretation": (
                    "Observed report concentration, not population-adjusted risk, "
                    "causation or fairness"
                ),
            }
        else:
            result = {
                "firstAssignment": stats(
                    [r["responseHours"] for r in incidents if r["responseHours"] is not None]
                ),
                "workStart": stats(
                    [r["workStartHours"] for r in incidents if r["workStartHours"] is not None]
                ),
                "recordedResolution": stats(
                    [r["resolutionHours"] for r in incidents if r["resolutionHours"] is not None]
                ),
                "resolutionReason": (
                    "Valid recorded OPEN→RESOLVED audit transitions only; "
                    "citizen repair verification is not implemented"
                ),
            }
        return meta | result

    @staticmethod
    def cross(rows, key):
        groups = defaultdict(Counter)
        for r in rows:
            groups[str(r[key] or "Unassigned")][r["band"]] += 1
        return [{"label": k, "priorities": dict(v)} for k, v in sorted(groups.items())]

    def rebuild(self, filters, views, dry_run=False):
        results = []
        for view in views:
            body = self.view(view, filters)
            identity = hashlib.sha256(
                (
                    view
                    + json.dumps(
                        filters.model_dump(mode="json", exclude={"cursor"}), sort_keys=True
                    )
                ).encode()
            ).hexdigest()
            previous = self.repository.projection(identity)
            old = json.loads(previous["body"]) if previous else None

            # Compare only metrics, not timestamps/checkpoint metadata.
            def clean(x):
                if isinstance(x, dict):
                    return {
                        k: clean(v)
                        for k, v in x.items()
                        if k not in ("calculatedAt", "dataFreshness", "ageDays")
                    }
                if isinstance(x, list):
                    return [clean(v) for v in x]
                return x

            matches = old is not None and clean(old) == clean(body)
            if not dry_run:
                self.repository.save_snapshot(
                    identity, body["dataFreshness"]["sourceRevision"], body, body["calculatedAt"]
                )
            results.append(
                {
                    "view": view,
                    "matchesPrevious": matches,
                    "previousAvailable": old is not None,
                    "sourceRevision": body["dataFreshness"]["sourceRevision"],
                    "saved": not dry_run,
                }
            )
        return {
            "dryRun": dry_run,
            "projectionVersion": 1,
            "results": results,
            "operationalRecordsModified": False,
        }
