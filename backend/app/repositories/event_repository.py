"""SQLite transport and execution store. Claims are serialized by the database, not Python locks."""

import json
from uuid import uuid4

from app.events.schema import Event, consumer, new_event, utcnow
from app.models.incident import IncidentError, stable_id


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def backoff(attempt):
    return min(300, 2 ** min(attempt, 9))


class SQLiteEvents:
    lease_seconds = 120

    def __init__(self, store, clock=utcnow):
        self.store, self.clock = store, clock

    @staticmethod
    def put(db, event):
        from app.events.schema import check_causation

        def parent(identity):
            row = db.execute(
                "SELECT causation_id FROM event_outbox WHERE event_id=?", (identity,)
            ).fetchone()
            return row[0] if row else None

        check_causation(event, parent)
        db.execute(
            "INSERT OR IGNORE INTO event_outbox(event_id,event_type,aggregate_type,aggregate_id,"
            "correlation_id,causation_id,occurred_at,payload) VALUES(?,?,?,?,?,?,?,?)",
            (
                str(event.eventId),
                event.eventType,
                event.aggregateType,
                str(event.aggregateId),
                str(event.correlationId),
                str(event.causationId) if event.causationId else None,
                event.occurredAt.isoformat(),
                encoded(event.model_dump(mode="json")["payload"]),
            ),
        )

    def publish(self, event):
        with self.store.connection() as db:
            self.put(db, event)

    def claim_outbox(self):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM event_outbox WHERE status IN('PENDING','RETRY','RUNNING') "
                "AND available_at<=? ORDER BY available_at,event_id LIMIT 1",
                (self.clock().timestamp(),),
            ).fetchone()
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                "UPDATE event_outbox SET "
                "status='RUNNING',attempts=attempts+1,lease_token=?,available_at=? WHERE "
                "event_id=?",
                (token, self.clock().timestamp() + self.lease_seconds, row["event_id"]),
            )
            return dict(row) | {"lease_token": token, "attempts": row["attempts"] + 1}

    @staticmethod
    def envelope(row):
        return Event.parse(
            {
                "eventId": row["event_id"],
                "eventType": row["event_type"],
                "eventVersion": row["event_version"],
                "aggregateType": row["aggregate_type"],
                "aggregateId": row["aggregate_id"],
                "correlationId": row["correlation_id"],
                "causationId": row["causation_id"],
                "occurredAt": row["occurred_at"],
                "payload": json.loads(row["payload"]),
            }
        )

    def enqueue(self, event):
        name = consumer(event)
        identity = stable_id(f"event/{event.eventId}/{name}/1")
        with self.store.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO "
                "event_queue(message_id,event_id,consumer,envelope,created_at) "
                "VALUES(?,?,?,?,?)",
                (
                    identity,
                    str(event.eventId),
                    name,
                    event.model_dump_json(),
                    self.clock().isoformat(),
                ),
            )
        return identity

    def dispatch_one(self, transport=None):
        row = self.claim_outbox()
        if row is None:
            return False
        try:
            if row["attempts"] > 5:
                raise RuntimeError("Dispatcher lease attempts exhausted")
            event = self.envelope(row)
            (transport or self.enqueue)(event)
        except Exception as error:
            # Invalid events are preserved visibly in the same DLQ as consumer failures.
            permanent = isinstance(error, (ValueError, KeyError, TypeError))
            terminal = permanent or row["attempts"] >= 5
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT lease_token,status FROM event_outbox WHERE event_id=?",
                    (row["event_id"],),
                ).fetchone()
                if not current or current[0] != row["lease_token"] or current[1] != "RUNNING":
                    return True
                if terminal:
                    raw = encoded(
                        {
                            "eventId": row["event_id"],
                            "eventType": row["event_type"],
                            "aggregateId": row["aggregate_id"],
                            "correlationId": row["correlation_id"],
                        }
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO "
                        "event_queue(message_id,event_id,consumer,envelope,state,created_at"
                        ",dead_at,error_category,attempts) VALUES(?,?,?,?,'DEAD',?,?,?,?)",
                        (
                            stable_id("dispatch/" + row["event_id"]),
                            row["event_id"],
                            "dispatch",
                            raw,
                            self.clock().isoformat(),
                            self.clock().isoformat(),
                            "INVALID_EVENT" if permanent else "DISPATCH_FAILED",
                            row["attempts"],
                        ),
                    )
                    db.execute(
                        "UPDATE event_queue SET state='DEAD',dead_at=?,acknowledged_at=NULL,"
                        "error_category=?,attempts=? WHERE event_id=? AND consumer='dispatch'",
                        (
                            self.clock().isoformat(),
                            "INVALID_EVENT" if permanent else "DISPATCH_FAILED",
                            row["attempts"],
                            row["event_id"],
                        ),
                    )
                db.execute(
                    "UPDATE event_outbox SET status=?,available_at=?,error_category=? "
                    "WHERE event_id=? AND lease_token=?",
                    (
                        "FAILED" if terminal else "RETRY",
                        self.clock().timestamp() + backoff(row["attempts"]),
                        "INVALID_EVENT" if permanent else "TRANSPORT_UNAVAILABLE",
                        row["event_id"],
                        row["lease_token"],
                    ),
                )
            return True
        # Crash between enqueue and this update is safe: delivery has a stable identity.
        with self.store.connection() as db:
            db.execute(
                "UPDATE event_outbox SET "
                "status='DISPATCHED',dispatched_at=?,error_category=NULL WHERE event_id=? "
                "AND lease_token=?",
                (self.clock().isoformat(), row["event_id"], row["lease_token"]),
            )
        return True

    def claim(self):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM event_queue WHERE state IN('PENDING','RETRY','RUNNING') AND "
                "available_at<=? ORDER BY available_at,message_id LIMIT 1",
                (self.clock().timestamp(),),
            ).fetchone()
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                "UPDATE event_queue SET "
                "state='RUNNING',lease_token=?,attempts=attempts+1,available_at=? WHERE "
                "message_id=?",
                (token, self.clock().timestamp() + self.lease_seconds, row["message_id"]),
            )
            return dict(row) | {"lease_token": token, "attempts": row["attempts"] + 1}

    @staticmethod
    def guard(db, message):
        row = db.execute(
            "SELECT lease_token,state FROM event_queue WHERE message_id=?", (message["message_id"],)
        ).fetchone()
        if not row or row[0] != message["lease_token"] or row[1] != "RUNNING":
            raise IncidentError(409, "Processing lease lost; another worker owns this message")

    def completed(self, event, name):
        with self.store.connection() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM event_receipts WHERE event_id=? AND consumer=? AND "
                    "handler_version=1",
                    (str(event.eventId), name),
                ).fetchone()
            )

    def ack(self, message, event):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            now = self.clock().isoformat()
            db.execute(
                "INSERT OR IGNORE INTO event_receipts VALUES(?,?,1,?)",
                (str(event.eventId), message["consumer"], now),
            )
            db.execute(
                "UPDATE event_queue SET "
                "state='COMPLETE',processed_at=?,error_category=NULL WHERE message_id=?",
                (now, message["message_id"]),
            )

    def fail(self, message, permanent=False):
        terminal = permanent or message["attempts"] >= message["max_attempts"]
        category = (
            "PERMANENT_EVENT_ERROR"
            if permanent
            else "RETRIES_EXHAUSTED"
            if terminal
            else "TRANSIENT_STEP_ERROR"
        )
        now = self.clock()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            db.execute(
                "UPDATE event_queue SET state=?,available_at=?,error_category=?,dead_at=? "
                "WHERE message_id=?",
                (
                    "DEAD" if terminal else "RETRY",
                    now.timestamp() + backoff(message["attempts"]),
                    category,
                    now.isoformat() if terminal else None,
                    message["message_id"],
                ),
            )
            workflow = db.execute(
                "SELECT * FROM workflow_executions WHERE event_id=?", (message["event_id"],)
            ).fetchone()
            if workflow:
                db.execute(
                    "UPDATE workflow_steps SET status='FAILED',result=?,updated_at=? "
                    "WHERE workflow_id=? AND status='RUNNING'",
                    (
                        encoded({"errorCategory": category}),
                        now.isoformat(),
                        workflow["workflow_id"],
                    ),
                )
                db.execute(
                    "UPDATE workflow_executions SET status=?,error_category=?,updated_at=? "
                    "WHERE workflow_id=? AND status NOT "
                    "IN('COMPLETED','COMPLETED_WITH_REVIEW_REQUIRED','CANCELLED')",
                    (
                        "FAILED" if terminal else "WAITING_RETRY",
                        category,
                        now.isoformat(),
                        workflow["workflow_id"],
                    ),
                )
                if terminal:
                    event = new_event(
                        "WorkflowFailed",
                        workflow["aggregate_id"],
                        correlation=workflow["correlation_id"],
                        cause=message["event_id"],
                        now=now,
                    )
                    # Stable failure identity prevents recursive/flooding failure alerts.
                    event = Event.parse(
                        event.model_dump(mode="json")
                        | {"eventId": stable_id("workflow-failed/" + workflow["workflow_id"])}
                    )
                    self.put(db, event)
        return terminal

    def workflow_begin(self, event, message):
        identity = stable_id("IncidentTriageWorkflow/1/" + str(event.aggregateId))
        now = self.clock().isoformat()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            db.execute(
                "INSERT OR IGNORE INTO "
                "workflow_executions(workflow_id,workflow_type,aggregate_id,correlation_id,"
                "event_id,updated_at) VALUES(?,'IncidentTriageWorkflow',?,?,?,?)",
                (
                    identity,
                    str(event.aggregateId),
                    str(event.correlationId),
                    str(event.eventId),
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM workflow_executions WHERE workflow_id=?", (identity,)
            ).fetchone()
            if row["status"] not in ("COMPLETED", "COMPLETED_WITH_REVIEW_REQUIRED", "CANCELLED"):
                if (
                    row["status"] == "RUNNING"
                    and row["owner_token"] != message["lease_token"]
                    and row["lease_until"] > self.clock().timestamp()
                ):
                    raise RuntimeError("Workflow is leased by another event consumer")
                db.execute(
                    "UPDATE workflow_executions SET "
                    "status='RUNNING',attempt_count=attempt_count+1,started_at=coalesce(sta"
                    "rted_at,?),updated_at=?,event_id=?,error_category=NULL,owner_token=?,l"
                    "ease_until=? WHERE workflow_id=?",
                    (
                        now,
                        now,
                        str(event.eventId),
                        message["lease_token"],
                        self.clock().timestamp() + self.lease_seconds,
                        identity,
                    ),
                )
            return dict(row)

    def step(self, identity, step, result=None, message=None):
        with self.store.connection() as db:
            if result is None:
                row = db.execute(
                    "SELECT result FROM workflow_steps WHERE workflow_id=? AND step=? AND "
                    "status='COMPLETED'",
                    (identity, step),
                ).fetchone()
                return json.loads(row[0]) if row else None
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            now = self.clock().isoformat()
            db.execute(
                "INSERT INTO workflow_steps VALUES(?,?,'COMPLETED',?,?,1) ON "
                "CONFLICT(workflow_id,step) DO UPDATE SET "
                "status='COMPLETED',result=excluded.result,updated_at=excluded.updated_at",
                (identity, step, encoded(result), now),
            )
            db.execute(
                "UPDATE workflow_executions SET "
                "current_step=?,updated_at=?,incident_id=coalesce(?,incident_id),review_req"
                "uired=max(review_required,?) WHERE workflow_id=?",
                (
                    step,
                    now,
                    result.get("incidentId"),
                    int(result.get("reviewRequired", False)),
                    identity,
                ),
            )

    def step_start(self, identity, step, message):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            db.execute(
                "INSERT INTO workflow_steps VALUES(?,?,'RUNNING','{}',?,1) "
                "ON CONFLICT(workflow_id,step) DO UPDATE SET status='RUNNING',"
                "updated_at=excluded.updated_at,attempts=attempts+1",
                (identity, step, self.clock().isoformat()),
            )
            db.execute(
                "UPDATE workflow_executions SET current_step=?,updated_at=? WHERE workflow_id=?",
                (step, self.clock().isoformat(), identity),
            )

    def workflow_finish(self, identity, message, cancelled=False):
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.guard(db, message)
            completed = db.execute(
                "SELECT count(*) FROM workflow_steps WHERE workflow_id=? AND status='COMPLETED'",
                (identity,),
            ).fetchone()[0]
            if not cancelled and completed != 6:
                raise IncidentError(409, "Required workflow stages have not completed")
            db.execute(
                "UPDATE workflow_executions SET status=CASE WHEN ? THEN 'CANCELLED' WHEN "
                "review_required=1 THEN 'COMPLETED_WITH_REVIEW_REQUIRED' ELSE 'COMPLETED' "
                "END,current_step='CompleteWorkflow',completed_at=?,updated_at=?,"
                "error_category=NULL WHERE workflow_id=?",
                (int(cancelled), self.clock().isoformat(), self.clock().isoformat(), identity),
            )

    def notify(self, event, recipient, kind, title, message, entity_type, identity, url):
        dedup = f"{event.eventId}/{recipient}/{kind}"
        with self.store.connection() as db:
            # Recheck account eligibility at delivery time, not from an event-provided user ID.
            db.execute(
                "INSERT OR IGNORE INTO "
                "notifications(notification_id,recipient_user_id,notification_type,title,me"
                "ssage,entity_type,entity_id,target_url,created_at,deduplication_key) "
                "SELECT ?,?,?,?,?,?,?,?,?,? WHERE EXISTS(SELECT 1 FROM users WHERE id=? "
                "AND is_active=1 AND is_verified=1 AND role=?)",
                (
                    stable_id(dedup),
                    recipient,
                    kind,
                    title,
                    message,
                    entity_type,
                    identity,
                    url,
                    self.clock().isoformat(),
                    dedup,
                    recipient,
                    "ADMIN"
                    if kind in ("INCIDENT_OVERDUE", "URGENT_HAZARD_REVIEW", "ADMIN_ACTION_REQUIRED")
                    else "OFFICER"
                    if kind in ("OFFICER_ASSIGNED", "OFFICER_REPAIR_UPDATE")
                    else "CITIZEN",
                ),
            )

    def admins(self):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT id FROM users WHERE role='ADMIN' AND is_active=1 AND is_verified=1 "
                "ORDER BY id LIMIT 101"
            ).fetchall()
            if len(rows) > 100:
                raise IncidentError(409, "Administrator notification recipient bound exceeded")
            return [r[0] for r in rows]

    def notifications(self, user, limit=20, after=None, kind=None, read=None):
        where, args = ["recipient_user_id=?"], [user]
        if after:
            where.append("(created_at,notification_id)<(?,?)")
            args.extend(after)
        if kind:
            where.append("notification_type=?")
            args.append(kind)
        if read is not None:
            where.append("read_at IS NOT NULL" if read else "read_at IS NULL")
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT * FROM notifications WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at DESC,notification_id DESC LIMIT ?",
                [*args, limit + 1],
            ).fetchall()
            return {
                "items": [
                    {
                        "notificationId": r["notification_id"],
                        "type": r["notification_type"],
                        "title": r["title"],
                        "message": r["message"],
                        "targetUrl": r["target_url"],
                        "createdAt": r["created_at"],
                        "read": bool(r["read_at"]),
                        "isSimulated": False,
                        "deliveryStatus": r["delivery_status"],
                    }
                    for r in rows[:limit]
                ],
                "after": [rows[limit - 1]["created_at"], rows[limit - 1]["notification_id"]]
                if len(rows) > limit
                else None,
            }

    def unread(self, user):
        with self.store.connection() as db:
            return {
                "unreadCount": db.execute(
                    "SELECT count(*) FROM notifications WHERE recipient_user_id=? AND "
                    "read_at IS NULL",
                    (user,),
                ).fetchone()[0]
            }

    def read(self, user, identity=None):
        with self.store.connection() as db:
            if (
                identity
                and not db.execute(
                    "SELECT 1 FROM notifications WHERE notification_id=? AND recipient_user_id=?",
                    (identity, user),
                ).fetchone()
            ):
                raise IncidentError(404, "Notification not found")
            db.execute(
                "UPDATE notifications SET read_at=coalesce(read_at,?) WHERE recipient_user_id=?"
                + (" AND notification_id=?" if identity else ""),
                [self.clock().isoformat(), user, *([identity] if identity else [])],
            )
        return self.unread(user)

    def listing(self, kind, limit=20, after=None, status=None):
        table, order, key = (
            ("event_queue", "created_at", "message_id")
            if kind == "dead"
            else ("workflow_executions", "updated_at", "workflow_id")
        )
        where, args = (["state='DEAD'"], []) if kind == "dead" else (["1=1"], [])
        if status and kind != "dead":
            where.append("status=?")
            args.append(status)
        if after:
            where.append(f"({order},{key})<(?,?)")
            args.extend(after)
        with self.store.connection() as db:
            rows = db.execute(
                f"SELECT * FROM {table} WHERE "
                + " AND ".join(where)
                + f" ORDER BY {order} DESC,{key} DESC LIMIT ?",
                [*args, limit + 1],
            ).fetchall()
            items = [self.safe_message(r) if kind == "dead" else dict(r) for r in rows[:limit]]
            return {
                "items": items,
                "after": [rows[limit - 1][order], rows[limit - 1][key]]
                if len(rows) > limit
                else None,
            }

    @staticmethod
    def safe_message(row):
        # Deliberately never return the envelope or arbitrary diagnostic strings.
        from uuid import UUID

        try:
            correlation = str(UUID(json.loads(row["envelope"]).get("correlationId", "")))
        except (ValueError, TypeError, AttributeError):
            correlation = None
        return {
            k: row[k]
            for k in (
                "message_id",
                "event_id",
                "consumer",
                "state",
                "attempts",
                "error_category",
                "created_at",
                "dead_at",
                "redrives",
                "acknowledged_at",
            )
        } | {"correlation_id": correlation}

    def detail(self, identity):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM workflow_executions WHERE workflow_id=?", (identity,)
            ).fetchone()
            if not row:
                raise IncidentError(404, "Workflow not found")
            return dict(row) | {
                "steps": [
                    dict(r) | {"result": json.loads(r["result"])}
                    for r in db.execute(
                        "SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY "
                        "updated_at,step LIMIT 20",
                        (identity,),
                    )
                ]
            }

    def summary(self):
        with self.store.connection() as db:
            states = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT status,count(*) FROM workflow_executions GROUP BY status"
                )
            }
            queues = {
                r[0]: r[1]
                for r in db.execute("SELECT state,count(*) FROM event_queue GROUP BY state")
            }
            return {
                "workflows": states,
                "queue": queues,
                "pendingEvents": db.execute(
                    "SELECT count(*) FROM event_outbox WHERE status IN('PENDING','RETRY','RUNNING')"
                ).fetchone()[0],
                "averageProcessingSeconds": db.execute(
                    "SELECT avg((julianday(completed_at)-julianday(started_at))*86400) "
                    "FROM workflow_executions WHERE completed_at IS NOT NULL AND "
                    "started_at IS NOT NULL"
                ).fetchone()[0],
                "openEscalations": db.execute(
                    "SELECT count(*) FROM escalations WHERE status='OPEN'"
                ).fetchone()[0],
            }

    def replay(self, identity, data, actor, workflow=False, acknowledge=False):
        if not data["confirmed"]:
            raise IncidentError(422, "Explicit replay confirmation required")
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Durable operation receipt: identical retry cannot consume a second redrive budget.
            op = stable_id(f"workflow-control/{actor}/{data['operationId']}")
            fingerprint = encoded(
                {"id": identity, "data": data, "workflow": workflow, "ack": acknowledge}
            )
            previous = db.execute("SELECT reason FROM workflow_audit WHERE id=?", (op,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise IncidentError(409, "Operation ID reused with different input")
                return {"accepted": True}
            if workflow:
                wf = db.execute(
                    "SELECT * FROM workflow_executions WHERE workflow_id=?", (identity,)
                ).fetchone()
                if not wf or wf["status"] not in ("FAILED", "WAITING_RETRY"):
                    raise IncidentError(409, "Workflow is not eligible for retry")
                row = db.execute(
                    "SELECT * FROM event_queue WHERE event_id=? AND consumer='triage'",
                    (wf["event_id"],),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM event_queue WHERE message_id=?", (identity,)
                ).fetchone()
            if not row or row["state"] not in ("DEAD", "RETRY"):
                raise IncidentError(409, "Message is not eligible for replay")
            if acknowledge:
                db.execute(
                    "UPDATE event_queue SET acknowledged_at=? WHERE message_id=?",
                    (self.clock().isoformat(), row["message_id"]),
                )
            else:
                if row["redrives"] >= 3 or row["error_category"] == "PERMANENT_EVENT_ERROR":
                    raise IncidentError(
                        409,
                        "Message requires source/configuration repair; automatic redrive "
                        "prohibited",
                    )
                if row["consumer"] == "dispatch":
                    original = db.execute(
                        "SELECT * FROM event_outbox WHERE event_id=?", (row["event_id"],)
                    ).fetchone()
                    try:
                        if not original:
                            raise ValueError("Missing outbox source")
                        self.envelope(original)
                    except (ValueError, TypeError) as error:
                        raise IncidentError(
                            409, "Invalid source event requires authorized source repair"
                        ) from error
                    db.execute(
                        "UPDATE event_outbox SET status='PENDING',attempts=0,available_at=0,"
                        "error_category=NULL,lease_token=NULL WHERE event_id=?",
                        (row["event_id"],),
                    )
                    db.execute(
                        "UPDATE event_queue SET state='COMPLETE',redrives=redrives+1,"
                        "processed_at=? WHERE message_id=?",
                        (self.clock().isoformat(), row["message_id"]),
                    )
                else:
                    Event.parse(row["envelope"])
                    db.execute(
                        "UPDATE event_queue SET state='PENDING',attempts=0,redrives=redrives+1,"
                        "available_at=0,lease_token=NULL,dead_at=NULL,error_category=NULL "
                        "WHERE message_id=?",
                        (row["message_id"],),
                    )
                    db.execute(
                        "UPDATE workflow_executions SET status='PENDING',updated_at=? "
                        "WHERE event_id=?",
                        (self.clock().isoformat(), row["event_id"]),
                    )
            db.execute(
                "INSERT INTO workflow_audit VALUES(?,?,?,?,?,?)",
                (
                    op,
                    identity,
                    "ACKNOWLEDGE" if acknowledge else "REDRIVE",
                    actor,
                    fingerprint,
                    self.clock().isoformat(),
                ),
            )
            return {"accepted": True}
