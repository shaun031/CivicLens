import json
import sqlite3
import time
from dataclasses import asdict

from app.models.incident import Incident, IncidentError, IncidentPlan, Member, stable_id
from app.repositories.duplicate_candidate_repository import timestamp

FIELDS = (
    ("incidentId", "incident_id"),
    ("canonicalTitle", "canonical_title"),
    ("canonicalDescription", "canonical_description"),
    ("category", "category"),
    ("latitude", "latitude"),
    ("longitude", "longitude"),
    ("status", "status"),
    ("representativeComplaintId", "representative_complaint_id"),
    ("totalComplaintCount", "total_complaint_count"),
    ("uniqueReporterCount", "unique_reporter_count"),
    ("firstReportedAt", "first_reported_at"),
    ("lastReportedAt", "last_reported_at"),
    ("createdAt", "created_at"),
    ("updatedAt", "updated_at"),
    ("resolvedAt", "resolved_at"),
    ("mergedIntoIncidentId", "merged_into_incident_id"),
    ("version", "version"),
)


def incident_row(row) -> Incident:
    return Incident.model_validate({key: row[column] for key, column in FIELDS})


class SQLiteIncidents:
    """complaints.incident_id is the ONLY active-membership source of truth."""

    def __init__(self, complaints):
        self.complaints, self.store = complaints, complaints.store

    def load(self, identity: str) -> Incident | None:
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM incidents WHERE incident_id=?", (identity,)).fetchone()
            return incident_row(row) if row else None

    def member(self, complaint_id: str) -> Member | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM complaints WHERE complaint_id=?", (complaint_id,)
            ).fetchone()
            if row is None:
                return None
            user = db.execute(
                "SELECT role,is_active,is_verified FROM users WHERE id=?", (row["citizen_id"],)
            ).fetchone()
            eligible = bool(
                user
                and user[0] == "CITIZEN"
                and user[1]
                and user[2]
                and row["status"] != "REJECTED"
            )
            return Member(self.complaints.hydrate(db, row), eligible)

    def members(self, incident_id: str, limit: int = 30) -> list[Member]:
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT complaint_id FROM complaints WHERE incident_id=? "
                "ORDER BY created_at,complaint_id LIMIT ?",
                (incident_id, limit + 1),
            ).fetchall()
        if len(rows) > limit:
            raise IncidentError(
                409, "Incident exceeds the bounded operation size; controlled review required"
            )
        return [self.member(row[0]) for row in rows]

    def operation(self, identity: str, fingerprint: str) -> dict | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT fingerprint,result FROM incident_operations WHERE operation_id=?",
                (identity,),
            ).fetchone()
        if row and row[0] != fingerprint:
            raise IncidentError(409, "Operation ID was already used with different input")
        return json.loads(row[1]) if row else None

    def commit(self, plan: IncidentPlan) -> dict:
        for attempt in range(3):
            try:
                return self._commit(plan)
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 2:
                    raise IncidentError(
                        503, "Incident storage unavailable; retry the same operation ID"
                    ) from error
                time.sleep(0.05 * (attempt + 1))
            except sqlite3.IntegrityError as error:
                raise IncidentError(
                    409, "Incident membership changed or a constraint rejected the operation"
                ) from error
        raise AssertionError("Unreachable bounded retry")

    def _commit(self, plan: IncidentPlan) -> dict:
        with self.store.connection() as db:
            db.execute("PRAGMA busy_timeout=250")
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT fingerprint,result FROM incident_operations WHERE operation_id=?",
                (plan.operation_id,),
            ).fetchone()
            if existing:
                if existing[0] != plan.fingerprint:
                    raise IncidentError(409, "Operation ID was already used with different input")
                return json.loads(existing[1])
            if plan.operation == "AUTOMATIC_LINK":
                ids = [member.complaint.complaintId for member in plan.observed]
                placeholders = ",".join("?" for _ in ids)
                dismissed = db.execute(
                    "SELECT 1 FROM duplicate_candidates WHERE review_status='DISMISSED' "
                    f"AND source_id IN ({placeholders}) "
                    f"AND duplicate_id IN ({placeholders}) LIMIT 1",
                    (*ids, *ids),
                ).fetchone()
                if dismissed:
                    raise IncidentError(
                        409, "A member pair was dismissed during automatic validation"
                    )
            for identity, previous in plan.before.items():
                row = db.execute(
                    "SELECT version FROM incidents WHERE incident_id=?", (identity,)
                ).fetchone()
                if (previous is None and row) or (
                    previous and (not row or row[0] != previous.version)
                ):
                    raise IncidentError(409, "Incident version changed; refresh before retrying")
            for member in plan.observed:
                row = db.execute(
                    "SELECT incident_id,status FROM complaints WHERE complaint_id=?",
                    (member.complaint.complaintId,),
                ).fetchone()
                if (
                    not row
                    or row[0] != member.complaint.incidentId
                    or row[1] != member.complaint.status
                ):
                    raise IncidentError(409, "Complaint membership or eligibility changed")
                user = db.execute(
                    "SELECT role,is_active,is_verified FROM users WHERE id=?",
                    (member.complaint.citizenId,),
                ).fetchone()
                eligible = bool(
                    user and user[0] == "CITIZEN" and user[1] and user[2] and row[1] != "REJECTED"
                )
                if eligible != member.eligible_reporter:
                    raise IncidentError(409, "Reporter eligibility changed; refresh the incident")
            columns = ",".join(column for _, column in FIELDS)
            marks = ",".join("?" for _ in FIELDS)
            updates = ",".join(f"{column}=excluded.{column}" for _, column in FIELDS[1:])
            for incident in plan.after.values():
                data = incident.model_dump(mode="json")
                db.execute(
                    f"INSERT INTO incidents({columns}) VALUES({marks}) "
                    f"ON CONFLICT(incident_id) DO UPDATE SET {updates}",
                    tuple(data[key] for key, _ in FIELDS),
                )
            for change in plan.changes:
                cursor = db.execute(
                    "UPDATE complaints SET incident_id=? WHERE complaint_id=? AND incident_id IS ?",
                    (change.new_incident_id, change.complaint_id, change.previous_incident_id),
                )
                if cursor.rowcount != 1:
                    raise IncidentError(409, "Complaint is no longer in its expected incident")
            # Summaries come from authoritative membership and currently eligible local users.
            for identity, incident in plan.after.items():
                total = db.execute(
                    "SELECT count(*) FROM complaints WHERE incident_id=?", (identity,)
                ).fetchone()[0]
                reporters = db.execute(
                    "SELECT count(DISTINCT c.citizen_id) FROM complaints c JOIN users u "
                    "ON u.id=c.citizen_id WHERE c.incident_id=? AND c.status<>'REJECTED' "
                    "AND u.role='CITIZEN' AND u.is_active=1 AND u.is_verified=1",
                    (identity,),
                ).fetchone()[0]
                if total != incident.totalComplaintCount:
                    raise IncidentError(
                        409, "Membership snapshot is incomplete; reconcile before changing it"
                    )
                db.execute(
                    "UPDATE incidents SET total_complaint_count=?,unique_reporter_count=? "
                    "WHERE incident_id=?",
                    (total, reporters, identity),
                )
            result = incident_row(
                db.execute(
                    "SELECT * FROM incidents WHERE incident_id=?", (plan.result_incident_id,)
                ).fetchone()
            ).model_dump(mode="json")
            db.execute(
                "INSERT INTO incident_operations VALUES(?,?,?,?,?,?,?)",
                (
                    plan.operation_id,
                    plan.fingerprint,
                    plan.operation,
                    plan.actor.id,
                    plan.reason,
                    json.dumps(result),
                    plan.created_at,
                ),
            )
            changes = [asdict(change) for change in plan.changes]
            for change in plan.changes:
                candidate = change.evidence.get("candidateId")
                db.execute(
                    "INSERT INTO incident_membership_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        stable_id(f"event/{plan.operation_id}/{change.complaint_id}"),
                        plan.operation_id,
                        change.complaint_id,
                        change.previous_incident_id,
                        change.new_incident_id,
                        plan.operation,
                        plan.reason,
                        plan.actor.id,
                        plan.actor.type,
                        candidate,
                        json.dumps(change.evidence),
                        plan.created_at,
                    ),
                )
            for identity, incident in plan.after.items():
                payload = {
                    "before": plan.before[identity].model_dump(mode="json")
                    if plan.before[identity]
                    else None,
                    "after": incident.model_dump(mode="json"),
                    "changes": changes,
                }
                db.execute(
                    "INSERT INTO incident_audit VALUES(?,?,?,?,?,?,?,?)",
                    (
                        stable_id(f"audit/{plan.operation_id}/{identity}"),
                        identity,
                        plan.operation_id,
                        plan.operation,
                        plan.actor.id,
                        plan.reason,
                        plan.created_at,
                        json.dumps(payload),
                    ),
                )
            if plan.operation == "RECHECK":
                for member in plan.observed:
                    db.execute(
                        "UPDATE matching_jobs SET state='PENDING',available_at=0 "
                        "WHERE source_id=? AND state<>'RUNNING'",
                        (member.complaint.complaintId,),
                    )
                    db.execute(
                        "INSERT INTO clustering_jobs(source_id,state,updated_at) "
                        "VALUES(?,'PENDING',?) ON CONFLICT(source_id) DO UPDATE SET "
                        "rerun_requested=CASE WHEN clustering_jobs.state='RUNNING' "
                        "THEN 1 ELSE 0 END,"
                        "state=CASE WHEN clustering_jobs.state='RUNNING' "
                        "THEN 'RUNNING' ELSE 'PENDING' END,"
                        "available_at=CASE WHEN clustering_jobs.state='RUNNING' "
                        "THEN clustering_jobs.available_at ELSE 0 END,"
                        "updated_at=excluded.updated_at",
                        (member.complaint.complaintId, plan.created_at),
                    )
            return result

    def catalog(self, filters: dict, limit: int, after: list | None):
        where, args = ["1=1"], []
        for key, column in (("status", "status"), ("category", "category")):
            if filters.get(key):
                where.append(f"{column}=?")
                args.append(filters[key])
        if filters.get("q"):
            where.append("instr(search_normalize(canonical_title),search_normalize(?))>0")
            args.append(filters["q"])
        descending = filters.get("sort", "newest") == "newest"
        if after:
            sign = "<" if descending else ">"
            where.append(f"(created_at,incident_id){sign}(?,?)")
            args.extend(after)
        order = "DESC" if descending else "ASC"
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM incidents WHERE "
                + " AND ".join(where)
                + f" ORDER BY created_at {order},incident_id {order} LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
        items = [incident_row(row).model_dump(mode="json") for row in rows[:limit]]
        for row in items:
            row["reviewNeeded"] = self.review_needed(row["incidentId"])
        return items, (
            [items[-1]["createdAt"], items[-1]["incidentId"]] if len(rows) > limit else None
        )

    def review_needed(self, identity: str) -> bool:
        with self.store.connection() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM duplicate_candidates d "
                    "JOIN complaints a ON a.complaint_id=d.source_id "
                    "JOIN complaints b ON b.complaint_id=d.duplicate_id "
                    "WHERE (a.incident_id=? OR b.incident_id=?) "
                    "AND a.incident_id IS NOT b.incident_id AND d.review_status<>'DISMISSED' "
                    "AND d.classification IN ('STRONG_CANDIDATE','REVIEW_REQUIRED') LIMIT 1",
                    (identity, identity),
                ).fetchone()
            )

    def history(self, identity: str, limit: int, after: list | None):
        where = " AND (created_at,event_id)>(?,?)" if after else ""
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM incident_audit WHERE incident_id=?"
                + where
                + " ORDER BY created_at,event_id LIMIT ?",
                (identity, *(after or []), limit + 1),
            ).fetchall()
        items = [
            {
                "eventId": row["event_id"],
                "operationId": row["operation_id"],
                "operation": row["operation"],
                "actorId": row["actor_id"],
                "reason": row["reason"],
                "createdAt": row["created_at"],
                "evidence": json.loads(row["payload"]),
            }
            for row in rows[:limit]
        ]
        return items, [items[-1]["createdAt"], items[-1]["eventId"]] if len(rows) > limit else None

    def summary(self):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT count(*),coalesce(sum(total_complaint_count=1),0),"
                "coalesce(sum(total_complaint_count>1),0),coalesce(sum(total_complaint_count),0) "
                "FROM incidents WHERE status='OPEN'"
            ).fetchone()
            kinds = dict(
                db.execute("SELECT operation,count(*) FROM incident_operations GROUP BY operation")
            )
            merged = db.execute("SELECT count(*) FROM incidents WHERE status='MERGED'").fetchone()[
                0
            ]
            pending = db.execute(
                "SELECT count(*) FROM duplicate_candidates d JOIN complaints a "
                "ON a.complaint_id=d.source_id JOIN complaints b ON b.complaint_id=d.duplicate_id "
                "WHERE a.incident_id IS NOT b.incident_id AND d.review_status<>'DISMISSED' "
                "AND d.classification IN ('STRONG_CANDIDATE','REVIEW_REQUIRED')"
            ).fetchone()[0]
        return {
            "activeIncidents": row[0],
            "singleReportIncidents": row[1],
            "multiReportIncidents": row[2],
            "linkedComplaints": row[3],
            "pendingClusteringReviews": pending,
            "splitOperations": kinds.get("SPLIT", 0),
            "correctionOperations": sum(
                kinds.get(key, 0) for key in ("UNLINK", "CORRECTION", "SPLIT")
            ),
            "mergedIncidentRecords": merged,
        }

    def enqueue(self, source: str):
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO clustering_jobs(source_id,state,updated_at) VALUES(?,'PENDING',?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "rerun_requested=CASE WHEN clustering_jobs.state='RUNNING' THEN 1 ELSE 0 END,"
                "state=CASE WHEN clustering_jobs.state='RUNNING' THEN 'RUNNING' ELSE 'PENDING' END,"
                "available_at=CASE WHEN clustering_jobs.state='RUNNING' "
                "THEN clustering_jobs.available_at ELSE 0 END,updated_at=excluded.updated_at",
                (source, timestamp()),
            )

    def claim(self, source: str | None = None):
        from uuid import uuid4

        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT source_id FROM clustering_jobs WHERE "
                "state IN ('PENDING','RETRY','RUNNING') AND available_at<=? "
                "AND (? IS NULL OR source_id=?) ORDER BY available_at,source_id LIMIT 1",
                (time.time(), source, source),
            ).fetchone()
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                "UPDATE clustering_jobs SET state='RUNNING',lease_token=?,available_at=?,"
                "attempts=attempts+1,rerun_requested=0,updated_at=? WHERE source_id=?",
                (token, time.time() + 120, timestamp(), row[0]),
            )
            return row[0], token

    def finish_job(self, source: str, token: str, report: dict):
        with self.store.connection() as db:
            db.execute(
                "UPDATE clustering_jobs SET state=CASE WHEN rerun_requested=1 THEN 'PENDING' "
                "ELSE 'COMPLETE' END,available_at=0,error_category=NULL,report=?,updated_at=? "
                "WHERE source_id=? AND state='RUNNING' AND lease_token=?",
                (json.dumps(report), timestamp(), source, token),
            )

    def fail_job(self, source: str, token: str, error: str):
        with self.store.connection() as db:
            db.execute(
                "UPDATE clustering_jobs SET state='RETRY',available_at=?,error_category=?,"
                "updated_at=? WHERE source_id=? AND state='RUNNING' AND lease_token=?",
                (time.time() + 60, error, timestamp(), source, token),
            )

    def job(self, source: str):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT state,attempts,report,error_category,updated_at "
                "FROM clustering_jobs WHERE source_id=?",
                (source,),
            ).fetchone()
        return (
            {
                "state": row[0],
                "attempts": row[1],
                "report": json.loads(row[2]) if row[2] else None,
                "errorCategory": row[3],
                "updatedAt": row[4],
            }
            if row
            else None
        )

    def source_ids(self, after: str, limit: int):
        with self.store.connection() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT complaint_id FROM complaints "
                    "WHERE complaint_id>? ORDER BY complaint_id LIMIT ?",
                    (after, limit),
                )
            ]

    def candidates(self, source: str, limit: int):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT candidate_id FROM duplicate_candidates WHERE "
                "(source_id=? OR duplicate_id=?) AND review_status<>'DISMISSED' "
                "AND classification IN ('STRONG_CANDIDATE','REVIEW_REQUIRED') "
                "ORDER BY combined_score DESC,candidate_id LIMIT ?",
                (source, source, limit + 1),
            ).fetchall()
        return [row[0] for row in rows[:limit]], len(rows) > limit
