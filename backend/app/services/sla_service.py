"""Hypothetical operational targets, never a legal deadline or a severity override."""

from datetime import datetime, timedelta
from uuid import uuid4

from app.events.schema import Event, new_event
from app.models.incident import IncidentError, stable_id
from app.repositories.event_repository import encoded


def target_states(opened_at, assignment, policy, now):
    """Pure deadline logic shared by SQLite and DynamoDB scheduling."""
    baseline = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
    result = []
    for milestone, hours in (
        ("RESPONSE", policy["response_hours"]),
        ("RESOLUTION", policy["resolution_hours"]),
    ):
        deadline = baseline + timedelta(hours=hours)
        assigned_at = assignment.get("responseAt") or assignment.get("assignedAt")
        reached = bool(
            milestone == "RESPONSE"
            and (
                assignment.get("responseAt")
                or (assignment.get("departmentId") and assignment.get("status") != "NEEDS_REVIEW")
            )
            and assigned_at
            and baseline <= datetime.fromisoformat(assigned_at.replace("Z", "+00:00")) <= deadline
        )
        result.append((milestone, deadline, reached, not reached and now >= deadline))
    return result


def first_response(repository, identity, opened_at):
    """Bounded strong audit chronology; an old reassignment must not erase a met response target."""
    baseline = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
    after = None
    for _ in range(2):
        page = repository.history(identity, 50, after)
        for item in page["items"]:
            record = item["after"]
            at = record.get("assignedAt")
            if (
                item["kind"].startswith("ASSIGNMENT_")
                and record.get("departmentId")
                and record.get("status") != "NEEDS_REVIEW"
                and at
                and datetime.fromisoformat(at.replace("Z", "+00:00")) >= baseline
            ):
                return at
        after = page.get("after")
        if not after:
            return None
    raise IncidentError(
        409, "SLA response chronology exceeds100 records; controlled review required"
    )


class SQLiteSLA:
    def __init__(self, events, priorities):
        self.events, self.priorities, self.store = events, priorities, events.store

    def policies(self):
        with self.store.connection() as db:
            return {
                "items": [
                    dict(r)
                    for r in db.execute("SELECT * FROM sla_policies ORDER BY policy_id LIMIT 101")
                ]
            }

    def save(self, identity, data, actor):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            operation = stable_id(f"sla-policy/{actor}/{data['operationId']}")
            fingerprint = encoded({"policyId": identity, "data": data})
            receipt = db.execute(
                "SELECT reason FROM workflow_audit WHERE id=?", (operation,)
            ).fetchone()
            if receipt:
                if receipt[0] != fingerprint:
                    raise IncidentError(409, "SLA operation ID reused with different input")
                return self.policies()
            existing = db.execute(
                "SELECT version FROM sla_policies WHERE policy_id=?", (identity,)
            ).fetchone()
            if (existing[0] if existing else 0) != data["expectedVersion"]:
                raise IncidentError(409, "SLA policy changed; reload before editing")
            if not data["confirmed"]:
                raise IncidentError(422, "Confirm demonstration SLA policy change")
            if (
                data.get("departmentId")
                and not db.execute(
                    "SELECT 1 FROM departments WHERE id=?", (str(data["departmentId"]),)
                ).fetchone()
            ):
                raise IncidentError(422, "Department not found")
            count = db.execute("SELECT count(*) FROM sla_policies").fetchone()[0]
            if not existing and count >= 100:
                raise IncidentError(409, "Bounded demo supports at most100 SLA policies")
            db.execute(
                "INSERT INTO sla_policies VALUES(?,?,?,?,?,?,?,1,?,?) ON "
                "CONFLICT(policy_id) DO UPDATE SET "
                "priority_band=excluded.priority_band,category=excluded.category,department"
                "_id=excluded.department_id,urgent=excluded.urgent,response_hours=excluded."
                "response_hours,resolution_hours=excluded.resolution_hours,version=version+"
                "1,updated_at=excluded.updated_at,updated_by=excluded.updated_by",
                (
                    identity,
                    data["priorityBand"],
                    data.get("category"),
                    data.get("departmentId"),
                    int(data["urgent"]),
                    data["responseHours"],
                    data["resolutionHours"],
                    self.events.clock().isoformat(),
                    actor,
                ),
            )
            # Future sweep takes the new policy, preserves breach receipts and first-open baseline.
            db.execute("UPDATE sla_checks SET next_due=0")
            db.execute(
                "INSERT INTO workflow_audit VALUES(?,?,?,?,?,?)",
                (
                    operation,
                    identity,
                    "SLA_POLICY_CHANGED",
                    actor,
                    fingerprint,
                    self.events.clock().isoformat(),
                ),
            )
        return self.policies()

    def check(self, identity, dry_run=False):
        now = self.events.clock()
        with self.store.connection() as db:
            db.execute("BEGIN" if dry_run else "BEGIN IMMEDIATE")
            incident = db.execute(
                "SELECT i.*,s.cycle,s.opened_at FROM incidents i JOIN sla_checks s "
                "USING(incident_id) WHERE incident_id=?",
                (identity,),
            ).fetchone()
            if not incident:
                raise IncidentError(404, "Incident not found")
            if incident["status"] != "OPEN":
                if not dry_run:
                    db.execute(
                        "UPDATE sla_checks SET next_due=? WHERE incident_id=?",
                        (253402214400, identity),
                    )
                return {"incidentId": identity, "excluded": incident["status"], "overdue": []}
            priority = db.execute(
                "SELECT * FROM incident_priority WHERE incident_id=?", (identity,)
            ).fetchone()
            if (
                not priority
                or priority["needs_recalculation"]
                or priority["source_version"] != incident["version"]
                or priority["config_version"] != self.priorities.config.version
                or priority["next_due"] <= now.timestamp()
            ):
                if not dry_run:
                    db.execute(
                        "UPDATE sla_checks SET "
                        "next_due=?,attempts=attempts+1,error_category='PRIORITY_NOT_CURREN"
                        "T' WHERE incident_id=?",
                        (now.timestamp() + 60, identity),
                    )
                return {"incidentId": identity, "pending": "PRIORITY_NOT_CURRENT", "overdue": []}
            assignment = db.execute(
                "SELECT * FROM incident_assignments WHERE incident_id=?", (identity,)
            ).fetchone()
            policies = db.execute(
                "SELECT * FROM sla_policies WHERE priority_band=? AND (category IS NULL OR "
                "category=?) AND (department_id IS NULL OR department_id=?) AND (urgent=0 "
                "OR urgent=?) ORDER BY (department_id IS NOT NULL)+(category IS NOT "
                "NULL)+urgent DESC,policy_id LIMIT 1",
                (
                    priority["priority_band"],
                    incident["category"],
                    assignment["department_id"] if assignment else None,
                    priority["urgent_hazard"],
                ),
            ).fetchone()
            if not policies:
                raise IncidentError(422, "No applicable demonstration SLA policy")
            overdue, deadlines, receipts = [], [], []
            from app.repositories.work_repository import assignment as assignment_dto

            response = db.execute(
                "SELECT json_extract(after_state,'$.assignedAt') FROM work_history "
                "WHERE entity_id=? AND kind LIKE 'ASSIGNMENT_%' "
                "AND json_extract(after_state,'$.departmentId') IS NOT NULL "
                "AND json_extract(after_state,'$.status')<>'NEEDS_REVIEW' "
                "AND julianday(json_extract(after_state,'$.assignedAt'))>=julianday(?) "
                "ORDER BY julianday(json_extract(after_state,'$.assignedAt')),event_id LIMIT 1",
                (identity, incident["opened_at"]),
            ).fetchone()
            assignment_state = assignment_dto(assignment) if assignment else {}
            assignment_state["responseAt"] = response[0] if response else None

            for milestone, deadline, reached, breached in target_states(
                incident["opened_at"],
                assignment_state,
                policies,
                now,
            ):
                if breached:
                    overdue.append(milestone)
                    receipt = stable_id(f"sla/{identity}/{incident['cycle']}/{milestone}")
                    exists = db.execute(
                        "SELECT 1 FROM escalations WHERE escalation_id=?", (receipt,)
                    ).fetchone()
                    if not exists:
                        receipts.append(receipt)
                        if not dry_run:
                            db.execute(
                                "INSERT INTO "
                                "escalations(escalation_id,incident_id,cycle,milestone,dead"
                                "line,policy_id,policy_version,created_at) "
                                "VALUES(?,?,?,?,?,?,?,?)",
                                (
                                    receipt,
                                    identity,
                                    incident["cycle"],
                                    milestone,
                                    deadline.isoformat(),
                                    policies["policy_id"],
                                    policies["version"],
                                    now.isoformat(),
                                ),
                            )
                            event = new_event(
                                "IncidentOverdue",
                                identity,
                                payload={"escalationId": receipt},
                                now=now,
                            )
                            self.events.put(
                                db,
                                Event.parse(
                                    event.model_dump(mode="json")
                                    | {"eventId": stable_id("sla-event/" + receipt)}
                                ),
                            )
                            db.execute(
                                "INSERT INTO workflow_audit VALUES(?,?,?,?,?,?)",
                                (
                                    str(uuid4()),
                                    identity,
                                    "SLA_OVERDUE",
                                    "scheduled-checks",
                                    f"Demonstration {milestone} target exceeded; no "
                                    f"priority override",
                                    now.isoformat(),
                                ),
                            )
                elif not reached:
                    deadlines.append(deadline.timestamp())
            if not dry_run:
                db.execute(
                    "UPDATE sla_checks SET next_due=?,attempts=0,error_category=NULL WHERE "
                    "incident_id=?",
                    (min(deadlines + [now.timestamp() + 3600]), identity),
                )
            return {
                "incidentId": identity,
                "overdue": overdue,
                "newEscalations": receipts,
                "demonstrationPolicy": True,
            }

    def sweep(self, size=20, dry_run=False):
        with self.store.connection() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT incident_id FROM sla_checks WHERE next_due<=? ORDER BY "
                    "next_due,incident_id LIMIT ?",
                    (self.events.clock().timestamp(), size),
                )
            ]
        results = []
        for identity in ids:
            try:
                results.append(self.check(identity, dry_run))
            except (IncidentError, ValueError):
                if not dry_run:
                    with self.store.connection() as db:
                        db.execute(
                            "UPDATE sla_checks SET "
                            "next_due=?,attempts=attempts+1,error_category='SLA_CHECK_FAILE"
                            "D' WHERE incident_id=?",
                            (self.events.clock().timestamp() + 300, identity),
                        )
                results.append({"incidentId": identity, "errorCategory": "SLA_CHECK_FAILED"})
        return {"checked": len(ids), "results": results, "dryRun": dry_run}

    def escalations(self, limit=20, after=None):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM escalations"
                + (" WHERE (created_at,escalation_id)<(?,?)" if after else "")
                + " ORDER BY created_at DESC,escalation_id DESC LIMIT ?",
                [*(after or []), limit + 1],
            ).fetchall()
            return {
                "items": [dict(r) for r in rows[:limit]],
                "after": [rows[limit - 1]["created_at"], rows[limit - 1]["escalation_id"]]
                if len(rows) > limit
                else None,
            }

    def acknowledge(self, identity, actor):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM escalations WHERE escalation_id=?", (identity,)
            ).fetchone()
            if not row:
                raise IncidentError(404, "Escalation not found")
            if row["status"] == "OPEN":
                db.execute(
                    "UPDATE escalations SET "
                    "status='ACKNOWLEDGED',acknowledged_at=?,acknowledged_by=? WHERE "
                    "escalation_id=?",
                    (self.events.clock().isoformat(), actor, identity),
                )
                db.execute(
                    "INSERT INTO workflow_audit VALUES(?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identity,
                        "SLA_ACKNOWLEDGED",
                        actor,
                        "Administrator acknowledged operational alert",
                        self.events.clock().isoformat(),
                    ),
                )
        return {"acknowledged": True}


def scheduled_checks(workflows, sla, size=20, dry_run=False):
    size = max(1, min(size, 100))
    priority = 0
    if not dry_run:
        for _ in range(size):
            if not workflows.priorities.process_one():
                break
            priority += 1
    return {"prioritiesProcessed": priority, "sla": sla.sweep(size, dry_run), "dryRun": dry_run}
