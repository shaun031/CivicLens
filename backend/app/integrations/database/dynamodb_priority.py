"""Prepared conditional priority persistence using existing Incidents/AuditEvents only."""

import json
from uuid import uuid4

from app.algorithms.priority_scoring.aging import utc
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.models.incident import IncidentError
from app.repositories.priority_repository import PrioritySnapshot, history_payload, write_response

MAX_AGE_MILLIS = 999999999999999999


def ranking_key(priority, identity):
    cents = int(round(priority["effectiveScore"] * 100))
    age = min(MAX_AGE_MILLIS, int(round(priority["unresolvedSeconds"] * 1000)))
    return (
        f"{0 if priority['urgentHazard'] else 1}#{10000 - cents:05d}#"
        f"{MAX_AGE_MILLIS - age:018d}#{identity}"
    )


def dirty_priority_actions(repository, plan):
    """Included in the SAME P7 transaction; no scoring failure can break complaint submission."""
    actions = []
    for identity, incident in plan.after.items():
        before = plan.before[identity]
        actions.append(
            {
                "Update": {
                    "TableName": repository.table,
                    "Key": marshal({"incidentId": f"priority#{identity}"}),
                    "UpdateExpression": "SET canonicalIncidentId=:id,"
                    "needs_recalculation=:true,available_at=:zero,"
                    "controls=if_not_exists(controls,:empty),"
                    "controls_version=if_not_exists(controls_version,:zero),"
                    "age_open_since=if_not_exists(age_open_since,:first),"
                    "age_frozen_seconds=if_not_exists(age_frozen_seconds,:zero),"
                    "age_lifecycle_status=if_not_exists(age_lifecycle_status,:oldstatus) "
                    "ADD generation :one,membership_epoch :epoch "
                    "REMOVE #status,prioritySortKey,catalogPartition,catalogSortKey",
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": marshal(
                        {
                            ":id": identity,
                            ":true": True,
                            ":zero": 0,
                            ":empty": {},
                            ":first": incident.firstReportedAt,
                            ":oldstatus": before.status if before else incident.status,
                            ":one": 1,
                            ":epoch": int(bool(plan.changes)),
                        }
                    ),
                }
            }
        )
    actions.append(
        {
            "Update": {
                "TableName": repository.table,
                "Key": marshal({"incidentId": "priority-meta"}),
                "UpdateExpression": "ADD queueRevision :one",
                "ExpressionAttributeValues": marshal({":one": 1}),
            }
        }
    )
    return actions


class DynamoPriority:
    def __init__(self, incidents):
        self.incidents, self.table, self.audit_table = (
            incidents,
            incidents.table,
            incidents.audit_table,
        )

    def read(self, key):
        return self.incidents.read(key)

    def record(self, identity):
        raw = self.read(f"priority#{identity}") or {}
        return {
            "controls": {},
            "controls_version": 0,
            "result_revision": 0,
            "membership_epoch": 0,
            "generation": 0,
            "needs_recalculation": True,
            "source_version": 0,
            "config_version": "",
            "result": None,
            "fingerprint": None,
            "next_due": 0,
            "age_open_since": None,
            "age_frozen_seconds": 0,
            "age_quality": "APPROXIMATE_BASELINE",
            **raw,
        }

    def snapshot(self, identity):
        incident = self.incidents.load(identity)
        if not incident:
            raise IncidentError(404, "Incident not found")
        record = self.record(identity)
        members = self.incidents.members(identity)
        old_status = record.get("age_lifecycle_status", incident.status)
        start = record.get("age_open_since") or incident.firstReportedAt
        frozen = record["age_frozen_seconds"]
        try:
            if old_status == "OPEN" and incident.status != "OPEN":
                frozen += max(
                    0, (utc(incident.resolvedAt or incident.updatedAt) - utc(start)).total_seconds()
                )
                start = None
            elif old_status != "OPEN" and incident.status == "OPEN":
                start = incident.updatedAt
            elif incident.status == "OPEN" and not frozen:
                start = incident.firstReportedAt
            elif incident.status == "RESOLVED" and not record.get("age_lifecycle_status"):
                frozen = max(
                    0, (utc(incident.resolvedAt) - utc(incident.firstReportedAt)).total_seconds()
                )
        except (ValueError, TypeError):
            record["age_quality"] = "INVALID"
        record.update(age_open_since=start, age_frozen_seconds=frozen)
        return PrioritySnapshot(incident, record, members)

    def operation(self, identity, fingerprint):
        return self.incidents.operation(identity, fingerprint)

    def commit(self, plan):
        if not self.audit_table:
            raise IncidentError(503, "AUDIT_EVENTS_TABLE_NAME is required; no local fallback")
        old, incident = plan.snapshot.record, plan.snapshot.incident
        if plan.operation_id:
            replay = self.operation(plan.operation_id, plan.request_fingerprint)
            if replay is not None:
                return replay
        revision = old["controls_version"] + int(plan.kind != "RECALCULATE")
        response = write_response(plan, revision)
        priority = plan.result
        payload = {
            **old,
            "incidentId": f"priority#{incident.incidentId}",
            "canonicalIncidentId": incident.incidentId,
            "controls": plan.controls,
            "controls_version": revision,
            "result_revision": old.get("result_revision", 0) + 1,
            "source_version": incident.version,
            "config_version": priority["algorithmVersion"],
            "result": priority,
            "fingerprint": plan.fingerprint,
            "next_due": plan.next_due,
            "needs_recalculation": False,
            "age_lifecycle_status": incident.status,
            "available_at": 0,
            "error_category": None,
        }
        payload.pop("lease_token", None)
        if incident.status in ("OPEN", "RESOLVED"):
            payload.update(
                status=f"PRIORITY#{incident.status}",
                prioritySortKey=ranking_key(priority, incident.incidentId),
                catalogPartition=f"PRIORITY#{incident.status}",
                catalogSortKey=(
                    f"{0 if priority['urgentHazard'] else 1}#"
                    f"{incident.firstReportedAt}#{incident.incidentId}"
                ),
            )
        else:
            for key in ("status", "prioritySortKey", "catalogPartition", "catalogSortKey"):
                payload.pop(key, None)
        put = {
            "TableName": self.table,
            "Item": marshal(payload),
            "ConditionExpression": "generation=:generation AND controls_version=:revision "
            "AND (attribute_not_exists(result_revision) OR result_revision=:calculation)"
            if old["generation"]
            else "attribute_not_exists(incidentId)",
        }
        if old["generation"]:
            put["ExpressionAttributeValues"] = marshal(
                {
                    ":generation": old["generation"],
                    ":revision": old["controls_version"],
                    ":calculation": old.get("result_revision", 0),
                }
            )
        actions = [
            {
                "ConditionCheck": {
                    "TableName": self.table,
                    "Key": marshal({"incidentId": incident.incidentId}),
                    "ConditionExpression": "#version=:version",
                    "ExpressionAttributeNames": {"#version": "version"},
                    "ExpressionAttributeValues": marshal({":version": incident.version}),
                }
            },
            {"Put": put},
        ]
        for member in plan.snapshot.members:
            condition, names, values = self.incidents.membership_condition(member)
            actions.append(
                {
                    "ConditionCheck": {
                        "TableName": self.incidents.complaints.table,
                        "Key": marshal({"complaintId": member.complaint.complaintId}),
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": names,
                        "ExpressionAttributeValues": marshal(values),
                    }
                }
            )
        if plan.operation_id:
            actions.append(
                {
                    "Put": {
                        "TableName": self.table,
                        "Item": marshal(
                            {
                                "incidentId": f"operation#{plan.operation_id}",
                                "fingerprint": plan.request_fingerprint,
                                "result": response,
                            }
                        ),
                        "ConditionExpression": "attribute_not_exists(incidentId)",
                    }
                }
            )
        if old.get("fingerprint") != plan.fingerprint or plan.kind != "RECALCULATE":
            event = str(uuid4())
            actions.append(
                {
                    "Put": {
                        "TableName": self.audit_table,
                        "Item": marshal(
                            {
                                "entityId": f"priority#{incident.incidentId}",
                                "timestampEventId": f"{priority['calculatedAt']}#{event}",
                                "eventId": event,
                                "operationId": plan.operation_id,
                                "kind": plan.kind,
                                "actorId": plan.actor.id,
                                "reason": plan.reason,
                                "createdAt": priority["calculatedAt"],
                                "snapshot": history_payload(plan),
                            }
                        ),
                        "ConditionExpression": "attribute_not_exists(entityId) "
                        "AND attribute_not_exists(timestampEventId)",
                    }
                }
            )
        actions.append(
            {
                "Update": {
                    "TableName": self.table,
                    "Key": marshal({"incidentId": "priority-meta"}),
                    "UpdateExpression": "ADD queueRevision :one",
                    "ExpressionAttributeValues": marshal({":one": 1}),
                }
            }
        )
        from app.integrations.database.dynamodb_work import work_priority_actions

        actions.extend(
            work_priority_actions(self.incidents, incident.incidentId, priority, incident.status)
        )
        from app.events.schema import Event, new_event
        from app.integrations.database.dynamodb_events import event_action
        from app.models.incident import stable_id

        previous = plan.snapshot.record.get("result") or {}
        if previous.get("priorityBand") != priority.get("priorityBand") or previous.get(
            "urgentHazard"
        ) != priority.get("urgentHazard"):
            event = new_event("IncidentPriorityChanged", incident.incidentId)
            event = Event.parse(
                event.model_dump(mode="json")
                | {
                    "eventId": stable_id(
                        f"priority-domain/{incident.incidentId}/{old.get('result_revision', 0) + 1}"
                    )
                }
            )
            actions.extend(event_action(self.incidents.complaints.settings, event))
        if (
            len(actions) > 95
            or len(json.dumps(actions).encode()) > 3_000_000
            or any(len(json.dumps(action).encode()) > 380_000 for action in actions)
        ):
            raise IncidentError(413, "Priority update exceeds bounded atomic envelope")
        try:
            self.incidents.call(
                "transact_write_items",
                TransactItems=actions,
                ClientRequestToken=plan.operation_id or str(uuid4()),
            )
        except Exception as error:
            if plan.operation_id:
                replay = self.operation(plan.operation_id, plan.request_fingerprint)
                if replay is not None:
                    return replay
            raise IncidentError(
                409, "Priority transaction conflicted; retry the same operation ID"
            ) from error
        return response

    def queue(self, filters, limit, after, revision, now, config_version, valid_until=None):
        if valid_until is not None and now >= valid_until:
            raise IncidentError(409, "Priority page expired; restart the first page")
        expiry = valid_until or now + 60
        current = int((self.read("priority-meta") or {}).get("queueRevision", 0))
        if revision is not None and revision != current:
            raise IncidentError(409, "Priority queue changed; restart the first page")
        items, last, visited = [], after, 0
        oldest, status = (
            filters.get("sort") == "oldest",
            f"PRIORITY#{filters.get('status', 'OPEN')}",
        )
        while len(items) < limit and visited < 200:
            arguments = {
                "TableName": self.table,
                "IndexName": "ByCatalog" if oldest else "ByStatusPriority",
                "KeyConditionExpression": "catalogPartition=:partition"
                if oldest
                else "#status=:partition",
                "ExpressionAttributeValues": marshal({":partition": status}),
                "Limit": 1,
                "ScanIndexForward": True,
            }
            if not oldest:
                arguments["ExpressionAttributeNames"] = {"#status": "status"}
            if last:
                key = {"incidentId": f"priority#{last[-1]}"}
                if oldest:
                    key.update(
                        catalogPartition=status,
                        catalogSortKey=f"{0 if -last[0] else 1}#{last[1]}#{last[-1]}",
                    )
                else:
                    key.update(
                        status=status,
                        prioritySortKey=ranking_key(
                            {
                                "urgentHazard": bool(-last[0]),
                                "effectiveScore": -last[1],
                                "unresolvedSeconds": -last[2],
                            },
                            last[-1],
                        ),
                    )
                arguments["ExclusiveStartKey"] = marshal(key)
            response = self.incidents.call("query", **arguments)
            rows = response.get("Items", [])
            if not rows:
                last = None
                break
            key = unmarshal(rows[0])
            identity = key["incidentId"].removeprefix("priority#")
            record, incident = self.record(identity), self.incidents.load(identity)
            visited += 1
            if oldest:
                parts = key["catalogSortKey"].split("#")
                last = [-int(parts[0] == "0"), parts[1], identity]
            else:
                parts = key["prioritySortKey"].split("#")
                last = [
                    -int(parts[0] == "0"),
                    -(10000 - int(parts[1])) / 100,
                    -(MAX_AGE_MILLIS - int(parts[2])) / 1000,
                    identity,
                ]
            priority = record.get("result")
            if valid_until is not None and priority and record["next_due"] <= now:
                raise IncidentError(409, "A time-based priority expired; restart the first page")
            valid = bool(
                incident
                and incident.status == filters.get("status", "OPEN")
                and priority
                and not record["needs_recalculation"]
                and record["source_version"] == incident.version
                and record["config_version"] == config_version
                and record["next_due"] > now
            )
            if valid:
                authoritative_key = (
                    f"{0 if priority['urgentHazard'] else 1}#{incident.firstReportedAt}#{identity}"
                    if oldest
                    else ranking_key(priority, identity)
                )
                if authoritative_key != key["catalogSortKey" if oldest else "prioritySortKey"]:
                    valid = False  # Eventual old index entry must not misorder a current result.
            if valid and self.matches(filters, incident, priority):
                items.append({"incident": incident.model_dump(mode="json"), "priority": priority})
            if not response.get("LastEvaluatedKey"):
                last = None
                break
        if int((self.read("priority-meta") or {}).get("queueRevision", 0)) != current:
            raise IncidentError(
                409, "Priority queue changed during retrieval; restart its first page"
            )
        return items, last, current, expiry

    @staticmethod
    def matches(filters, incident, priority):
        comparisons = {
            "band": priority["priorityBand"],
            "category": incident.category,
            "assessmentStatus": priority["assessmentStatus"],
            "overrideStatus": priority["overrideStatus"],
        }
        if any(filters.get(k) and filters[k] != value for k, value in comparisons.items()):
            return False
        if filters.get("q") and filters["q"].casefold() not in incident.canonicalTitle.casefold():
            return False
        if filters.get("urgent") is not None and filters["urgent"] != priority["urgentHazard"]:
            return False
        for suffix, value in (
            ("Severity", priority["factors"]["severity"]["normalizedValue"]),
            ("Impact", priority["factors"]["publicImpact"]["normalizedValue"]),
            ("Days", priority["unresolvedDays"]),
        ):
            for prefix, failed in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
                bound = filters.get(prefix + suffix)
                if bound is not None and failed(value, bound):
                    return False
        return True

    def history(self, identity, limit, after):
        arguments = {
            "TableName": self.audit_table,
            "KeyConditionExpression": "entityId=:entity",
            "ExpressionAttributeValues": marshal({":entity": f"priority#{identity}"}),
            "ConsistentRead": True,
            "Limit": limit,
        }
        if after:
            arguments["ExclusiveStartKey"] = marshal(
                {"entityId": f"priority#{identity}", "timestampEventId": after[1]}
            )
        response = self.incidents.call("query", **arguments)
        items = [
            json.loads(json.dumps(unmarshal(row), default=float))
            for row in response.get("Items", [])
        ]
        return items, [
            items[-1]["createdAt"],
            items[-1]["timestampEventId"],
        ] if items and response.get("LastEvaluatedKey") else None

    def summary(self, now, config_version):
        active = (self.read("summary#incidents") or {}).get("activeIncidents", 0)
        return {
            "activeIncidents": active,
            "scoredIncidents": None,
            "pendingOrStale": None,
            "bands": {band: None for band in ("LOW", "MEDIUM", "HIGH", "CRITICAL")},
            "needsAssessment": None,
            "urgentHazards": None,
            "overridden": None,
            "providerNote": "Global fresh priority totals require controlled cloud materialization",
        }

    def claim(self, now, config_version):
        raise IncidentError(422, "Cloud scheduled/bulk execution is not enabled in Phase8")

    def batch(self, after, limit):
        raise IncidentError(422, "Priority maintenance is local-only; no DynamoDB Scan")
