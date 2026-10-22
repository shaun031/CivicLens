"""Conditional, bounded workflow records on one sparse-indexed operations table.

No routine Scan, no SQLite fallback, no network at import. Event outbox Put actions can join
existing business transactions; the transport confirms acceptance before removing due indexing.
"""

import json
from datetime import datetime
from uuid import UUID, uuid4

from botocore.exceptions import ClientError

from app.events.schema import Event, consumer, utcnow
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.models.incident import IncidentError, stable_id
from app.repositories.event_repository import backoff, encoded


def event_action(settings, event):
    if not settings.workflow_table_name:
        return []  # Legacy fixtures; cloud execution requires the configured operations table.
    return [
        {
            "Put": {
                "TableName": settings.workflow_table_name,
                "Item": marshal(
                    {
                        "pk": "outbox#" + str(event.eventId),
                        "sk": "0",
                        "revision": 1,
                        "queue": "outbox",
                        "due": "0000000000000#" + str(event.eventId),
                        "data": {
                            "event": event.model_dump(mode="json"),
                            "status": "PENDING",
                            "attempts": 0,
                            "available_at": 0,
                        },
                    }
                ),
                "ConditionExpression": "attribute_not_exists(pk)",
            }
        }
    ]


class DynamoEvents:
    lease_seconds = 600  # Longer than the bounded five-minute Standard execution.

    def __init__(self, settings, incidents, clock=utcnow):
        self.settings, self.incidents, self.clock = settings, incidents, clock
        self.table = settings.workflow_table_name

    def call(self, method, **args):
        if not self.table:
            raise IncidentError(503, "WORKFLOW_TABLE_NAME is required; no local fallback")
        return getattr(self.incidents.complaints.client, method)(**args)

    def load(self, key):
        result = self.call(
            "get_item",
            TableName=self.table,
            Key=marshal({"pk": key, "sk": "0"}),
            ConsistentRead=True,
        )
        if not result.get("Item"):
            return None
        item = json.loads(
            json.dumps(
                unmarshal(result["Item"]),
                default=lambda value: int(value) if value % 1 == 0 else float(value),
            )
        )
        return item["data"] | {"_revision": int(item["revision"]), "_key": key}

    def write_action(self, key, data, queue=None, due=None, revision=0):
        value = {k: v for k, v in data.items() if not k.startswith("_")}
        item = {"pk": key, "sk": "0", "revision": revision + 1, "data": value}
        if queue:
            item.update(
                queue=queue, due=due or str(value.get("updated_at", value.get("created_at", key)))
            )
        condition = (
            {
                "ConditionExpression": "revision=:r",
                "ExpressionAttributeValues": marshal({":r": revision}),
            }
            if revision
            else {"ConditionExpression": "attribute_not_exists(pk)"}
        )
        return {"Put": {"TableName": self.table, "Item": marshal(item), **condition}}

    def save(self, key, data, queue=None, due=None, revision=0):
        try:
            self.call("put_item", **self.write_action(key, data, queue, due, revision)["Put"])
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise IncidentError(
                    409, "Concurrent workflow state change; retry safely"
                ) from error
            raise
        return data | {"_revision": revision + 1, "_key": key}

    def query(self, queue, limit=20, after=None, descending=False, due=None):
        values = {":q": queue}
        condition = "#q=:q"
        if due:
            condition += " AND #d<=:d"
            values[":d"] = due
        args = {
            "TableName": self.table,
            "IndexName": "ByQueue",
            "KeyConditionExpression": condition,
            "ExpressionAttributeNames": {"#q": "queue", **({"#d": "due"} if due else {})},
            "ExpressionAttributeValues": marshal(values),
            "Limit": limit,
            "ScanIndexForward": not descending,
        }
        if after:
            args["ExclusiveStartKey"] = marshal(
                {"pk": after[0], "sk": "0", "queue": queue, "due": after[1]}
            )
        result = self.call("query", **args)
        items = []
        for key in result.get("Items", []):
            value = unmarshal(key)
            row = self.load(value["pk"])
            if row:
                items.append(row)
        last = unmarshal(result["LastEvaluatedKey"]) if result.get("LastEvaluatedKey") else None
        return items, [last["pk"], last["due"]] if last else None

    def due_key(self, seconds, identity):
        return f"{int(seconds * 1000):013d}#{identity}"

    def publish(self, event):
        from app.events.schema import check_causation

        check_causation(
            event,
            lambda identity: ((self.load("outbox#" + identity) or {}).get("event") or {}).get(
                "causationId"
            ),
        )
        actions = event_action(self.settings, event)
        if not actions:
            raise IncidentError(503, "Workflow persistence not configured")
        try:
            self.call("put_item", **actions[0]["Put"])
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def dispatch_one(self, transport=None):
        from app.integrations.events import EventBridgePublisher

        rows, _ = self.query("outbox", 1, due=self.due_key(self.clock().timestamp(), "~"))
        if not rows:
            return False
        row = rows[0]
        if (
            row["status"] in ("DISPATCHED", "FAILED")
            or row["available_at"] > self.clock().timestamp()
        ):
            return False
        row["attempts"] += 1
        row["available_at"] = self.clock().timestamp() + self.lease_seconds
        row = self.save(
            row["_key"],
            row,
            "outbox",
            self.due_key(row["available_at"], row["_key"]),
            row["_revision"],
        )
        try:
            event = Event.parse(row["event"])
            (transport or EventBridgePublisher(self.settings.event_bus_name).publish)(event)
            row.update(status="DISPATCHED", dispatched_at=self.clock().isoformat())
            self.save(row["_key"], row, revision=row["_revision"])
        except Exception as error:
            permanent = isinstance(error, (ValueError, TypeError, KeyError))
            terminal = permanent or row["attempts"] >= 5
            row.update(
                status="FAILED" if terminal else "RETRY",
                error_category="INVALID_EVENT" if permanent else "TRANSPORT_UNAVAILABLE",
                available_at=self.clock().timestamp() + backoff(row["attempts"]),
            )
            self.save(
                row["_key"],
                row,
                None if terminal else "outbox",
                self.due_key(row["available_at"], row["_key"]),
                row["_revision"],
            )
            if terminal:
                if permanent:
                    raw = row.get("event") if isinstance(row.get("event"), dict) else {}
                    try:
                        event_id = str(UUID(str(raw.get("eventId"))))
                    except ValueError:
                        event_id = "UNKNOWN"
                    identity = stable_id("dispatch/" + row["_key"])
                    previous = self.load("message#" + identity)
                    data = {
                        "message_id": identity,
                        "event_id": event_id,
                        "consumer": "dispatch",
                        "envelope": encoded({"correlationId": raw.get("correlationId")}),
                        "state": "DEAD",
                        "attempts": row["attempts"],
                        "max_attempts": 5,
                        "created_at": self.clock().isoformat(),
                        "dead_at": self.clock().isoformat(),
                        "redrives": (previous or {}).get("redrives", 0),
                        "acknowledged_at": None,
                        "error_category": "PERMANENT_EVENT_ERROR",
                    }
                    self.save(
                        "message#" + identity,
                        data,
                        "dead",
                        revision=(previous or {}).get("_revision", 0),
                    )
                    return True
                message = self.enqueue(Event.parse(row["event"]))
                data = self.load("message#" + message)
                data.update(
                    state="DEAD", dead_at=self.clock().isoformat(), error_category="DISPATCH_FAILED"
                )
                self.save(data["_key"], data, "dead", revision=data["_revision"])
        return True

    def enqueue(self, event):
        identity = stable_id(f"event/{event.eventId}/{consumer(event)}/1")
        key = "message#" + identity
        if not self.load(key):
            self.save(
                key,
                {
                    "message_id": identity,
                    "event_id": str(event.eventId),
                    "consumer": consumer(event),
                    "envelope": event.model_dump_json(),
                    "state": "PENDING",
                    "attempts": 0,
                    "max_attempts": 5,
                    "available_at": 0,
                    "lease_token": None,
                    "redrives": 0,
                    "created_at": self.clock().isoformat(),
                    "dead_at": None,
                    "acknowledged_at": None,
                    "error_category": None,
                },
                "messages",
                self.due_key(0, identity),
            )
        return identity

    def prepare_execution(self, identity):
        row = self.load("message#" + identity)
        if row and row["state"] == "PENDING":
            row.update(state="STARTING", available_at=self.clock().timestamp() + self.lease_seconds)
            self.save(
                row["_key"],
                row,
                "messages",
                self.due_key(row["available_at"], identity),
                row["_revision"],
            )

    def claim(self, identity=None):
        if identity:
            row = self.load("message#" + identity)
        else:
            rows, _ = self.query("messages", 1, due=self.due_key(self.clock().timestamp(), "~"))
            row = rows[0] if rows else None
        if (
            not row
            or row["state"] not in ("PENDING", "STARTING", "RUNNING", "RETRY")
            or (
                row["available_at"] > self.clock().timestamp()
                and not (identity and row["state"] == "STARTING")
            )
        ):
            return None
        row.update(
            state="RUNNING",
            attempts=row["attempts"] + 1,
            lease_token=str(uuid4()),
            available_at=self.clock().timestamp() + self.lease_seconds,
        )
        return self.save(
            row["_key"],
            row,
            "messages",
            self.due_key(row["available_at"], row["message_id"]),
            row["_revision"],
        )

    def guard(self, message):
        row = self.load("message#" + message["message_id"])
        if not row or row["state"] != "RUNNING" or row["lease_token"] != message["lease_token"]:
            raise IncidentError(409, "Message lease lost")
        return row

    def completed(self, event, name):
        return self.load(f"receipt#{event.eventId}#{name}#1") is not None

    def ack(self, message, event):
        row = self.guard(message)
        row.update(state="COMPLETE", processed_at=self.clock().isoformat(), error_category=None)
        receipt = f"receipt#{event.eventId}#{message['consumer']}#1"
        if self.load(receipt):
            self.save(row["_key"], row, revision=row["_revision"])
            return
        self.call(
            "transact_write_items",
            TransactItems=[
                self.write_action(row["_key"], row, revision=row["_revision"]),
                self.write_action(receipt, {"completed_at": self.clock().isoformat()}),
            ],
        )

    def fail(self, message, permanent=False):
        row = self.guard(message)
        terminal = permanent or row["attempts"] >= row["max_attempts"]
        row.update(
            state="DEAD" if terminal else "RETRY",
            error_category="PERMANENT_EVENT_ERROR"
            if permanent
            else "RETRIES_EXHAUSTED"
            if terminal
            else "TRANSIENT_STEP_ERROR",
            available_at=self.clock().timestamp() + backoff(row["attempts"]),
            dead_at=self.clock().isoformat() if terminal else None,
        )
        actions = [
            self.write_action(
                row["_key"],
                row,
                "dead" if terminal else "messages",
                None if terminal else self.due_key(row["available_at"], row["message_id"]),
                row["_revision"],
            )
        ]
        event = Event.parse(row["envelope"])
        key = "workflow#" + stable_id("IncidentTriageWorkflow/1/" + str(event.aggregateId))
        workflow = self.load(key)
        if (
            workflow
            and workflow.get("owner_token") == message["lease_token"]
            and workflow["status"]
            not in (
                "COMPLETED",
                "COMPLETED_WITH_REVIEW_REQUIRED",
                "CANCELLED",
            )
        ):
            workflow.update(
                status="FAILED" if terminal else "WAITING_RETRY",
                error_category=row["error_category"],
                updated_at=self.clock().isoformat(),
                lease_until=0,
            )
            for stage in workflow["steps"].values():
                if stage["status"] == "RUNNING":
                    stage.update(status="FAILED", result={"errorCategory": row["error_category"]})
            actions.append(
                self.write_action(key, workflow, "workflows", revision=workflow["_revision"])
            )
            if terminal:
                from app.events.schema import new_event

                alert = new_event(
                    "WorkflowFailed",
                    workflow["aggregate_id"],
                    correlation=workflow["correlation_id"],
                    cause=workflow["event_id"],
                )
                alert = Event.parse(
                    alert.model_dump(mode="json")
                    | {"eventId": stable_id("workflow-failed/" + workflow["workflow_id"])}
                )
                if not self.load("outbox#" + str(alert.eventId)):
                    actions.extend(event_action(self.settings, alert))
        self.call("transact_write_items", TransactItems=actions)
        return terminal

    def workflow_begin(self, event, message):
        self.guard(message)
        identity = stable_id("IncidentTriageWorkflow/1/" + str(event.aggregateId))
        key, now = "workflow#" + identity, self.clock().isoformat()
        row = self.load(key)
        if row and row["status"] in ("COMPLETED", "COMPLETED_WITH_REVIEW_REQUIRED", "CANCELLED"):
            return row
        row = row or {
            "workflow_id": identity,
            "workflow_type": "IncidentTriageWorkflow",
            "aggregate_id": str(event.aggregateId),
            "correlation_id": str(event.correlationId),
            "event_id": str(event.eventId),
            "status": "PENDING",
            "attempt_count": 0,
            "started_at": now,
            "current_step": None,
            "steps": {},
            "workflow_version": 1,
            "review_required": 0,
            "incident_id": None,
            "completed_at": None,
        }
        if (
            row.get("status") == "RUNNING"
            and row.get("owner_token") != message["lease_token"]
            and row.get("lease_until", 0) > self.clock().timestamp()
        ):
            raise RuntimeError("Workflow is already leased")
        row.update(
            status="RUNNING",
            error_category=None,
            attempt_count=row["attempt_count"] + 1,
            updated_at=now,
            owner_token=message["lease_token"],
            lease_until=self.clock().timestamp() + self.lease_seconds,
        )
        return self.save(key, row, "workflows", revision=row.get("_revision", 0))

    def step(self, identity, step, result=None, message=None):
        row = self.load("workflow#" + identity)
        if result is None:
            record = row.get("steps", {}).get(step) or {}
            return record.get("result") if record.get("status") == "COMPLETED" else None
        self.guard(message)
        row["steps"][step] = {
            "step": step,
            "status": "COMPLETED",
            "result": result,
            "updated_at": self.clock().isoformat(),
            "attempts": (row["steps"].get(step) or {}).get("attempts", 1),
        }
        row.update(
            current_step=step,
            updated_at=self.clock().isoformat(),
            incident_id=result.get("incidentId", row.get("incident_id")),
            review_required=max(
                row.get("review_required", 0), int(result.get("reviewRequired", False))
            ),
        )
        self.save(row["_key"], row, "workflows", revision=row["_revision"])

    def step_start(self, identity, step, message):
        self.guard(message)
        row = self.load("workflow#" + identity)
        previous = row["steps"].get(step) or {}
        row["steps"][step] = {
            "step": step,
            "status": "RUNNING",
            "result": {},
            "updated_at": self.clock().isoformat(),
            "attempts": previous.get("attempts", 0) + 1,
        }
        row.update(current_step=step, updated_at=self.clock().isoformat())
        self.save(row["_key"], row, "workflows", revision=row["_revision"])

    def workflow_finish(self, identity, message, cancelled=False):
        self.guard(message)
        row = self.load("workflow#" + identity)
        if not cancelled and sum(s["status"] == "COMPLETED" for s in row["steps"].values()) != 6:
            raise IncidentError(409, "Required workflow stages have not completed")
        row.update(
            status="CANCELLED"
            if cancelled
            else "COMPLETED_WITH_REVIEW_REQUIRED"
            if row["review_required"]
            else "COMPLETED",
            completed_at=self.clock().isoformat(),
            updated_at=self.clock().isoformat(),
            current_step="CompleteWorkflow",
            error_category=None,
        )
        self.save(row["_key"], row, "workflows", revision=row["_revision"])

    def notify(self, event, recipient, kind, title, message, entity_type, identity, url):
        # Trusted WorkflowService selects recipients from authoritative records.
        key = "notification#" + stable_id(f"{event.eventId}/{recipient}/{kind}")
        if self.load(key):
            return
        self.save(
            key,
            {
                "notificationId": key.split("#")[1],
                "recipient": recipient,
                "type": kind,
                "title": title,
                "message": message,
                "targetUrl": url,
                "createdAt": self.clock().isoformat(),
                "read": False,
                "isSimulated": False,
                "deliveryStatus": "IN_APP",
            },
            "notifications#" + recipient,
            self.clock().isoformat() + "#" + key,
        )

    def admins(self):
        # Trusted directory provisioning; never infer recipients from arbitrary tokens.
        return (self.load("directory#admins") or {}).get("ids", [])[:100]

    def notifications(self, user, limit=20, after=None, kind=None, read=None):
        rows, after = self.query("notifications#" + user, limit, after, True)
        return {
            "items": [
                {k: v for k, v in r.items() if not k.startswith("_") and k != "recipient"}
                for r in rows
                if r.get("recipient") == user
                and (kind is None or r["type"] == kind)
                and (read is None or r["read"] == read)
            ],
            "after": after,
        }

    def unread(self, user):
        # Strong per-user bounded manifest avoids an unbounded scan or fabricated GSI count.
        rows, after = self.query("notifications#" + user, 100)
        if after:
            raise IncidentError(
                409, "Notification count requires retention reconciliation beyond100 records"
            )
        return {"unreadCount": sum(not r["read"] for r in rows if r.get("recipient") == user)}

    def read(self, user, identity=None):
        rows = (
            [self.load("notification#" + identity)]
            if identity
            else self.query("notifications#" + user, 100)[0]
        )
        for row in rows:
            if not row or row.get("recipient") != user:
                raise IncidentError(404, "Notification not found")
            if not row["read"]:
                row.update(read=True, readAt=self.clock().isoformat())
                self.save(
                    row["_key"],
                    row,
                    "notifications#" + user,
                    row["createdAt"] + "#" + row["_key"],
                    row["_revision"],
                )
        return self.unread(user)

    def listing(self, kind, limit=20, after=None, status=None):
        rows, after = self.query("dead" if kind == "dead" else "workflows", limit, after, True)
        if kind == "dead":
            from app.repositories.event_repository import SQLiteEvents

            items = [SQLiteEvents.safe_message(r) for r in rows if r["state"] == "DEAD"]
        else:
            items = [
                {
                    k: v
                    for k, v in r.items()
                    if not k.startswith("_") and k not in ("steps", "owner_token", "lease_until")
                }
                for r in rows
                if status is None or r["status"] == status
            ]
        return {"items": items, "after": after}

    def detail(self, identity):
        row = self.load("workflow#" + identity)
        if not row:
            raise IncidentError(404, "Workflow not found")
        return {
            k: v
            for k, v in row.items()
            if not k.startswith("_") and k not in ("steps", "owner_token", "lease_until")
        } | {"steps": list(row["steps"].values())}

    def summary(self):
        rows, after = self.query("workflows", 100)
        states = {}
        for row in rows:
            states[row["status"]] = states.get(row["status"], 0) + 1
        return {
            "workflows": states,
            "queue": {},
            "pendingEvents": None,
            "averageProcessingSeconds": None,
            "openEscalations": None,
            "sampled": True,
            "sampleLimit": 100,
            "hasMore": bool(after),
            "note": "Bounded cloud sample; global metrics use basic AWS service metrics, "
            "not invented counts",
        }

    def replay(self, identity, data, actor, workflow=False, acknowledge=False):
        if not data["confirmed"]:
            raise IncidentError(422, "Explicit confirmation required")
        audit = "control#" + stable_id(actor + "/" + data["operationId"])
        fingerprint = encoded(
            {"id": identity, "data": data, "workflow": workflow, "ack": acknowledge}
        )
        receipt = self.load(audit)
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise IncidentError(409, "Operation ID reused")
            return {"accepted": True}
        if workflow:
            row = self.load("workflow#" + identity)
            if not row or row["status"] not in ("FAILED", "WAITING_RETRY"):
                raise IncidentError(409, "Workflow is not eligible")
            identity = stable_id(f"event/{row['event_id']}/triage/1")
        row = self.load("message#" + identity)
        if (
            not row
            or row["state"] not in ("DEAD", "RETRY")
            or not acknowledge
            and (row["redrives"] >= 3 or row["error_category"] == "PERMANENT_EVENT_ERROR")
        ):
            raise IncidentError(409, "Message is not eligible for redrive")
        if acknowledge:
            row["acknowledged_at"] = self.clock().isoformat()
        else:
            Event.parse(row["envelope"])
            row.update(
                state="PENDING",
                attempts=0,
                redrives=row["redrives"] + 1,
                available_at=0,
                lease_token=None,
            )
        self.call(
            "transact_write_items",
            TransactItems=[
                self.write_action(
                    row["_key"],
                    row,
                    "dead" if acknowledge else "messages",
                    None if acknowledge else self.due_key(0, identity),
                    row["_revision"],
                ),
                self.write_action(
                    audit,
                    {
                        "fingerprint": fingerprint,
                        "actor": actor,
                        "created_at": self.clock().isoformat(),
                    },
                ),
            ],
        )
        return {"accepted": True}


class DynamoSLA:
    """Prepared bounded cloud SLA persistence. Canonical due sidecars are transactionally "
    "produced."""

    def __init__(self, workflows):
        self.workflows, self.repository = workflows, workflows.repository

    def policies(self):
        return {"items": (self.repository.load("sla#policies") or {}).get("items", [])}

    def save(self, identity, data, actor):
        operation = "sla-control#" + stable_id(f"{actor}/{data['operationId']}")
        fingerprint = encoded({"policyId": identity, "data": data})
        receipt = self.repository.load(operation)
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise IncidentError(409, "SLA operation ID reused with different input")
            return self.policies()
        row = self.repository.load("sla#policies") or {"items": []}
        policy = next((p for p in row["items"] if p["policy_id"] == identity), None)
        if not data["confirmed"] or (policy or {}).get("version", 0) != data["expectedVersion"]:
            raise IncidentError(409, "SLA policy version or confirmation invalid")
        if len(row["items"]) >= 100 and policy is None:
            raise IncidentError(409, "Policy bound reached")
        value = {
            "policy_id": identity,
            "priority_band": data["priorityBand"],
            "category": data.get("category"),
            "department_id": data.get("departmentId"),
            "urgent": data["urgent"],
            "response_hours": data["responseHours"],
            "resolution_hours": data["resolutionHours"],
            "version": data["expectedVersion"] + 1,
            "updated_by": actor,
        }
        row["items"] = [p for p in row["items"] if p["policy_id"] != identity] + [value]
        if data.get("departmentId"):
            self.workflows.work.repository.department_exists(data["departmentId"])
        self.repository.call(
            "transact_write_items",
            TransactItems=[
                self.repository.write_action("sla#policies", row, revision=row.get("_revision", 0)),
                self.repository.write_action(
                    operation,
                    {
                        "fingerprint": fingerprint,
                        "actor": actor,
                        "kind": "SLA_POLICY_CHANGED",
                        "before": policy,
                        "after": value,
                        "created_at": self.repository.clock().isoformat(),
                    },
                ),
            ],
        )
        return self.policies()

    def escalations(self, limit=20, after=None):
        rows, after = self.repository.query("escalations", limit, after, True)
        return {
            "items": [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows],
            "after": after,
        }

    def acknowledge(self, identity, actor):
        row = self.repository.load("escalation#" + identity)
        if not row:
            raise IncidentError(404, "Escalation not found")
        row.update(
            status="ACKNOWLEDGED",
            acknowledged_by=actor,
            acknowledged_at=self.repository.clock().isoformat(),
        )
        self.repository.save(row["_key"], row, "escalations", row["created_at"], row["_revision"])
        return {"acknowledged": True}

    def sweep(self, size=20, dry_run=False):
        from app.events.schema import new_event
        from app.services.sla_service import first_response, target_states

        repo, now = self.repository, self.repository.clock()
        rows, _ = repo.query("sla-due", size, due=repo.due_key(now.timestamp(), "~"))
        results = []
        for row in rows:
            identity = row["incident_id"]
            incident = self.workflows.incidents.repository.load(identity)
            if not incident or incident.status != "OPEN":
                if not dry_run:
                    repo.save(row["_key"], row, revision=row["_revision"])
                results.append({"incidentId": identity, "excluded": True})
                continue
            snapshot = self.workflows.priorities.repository.snapshot(identity)
            priority = {"priority": snapshot.record["result"]}
            if (
                snapshot.incident.version != incident.version
                or self.workflows.priorities.stale_reasons(snapshot)
            ):
                if not dry_run:
                    repo.save(
                        row["_key"],
                        row,
                        "sla-due",
                        repo.due_key(now.timestamp() + 60, identity),
                        row["_revision"],
                    )
                results.append({"incidentId": identity, "pending": "PRIORITY_NOT_CURRENT"})
                continue
            assignment = self.workflows.work.detail(identity)["assignment"]
            assignment["responseAt"] = first_response(
                self.workflows.work.repository, identity, row["opened_at"]
            )
            band, urgent = (
                priority["priority"]["priorityBand"],
                priority["priority"]["urgentHazard"],
            )
            policies = self.policies()["items"]
            candidates = [
                p
                for p in policies
                if p["priority_band"] == band
                and (not p.get("category") or p["category"] == incident.category)
                and (not p.get("department_id") or p["department_id"] == assignment["departmentId"])
                and (not p.get("urgent") or urgent)
            ]
            candidates.sort(
                key=lambda p: (
                    -(
                        bool(p.get("category"))
                        + bool(p.get("department_id"))
                        + bool(p.get("urgent"))
                    ),
                    p["policy_id"],
                )
            )
            response = {"LOW": 336, "MEDIUM": 168, "HIGH": 72, "CRITICAL": 24}[band]
            policy = (
                candidates[0]
                if candidates
                else {
                    "policy_id": "DEMO-" + band,
                    "version": 1,
                    "response_hours": response,
                    "resolution_hours": {"LOW": 672, "MEDIUM": 336, "HIGH": 168, "CRITICAL": 72}[
                        band
                    ],
                }
            )
            overdue, deadlines = [], []
            for milestone, deadline, reached, breached in target_states(
                row["opened_at"], assignment, policy, now
            ):
                if breached:
                    overdue.append(milestone)
                    receipt = stable_id(f"sla/{identity}/{row['cycle']}/{milestone}")
                    key = "escalation#" + receipt
                    if not dry_run and not repo.load(key):
                        event = new_event(
                            "IncidentOverdue", identity, payload={"escalationId": receipt}, now=now
                        )
                        data = {
                            "escalation_id": receipt,
                            "incident_id": identity,
                            "milestone": milestone,
                            "cycle": row["cycle"],
                            "deadline": deadline.isoformat(),
                            "status": "OPEN",
                            "policy_id": policy["policy_id"],
                            "policy_version": policy["version"],
                            "created_at": now.isoformat(),
                        }
                        repo.call(
                            "transact_write_items",
                            TransactItems=[
                                repo.write_action(key, data, "escalations", now.isoformat()),
                                *event_action(repo.settings, event),
                                {
                                    "ConditionCheck": {
                                        "TableName": repo.table,
                                        "Key": marshal({"pk": row["_key"], "sk": "0"}),
                                        "ConditionExpression": "revision=:r",
                                        "ExpressionAttributeValues": marshal(
                                            {":r": row["_revision"]}
                                        ),
                                    }
                                },
                                {
                                    "ConditionCheck": {
                                        "TableName": repo.settings.incidents_table_name,
                                        "Key": marshal({"incidentId": identity}),
                                        "ConditionExpression": "#v=:v AND #s=:open",
                                        "ExpressionAttributeNames": {
                                            "#v": "version",
                                            "#s": "status",
                                        },
                                        "ExpressionAttributeValues": marshal(
                                            {":v": incident.version, ":open": "OPEN"}
                                        ),
                                    }
                                },
                                {
                                    "ConditionCheck": {
                                        "TableName": repo.settings.incidents_table_name,
                                        "Key": marshal({"incidentId": "work#" + identity}),
                                        "ConditionExpression": "assignment.#v=:v AND "
                                        "sourceVersion=:source",
                                        "ExpressionAttributeNames": {"#v": "version"},
                                        "ExpressionAttributeValues": marshal(
                                            {
                                                ":v": assignment["version"],
                                                ":source": incident.version,
                                            }
                                        ),
                                    }
                                },
                                {
                                    "ConditionCheck": {
                                        "TableName": repo.settings.incidents_table_name,
                                        "Key": marshal({"incidentId": "priority#" + identity}),
                                        "ConditionExpression": "generation=:g AND "
                                        "result_revision=:r",
                                        "ExpressionAttributeValues": marshal(
                                            {
                                                ":g": snapshot.record["generation"],
                                                ":r": snapshot.record.get("result_revision", 0),
                                            }
                                        ),
                                    }
                                },
                            ],
                        )
                elif not reached:
                    deadlines.append(deadline.timestamp())
            if not dry_run:
                repo.save(
                    row["_key"],
                    row,
                    "sla-due",
                    repo.due_key(min(deadlines + [now.timestamp() + 3600]), identity),
                    row["_revision"],
                )
            results.append({"incidentId": identity, "overdue": overdue})
        return {"checked": len(rows), "results": results, "dryRun": dry_run}


def incident_event_actions(repository, plan):
    """Join the original bounded P7 transaction; never emit ahead of domain commit."""
    from app.events.schema import new_event

    settings = repository.complaints.settings
    if not settings.workflow_table_name:
        return []
    actions = []
    for identity, after in plan.after.items():
        before = plan.before.get(identity)
        kind = (
            "IncidentStatusChanged"
            if before and before.status != after.status
            else "IncidentMembershipChanged"
        )
        event = new_event(
            kind,
            identity,
            correlation=plan.operation_id,
            now=datetime.fromisoformat(plan.created_at.replace("Z", "+00:00")),
        )
        event = Event.parse(
            event.model_dump(mode="json")
            | {"eventId": stable_id(f"domain/{plan.operation_id}/{identity}/{kind}")}
        )
        actions.extend(event_action(settings, event))
        if not before or before.status != "OPEN" and after.status == "OPEN":
            baseline = after.updatedAt if before else after.firstReportedAt
            actions.append(
                {
                    "Put": {
                        "TableName": settings.workflow_table_name,
                        "Item": marshal(
                            {
                                "pk": "sla#" + identity,
                                "sk": "0",
                                "revision": 1,
                                "queue": "sla-due",
                                "due": "0000000000000#" + identity,
                                "data": {
                                    "incident_id": identity,
                                    "opened_at": baseline,
                                    "cycle": after.updatedAt,
                                },
                            }
                        ),
                    }
                }
            )
    return actions
