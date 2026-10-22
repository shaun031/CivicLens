"""Bounded local diagnostics and conservative, auditable repairs; never delete history."""

import time
from collections import Counter
from uuid import uuid4

from app.models.incident import Actor, IncidentError, IncidentPlan, MembershipChange, stable_id
from app.repositories.duplicate_candidate_repository import timestamp


def reconcile(
    service,
    limit: int = 50,
    after: str = "",
    repair: bool = False,
    incident_after: str = "",
    candidate_after: str = "",
    event_after: str = "",
) -> dict:
    repository = service.repository
    if not hasattr(repository, "store"):
        raise IncidentError(422, "Reconciliation CLI is local-only")
    store = repository.store
    issues, repaired, seen = [], [], []
    with store.connection() as db:
        rows = db.execute(
            "SELECT complaint_id,incident_id FROM complaints WHERE complaint_id>? "
            "ORDER BY complaint_id LIMIT ?",
            (after, limit),
        ).fetchall()
    for row in rows:
        identity, incident_id = row[0], row[1]
        seen.append(identity)
        incident = repository.load(incident_id) if incident_id else None
        if incident is None or incident.status in ("MERGED", "SUPERSEDED"):
            issue = {
                "kind": "UNASSIGNED" if incident_id is None else "INVALID_ACTIVE_REFERENCE",
                "complaintId": identity,
                "previousIncidentId": incident_id,
            }
            issues.append(issue)
            if not repair:
                continue
            if incident_id is None:
                service.ensure_singleton(identity)
                repaired.append(issue)
                continue
            # Corrupt/alias references never justify combining reports: detach to singletons.
            members = service.members(incident_id)
            now, token = timestamp(), str(uuid4())
            before, new, changes = {}, {}, []
            if not members:
                members = [service.require_member(identity)]
            for member in members:
                new_id = stable_id(f"repair/{token}/{member.complaint.complaintId}")
                before[new_id] = None
                new[new_id] = service.new_incident(new_id, [member], now)
                changes.append(
                    MembershipChange(
                        member.complaint.complaintId,
                        incident_id,
                        new_id,
                        {"repair": "Invalid association; isolated, not merged"},
                    )
                )
            if incident:
                before[incident_id] = incident
                new[incident_id] = service.refreshed(
                    incident, [], now, incident.status, incident.mergedIntoIncidentId
                )
            else:
                # Preserve the invalid historical identifier as an audited retired placeholder.
                before[incident_id] = None
                placeholder = service.new_incident(incident_id, [members[0]], now)
                new[incident_id] = replace_model(
                    placeholder,
                    status="SUPERSEDED",
                    totalComplaintCount=0,
                    uniqueReporterCount=0,
                    mergedIntoIncidentId=changes[0].new_incident_id,
                )
            plan = IncidentPlan(
                stable_id(token),
                token,
                "CORRECTION",
                Actor("reconciliation-cli", "SYSTEM"),
                "Explicit repair of invalid membership; every report retained as a singleton",
                before,
                new,
                changes,
                members,
                changes[0].new_incident_id,
                now,
            )
            repository.commit(plan)
            repaired.append(issue)
    # Incident cursor is separate: a bounded batch, not a global all-pairs pass.
    with store.connection() as db:
        incident_ids = [
            row[0]
            for row in db.execute(
                "SELECT incident_id FROM incidents "
                "WHERE incident_id>? ORDER BY incident_id LIMIT ?",
                (incident_after, limit),
            )
        ]
        events = db.execute(
            "SELECT membership_event_id,operation_id,complaint_id FROM incident_membership_events "
            "WHERE membership_event_id>? ORDER BY membership_event_id LIMIT ?",
            (event_after, limit),
        ).fetchall()
        duplicates = Counter((e[1], e[2]) for e in events)
        duplicate_events = sum(count > 1 for count in duplicates.values())
        candidates = db.execute(
            "WITH batch AS (SELECT candidate_id,source_id,duplicate_id FROM duplicate_candidates "
            "WHERE candidate_id>? ORDER BY candidate_id LIMIT ?) "
            "SELECT d.candidate_id,a.complaint_id,b.complaint_id FROM batch d "
            "LEFT JOIN complaints a ON a.complaint_id=d.source_id "
            "LEFT JOIN complaints b ON b.complaint_id=d.duplicate_id "
            "ORDER BY d.candidate_id",
            (candidate_after, limit),
        ).fetchall()
        stale = [row[0] for row in candidates if row[1] is None or row[2] is None]
        jobs = []
        for identity in seen:
            job = db.execute(
                "SELECT state,available_at,error_category FROM clustering_jobs WHERE source_id=?",
                (identity,),
            ).fetchone()
            if job and (job[0] == "RETRY" or (job[0] == "RUNNING" and job[1] <= time.time())):
                jobs.append({"complaintId": identity, "state": job[0], "errorCategory": job[2]})
    for identity in incident_ids:
        incident = service.require(identity)
        try:
            _, chain = service.resolve(identity)
            members = service.members(identity)
        except IncidentError as error:
            issues.append(
                {
                    "kind": "ALIAS_OR_MEMBERSHIP_ERROR",
                    "incidentId": identity,
                    "manualReviewRequired": True,
                    "message": error.message,
                }
            )
            continue
        count = len(members)
        reporters = len({m.complaint.citizenId for m in members if m.eligible_reporter})
        invalid = (
            incident.totalComplaintCount != count
            or incident.uniqueReporterCount != reporters
            or (incident.status == "OPEN" and count == 0)
        )
        if invalid:
            issue = {
                "kind": "SUMMARY_OR_EMPTY_ACTIVE",
                "incidentId": identity,
                "actualComplaints": count,
                "actualReporters": reporters,
            }
            issues.append(issue)
            if repair:
                now, token = timestamp(), str(uuid4())
                updated = service.refreshed(
                    incident,
                    members,
                    now,
                    incident.status if incident.status != "OPEN" else "SUPERSEDED",
                    incident.mergedIntoIncidentId,
                )
                repository.commit(
                    IncidentPlan(
                        stable_id(token),
                        token,
                        "CORRECTION",
                        Actor("reconciliation-cli", "SYSTEM"),
                        "Explicit recalculation from authoritative memberships",
                        {identity: incident},
                        {identity: updated},
                        [],
                        members,
                        identity,
                        now,
                    )
                )
                repaired.append(issue)
        if (incident.status == "OPEN" and incident.resolvedAt) or (
            incident.status == "RESOLVED" and not incident.resolvedAt
        ):
            issues.append(
                {"kind": "LIFECYCLE_METADATA", "incidentId": identity, "manualReviewRequired": True}
            )
        if len(chain) >= 64:
            issues.append(
                {"kind": "ALIAS_DEPTH", "incidentId": identity, "manualReviewRequired": True}
            )
    return {
        "dryRun": not repair,
        "complaintsChecked": len(rows),
        "incidentsChecked": len(incident_ids),
        "issues": issues,
        "repaired": repaired,
        "duplicateMembershipEvents": duplicate_events,
        "staleCandidateReferences": len(stale),
        "retryOrExpiredJobs": jobs,
        "candidateReferencesChecked": len(candidates),
        "membershipEventsChecked": len(events),
        "nextComplaintAfter": seen[-1] if seen else after,
        "nextIncidentAfter": incident_ids[-1] if incident_ids else incident_after,
        "nextCandidateAfter": candidates[-1][0] if candidates else candidate_after,
        "nextEventAfter": events[-1][0] if events else event_after,
        "note": "Cycles, lifecycle ambiguity and stale references need manual review; no deletion",
    }


def replace_model(model, **updates):
    return type(model).model_validate(model.model_dump() | updates)
