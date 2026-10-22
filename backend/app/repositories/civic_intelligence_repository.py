"""Phase12 transactions. Membership remains complaints.incident_id; no parallel lifecycle."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.analytics.metrics import stamp
from app.events.schema import new_event
from app.models.incident import IncidentError, stable_id
from app.repositories.event_repository import SQLiteEvents, encoded


def require(condition, message, status=409):
    if not condition:
        raise IncidentError(status, message)


class SQLiteCivicIntelligence:
    def __init__(self, store, work, clock=None):
        self.store, self.work = store, work
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def row(db, table, field, identity):
        row = db.execute(f"SELECT * FROM {table} WHERE {field}=?", (identity,)).fetchone()
        require(row is not None, "Record not found", 404)
        return dict(row)

    def transaction(self, kind, data, actor, entity, write):
        fingerprint = hashlib.sha256(encoded([kind, data, actor, entity]).encode()).hexdigest()
        op = str(data["operationId"])
        now = self.clock().isoformat()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute(
                "SELECT fingerprint,result FROM incident_operations WHERE operation_id=?", (op,)
            ).fetchone()
            if saved:
                require(saved[0] == fingerprint, "Operation ID already used with different input")
                return json.loads(saved[1])
            user = self.row(db, "users", "id", actor["id"])
            require(
                user["is_active"] and user["is_verified"] and user["role"] == actor["role"],
                "Active verified account required",
                403,
            )
            result, events = write(db, now)
            db.execute(
                "INSERT INTO incident_operations VALUES(?,?,?,?,?,?,?)",
                (
                    op,
                    fingerprint,
                    kind,
                    actor["id"],
                    data.get("reason", kind),
                    encoded(result),
                    now,
                ),
            )
            db.execute(
                "INSERT INTO civic_intelligence_audit VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    entity,
                    op,
                    kind,
                    actor["id"],
                    data.get("reason", kind),
                    encoded(result),
                    now,
                ),
            )
            for event_kind, identity, payload in events:
                SQLiteEvents.put(
                    db,
                    new_event(
                        event_kind, identity, correlation=op, payload=payload, now=self.clock()
                    ),
                )
            return result

    @staticmethod
    def eligible(db, identity):
        return [
            dict(r)
            for r in db.execute(
                "SELECT DISTINCT u.id FROM complaints c JOIN users u ON u.id=c.citizen_id "
                "WHERE c.incident_id=? AND c.status<>'REJECTED' AND u.role='CITIZEN' "
                "AND u.is_active=1 AND u.is_verified=1 ORDER BY u.id LIMIT 31",
                (identity,),
            )
        ]

    def incident(self, db, identity, expected=None):
        row = self.row(db, "incidents", "incident_id", identity)
        require(
            row["status"] in ("OPEN", "RESOLVED"), "Canonical incident changed; review membership"
        )
        if expected is not None:
            require(row["version"] == expected, "Incident changed; refresh before retrying")
        return row

    def add_evidence(self, db, attempt, actor, images, kind, now):
        for image in images:
            db.execute(
                "INSERT INTO repair_evidence VALUES(?,?,?,?,?,?,0,?)",
                (
                    image["imageId"],
                    attempt,
                    actor,
                    kind,
                    image["storageKey"],
                    image["fileSize"],
                    now,
                ),
            )

    def submit(self, identity, data, actor, images):
        require(actor["role"] == "OFFICER", "Officer submission required", 403)
        attempt = stable_id(f"repair/{actor['id']}/{data['operationId']}")

        def write(db, now):
            incident = self.incident(db, identity, data["expectedIncidentVersion"])
            assignment = self.row(db, "incident_assignments", "incident_id", identity)
            self.work.authorize_officer(db, incident, assignment, actor["id"])
            require(
                assignment["version"] == data["expectedAssignmentVersion"], "Assignment changed"
            )
            require(
                assignment["status"] == "IN_PROGRESS",
                "Start assigned work before submitting repair",
            )
            repaired = stamp(data["repairedAt"])
            require(
                stamp(incident["created_at"]) <= repaired <= self.clock(),
                "Repair timestamp must be between incident creation and now",
                422,
            )
            pending = db.execute(
                "SELECT 1 FROM repair_attempts WHERE incident_id=? AND "
                "state IN ('PENDING_VERIFICATION','INFORMATION_REQUIRED')",
                (identity,),
            ).fetchone()
            require(not pending, "A repair attempt is already awaiting review")
            cycle = db.execute(
                "SELECT COALESCE(MAX(cycle),0)+1 FROM repair_attempts WHERE incident_id=?",
                (identity,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO repair_attempts(attempt_id,incident_id,officer_id,department_id,cycle,"
                "description,notes,repaired_at,submitted_at,state,source_vers"
                "ion,assignment_version,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'PENDING_VERIFICATION',?,?,?)",
                (
                    attempt,
                    identity,
                    actor["id"],
                    assignment["department_id"],
                    cycle,
                    data["description"],
                    data["notes"],
                    data["repairedAt"],
                    now,
                    incident["version"],
                    assignment["version"],
                    now,
                ),
            )
            eligible = self.eligible(db, identity)
            require(len(eligible) <= 30, "Membership exceeds bounded verification size")
            for citizen in eligible:
                db.execute(
                    "INSERT INTO repair_verification_requests VALUES(?,?,?,?)",
                    (stable_id(f"verify/{attempt}/{citizen['id']}"), attempt, citizen["id"], now),
                )
            self.add_evidence(db, attempt, actor["id"], images, "REPAIR", now)
            return {
                "attemptId": attempt,
                "incidentId": identity,
                "state": "PENDING_VERIFICATION",
                "version": 1,
                "requestCount": len(eligible),
            }, [
                ("RepairSubmitted", identity, {"attemptId": attempt}),
                ("RepairVerificationRequested", identity, {"attemptId": attempt}),
            ]

        return self.transaction("REPAIR_SUBMITTED", data, actor, identity, write)

    def request_row(self, db, identity, citizen):
        row = self.row(db, "repair_verification_requests", "request_id", identity)
        require(row["citizen_id"] == citizen, "Verification request not found", 404)
        attempt = self.row(db, "repair_attempts", "attempt_id", row["attempt_id"])
        require(
            any(r["id"] == citizen for r in self.eligible(db, attempt["incident_id"])),
            "Verification request not found",
            404,
        )
        return row, attempt

    def respond(self, request_id, data, actor, images):
        require(actor["role"] == "CITIZEN", "Citizen response required", 403)

        def write(db, now):
            request, attempt = self.request_row(db, request_id, actor["id"])
            incident = self.incident(db, attempt["incident_id"], attempt["source_version"])
            require(
                incident["status"] == "OPEN"
                and attempt["state"] in ("PENDING_VERIFICATION", "INFORMATION_REQUIRED"),
                "This attempt no longer accepts responses",
            )
            require(attempt["version"] == data["expectedVersion"], "Repair review changed; refresh")
            require(
                not db.execute(
                    "SELECT 1 FROM repair_verifications WHERE request_id=?", (request_id,)
                ).fetchone(),
                "A response is already recorded; contact administration for correction",
            )
            db.execute(
                "INSERT INTO repair_verifications VALUES(?,?,?,?,?)",
                (str(uuid4()), request_id, data["result"], data["feedback"], now),
            )
            self.add_evidence(db, attempt["attempt_id"], actor["id"], images, "FEEDBACK", now)
            db.execute(
                "UPDATE repair_attempts SET version=version+1,updated_at=? WHERE attempt_id=?",
                (now, attempt["attempt_id"]),
            )
            kind = (
                "RepairVerificationDisputed"
                if data["result"] == "STILL_BROKEN"
                else "RepairVerificationResponded"
            )
            return {
                "requestId": request_id,
                "result": data["result"],
                "recordedAt": now,
                "message": "Feedback recorded. Only an administrator can decide "
                "official resolution.",
            }, [(kind, attempt["incident_id"], {"attemptId": attempt["attempt_id"]})]

        return self.transaction("REPAIR_RESPONSE", data, actor, request_id, write)

    def decision(self, attempt_id, kind, data, actor):
        require(actor["role"] == "ADMIN", "Administrator decision required", 403)

        def write(db, now):
            attempt = self.row(db, "repair_attempts", "attempt_id", attempt_id)
            identity = attempt["incident_id"]
            incident = self.incident(db, identity, data["expectedIncidentVersion"])
            require(
                attempt["version"] == data["expectedVersion"],
                "Repair or citizen feedback changed; refresh",
            )
            pending = attempt["state"] in ("PENDING_VERIFICATION", "INFORMATION_REQUIRED")
            evidence = [
                r[0]
                for r in db.execute(
                    "SELECT image_id FROM repair_evidence WHERE attempt_id=? AND kind='REPAIR'",
                    (attempt_id,),
                )
            ]
            approved = list(map(str, data.get("approvedEvidenceIds", [])))
            require(set(approved) <= set(evidence), "Only repair photographs can be approved", 422)
            if kind == "reopen":
                require(
                    attempt["state"] == "VERIFIED_RESOLVED"
                    and incident["status"] == "RESOLVED"
                    and incident["resolved_at"] == attempt["verified_at"],
                    "Only current verified resolution can be reopened",
                )
                state, event = "REOPENED", "IncidentReopened"
            else:
                require(
                    pending and incident["status"] == "OPEN",
                    "Repair is not awaiting administrative review",
                )
                if kind in ("approve", "approve-evidence"):
                    require(
                        incident["version"] == attempt["source_version"],
                        "Membership changed after submission; request rework and a new attempt",
                    )
                state, event = {
                    "approve": ("VERIFIED_RESOLVED", "RepairApproved"),
                    "reject": ("REJECTED", "RepairRejected"),
                    "request-rework": ("REWORK_REQUIRED", "RepairReworkRequested"),
                    "request-information": ("INFORMATION_REQUIRED", "RepairInformationRequested"),
                    "approve-evidence": (attempt["state"], "RepairVerificationRequested"),
                }[kind]
            if kind == "approve":
                assignment = self.row(db, "incident_assignments", "incident_id", identity)
                require(
                    assignment["version"] == attempt["assignment_version"],
                    "Assignment/progress changed since repair submission; request rework",
                )
                # Zero votes never imply success. Reason records the accountable evidence,
                # hazard and dispute decision, not a majority rule.
                require(
                    bool(evidence) or len(data["reason"]) >= 40,
                    "Approval without photographs requires a detailed "
                    "independent verification reason",
                    422,
                )
            if kind in ("reject", "request-rework"):
                db.execute(
                    "UPDATE incident_assignments SET "
                    "percentage=0,version=version+1,updated_at=? "
                    "WHERE incident_id=? AND status='IN_PROGRESS'",
                    (now, identity),
                )
            if kind == "approve-evidence":
                for image_id in approved:
                    db.execute(
                        "UPDATE repair_evidence SET approved=1 WHERE image_id=?", (image_id,)
                    )
            db.execute(
                "UPDATE repair_attempts SET "
                "state=?,version=version+1,updated_at=?,decision_reason=?,"
                "verified_at=CASE WHEN ?='approve' THEN ? ELSE verified_at END,"
                "verified_by=CASE WHEN ?='approve' THEN ? ELSE verified_by END WHERE attempt_id=?",
                (state, now, data["reason"], kind, now, kind, actor["id"], attempt_id),
            )
            if kind in ("approve", "reopen"):
                status = "RESOLVED" if kind == "approve" else "OPEN"
                resolved = now if kind == "approve" else None
                db.execute(
                    "UPDATE incidents SET "
                    "status=?,resolved_at=?,updated_at=?,version=version+1 WHERE "
                    "incident_id=?",
                    (status, resolved, now, identity),
                )
                if kind == "approve":
                    db.execute(
                        "UPDATE complaints SET status='RESOLVED',updated_at=? WHERE "
                        "incident_id=? "
                        "AND status NOT IN ('RESOLVED','REJECTED')",
                        (now, identity),
                    )
                else:
                    db.execute(
                        "UPDATE complaints SET status='UNDER_REVIEW',updated_at=? "
                        "WHERE incident_id=? "
                        "AND status='RESOLVED'",
                        (now, identity),
                    )
                # P8 age, P9 suspension and P10 SLA/outbox triggers run in this transaction.
                # P11 resolution metric reuses its original canonical lifecycle audit format.
                before = {"status": incident["status"], "resolvedAt": incident["resolved_at"]}
                after = {"status": status, "resolvedAt": resolved, "repairAttemptId": attempt_id}
                # Audit FK is deferred until operation receipt is inserted below.
                db.execute("PRAGMA defer_foreign_keys=ON")
                db.execute(
                    "INSERT INTO incident_audit VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identity,
                        str(data["operationId"]),
                        "VERIFIED_RESOLUTION" if kind == "approve" else "REOPEN",
                        actor["id"],
                        data["reason"],
                        now,
                        encoded({"before": before, "after": after}),
                    ),
                )
            result = {
                "attemptId": attempt_id,
                "incidentId": identity,
                "state": state,
                "version": attempt["version"] + 1,
                "verifiedAt": now if kind == "approve" else attempt["verified_at"],
                "decisionReason": data["reason"],
                "supportingEvidenceIds": [
                    r[0]
                    for r in db.execute(
                        "SELECT image_id FROM repair_evidence WHERE attempt_id=? ORDER BY image_id",
                        (attempt_id,),
                    )
                ],
                "approvedEvidenceIds": approved if kind == "approve-evidence" else [],
            }
            events = [(event, identity, {"attemptId": attempt_id})]
            if kind == "approve":
                events.append(("IncidentVerifiedResolved", identity, {"attemptId": attempt_id}))
            return result, events

        return self.transaction(f"REPAIR_{kind.upper()}", data, actor, attempt_id, write)

    def detail(self, attempt_id, actor, request_id=None):
        with self.store.connection() as db:
            attempt = self.row(db, "repair_attempts", "attempt_id", attempt_id)
            incident = self.row(db, "incidents", "incident_id", attempt["incident_id"])
            if actor["role"] == "CITIZEN":
                require(request_id is not None, "Verification request not found", 404)
                self.request_row(db, request_id, actor["id"])
            elif actor["role"] == "OFFICER":
                assignment = self.row(
                    db, "incident_assignments", "incident_id", attempt["incident_id"]
                )
                self.work.authorize_officer(db, incident, assignment, actor["id"])
            eligible = {r["id"] for r in self.eligible(db, attempt["incident_id"])}
            votes = [
                dict(r)
                for r in db.execute(
                    "SELECT v.*,r.citizen_id FROM repair_verifications v "
                    "JOIN repair_verification_requests r ON "
                    "r.request_id=v.request_id WHERE r.attempt_id=?",
                    (attempt_id,),
                )
            ]
            effective = [v for v in votes if v["citizen_id"] in eligible]
            counts = {
                result: sum(v["result"] == result for v in effective)
                for result in ("CONFIRMED_FIXED", "STILL_BROKEN", "UNSURE")
            }
            images = []
            for r in db.execute(
                "SELECT * FROM repair_evidence WHERE attempt_id=? ORDER BY image_id", (attempt_id,)
            ):
                if actor["role"] == "CITIZEN" and not (
                    r["owner_id"] == actor["id"] or r["kind"] == "REPAIR" and r["approved"]
                ):
                    continue
                images.append(
                    {
                        "imageId": r["image_id"],
                        "kind": r["kind"],
                        "approved": bool(r["approved"]),
                        "url": (
                            f"/incidents/{attempt['incident_id']}/repair-attempts/"
                            f"{attempt_id}/evidence/{r['image_id']}"
                        ),
                    }
                )
            result = {
                "attemptId": attempt_id,
                "incidentId": attempt["incident_id"],
                "title": incident["canonical_title"],
                "cycle": attempt["cycle"],
                "description": attempt["description"],
                "submittedAt": attempt["submitted_at"],
                "repairedAt": attempt["repaired_at"],
                "state": attempt["state"],
                "version": attempt["version"],
                "incidentVersion": incident["version"],
                "incidentStatus": incident["status"],
                "membershipChanged": incident["version"] != attempt["source_version"],
                "verifiedAt": attempt["verified_at"],
                "images": images,
            }
            if actor["role"] == "CITIZEN":
                result["requestId"] = request_id
                result["response"] = next(
                    (
                        {
                            "result": v["result"],
                            "feedback": v["feedback"],
                            "createdAt": v["created_at"],
                        }
                        for v in votes
                        if v["citizen_id"] == actor["id"]
                    ),
                    None,
                )
                result["canRespond"] = (
                    result["response"] is None
                    and not result["membershipChanged"]
                    and incident["status"] == "OPEN"
                    and attempt["state"] in ("PENDING_VERIFICATION", "INFORMATION_REQUIRED")
                )
                result["relatedComplaints"] = [
                    r[0]
                    for r in db.execute(
                        "SELECT complaint_id FROM complaints "
                        "WHERE incident_id=? AND citizen_id=? ORDER BY complaint_id LIMIT 30",
                        (attempt["incident_id"], actor["id"]),
                    )
                ]
            else:
                recommendation = (
                    "DISPUTE_REQUIRES_REVIEW"
                    if counts["STILL_BROKEN"]
                    else (
                        "CONFIRMATION_SUPPORT"
                        if counts["CONFIRMED_FIXED"]
                        else "INSUFFICIENT_RESPONSES"
                    )
                )
                result.update(
                    notes=attempt["notes"],
                    decisionReason=attempt["decision_reason"],
                    officerId=attempt["officer_id"],
                    departmentId=attempt["department_id"],
                    eligibleCitizens=len(eligible),
                    missingResponses=len(eligible) - len(effective),
                    responses=counts,
                    recommendation=recommendation,
                    audit=[
                        dict(r)
                        for r in db.execute(
                            "SELECT kind,reason,created_at FROM civic_intelligence_audit "
                            "WHERE entity_id IN (?,?) ORDER BY created_at LIMIT 100",
                            (attempt_id, attempt["incident_id"]),
                        )
                    ],
                )
                if actor["role"] == "ADMIN":
                    result["feedback"] = [
                        {
                            "result": v["result"],
                            "feedback": v["feedback"],
                            "eligible": v["citizen_id"] in eligible,
                            "createdAt": v["created_at"],
                        }
                        for v in votes
                    ]
            return result

    def attempts(self, identity, actor):
        with self.store.connection() as db:
            self.incident(db, identity)
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT attempt_id FROM repair_attempts WHERE incident_id=? "
                    "ORDER BY cycle DESC LIMIT 101",
                    (identity,),
                )
            ]
        require(len(ids) <= 100, "Repair history exceeds bounded view", 413)
        if actor["role"] == "OFFICER":
            self.work.detail(identity, actor["id"])
        return {"items": [self.detail(i, actor) for i in ids]}

    def requests(self, actor, after="", limit=25, history=False):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT r.request_id,r.attempt_id FROM repair_verification_requests r "
                "JOIN repair_attempts a ON a.attempt_id=r.attempt_id JOIN "
                "incidents i ON i.incident_id=a.incident_id "
                "WHERE r.citizen_id=? AND r.request_id>? AND i.status IN ('OPEN','RESOLVED') "
                "AND EXISTS(SELECT 1 FROM complaints c WHERE "
                "c.incident_id=a.incident_id AND c.citizen_id=? "
                "AND c.status<>'REJECTED') "
                + (
                    ""
                    if history
                    else "AND a.state IN ('PENDING_VERIFICATION','INFORMATION_REQUIRED') "
                )
                + "ORDER BY r.request_id LIMIT ?",
                (actor["id"], after, actor["id"], limit + 1),
            ).fetchall()
        return {
            "items": [self.detail(r[1], actor, r[0]) for r in rows[:limit]],
            "nextAfter": rows[limit - 1][0] if len(rows) > limit else None,
        }

    def pending(self, after="", limit=25, state=None):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT a.attempt_id FROM repair_attempts a WHERE a.attempt_id>? "
                + ("AND a.state=? " if state else "")
                + "ORDER BY a.attempt_id LIMIT ?",
                (after, state, limit + 1) if state else (after, limit + 1),
            ).fetchall()
            summary = {
                r[0]: r[1]
                for r in db.execute("SELECT state,count(*) FROM repair_attempts GROUP BY state")
            }
        return {
            "attemptIds": [r[0] for r in rows[:limit]],
            "summary": summary,
            "nextAfter": rows[limit - 1][0] if len(rows) > limit else None,
        }

    def evidence(self, identity, attempt_id, image_id, actor):
        with self.store.connection() as db:
            attempt = self.row(db, "repair_attempts", "attempt_id", attempt_id)
            require(attempt["incident_id"] == identity, "Evidence not found", 404)
            image = self.row(db, "repair_evidence", "image_id", image_id)
            require(image["attempt_id"] == attempt_id, "Evidence not found", 404)
            if actor["role"] == "CITIZEN":
                require(
                    any(r["id"] == actor["id"] for r in self.eligible(db, identity)),
                    "Evidence not found",
                    404,
                )
                require(
                    image["owner_id"] == actor["id"]
                    or image["kind"] == "REPAIR"
                    and image["approved"],
                    "Evidence not approved for verification",
                    404,
                )
            elif actor["role"] == "OFFICER":
                incident = self.incident(db, identity)
                assignment = self.row(db, "incident_assignments", "incident_id", identity)
                self.work.authorize_officer(db, incident, assignment, actor["id"])
            else:
                require(actor["role"] == "ADMIN", "Evidence not found", 404)
            return image["storage_key"]

    def request_detail(self, identity, actor):
        with self.store.connection() as db:
            row, attempt = self.request_row(db, identity, actor["id"])
        return self.detail(attempt["attempt_id"], actor, row["request_id"])

    def historical_candidates(self, identity, settings):
        from app.algorithms.duplicate_detection.geographic_similarity import envelope

        with self.store.connection() as db:
            current = self.incident(db, identity)
            box = envelope(
                current["latitude"], current["longitude"], settings.recurrence_radius_meters
            )
            longitude = (
                "i.longitude BETWEEN ? AND ?"
                if box.west <= box.east
                else "(i.longitude>=? OR i.longitude<=?)"
            )
            rows = db.execute(
                "SELECT i.*,a.attempt_id AS repair_attempt_id,a.verified_at FROM incidents i "
                "JOIN repair_attempts a ON a.incident_id=i.incident_id AND "
                "a.state='VERIFIED_RESOLVED' "
                "AND a.verified_at=i.resolved_at WHERE i.status='RESOLVED' AND i.incident_id<>? "
                "AND i.category=? AND i.latitude BETWEEN ? AND ? AND "
                + longitude
                + " AND julianday(a.verified_at)<julianday(?) AND "
                "julianday(a.verified_at)>=julianday(?)-? "
                "ORDER BY a.verified_at DESC,i.incident_id LIMIT 101",
                (
                    identity,
                    current["category"],
                    box.south,
                    box.north,
                    box.west,
                    box.east,
                    current["created_at"],
                    current["created_at"],
                    settings.recurrence_horizon_days,
                ),
            ).fetchall()
            require(
                len(rows) <= 100,
                "Historical candidate bound exceeded; reduce recurrence search configuration",
                413,
            )
            return current, [dict(r) for r in rows]

    def complaint_image_keys(self, complaint_id):
        with self.store.connection() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT storage_key FROM complaint_images WHERE complaint_id=? "
                    "ORDER BY image_id LIMIT 2",
                    (complaint_id,),
                )
            ]

    def save_candidates(self, identity, current, candidates, data, actor):
        def write(db, now):
            self.incident(db, identity, current["version"])
            created, events = [], []
            for previous, score in candidates:
                score = score | {
                    "previousMembershipEpoch": db.execute(
                        "SELECT membership_epoch FROM incident_priority WHERE incident_id=?",
                        (previous["incident_id"],),
                    ).fetchone()[0],
                    "newMembershipEpoch": db.execute(
                        "SELECT membership_epoch FROM incident_priority WHERE incident_id=?",
                        (identity,),
                    ).fetchone()[0],
                }
                historical = self.incident(db, previous["incident_id"], previous["version"])
                require(
                    historical["status"] == "RESOLVED"
                    and historical["resolved_at"] == previous["verified_at"],
                    "Historical repair changed during recurrence analysis",
                )
                repair = self.row(
                    db, "repair_attempts", "attempt_id", previous["repair_attempt_id"]
                )
                require(repair["state"] == "VERIFIED_RESOLVED", "Historical verification changed")
                if not score["eligible"]:
                    continue
                recurrence = stable_id(f"recurrence/{previous['incident_id']}/{identity}")
                saved = db.execute(
                    "SELECT * FROM incident_recurrences WHERE recurrence_id=?", (recurrence,)
                ).fetchone()
                if saved and (
                    saved["state"] == "DISMISSED"
                    or saved["state"] == "CONFIRMED_RECURRENCE"
                    and self.valid_relationship(db, dict(saved))
                ):
                    created.append(recurrence)
                    continue
                if saved:
                    db.execute(
                        "UPDATE incident_recurrences SET "
                        "score=?,distance=?,days_since_repair=?,state=?,"
                        "explanation=?,algorithm_version=?,previous_version=?,new_ver"
                        "sion=?,version=version+1,updated_at=? "
                        "WHERE recurrence_id=?",
                        (
                            score["score"],
                            score["distance"],
                            score["days"],
                            score["state"],
                            encoded(score),
                            score["algorithmVersion"],
                            previous["version"],
                            current["version"],
                            now,
                            recurrence,
                        ),
                    )
                else:
                    db.execute(
                        "INSERT INTO incident_recurrences(recurrence_id,previous_inci"
                        "dent_id,new_incident_id,"
                        "repair_attempt_id,score,distance,days_since_repair,state,exp"
                        "lanation,algorithm_version,"
                        "previous_version,new_version,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            recurrence,
                            previous["incident_id"],
                            identity,
                            previous["repair_attempt_id"],
                            score["score"],
                            score["distance"],
                            score["days"],
                            score["state"],
                            encoded(score),
                            score["algorithmVersion"],
                            previous["version"],
                            current["version"],
                            now,
                            now,
                        ),
                    )
                    if score["state"] == "POTENTIAL_RECURRENCE":
                        events.append(
                            ("PotentialRecurrenceDetected", identity, {"recurrenceId": recurrence})
                        )
                created.append(recurrence)
                db.execute("PRAGMA defer_foreign_keys=ON")
                db.execute(
                    "INSERT INTO civic_intelligence_audit VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        recurrence,
                        str(data["operationId"]),
                        "RECURRENCE_EVIDENCE",
                        actor["id"],
                        "Bounded recurrence recalculation; no automatic confirmation or merge",
                        encoded({"before": dict(saved) if saved else None, "after": score}),
                        now,
                    ),
                )
            return {
                "incidentId": identity,
                "recurrenceIds": created,
                "message": "Suggestions require physical identity review; incidents "
                "were not merged.",
            }, events

        return self.transaction("CHECK_RECURRENCE", data, actor, identity, write)

    def valid_relationship(self, db, row):
        old = self.row(db, "incidents", "incident_id", row["previous_incident_id"])
        new = self.row(db, "incidents", "incident_id", row["new_incident_id"])
        repair = self.row(db, "repair_attempts", "attempt_id", row["repair_attempt_id"])
        evidence = json.loads(row["explanation"])

        def unchanged(identity, key):
            current = db.execute(
                "SELECT membership_epoch FROM incident_priority WHERE incident_id=?", (identity,)
            ).fetchone()
            return bool(current and current[0] == evidence.get(key))

        canonical_versions = (
            (
                unchanged(old["incident_id"], "previousMembershipEpoch")
                and unchanged(new["incident_id"], "newMembershipEpoch")
            )
            if row["state"] == "CONFIRMED_RECURRENCE"
            else (
                old["version"] == row["previous_version"] and new["version"] == row["new_version"]
            )
        )
        return (
            old["status"] == "RESOLVED"
            and new["status"] in ("OPEN", "RESOLVED")
            and canonical_versions
            and repair["state"] == "VERIFIED_RESOLVED"
            and old["resolved_at"] == repair["verified_at"]
            and stamp(new["first_reported_at"]) > stamp(repair["verified_at"])
        )

    def recurrence_detail(self, identity):
        with self.store.connection() as db:
            row = self.row(db, "incident_recurrences", "recurrence_id", identity)
            valid = self.valid_relationship(db, row)
            old = self.row(db, "incidents", "incident_id", row["previous_incident_id"])
            new = self.row(db, "incidents", "incident_id", row["new_incident_id"])
            repair = self.row(db, "repair_attempts", "attempt_id", row["repair_attempt_id"])
            return {
                "recurrenceId": identity,
                "previousIncidentId": row["previous_incident_id"],
                "newIncidentId": row["new_incident_id"],
                "repairAttemptId": row["repair_attempt_id"],
                "previousTitle": old["canonical_title"],
                "newTitle": new["canonical_title"],
                "category": new["category"],
                "newIncidentStatus": new["status"],
                "previousRepairVerifiedAt": repair["verified_at"],
                "newReportedAt": new["first_reported_at"],
                "state": row["state"],
                "version": row["version"],
                "needsReassessment": not valid,
                "score": row["score"],
                "distanceMeters": row["distance"],
                "daysSinceRepair": row["days_since_repair"],
                "explanation": json.loads(row["explanation"]),
                "reviewReason": row["review_reason"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "timeline": [
                    {
                        "incidentId": old["incident_id"],
                        "at": old["first_reported_at"],
                        "kind": "REPORTED",
                    },
                    {
                        "incidentId": old["incident_id"],
                        "at": repair["verified_at"],
                        "kind": "VERIFIED_REPAIR",
                    },
                    {
                        "incidentId": new["incident_id"],
                        "at": new["first_reported_at"],
                        "kind": "NEW_REPORT",
                    },
                    *(
                        [
                            {
                                "incidentId": new["incident_id"],
                                "at": row["reviewed_at"],
                                "kind": row["state"],
                            }
                        ]
                        if row["reviewed_at"]
                        else []
                    ),
                ],
            }

    def recurrences(
        self, after="", limit=25, state=None, category=None, start=None, end=None, incident=None
    ):
        clauses, args = ["r.recurrence_id> ?"], [after]
        for column, value in (("r.state", state), ("i.category", category)):
            if value:
                clauses.append(column + "=?")
                args.append(value)
        if start:
            clauses.append("r.created_at>=?")
            args.append(start)
        if end:
            clauses.append("r.created_at<?")
            args.append(end)
        if incident:
            clauses.append("(r.previous_incident_id=? OR r.new_incident_id=?)")
            args.extend([incident, incident])
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT r.recurrence_id FROM incident_recurrences r JOIN incidents i "
                "ON i.incident_id=r.new_incident_id WHERE "
                + " AND ".join(clauses)
                + " ORDER BY r.recurrence_id LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
        return {
            "items": [self.recurrence_detail(r[0]) for r in rows[:limit]],
            "nextAfter": rows[limit - 1][0] if len(rows) > limit else None,
        }

    def review_recurrence(self, identity, kind, data, actor):
        require(actor["role"] == "ADMIN", "Administrator review required", 403)

        def write(db, now):
            row = self.row(db, "incident_recurrences", "recurrence_id", identity)
            require(row["version"] == data["expectedVersion"], "Recurrence changed; refresh")
            if kind == "confirm":
                require(
                    self.valid_relationship(db, row),
                    "Canonical incident/repair changed; reassess before confirmation",
                )
                require(
                    data["physicalIdentityConfirmed"],
                    "Physical infrastructure identity must be explicitly reviewed",
                    422,
                )
                # Temporal ordering is strict for every edge, so cycles cannot be introduced.
                state, event = "CONFIRMED_RECURRENCE", "RecurrenceConfirmed"
            elif kind == "dismiss":
                state, event = "DISMISSED", "RecurrenceDismissed"
            else:
                state, event = "INSUFFICIENT_EVIDENCE", "PotentialRecurrenceDetected"
            db.execute(
                "UPDATE incident_recurrences SET "
                "state=?,review_reason=?,reviewed_by=?,reviewed_at=?,"
                "updated_at=?,version=version+1 WHERE recurrence_id=?",
                (state, data["reason"], actor["id"], now, now, identity),
            )
            return {"recurrenceId": identity, "state": state, "version": row["version"] + 1}, [
                (event, row["new_incident_id"], {"recurrenceId": identity})
            ]

        return self.transaction("RECURRENCE_" + kind.upper(), data, actor, identity, write)

    def intelligence_snapshot(self):
        with self.store.connection() as db:
            db.execute("BEGIN")
            repairs = [
                dict(r)
                for r in db.execute(
                    "SELECT incident_id,state,verified_at,cycle,submitted_at "
                    "FROM repair_attempts LIMIT 10001"
                )
            ]
            recurrences = [
                dict(r)
                for r in db.execute(
                    "SELECT r.recurrence_id,r.previous_incident_id,r.new_incident_id,r.state,"
                    "(old.status='RESOLVED' AND new.status IN ('OPEN','RESOLVED') "
                    "AND ((r.state='CONFIRMED_RECURRENCE' "
                    "AND po.membership_epoch="
                    "json_extract(r.explanation,'$.previousMembershipEpoch') "
                    "AND pn.membership_epoch=json_extract(r.explanation,'$.newMembershipEpoch')) "
                    "OR (r.state<>'CONFIRMED_RECURRENCE' AND old.version=r.previous_version "
                    "AND new.version=r.new_version)) "
                    "AND a.state='VERIFIED_RESOLVED' AND old.resolved_at=a.verified_at "
                    "AND julianday(new.first_reported_at)>julianday(a.verified_at)) AS valid "
                    "FROM incident_recurrences r JOIN incidents old ON "
                    "old.incident_id=r.previous_incident_id "
                    "JOIN incidents new ON new.incident_id=r.new_incident_id "
                    "JOIN incident_priority po ON po.incident_id=old.incident_id "
                    "JOIN incident_priority pn ON pn.incident_id=new.incident_id "
                    "JOIN repair_attempts a ON a.attempt_id=r.repair_attempt_id LIMIT 10001"
                )
            ]
            require(
                len(repairs) <= 10000 and len(recurrences) <= 10000,
                "Intelligence projection bound exceeded; narrow/rebuild scoped projection",
                413,
            )
            revision = db.execute(
                "SELECT revision FROM analytics_meta WHERE singleton=1"
            ).fetchone()[0]
            return {"repairs": repairs, "recurrences": recurrences, "revision": revision}

    def revision(self):
        with self.store.connection() as db:
            return db.execute("SELECT revision FROM analytics_meta WHERE singleton=1").fetchone()[0]

    def submitting_officer(self, attempt_id, incident_id):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT a.officer_id FROM repair_attempts a JOIN users u ON u.id=a.officer_id "
                "JOIN officer_memberships m ON m.officer_id=a.officer_id "
                "AND m.department_id=a.department_id JOIN departments d ON d.id=a.department_id "
                "WHERE a.attempt_id=? AND a.incident_id=? AND u.role='OFFICER' "
                "AND u.is_active=1 AND u.is_verified=1 AND m.active=1 AND d.active=1",
                (attempt_id, incident_id),
            ).fetchone()
            return row[0] if row else None

    def fairness_reviews(self, after="", limit=25):
        with self.store.connection() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM fairness_review_records WHERE review_id>? "
                    "ORDER BY review_id LIMIT ?",
                    (after, limit + 1),
                )
            ]
        for row in rows:
            row["context"] = json.loads(row["context"])
        return {
            "items": rows[:limit],
            "nextAfter": rows[limit - 1]["review_id"] if len(rows) > limit else None,
        }

    def save_fairness_review(self, identity, data, actor):
        require(actor["role"] == "ADMIN", "Administrator review required", 403)

        def write(db, now):
            row = db.execute(
                "SELECT version FROM fairness_review_records WHERE review_id=?", (identity,)
            ).fetchone()
            require(
                (row[0] if row else 0) == data["expectedVersion"],
                "Fairness review changed; refresh",
            )
            if row:
                db.execute(
                    "UPDATE fairness_review_records SET "
                    "state=?,notes=?,actor_id=?,version=version+1,updated_at=? "
                    "WHERE review_id=? AND area_id=? AND context=?",
                    (
                        data["state"],
                        data["notes"],
                        actor["id"],
                        now,
                        identity,
                        data["areaId"],
                        encoded(data["context"]),
                    ),
                )
                require(
                    db.execute("SELECT changes()").fetchone()[0] == 1,
                    "Review area/context cannot change",
                )
            else:
                db.execute(
                    "INSERT INTO fairness_review_records VALUES(?,?,?,?,?,?,1,?,?)",
                    (
                        identity,
                        data["areaId"],
                        encoded(data["context"]),
                        data["state"],
                        data["notes"],
                        actor["id"],
                        now,
                        now,
                    ),
                )
            return {
                "reviewId": identity,
                "state": data["state"],
                "version": (row[0] if row else 0) + 1,
            }, [("FairnessReviewFlagged", identity, {"reviewId": identity})]

        return self.transaction("FAIRNESS_REVIEW", data, actor, identity, write)
