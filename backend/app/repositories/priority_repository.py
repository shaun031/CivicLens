import json
import sqlite3
import time
from dataclasses import dataclass
from uuid import uuid4

from app.models.incident import Actor, IncidentError, Member
from app.repositories.incident_repository import incident_row


@dataclass
class PrioritySnapshot:
    incident: object
    record: dict
    members: list[Member]


@dataclass
class PriorityCommit:
    snapshot: PrioritySnapshot
    result: dict
    controls: dict
    fingerprint: str
    facts: dict
    next_due: float
    actor: Actor
    reason: str
    kind: str = "RECALCULATE"
    operation_id: str | None = None
    request_fingerprint: str | None = None
    lease_token: str | None = None


def decode_record(row):
    record = dict(row)
    for key in ("controls", "result"):
        record[key] = json.loads(record[key]) if record[key] else {} if key == "controls" else None
    return record


def write_response(plan, revision):
    return {
        "priority": plan.result,
        "priorityRevision": revision,
        "incidentVersion": plan.snapshot.incident.version,
        "membershipEpoch": plan.snapshot.record["membership_epoch"],
        "controls": plan.controls,
        "stale": False,
    }


def history_payload(plan):
    return {
        "before": plan.snapshot.record.get("result"),
        "after": plan.result,
        "controlsBefore": plan.snapshot.record["controls"],
        "controlsAfter": plan.controls,
        "inputs": plan.facts,
        "sourceIncidentVersion": plan.snapshot.incident.version,
        "membershipEpoch": plan.snapshot.record["membership_epoch"],
    }


class SQLitePriority:
    def __init__(self, incidents):
        self.incidents, self.store = incidents, incidents.store

    def snapshot(self, identity):
        with self.store.connection() as db:
            db.execute("BEGIN")
            incident = db.execute(
                "SELECT * FROM incidents WHERE incident_id=?", (identity,)
            ).fetchone()
            if not incident:
                raise IncidentError(404, "Incident not found")
            record = db.execute(
                "SELECT * FROM incident_priority WHERE incident_id=?", (identity,)
            ).fetchone()
            if not record:
                raise IncidentError(
                    503, "Priority migration is required; original incident is preserved"
                )
            rows = db.execute(
                "SELECT c.*,u.role AS reporter_role,u.is_active AS reporter_active,"
                "u.is_verified AS reporter_verified FROM complaints c LEFT JOIN users u "
                "ON u.id=c.citizen_id WHERE c.incident_id=? "
                "ORDER BY c.created_at,c.complaint_id LIMIT 31",
                (identity,),
            ).fetchall()
            if len(rows) > 30:
                raise IncidentError(409, "Priority input exceeds bounded incident membership")
            members = [
                Member(
                    self.incidents.complaints.hydrate(db, row),
                    bool(
                        row["reporter_role"] == "CITIZEN"
                        and row["reporter_active"]
                        and row["reporter_verified"]
                        and row["status"] != "REJECTED"
                    ),
                )
                for row in rows
            ]
            return PrioritySnapshot(incident_row(incident), decode_record(record), members)

    def operation(self, identity, fingerprint):
        return self.incidents.operation(identity, fingerprint)

    def commit(self, plan):
        for attempt in range(3):
            try:
                return self._commit(plan)
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 2:
                    raise IncidentError(
                        503, "Priority storage unavailable; retry the same operation"
                    ) from error
                time.sleep(0.05 * (attempt + 1))
            except sqlite3.IntegrityError as error:
                raise IncidentError(
                    409, "Priority transaction conflicted; refresh before retry"
                ) from error

    def _commit(self, plan):
        snapshot, result = plan.snapshot, plan.result
        identity, previous = snapshot.incident.incidentId, snapshot.record
        with self.store.connection() as db:
            db.execute("PRAGMA busy_timeout=250")
            db.execute("BEGIN IMMEDIATE")
            if plan.operation_id:
                op = db.execute(
                    "SELECT fingerprint,result FROM incident_operations WHERE operation_id=?",
                    (plan.operation_id,),
                ).fetchone()
                if op:
                    if op[0] != plan.request_fingerprint:
                        raise IncidentError(409, "Operation ID already used with different input")
                    return json.loads(op[1])
            version = db.execute(
                "SELECT version FROM incidents WHERE incident_id=?", (identity,)
            ).fetchone()
            row = db.execute(
                "SELECT * FROM incident_priority WHERE incident_id=?", (identity,)
            ).fetchone()
            if (
                not row
                or not version
                or version[0] != snapshot.incident.version
                or row["generation"] != previous["generation"]
                or row["controls_version"] != previous["controls_version"]
                or row["result_revision"] != previous["result_revision"]
                or (plan.lease_token and row["lease_token"] != plan.lease_token)
            ):
                raise IncidentError(409, "Incident or priority changed; refresh and confirm again")
            # Account/status triggers invalidate generation inside the same SQLite transaction.
            # Membership writes already increment the canonical incident version atomically.
            revision = row["controls_version"] + int(plan.kind != "RECALCULATE")
            response = write_response(plan, revision)
            if plan.operation_id:
                db.execute(
                    "INSERT INTO incident_operations VALUES(?,?,?,?,?,?,?)",
                    (
                        plan.operation_id,
                        plan.request_fingerprint,
                        "PRIORITY_" + plan.kind,
                        plan.actor.id,
                        plan.reason,
                        json.dumps(response, allow_nan=False),
                        result["calculatedAt"],
                    ),
                )
            if row["fingerprint"] != plan.fingerprint or plan.kind != "RECALCULATE":
                db.execute(
                    "INSERT INTO priority_history VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identity,
                        plan.operation_id,
                        plan.kind,
                        plan.actor.id,
                        plan.reason,
                        plan.fingerprint,
                        json.dumps(history_payload(plan), allow_nan=False),
                        result["calculatedAt"],
                    ),
                )
            db.execute(
                "UPDATE incident_priority SET controls=?,controls_version=?,"
                "result_revision=result_revision+1,needs_recalculation=0,"
                "source_version=?,config_version=?,result=?,fingerprint=?,calculated_score=?,"
                "effective_score=?,priority_band=?,assessment_status=?,severity=?,public_impact=?,"
                "urgent_hazard=?,override_status=?,unresolved_seconds=?,calculated_at=?,next_due=?,"
                "lease_token=NULL,available_at=0,error_category=NULL WHERE incident_id=?",
                (
                    json.dumps(plan.controls, allow_nan=False),
                    revision,
                    snapshot.incident.version,
                    result["algorithmVersion"],
                    json.dumps(result, allow_nan=False),
                    plan.fingerprint,
                    result["calculatedScore"],
                    result["effectiveScore"],
                    result["priorityBand"],
                    result["assessmentStatus"],
                    result["factors"]["severity"]["normalizedValue"],
                    result["factors"]["publicImpact"]["normalizedValue"],
                    int(result["urgentHazard"]),
                    result["overrideStatus"],
                    result["unresolvedSeconds"],
                    result["calculatedAt"],
                    plan.next_due,
                    identity,
                ),
            )
            return response

    def claim(self, now, config_version):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT p.incident_id FROM incident_priority p JOIN incidents i USING(incident_id) "
                "WHERE (p.needs_recalculation=1 OR p.config_version<>? OR "
                "(p.next_due<=? AND i.status IN ('OPEN','RESOLVED'))) AND p.available_at<=? "
                "ORDER BY p.available_at,p.incident_id LIMIT 1",
                (config_version, now, now),
            ).fetchone()
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                "UPDATE incident_priority SET lease_token=?,available_at=?,attempts=attempts+1 "
                "WHERE incident_id=?",
                (token, now + 60, row[0]),
            )
            return row[0], token

    def fail(self, identity, token, now, error):
        with self.store.connection() as db:
            db.execute(
                "UPDATE incident_priority SET needs_recalculation=1,"
                "available_at=?,error_category=? "
                "WHERE incident_id=? AND lease_token=?",
                (now + 60, error, identity, token),
            )

    def batch(self, after, limit):
        with self.store.connection() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT incident_id FROM incidents WHERE incident_id>? "
                    "AND status IN ('OPEN','RESOLVED') "
                    "ORDER BY incident_id LIMIT ?",
                    (after, limit),
                )
            ]

    def history(self, identity, limit, after):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM priority_history WHERE incident_id=? "
                + ("AND (created_at,event_id)>(?,?) " if after else "")
                + "ORDER BY created_at,event_id LIMIT ?",
                (identity, *(after or []), limit + 1),
            ).fetchall()
        items = [
            {
                "eventId": r["event_id"],
                "operationId": r["operation_id"],
                "kind": r["kind"],
                "actorId": r["actor_id"],
                "reason": r["reason"],
                "createdAt": r["created_at"],
                "snapshot": json.loads(r["snapshot"]),
            }
            for r in rows[:limit]
        ]
        return items, [items[-1]["createdAt"], items[-1]["eventId"]] if len(rows) > limit else None

    @staticmethod
    def fresh_where():
        return (
            "p.needs_recalculation=0 AND p.source_version=i.version "
            "AND p.config_version=? AND p.next_due>?"
        )

    def queue(self, filters, limit, after, revision, now, config_version, valid_until=None):
        with self.store.connection() as db:
            db.execute("BEGIN")
            current = db.execute(
                "SELECT queue_revision FROM priority_meta WHERE singleton=1"
            ).fetchone()[0]
            if revision is not None and revision != current:
                raise IncidentError(409, "Priority queue changed; restart from its first page")
            if valid_until is None:
                due = db.execute(
                    "SELECT min(next_due) FROM incident_priority WHERE next_due>?", (now,)
                ).fetchone()[0]
                valid_until = min(now + 60, due or now + 60)
            if now >= valid_until:
                raise IncidentError(409, "Priority page expired; refresh the first page")
            where, args = (
                [self.fresh_where(), "i.status=?"],
                [config_version, now, filters.get("status", "OPEN")],
            )
            for field, column in {
                "band": "p.priority_band",
                "category": "i.category",
                "assessmentStatus": "p.assessment_status",
                "overrideStatus": "p.override_status",
            }.items():
                if filters.get(field):
                    where.append(f"{column}=?")
                    args.append(filters[field])
            if filters.get("q"):
                where.append("instr(search_normalize(i.canonical_title),search_normalize(?))>0")
                args.append(filters["q"])
            if filters.get("urgent") is not None:
                where.append("p.urgent_hazard=?")
                args.append(int(filters["urgent"]))
            for field, column, operator in (
                ("minSeverity", "p.severity", ">="),
                ("maxSeverity", "p.severity", "<="),
                ("minImpact", "p.public_impact", ">="),
                ("maxImpact", "p.public_impact", "<="),
                ("minDays", "p.unresolved_seconds/86400.0", ">="),
                ("maxDays", "p.unresolved_seconds/86400.0", "<="),
            ):
                if filters.get(field) is not None:
                    where.append(f"{column}{operator}?")
                    args.append(filters[field])
            oldest = filters.get("sort") == "oldest"
            order = (
                "-p.urgent_hazard,i.first_reported_at,p.incident_id"
                if oldest
                else ("-p.urgent_hazard,-p.effective_score,-p.unresolved_seconds,p.incident_id")
            )
            if after:
                where.append(f"({order})>({','.join('?' for _ in after)})")
                args.extend(after)
            if oldest:
                order = "p.urgent_hazard DESC,i.first_reported_at,p.incident_id"
            else:
                order = (
                    "p.urgent_hazard DESC,p.effective_score DESC,"
                    "p.unresolved_seconds DESC,p.incident_id"
                )
            rows = db.execute(
                "SELECT i.*,p.result,p.urgent_hazard,p.effective_score,p.unresolved_seconds "
                "FROM incident_priority p JOIN incidents i USING(incident_id) WHERE "
                + " AND ".join(where)
                + f" ORDER BY {order} LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
            items = [
                {
                    "incident": incident_row(row).model_dump(mode="json"),
                    "priority": json.loads(row["result"]),
                }
                for row in rows[:limit]
            ]
            last = rows[limit - 1] if len(rows) > limit else None
            key = (
                (
                    [-last["urgent_hazard"], last["first_reported_at"], last["incident_id"]]
                    if oldest
                    else [
                        -last["urgent_hazard"],
                        -last["effective_score"],
                        -last["unresolved_seconds"],
                        last["incident_id"],
                    ]
                )
                if last
                else None
            )
            return items, key, current, valid_until

    def summary(self, now, config_version):
        with self.store.connection() as db:
            db.execute("BEGIN")
            active = db.execute("SELECT count(*) FROM incidents WHERE status='OPEN'").fetchone()[0]
            needs_assessment = db.execute(
                "SELECT count(*) FROM incident_priority p JOIN incidents i USING(incident_id) "
                "WHERE i.status='OPEN' AND ("
                "coalesce(json_extract(p.controls,'$.severity.status'),'UNASSESSED')"
                "<>'VERIFIED' OR "
                "coalesce(json_extract(p.controls,'$.severity.epoch'),-1)<>p.membership_epoch OR "
                "coalesce(json_extract(p.controls,'$.publicImpact.status'),'UNASSESSED')"
                "<>'VERIFIED' OR "
                "coalesce(json_extract(p.controls,'$.publicImpact.epoch'),-1)"
                "<>p.membership_epoch OR "
                "(p.assessment_status='NEEDS_REVIEW' AND p.source_version=i.version))"
            ).fetchone()[0]
            rows = db.execute(
                "SELECT p.priority_band,p.assessment_status,p.urgent_hazard,"
                "p.override_status,count(*) "
                "FROM incident_priority p JOIN incidents i USING(incident_id) "
                "WHERE i.status='OPEN' AND " + self.fresh_where() + " GROUP BY 1,2,3,4",
                (config_version, now),
            ).fetchall()
        counts = {
            band: sum(r[4] for r in rows if r[0] == band)
            for band in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        }
        return {
            "activeIncidents": active,
            "scoredIncidents": sum(counts.values()),
            "pendingOrStale": active - sum(counts.values()),
            "bands": counts,
            "needsAssessment": needs_assessment,
            "urgentHazards": sum(r[4] for r in rows if r[2]),
            "overridden": sum(r[4] for r in rows if r[3] == "ACTIVE"),
        }
