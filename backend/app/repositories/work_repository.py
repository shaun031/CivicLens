"""SQLite work unit of work: eligibility and capacity are checked inside the write lock."""

import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.algorithms.department_assignment.officer_allocator import (
    rebalance_analysis,
    recommend,
    validate_weights,
)
from app.algorithms.department_assignment.routing_engine import covered, route
from app.models.incident import IncidentError, stable_id

DEFAULTS = {
    "ROAD_MAINTENANCE": ("Road Maintenance", ["POTHOLE", "DAMAGED_ROAD"]),
    "ELECTRICAL_MAINTENANCE": ("Electrical Maintenance", ["BROKEN_STREETLIGHT"]),
    "SANITATION": ("Sanitation", ["GARBAGE"]),
    "DRAINAGE_MAINTENANCE": ("Drainage Maintenance", ["DRAINAGE"]),
    "PUBLIC_WORKS": ("Public Works", ["PUBLIC_PROPERTY_DAMAGE"]),
    "GENERAL_REVIEW": ("General Review", ["OTHER"]),
}


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def utc_now():
    return datetime.now(UTC).isoformat()


def department(row):
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "description": row["description"],
        "active": bool(row["active"]),
        "areas": json.loads(row["areas"]),
        "version": row["version"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def assignment(row):
    return {
        "incidentId": row["incident_id"],
        "departmentId": row["department_id"],
        "officerId": row["officer_id"],
        "status": row["status"],
        "method": row["method"],
        "ruleVersion": row["rule_version"],
        "explanation": json.loads(row["explanation"]),
        "version": row["version"],
        "percentage": row["percentage"],
        "assignedAt": row["assigned_at"],
        "updatedAt": row["updated_at"],
    }


class SQLiteWork:
    def __init__(self, store, config_version, settings, clock=None):
        self.store, self.config_version, self.settings = store, config_version, settings
        self.weights = validate_weights(settings.workload_weights)
        self.clock = clock or (lambda: datetime.now(UTC))

    def require(self, db, table, key, value):
        # Identifiers here are fixed internal literals, never request strings.
        row = db.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        if row is None:
            raise IncidentError(404, "Work record not found")
        return row

    def audit(self, db, entity, kind, before, after, actor, reason, operation=None):
        db.execute(
            "INSERT INTO work_history VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                entity,
                operation,
                kind,
                actor.id,
                actor.type,
                reason,
                encode(before),
                encode(after),
                self.clock().isoformat(),
            ),
        )

    def atomic(self, kind, entity, data, actor, callback):
        if not data.get("confirmed"):
            raise IncidentError(422, "Explicit confirmation is required")
        fingerprint = hashlib.sha256(encode([kind, entity, data, actor.id]).encode()).hexdigest()
        identity = stable_id(f"work-operation/{actor.id}/{data['operationId']}")
        for attempt in range(3):
            try:
                with self.store.connection() as db:
                    db.execute("PRAGMA busy_timeout=250")
                    db.execute("BEGIN IMMEDIATE")
                    if actor.type == "OFFICER":
                        incident, record = self.state(db, entity)
                        self.authorize_officer(db, incident, record, actor.id)
                    receipt = db.execute(
                        "SELECT * FROM incident_operations WHERE operation_id=?", (identity,)
                    ).fetchone()
                    if receipt:
                        if receipt["fingerprint"] != fingerprint:
                            raise IncidentError(409, "Operation ID reused with different input")
                        return json.loads(receipt["result"])
                    # Receipt, state and audit commit together; failure rolls back this placeholder.
                    db.execute(
                        "INSERT INTO incident_operations VALUES(?,?,?,?,?,?,?)",
                        (
                            identity,
                            fingerprint,
                            f"WORK_{kind}",
                            actor.id,
                            data["reason"],
                            "{}",
                            self.clock().isoformat(),
                        ),
                    )
                    result = callback(db, identity)
                    db.execute(
                        "UPDATE incident_operations SET result=? WHERE operation_id=?",
                        (encode(result), identity),
                    )
                    db.execute("UPDATE work_meta SET revision=revision+1 WHERE singleton=1")
                    return result
            except sqlite3.IntegrityError as error:
                raise IncidentError(409, "Work configuration or assignment conflicts") from error
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 2:
                    raise IncidentError(
                        503, "Work storage unavailable; retry the same operation"
                    ) from error
                time.sleep(0.05 * (attempt + 1))

    @staticmethod
    def version(row, expected):
        if (row["version"] if row else 0) != expected:
            raise IncidentError(409, "Record changed; refresh before submitting a new operation")

    def seed(self, data, actor):
        def write(db, op):
            added = []
            for code, (name, categories) in DEFAULTS.items():
                row = db.execute("SELECT * FROM departments WHERE code=?", (code,)).fetchone()
                if row:
                    continue  # Never restore/overwrite administrator-edited defaults.
                identity, now = str(uuid4()), self.clock().isoformat()
                db.execute(
                    "INSERT INTO departments VALUES(?,?,?,?,1,'[]',1,?,?,?,?)",
                    (
                        identity,
                        code,
                        name,
                        "Editable fictional demonstration configuration",
                        now,
                        now,
                        actor.id,
                        actor.id,
                    ),
                )
                for category in categories:
                    db.execute(
                        "INSERT INTO routing_rules VALUES(?,?,?,100,1,1)",
                        (str(uuid4()), category, identity),
                    )
                added.append(code)
            self.audit(
                db,
                "configuration",
                "DEFAULTS_SEEDED",
                {},
                {"added": added},
                actor,
                data["reason"],
                op,
            )
            db.execute(
                "UPDATE incident_assignments SET route_pending=1,available_at=0 "
                "WHERE department_id IS NULL AND officer_id IS NULL"
            )
            return {"added": added}

        return self.atomic("SEED", "configuration", data, actor, write)

    def departments(self):
        with self.store.connection() as db:
            db.execute("BEGIN")
            rows = db.execute("SELECT * FROM departments ORDER BY code LIMIT 101").fetchall()
            if len(rows) > 100:
                raise IncidentError(409, "Department configuration exceeds prototype bound100")
            result = []
            for row in rows:
                counts = db.execute(
                    "WITH department_work AS(SELECT p.priority_band,CASE WHEN p.result IS NOT NULL "
                    "AND p.needs_recalculation=0 AND p.source_version=i.version "
                    "AND p.config_version=? AND p.next_due>? THEN 1 ELSE 0 END AS fresh "
                    "FROM incident_assignments a JOIN incidents i USING(incident_id) "
                    "LEFT JOIN incident_priority p USING(incident_id) "
                    "WHERE a.department_id=? AND i.status='OPEN') SELECT count(*),"
                    "sum(fresh=1 AND priority_band IN('HIGH','CRITICAL')),sum(fresh=0) "
                    "FROM department_work",
                    (self.config_version, self.clock().timestamp(), row["id"]),
                ).fetchone()
                officers = db.execute(
                    "SELECT count(*) FROM officer_memberships m JOIN users u "
                    "ON u.id=m.officer_id WHERE m.department_id=? AND m.active=1 "
                    "AND u.role='OFFICER' AND u.is_active=1 AND u.is_verified=1",
                    (row["id"],),
                ).fetchone()[0]
                result.append(
                    department(row)
                    | {
                        "activeIncidents": counts[0],
                        "highCriticalIncidents": counts[1] or 0,
                        "pendingPriorityIncidents": counts[2] or 0,
                        "officerCount": officers,
                    }
                )
            return {"items": result}

    def save_department(self, identity, data, actor):
        def write(db, op):
            previous = db.execute("SELECT * FROM departments WHERE id=?", (identity,)).fetchone()
            self.version(previous, data["expectedVersion"])
            if not previous and db.execute("SELECT count(*) FROM departments").fetchone()[0] >= 100:
                raise IncidentError(409, "At most100 configured departments are supported")
            before = department(previous) if previous else {}
            if (
                previous
                and ((not data["active"]) or before["areas"] != data["areas"])
                and db.execute(
                    "SELECT 1 FROM incident_assignments a JOIN incidents i USING(incident_id) "
                    "WHERE department_id=? AND i.status='OPEN' LIMIT 1",
                    (identity,),
                ).fetchone()
            ):
                raise IncidentError(
                    409, "Reassign active incidents before deactivation or boundary changes"
                )
            now = self.clock().isoformat()
            db.execute(
                "INSERT INTO departments VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET code=excluded.code,name=excluded.name,description=excluded.description,"
                "active=excluded.active,areas=excluded.areas,version=excluded.version,"
                "updated_at=excluded.updated_at,updated_by=excluded.updated_by",
                (
                    identity,
                    data["code"],
                    data["name"],
                    data["description"],
                    data["active"],
                    encode(data["areas"]),
                    data["expectedVersion"] + 1,
                    before.get("createdAt", now),
                    now,
                    actor.id,
                    actor.id,
                ),
            )
            after = department(self.require(db, "departments", "id", identity))
            self.audit(db, identity, "DEPARTMENT_UPDATED", before, after, actor, data["reason"], op)
            db.execute(
                "UPDATE incident_assignments SET route_pending=1,available_at=0 "
                "WHERE department_id IS NULL AND officer_id IS NULL"
            )
            return after

        return self.atomic("DEPARTMENT", identity, data, actor, write)

    def rules(self, db):
        rows = db.execute(
            "SELECT * FROM routing_rules ORDER BY category,department_id LIMIT 1001"
        ).fetchall()
        if len(rows) > 1000:
            raise IncidentError(409, "Routing configuration exceeds1000 rules")
        return [
            {
                "id": r["id"],
                "category": r["category"],
                "departmentId": r["department_id"],
                "precedence": r["precedence"],
                "active": bool(r["active"]),
                "version": r["version"],
            }
            for r in rows
        ]

    def list_rules(self):
        with self.store.connection() as db:
            return {"items": self.rules(db)}

    def remove_membership(self, dept, officer, data, actor):
        def write(db, op):
            row = db.execute(
                "SELECT * FROM officer_memberships WHERE department_id=? AND officer_id=?",
                (dept, officer),
            ).fetchone()
            if not row:
                raise IncidentError(404, "Membership not found")
            self.version(row, data["expectedVersion"])
            if db.execute(
                "SELECT 1 FROM incident_assignments a JOIN incidents i USING(incident_id) "
                "WHERE a.department_id=? AND a.officer_id=? AND i.status='OPEN' LIMIT 1",
                (dept, officer),
            ).fetchone():
                raise IncidentError(409, "Reassign active work before removing membership")
            db.execute(
                "UPDATE officer_memberships SET active=0,version=version+1,updated_at=?,"
                "assigned_by=? WHERE id=?",
                (self.clock().isoformat(), actor.id, row["id"]),
            )
            result = {
                "id": row["id"],
                "officerId": officer,
                "departmentId": dept,
                "version": row["version"] + 1,
                "active": False,
            }
            self.audit(db, dept, "MEMBERSHIP_REMOVED", dict(row), result, actor, data["reason"], op)
            return result

        return self.atomic("REMOVE_MEMBERSHIP", f"{dept}/{officer}", data, actor, write)

    def save_rule(self, data, actor):
        def write(db, op):
            self.require(db, "departments", "id", data["departmentId"])
            row = db.execute(
                "SELECT * FROM routing_rules WHERE category=? AND department_id=?",
                (data["category"], data["departmentId"]),
            ).fetchone()
            self.version(row, data["expectedVersion"])
            if not row and db.execute("SELECT count(*) FROM routing_rules").fetchone()[0] >= 1000:
                raise IncidentError(409, "Routing rule bound reached")
            identity = row["id"] if row else str(uuid4())
            before = dict(row) if row else {}
            db.execute(
                "INSERT INTO routing_rules VALUES(?,?,?,?,?,?) ON CONFLICT(category,department_id) "
                "DO UPDATE SET precedence=excluded.precedence,active=excluded.active,"
                "version=excluded.version",
                (
                    identity,
                    data["category"],
                    data["departmentId"],
                    data["precedence"],
                    data["active"],
                    data["expectedVersion"] + 1,
                ),
            )
            result = next(r for r in self.rules(db) if r["id"] == identity)
            self.audit(
                db,
                "configuration",
                "ROUTING_RULE_UPDATED",
                before,
                result,
                actor,
                data["reason"],
                op,
            )
            db.execute(
                "UPDATE incident_assignments SET route_pending=1,available_at=0 "
                "WHERE department_id IS NULL AND officer_id IS NULL"
            )
            return result

        return self.atomic("RULE", "configuration", data, actor, write)

    def officer_directory(self, after="", limit=50):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT id,display_name FROM users WHERE role='OFFICER' "
                "AND is_active=1 AND is_verified=1 AND id>? ORDER BY id LIMIT ?",
                (after, limit + 1),
            ).fetchall()
            return {
                "items": [
                    {"officerId": r["id"], "displayName": r["display_name"]} for r in rows[:limit]
                ],
                "nextAfter": rows[limit - 1]["id"] if len(rows) > limit else None,
            }

    def save_membership(self, dept, data, actor):
        def write(db, op):
            department_row = self.require(db, "departments", "id", dept)
            user = self.require(db, "users", "id", data["officerId"])
            if data["active"] and (
                not department_row["active"]
                or user["role"] != "OFFICER"
                or not user["is_active"]
                or not user["is_verified"]
            ):
                raise IncidentError(
                    422, "An active verified OFFICER and active department are required"
                )
            row = db.execute(
                "SELECT * FROM officer_memberships WHERE department_id=? AND officer_id=?",
                (dept, data["officerId"]),
            ).fetchone()
            self.version(row, data["expectedVersion"])
            before = dict(row) if row else {}
            # Availability/boundary/capacity changes cannot silently strand existing work.
            if (
                row
                and any(
                    (
                        before["active"] != int(data["active"]),
                        before["availability"] != data["availability"],
                        before["areas"] != encode(data["areas"]),
                        before["capacity"] != data["capacity"],
                    )
                )
                and db.execute(
                    "SELECT 1 FROM incident_assignments a JOIN incidents i USING(incident_id) "
                    "WHERE a.department_id=? AND a.officer_id=? AND i.status='OPEN' LIMIT 1",
                    (dept, data["officerId"]),
                ).fetchone()
            ):
                raise IncidentError(
                    409, "Reassign active work before changing membership constraints"
                )
            if (
                not row
                and db.execute(
                    "SELECT count(*) FROM officer_memberships WHERE department_id=?", (dept,)
                ).fetchone()[0]
                >= 500
            ):
                raise IncidentError(409, "Department membership bound500 reached")
            identity, now = row["id"] if row else str(uuid4()), self.clock().isoformat()
            db.execute(
                "INSERT INTO officer_memberships VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(officer_id,department_id) DO UPDATE SET active=excluded.active,"
                "availability=excluded.availability,capacity=excluded.capacity,areas=excluded.areas,"
                "version=excluded.version,updated_at=excluded.updated_at,assigned_by=excluded.assigned_by",
                (
                    identity,
                    data["officerId"],
                    dept,
                    data["active"],
                    data["availability"],
                    data["capacity"],
                    encode(data["areas"]),
                    data["expectedVersion"] + 1,
                    before.get("created_at", now),
                    now,
                    actor.id,
                ),
            )
            result = {
                "id": identity,
                "officerId": data["officerId"],
                "departmentId": dept,
                "version": data["expectedVersion"] + 1,
            }
            self.audit(
                db, dept, "MEMBERSHIP_UPDATED", before, data | result, actor, data["reason"], op
            )
            return result

        return self.atomic("MEMBERSHIP", dept, data, actor, write)

    def fresh(self, row, now):
        return bool(
            row["result"]
            and not row["needs_recalculation"]
            and row["config_version"] == self.config_version
            and row["source_version"] == row["incident_version"]
            and row["next_due"] > now
        )

    def units(self, row, now):
        # Unknown work is conservatively charged CRITICAL units, never silently zero.
        return (
            self.weights[row["priority_band"]] if self.fresh(row, now) else self.weights["CRITICAL"]
        )

    def workload(self, db, officer, exclude=None):
        # Indexed officer partition; bounded input, never a citywide incident load.
        rows = db.execute(
            "SELECT p.*,i.version AS incident_version FROM incident_assignments a "
            "JOIN incidents i USING(incident_id) JOIN incident_priority p USING(incident_id) "
            "WHERE a.officer_id=? AND i.status='OPEN' AND a.incident_id<>? LIMIT 2501",
            (officer, exclude or ""),
        ).fetchall()
        if len(rows) > 2500:
            raise IncidentError(
                409, "Officer workload exceeds bounded2500 records; manual reconciliation required"
            )
        now = self.clock().timestamp()
        return {
            "workload": sum(self.units(r, now) for r in rows),
            "activeIncidents": len(rows),
            "pendingPriorities": sum(not self.fresh(r, now) for r in rows),
        }

    def workload_read(self, officer):
        with self.store.connection() as db:
            db.execute("BEGIN")
            return self.workload(db, officer)

    def officers(self, db, dept, exclude=None):
        rows = db.execute(
            "SELECT m.*,u.display_name,u.role,u.is_active,u.is_verified "
            "FROM officer_memberships m JOIN users u ON u.id=m.officer_id "
            "WHERE m.department_id=? ORDER BY officer_id LIMIT 501",
            (dept,),
        ).fetchall()
        if len(rows) > 500:
            raise IncidentError(409, "Department exceeds bounded500 memberships")
        return [
            {
                "id": r["id"],
                "officerId": r["officer_id"],
                "displayName": r["display_name"],
                "departmentId": dept,
                "active": bool(r["active"]),
                "eligibleAccount": bool(
                    r["role"] == "OFFICER" and r["is_active"] and r["is_verified"]
                ),
                "availability": r["availability"],
                "capacity": r["capacity"],
                "areas": json.loads(r["areas"]),
                "version": r["version"],
                **self.workload(db, r["officer_id"], exclude),
            }
            for r in rows
        ]

    def state(self, db, identity):
        incident = self.require(db, "incidents", "incident_id", identity)
        record = self.require(db, "incident_assignments", "incident_id", identity)
        return incident, record

    def routing(self, db, incident):
        rows = db.execute("SELECT * FROM departments ORDER BY code LIMIT 101").fetchall()
        if len(rows) > 100:
            raise IncidentError(409, "Department bound100 exceeded")
        return route(
            incident["category"],
            incident["latitude"],
            incident["longitude"],
            [department(r) for r in rows],
            self.rules(db),
        )

    def priority(self, db, incident):
        row = dict(self.require(db, "incident_priority", "incident_id", incident["incident_id"]))
        row["incident_version"] = incident["version"]
        fresh = self.fresh(row, self.clock().timestamp())
        return row, fresh

    def recommendations(self, db, incident, record):
        if not record["department_id"]:
            return {
                "ranked": [],
                "excluded": [],
                "message": "Confirm a responsible department first",
            }
        dept = self.require(db, "departments", "id", record["department_id"])
        if not dept["active"] or not covered(
            json.loads(dept["areas"]), incident["latitude"], incident["longitude"]
        ):
            return {
                "ranked": [],
                "excluded": [],
                "message": "Department jurisdiction requires review",
            }
        row, fresh = self.priority(db, incident)
        result = recommend(
            self.officers(db, dept["id"], incident["incident_id"]),
            self.units(row, self.clock().timestamp()),
            incident["latitude"],
            incident["longitude"],
        )
        return result | {
            "priorityStale": not fresh,
            "incomingUnits": self.units(row, self.clock().timestamp()),
            "mode": self.settings.assignment_mode,
            "assignmentChanged": False,
        }

    def detail(self, identity, officer=None):
        with self.store.connection() as db:
            db.execute("BEGIN")
            incident, record = self.state(db, identity)
            if officer:
                self.authorize_officer(db, incident, record, officer)
            priority, fresh = self.priority(db, incident)
            dto = {
                "incidentId": identity,
                "title": incident["canonical_title"],
                "category": incident["category"],
                "latitude": incident["latitude"],
                "longitude": incident["longitude"],
                "incidentStatus": incident["status"],
                "incidentVersion": incident["version"],
                "assignment": assignment(record),
                "priority": json.loads(priority["result"]) if priority["result"] else None,
                "priorityStale": not fresh,
                "department": department(
                    self.require(db, "departments", "id", record["department_id"])
                )
                if record["department_id"]
                else None,
            }
            if not officer:
                dto["suggestedRouting"] = self.routing(db, incident)
                dto["recommendations"] = self.recommendations(db, incident, record)
            return dto

    def authorize_officer(self, db, incident, record, officer):
        # Do not resolve aliases on an officer path: an old assignment conveys no new access.
        if incident["status"] != "OPEN" or record["officer_id"] != officer:
            raise IncidentError(404, "Assigned incident not found")
        membership = db.execute(
            "SELECT m.*,u.role,u.is_active,u.is_verified,d.active AS department_active,"
            "d.areas AS department_areas "
            "FROM officer_memberships m JOIN users u ON u.id=m.officer_id "
            "JOIN departments d ON d.id=m.department_id WHERE m.officer_id=? AND m.department_id=?",
            (officer, record["department_id"]),
        ).fetchone()
        if not membership or not (
            membership["active"]
            and membership["department_active"]
            and membership["role"] == "OFFICER"
            and membership["is_active"]
            and membership["is_verified"]
            and membership["availability"] in ("AVAILABLE", "BUSY")
            and covered(
                json.loads(membership["areas"]), incident["latitude"], incident["longitude"]
            )
            and covered(
                json.loads(membership["department_areas"]),
                incident["latitude"],
                incident["longitude"],
            )
        ):
            raise IncidentError(404, "Assigned incident not found or membership no longer eligible")

    def assign(self, identity, kind, data, actor):
        def write(db, op):
            incident, row = self.state(db, identity)
            if incident["status"] != "OPEN":
                raise IncidentError(409, "Only canonical OPEN incidents accept active assignments")
            self.version(incident, data["expectedIncidentVersion"])
            self.version(row, data["expectedAssignmentVersion"])
            before = assignment(row)
            dept, officer = row["department_id"], row["officer_id"]
            rule_version, explanation, method = row["rule_version"], [], "MANUAL_ADMIN"
            status = "DEPARTMENT_ASSIGNED"
            if kind == "ROUTE":
                if officer or row["status"] == "IN_PROGRESS":
                    raise IncidentError(
                        409, "Explicitly reassign or unassign existing work before rerouting"
                    )
                decision = self.routing(db, incident)
                dept, officer = decision["departmentId"], None
                rule_version, explanation = decision["ruleVersion"], decision["explanation"]
                status = (
                    "NEEDS_REVIEW"
                    if decision["review"] or row["method"] == "REVIEW_LOCK"
                    else status
                )
                method = "REVIEW_LOCK" if row["method"] == "REVIEW_LOCK" else "AUTO_DEPARTMENT"
                if data["mode"] == "CONSERVATIVE_AUTO_ASSIGN":
                    if self.settings.assignment_mode != "CONSERVATIVE_AUTO_ASSIGN":
                        raise IncidentError(
                            422,
                            "Conservative allocation must be explicitly enabled in configuration",
                        )
                    candidate_row = dict(row) | {"department_id": dept}
                    candidates = self.recommendations(db, incident, candidate_row)
                    priority, fresh = self.priority(db, incident)
                    ranked = candidates["ranked"]
                    if (
                        status != "NEEDS_REVIEW"
                        and fresh
                        and not priority["urgent_hazard"]
                        and len(ranked) == 1
                    ):
                        candidate = ranked[0]
                        if (
                            candidate["capacity"] is not None
                            and candidate["pendingPriorities"] == 0
                        ):
                            officer, status, method = (
                                candidate["officerId"],
                                "OFFICER_ASSIGNED",
                                "AUTO_OFFICER",
                            )
            elif kind == "UNASSIGN":
                officer = None
                status = "DEPARTMENT_ASSIGNED" if dept else "UNASSIGNED"
            else:
                if kind == "DEPARTMENT":
                    if not data.get("departmentId"):
                        raise IncidentError(422, "Select a department")
                    dept, officer = data["departmentId"], None
                elif kind == "OFFICER":
                    if not data.get("officerId") or not dept:
                        raise IncidentError(422, "Confirm a department and select an officer")
                    officer = data["officerId"]
                elif kind == "REASSIGN":
                    dept, officer = data.get("departmentId"), data.get("officerId")
                if data.get("review"):
                    officer, status = None, "NEEDS_REVIEW"
                elif officer:
                    status = "OFFICER_ASSIGNED"
                elif not dept:
                    status = "UNASSIGNED"
                method = "REASSIGNMENT" if before["departmentId"] or before["officerId"] else method
            if dept:
                target = self.require(db, "departments", "id", dept)
                if not target["active"] or not covered(
                    json.loads(target["areas"]), incident["latitude"], incident["longitude"]
                ):
                    raise IncidentError(
                        422, "Selected department is inactive or outside jurisdiction"
                    )
            if officer:
                if not dept:
                    raise IncidentError(422, "An officer requires a responsible department")
                candidates = self.recommendations(db, incident, dict(row) | {"department_id": dept})
                eligible = next(
                    (r for r in candidates["ranked"] if r["officerId"] == officer), None
                )
                if not eligible:
                    # Capacity overrides never bypass officer eligibility or jurisdiction.
                    raw = next(
                        (o for o in self.officers(db, dept, identity) if o["officerId"] == officer),
                        None,
                    )
                    if not (actor.type == "ADMIN" and data.get("capacityOverride") and raw):
                        raise IncidentError(
                            422, "Officer is unavailable, ineligible or lacks weighted capacity"
                        )
                    checked = recommend(
                        [raw | {"capacity": None}], 0, incident["latitude"], incident["longitude"]
                    )
                    if not checked["ranked"]:
                        raise IncidentError(
                            422, "Capacity override cannot bypass officer eligibility"
                        )
                    explanation.append(
                        "Administrator explicitly overrode experimental weighted capacity"
                    )
            now = self.clock().isoformat()
            db.execute(
                "UPDATE incident_assignments SET department_id=?,officer_id=?,status=?,method=?,"
                "rule_version=?,explanation=?,version=version+1,source_version=?,route_pending=0,"
                "percentage=0,assigned_at=?,updated_at=?,assigned_by=? WHERE incident_id=?",
                (
                    dept,
                    officer,
                    status,
                    method,
                    rule_version,
                    encode(explanation),
                    incident["version"],
                    now,
                    now,
                    actor.id,
                    identity,
                ),
            )
            result = assignment(self.require(db, "incident_assignments", "incident_id", identity))
            self.audit(
                db, identity, f"ASSIGNMENT_{kind}", before, result, actor, data["reason"], op
            )
            return result

        return self.atomic(kind, identity, data, actor, write)

    def progress(self, identity, kind, data, actor):
        def write(db, op):
            incident, row = self.state(db, identity)
            self.authorize_officer(db, incident, row, actor.id)
            self.version(incident, data["expectedIncidentVersion"])
            self.version(row, data["expectedAssignmentVersion"])
            if kind == "START" and row["status"] != "OFFICER_ASSIGNED":
                raise IncidentError(409, "Work can start only from OFFICER_ASSIGNED")
            if kind == "PROGRESS" and row["status"] != "IN_PROGRESS":
                raise IncidentError(409, "Start work before adding progress")
            if data["percentage"] < row["percentage"]:
                raise IncidentError(
                    422, "Progress percentage cannot decrease; request administrator review"
                )
            before = assignment(row)
            status = "NEEDS_REVIEW" if data["requestReview"] else "IN_PROGRESS"
            now = self.clock().isoformat()
            db.execute(
                "UPDATE incident_assignments SET status=?,percentage=?,"
                "version=version+1,updated_at=? "
                "WHERE incident_id=?",
                (status, data["percentage"], now, identity),
            )
            result = assignment(self.require(db, "incident_assignments", "incident_id", identity))
            self.audit(
                db,
                identity,
                f"WORK_{kind}",
                before,
                result | {"note": data["note"]},
                actor,
                data["reason"],
                op,
            )
            return result

        return self.atomic(kind, identity, data, actor, write)

    def history(self, entity, limit=20, after=None, officer=None):
        with self.store.connection() as db:
            db.execute("BEGIN")
            if officer:
                incident, record = self.state(db, entity)
                self.authorize_officer(db, incident, record, officer)
            where, args = "entity_id=?", [entity]
            if after:
                where += " AND (created_at,event_id)>(?,?)"
                args.extend(after)
            # Officers receive progress only, not administrator reasons or previous officers' notes.
            if officer:
                where += " AND kind IN('WORK_START','WORK_PROGRESS') AND actor_id=?"
                args.append(officer)
            rows = db.execute(
                f"SELECT * FROM work_history WHERE {where} ORDER BY created_at,event_id LIMIT ?",
                [*args, limit + 1],
            ).fetchall()
            return {
                "items": [
                    {
                        "eventId": r["event_id"],
                        "kind": r["kind"],
                        "actorId": r["actor_id"],
                        "reason": r["reason"],
                        "before": json.loads(r["before_state"]),
                        "after": json.loads(r["after_state"]),
                        "createdAt": r["created_at"],
                    }
                    for r in rows[:limit]
                ],
                "after": [rows[limit - 1]["created_at"], rows[limit - 1]["event_id"]]
                if len(rows) > limit
                else None,
            }

    def department_detail(self, identity):
        with self.store.connection() as db:
            db.execute("BEGIN")
            row = self.require(db, "departments", "id", identity)
            officers = self.officers(db, identity)
            summary = db.execute(
                "SELECT count(*),sum(officer_id IS NULL) FROM incident_assignments a "
                "JOIN incidents i USING(incident_id) WHERE a.department_id=? AND i.status='OPEN'",
                (identity,),
            ).fetchone()
            work_rows = db.execute(
                "SELECT p.*,i.version AS incident_version,a.officer_id,a.status AS work_status,"
                "i.latitude,i.longitude FROM incident_assignments a "
                "JOIN incidents i USING(incident_id) JOIN incident_priority p USING(incident_id) "
                "WHERE a.department_id=? AND i.status='OPEN' LIMIT 5001",
                (identity,),
            ).fetchall()
            if len(work_rows) > 5000:
                raise IncidentError(409, "Department workload exceeds bounded5000 records")
            now = self.clock().timestamp()
            return department(row) | {
                "officers": officers,
                "rules": [r for r in self.rules(db) if r["departmentId"] == identity],
                "rebalancing": rebalance_analysis(
                    officers,
                    [
                        {
                            "incidentId": r["incident_id"],
                            "officerId": r["officer_id"],
                            "status": r["work_status"],
                            "units": self.units(r, now),
                            "latitude": r["latitude"],
                            "longitude": r["longitude"],
                        }
                        for r in work_rows
                    ],
                ),
                "workload": {
                    "activeIncidents": summary[0],
                    "unassignedIncidents": summary[1] or 0,
                    "weightedWorkload": sum(self.units(r, now) for r in work_rows),
                    "unassignedWorkload": sum(
                        self.units(r, now) for r in work_rows if not r["officer_id"]
                    ),
                    "activeOfficers": sum(o["active"] and o["eligibleAccount"] for o in officers),
                    "availableOfficers": sum(
                        o["active"] and o["eligibleAccount"] and o["availability"] == "AVAILABLE"
                        for o in officers
                    ),
                    "overCapacity": [
                        o["officerId"]
                        for o in officers
                        if o["capacity"] and o["workload"] > o["capacity"]
                    ],
                    "policy": "Global officer workload; no automatic rebalancing. "
                    "Consider manual transfers of unstarted work to lower-load staff.",
                },
            }

    def department_exists(self, identity):
        with self.store.connection() as db:
            return self.require(db, "departments", "id", identity)["id"]

    def process_one(self):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT a.*,i.version AS incident_version FROM incident_assignments a "
                "JOIN incidents i USING(incident_id) WHERE a.route_pending=1 AND a.available_at<=? "
                "AND i.status='OPEN' ORDER BY a.incident_id LIMIT 1",
                (self.clock().timestamp(),),
            ).fetchone()
        if not row:
            return None
        from app.models.incident import Actor

        data = {
            "operationId": str(uuid4()),
            "expectedIncidentVersion": row["incident_version"],
            "expectedAssignmentVersion": row["version"],
            "reason": "Local bounded category routing worker",
            "confirmed": True,
            "mode": self.settings.assignment_mode,
        }
        try:
            return self.assign(
                row["incident_id"], "ROUTE", data, Actor("department-local-worker", "SYSTEM")
            )
        except IncidentError as error:
            with self.store.connection() as db:
                db.execute(
                    "UPDATE incident_assignments SET available_at=? "
                    "WHERE incident_id=? AND version=?",
                    (self.clock().timestamp() + 60, row["incident_id"], row["version"]),
                )
            return {"state": "RETRY", "status": error.status}

    def queue(
        self, query, after=None, revision=None, valid_until=None, officer=None, unassigned=False
    ):
        now = self.clock().timestamp()
        with self.store.connection() as db:
            db.execute("BEGIN")
            current = db.execute("SELECT revision FROM work_meta WHERE singleton=1").fetchone()[0]
            if revision is not None and (
                current != revision or valid_until is None or valid_until <= now
            ):
                raise IncidentError(409, "Work queue changed or aged; restart from its first page")
            where, args = ["i.status='OPEN'"], [self.config_version, now]
            if officer:
                where.append("a.officer_id=?")
                args.append(officer)
                where.append(
                    "EXISTS(SELECT 1 FROM officer_memberships m JOIN users u ON u.id=m.officer_id "
                    "JOIN departments d ON d.id=m.department_id WHERE m.officer_id=a.officer_id "
                    "AND m.department_id=a.department_id AND m.active=1 AND d.active=1 "
                    "AND u.role='OFFICER' AND u.is_active=1 AND u.is_verified=1 "
                    "AND m.availability IN('AVAILABLE','BUSY') "
                    "AND (json_array_length(m.areas)=0 OR EXISTS(SELECT 1 "
                    "FROM json_each(m.areas) x "
                    "WHERE i.latitude BETWEEN json_extract(x.value,'$.south') "
                    "AND json_extract(x.value,'$.north') AND i.longitude BETWEEN "
                    "json_extract(x.value,'$.west') AND json_extract(x.value,'$.east'))) "
                    "AND (json_array_length(d.areas)=0 OR EXISTS(SELECT 1 "
                    "FROM json_each(d.areas) x "
                    "WHERE i.latitude BETWEEN json_extract(x.value,'$.south') "
                    "AND json_extract(x.value,'$.north') AND i.longitude BETWEEN "
                    "json_extract(x.value,'$.west') AND json_extract(x.value,'$.east'))))"
                )
            if unassigned:
                where.append("(a.officer_id IS NULL OR a.status='NEEDS_REVIEW')")
            for key, column in (
                ("departmentId", "a.department_id"),
                ("officerId", "a.officer_id"),
                ("status", "a.status"),
                ("category", "i.category"),
            ):
                if query.get(key) is not None:
                    where.append(f"{column}=?")
                    args.append(query[key])
            if query.get("assignedAfter"):
                where.append("julianday(a.assigned_at)>=julianday(?)")
                args.append(query["assignedAfter"])
            fresh = "(p.result IS NOT NULL AND p.needs_recalculation=0 AND p.config_version=? "
            fresh += "AND p.source_version=i.version AND p.next_due>?)"
            sql = f"""WITH ranked AS(SELECT i.incident_id,i.canonical_title,
                i.category,i.latitude,i.longitude,
                i.version AS incident_version,a.*,d.name AS department_name,p.result,
                p.priority_band,p.effective_score,p.urgent_hazard,p.unresolved_seconds,p.next_due,
                CASE WHEN {fresh} THEN 0 ELSE 1 END AS pending
                FROM incident_assignments a JOIN incidents i USING(incident_id)
                JOIN incident_priority p USING(incident_id)
                LEFT JOIN departments d ON d.id=a.department_id
                WHERE {" AND ".join(where)}), ordered AS(SELECT *,
                CASE WHEN pending=0 THEN -urgent_hazard ELSE 0 END AS k1,
                -pending AS k2,CASE WHEN pending=0 THEN -effective_score ELSE 0 END AS k3,
                -unresolved_seconds AS k4 FROM ranked) """
            conditions, filters = [], []
            if query.get("band"):
                conditions.extend(["pending=0", "priority_band=?"])
                filters.append(query["band"])
            if query.get("urgent") is not None:
                conditions.extend(["pending=0", "urgent_hazard=?"])
                filters.append(query["urgent"])
            scope = " WHERE " + " AND ".join(conditions) if conditions else ""
            totals = db.execute(
                sql + "SELECT count(*),sum(officer_id IS NOT NULL),sum(status='IN_PROGRESS'),"
                "sum(pending=0 AND priority_band='HIGH'),"
                "sum(pending=0 AND priority_band='CRITICAL'),"
                "sum(pending=0 AND urgent_hazard=1),sum(pending=1) FROM ordered" + scope,
                [*args, *filters],
            ).fetchone()
            if after:
                conditions.append("(k1,k2,k3,k4,incident_id)>(?,?,?,?,?)")
                filters.extend(after)
            paging = " WHERE " + " AND ".join(conditions) if conditions else ""
            limit = query.get("limit", 20)
            rows = db.execute(
                sql
                + "SELECT * FROM ordered"
                + paging
                + " ORDER BY k1,k2,k3,k4,incident_id LIMIT ?",
                [*args, *filters, limit + 1],
            ).fetchall()
            # Minimum due time across canonical active records, not only this returned page.
            due = db.execute(
                "SELECT min(p.next_due) FROM incident_priority p JOIN incidents i "
                "USING(incident_id) WHERE i.status='OPEN' AND p.next_due>?",
                (now,),
            ).fetchone()[0]
            expiry = min(valid_until or now + 60, due or now + 60, now + 60)
            items = [
                {
                    "incidentId": r["incident_id"],
                    "title": r["canonical_title"],
                    "category": r["category"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "incidentVersion": r["incident_version"],
                    "assignment": assignment(r),
                    "departmentName": r["department_name"],
                    "priorityStale": bool(r["pending"]),
                    "priority": json.loads(r["result"]) if r["result"] else None,
                }
                for r in rows[:limit]
            ]
            last = rows[limit - 1] if len(rows) > limit else None
            return {
                "items": items,
                "after": [last[k] for k in ("k1", "k2", "k3", "k4", "incident_id")]
                if last
                else None,
                "queueRevision": current,
                "validUntil": expiry,
                "stats": dict(
                    zip(
                        (
                            "total",
                            "assigned",
                            "inProgress",
                            "high",
                            "critical",
                            "urgent",
                            "pendingPriority",
                        ),
                        [v or 0 for v in totals],
                        strict=True,
                    )
                ),
                "consistency": "Revision/expiry cursors; pending priorities require review",
                **({"workload": self.workload(db, officer)} if officer else {}),
            }

    def summary(self):
        with self.store.connection() as db:
            db.execute("BEGIN")
            counts = db.execute(
                "SELECT count(*),sum(a.officer_id IS NULL),sum(a.officer_id IS NOT NULL),"
                "sum(a.status='IN_PROGRESS'),sum(a.status='NEEDS_REVIEW') "
                "FROM incident_assignments a "
                "JOIN incidents i USING(incident_id) WHERE i.status='OPEN'"
            ).fetchone()
            depts = db.execute("SELECT count(*),sum(active=1) FROM departments").fetchone()
            officers = db.execute(
                "SELECT count(DISTINCT m.officer_id),"
                "count(DISTINCT CASE WHEN m.availability='AVAILABLE' THEN m.officer_id END) "
                "FROM officer_memberships m JOIN users u ON u.id=m.officer_id "
                "JOIN departments d ON d.id=m.department_id WHERE m.active=1 AND d.active=1 "
                "AND u.role='OFFICER' AND u.is_active=1 AND u.is_verified=1"
            ).fetchone()
            return {
                "totalDepartments": depts[0],
                "activeDepartments": depts[1] or 0,
                "officers": officers[0],
                "availableOfficers": officers[1],
                **dict(
                    zip(
                        ("activeIncidents", "unassigned", "assigned", "inProgress", "needsReview"),
                        [v or 0 for v in counts],
                        strict=True,
                    )
                ),
            }
