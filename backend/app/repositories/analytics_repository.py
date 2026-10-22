import json
from datetime import UTC, datetime
from uuid import uuid4

from app.models.incident import IncidentError


class SQLiteAnalytics:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    @staticmethod
    def rows(db, sql, cap):
        values = [dict(r) for r in db.execute(sql + " LIMIT ?", (cap + 1,))]
        if len(values) > cap:
            raise IncidentError(
                413, "Analytics source bound exceeded; controlled partitioning required"
            )
        return values

    def snapshot(self):
        with self.store.connection() as db:
            db.execute("BEGIN")
            meta = dict(db.execute("SELECT * FROM analytics_meta WHERE singleton=1").fetchone())
            incidents = self.rows(
                db,
                """SELECT i.incident_id,i.category,i.latitude,i.longitude,
                i.status,i.first_reported_at,i.created_at,i.updated_at,i.resolved_at,i.version,
                p.needs_recalculation,p.source_version,p.config_version,p.next_due,p.priority_band,
                p.calculated_score,p.effective_score,p.urgent_hazard,p.assessment_status,
                (p.result IS NOT NULL) AS has_priority_result,
                p.override_status,p.calculated_at,p.unresolved_seconds,a.department_id,a.officer_id,
                a.status AS assignment_status,a.percentage,a.assigned_at,s.cycle,s.opened_at
                FROM incidents i LEFT JOIN incident_priority p USING(incident_id)
                LEFT JOIN incident_assignments a USING(incident_id)
                LEFT JOIN sla_checks s USING(incident_id)
                WHERE i.status IN('OPEN','RESOLVED') ORDER BY i.incident_id""",
                self.settings.analytics_max_incidents,
            )
            complaints = self.rows(
                db,
                """SELECT c.complaint_id,c.citizen_id,c.incident_id,c.category,
                c.reported_severity,c.latitude,c.longitude,c.created_at FROM complaints c
                JOIN users u ON u.id=c.citizen_id WHERE u.role='CITIZEN' AND u.is_active=1
                AND u.is_verified=1 AND c.status<>'REJECTED' ORDER BY c.complaint_id""",
                self.settings.analytics_max_complaints,
            )
            data = {"meta": meta, "incidents": incidents, "complaints": complaints}
            for name, sql, cap in (
                ("departments", "SELECT id,code,name,active FROM departments ORDER BY id", 100),
                (
                    "officers",
                    """SELECT m.officer_id,m.department_id,m.active,m.availability,
                 m.capacity,u.display_name,u.role,u.is_active,u.is_verified
                 FROM officer_memberships m
                 JOIN users u ON u.id=m.officer_id ORDER BY m.officer_id,m.department_id""",
                    1000,
                ),
                (
                    "history",
                    "SELECT event_id,entity_id,actor_id,kind,created_at,"
                    "json_object('departmentId',json_extract(after_state,'$.departmentId'),"
                    "'officerId',json_extract(after_state,'$.officerId'),"
                    "'status',json_extract(after_state,'$.status'),"
                    "'assignedAt',json_extract(after_state,'$.assignedAt'),"
                    "'percentage',json_extract(after_state,'$.percentage')) AS after_state "
                    "FROM work_history "
                    "ORDER BY created_at,event_id",
                    50000,
                ),
                (
                    "audit",
                    """SELECT event_id,incident_id,operation,created_at,
                 json_extract(payload,'$.before.status') AS previous_status,
                 json_extract(payload,'$.after.status') AS next_status,
                 json_extract(payload,'$.after.resolvedAt') AS resolved_at
                 FROM incident_audit ORDER BY created_at,event_id""",
                    50000,
                ),
                (
                    "escalations",
                    "SELECT incident_id,cycle,milestone,status,created_at,deadline "
                    "FROM escalations ORDER BY created_at,escalation_id",
                    20000,
                ),
                ("policies", "SELECT * FROM sla_policies ORDER BY policy_id", 100),
                (
                    "membershipHistory",
                    "SELECT membership_event_id,complaint_id,operation,"
                    "created_at FROM incident_membership_events WHERE previous_incident_id IS NULL "
                    "ORDER BY created_at,membership_event_id",
                    20000,
                ),
                (
                    "priorityHistory",
                    "SELECT event_id,incident_id,kind,created_at,"
                    "json_extract(snapshot,'$.after.priorityBand') AS band FROM priority_history "
                    "ORDER BY created_at,event_id",
                    50000,
                ),
            ):
                data[name] = self.rows(db, sql, cap)
            return data

    def observe(self, event):
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            inserted = db.execute(
                "INSERT OR IGNORE INTO analytics_receipts VALUES(?,?,?)",
                (str(event.eventId), event.occurredAt.isoformat(), now),
            ).rowcount
            if inserted:
                db.execute(
                    "UPDATE analytics_meta SET observed_at=?,observed_event_at="
                    "CASE WHEN observed_event_at IS NULL OR julianday(?)>"
                    "julianday(observed_event_at) THEN ? ELSE observed_event_at END "
                    "WHERE singleton=1",
                    (now, event.occurredAt.isoformat(), event.occurredAt.isoformat()),
                )
            return bool(inserted)

    def save_snapshot(self, identity, revision, body, now):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute("SELECT revision FROM analytics_meta WHERE singleton=1").fetchone()[0]
                != revision
            ):
                raise IncidentError(409, "Sources changed during analytics rebuild; retry")
            db.execute(
                "INSERT INTO analytics_snapshots VALUES(?,?,1,?,?) ON CONFLICT(identity) "
                "DO UPDATE SET source_revision=excluded.source_revision,version=1,"
                "calculated_at=excluded.calculated_at,body=excluded.body",
                (identity, revision, now, json.dumps(body, sort_keys=True, allow_nan=False)),
            )

    def projection(self, identity):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM analytics_snapshots WHERE identity=?", (identity,)
            ).fetchone()
            return dict(row) if row else None

    def audit_export(self, actor, report, filters, count, now):
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO analytics_export_audit VALUES(?,?,?,?,?,?)",
                (str(uuid4()), actor, report, json.dumps(filters, sort_keys=True), count, now),
            )
