"""Bounded cloud work units using existing Incidents/AuditEvents; never SQLite.

Strong configuration manifests and officer ledgers avoid capacity decisions from eventual GSIs.
No SDK construction, credentials lookup, transport or cloud orchestration at import.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from app.algorithms.department_assignment.officer_allocator import recommend, validate_weights
from app.algorithms.department_assignment.routing_engine import covered, route
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.dynamodb_priority import ranking_key
from app.models.incident import IncidentError, stable_id
from app.repositories.work_repository import DEFAULTS, encode


def empty_assignment(identity):
    return {
        "incidentId": identity,
        "departmentId": None,
        "officerId": None,
        "status": "UNASSIGNED",
        "method": None,
        "ruleVersion": None,
        "explanation": [],
        "version": 0,
        "percentage": 0,
        "assignedAt": None,
        "updatedAt": None,
    }


def work_invalidation_actions(repository, plan):
    """P7 atomically marks old allocation historical; authoritative reads check sourceVersion."""
    actions = []
    for identity, incident in plan.after.items():
        actions.append(
            {
                "Update": {
                    "TableName": repository.table,
                    "Key": marshal({"incidentId": f"work#{identity}"}),
                    "UpdateExpression": "SET canonicalIncidentId=:id,sourceVersion=:zero,"
                    "#status=:partition,prioritySortKey=:rank ADD #rev :one "
                    "REMOVE catalogPartition,catalogSortKey,departmentId",
                    "ExpressionAttributeNames": {"#status": "status", "#rev": "_rev"},
                    "ExpressionAttributeValues": marshal(
                        {
                            ":id": identity,
                            ":zero": 0,
                            ":one": 1,
                            ":rank": f"1#pending#{identity}",
                            ":partition": "WORK#OPEN"
                            if incident.status == "OPEN"
                            else "WORK#RETIRED",
                        }
                    ),
                }
            }
        )
        event = stable_id(f"work-membership/{plan.operation_id}/{identity}")
        actions.append(
            {
                "Put": {
                    "TableName": repository.audit_table,
                    "Item": marshal(
                        {
                            "entityId": f"work#{identity}",
                            "timestampEventId": f"{plan.created_at}#{event}",
                            "eventId": event,
                            "kind": "CANONICAL_MEMBERSHIP_REVIEW_REQUIRED",
                            "actorId": plan.actor.id,
                            "actorType": plan.actor.type,
                            "reason": plan.reason,
                            "operationId": plan.operation_id,
                            "createdAt": plan.created_at,
                            "before": {
                                "canonicalVersion": plan.before[identity].version
                                if plan.before[identity]
                                else None,
                                "allocationProvenance": "Previous assignment events retained",
                            },
                            "after": {
                                "sourceVersion": 0,
                                "status": "NEEDS_REVIEW",
                                "canonicalVersion": incident.version,
                            },
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(entityId) "
                    "AND attribute_not_exists(timestampEventId)",
                }
            }
        )
    actions.append(meta_update(repository))
    return actions


def meta_update(repository):
    return {
        "Update": {
            "TableName": repository.table,
            "Key": marshal({"incidentId": "work-meta"}),
            "UpdateExpression": "ADD #rev :one",
            "ExpressionAttributeNames": {"#rev": "_rev"},
            "ExpressionAttributeValues": marshal({":one": 1}),
        }
    }


def work_rank(priority, identity):
    return ("0#" if priority["urgentHazard"] else "2#") + ranking_key(priority, identity)


def work_priority_actions(repository, identity, priority, status):
    return [
        {
            "Update": {
                "TableName": repository.table,
                "Key": marshal({"incidentId": f"work#{identity}"}),
                "UpdateExpression": "SET canonicalIncidentId=:id,#status=:partition,"
                "prioritySortKey=:rank,catalogSortKey=:rank ADD #rev :one",
                "ExpressionAttributeNames": {"#status": "status", "#rev": "_rev"},
                "ExpressionAttributeValues": marshal(
                    {
                        ":id": identity,
                        ":partition": "WORK#OPEN" if status == "OPEN" else "WORK#RETIRED",
                        ":rank": work_rank(priority, identity),
                        ":one": 1,
                    }
                ),
            }
        },
        meta_update(repository),
    ]


class Context:
    def __init__(self, repository):
        self.repository, self.reads, self.writes, self.events = repository, {}, {}, []

    def get(self, key):
        if key in self.writes:
            return copy.deepcopy(self.writes[key])
        if key not in self.reads:
            if len(self.reads) >= 200:
                raise IncidentError(
                    409, "Cloud snapshot exceeds bounded200 items; use controlled reconciliation"
                )
            self.reads[key] = self.repository.incidents.read(key)
        return copy.deepcopy(self.reads[key])

    def put(self, key, value):
        self.get(key)
        self.writes[key] = value | {
            "incidentId": key,
            "_rev": (self.reads[key] or {}).get("_rev", 0) + 1,
        }

    def ids(self, key, field):
        return (self.get(key) or {}).get(field, [])

    def add(self, key, field, value, bound):
        manifest = self.get(key) or {field: []}
        if value not in manifest[field]:
            if len(manifest[field]) >= bound:
                raise IncidentError(
                    409, "Cloud manifest bound reached; controlled reconciliation required"
                )
            manifest[field].append(value)
            self.put(key, manifest)

    def audit(self, entity, kind, before, after, actor, reason, op):
        now, event = self.repository.clock().isoformat(), str(uuid4())
        self.events.append(
            {
                "Put": {
                    "TableName": self.repository.incidents.audit_table,
                    "Item": marshal(
                        {
                            "entityId": f"work#{entity}",
                            "timestampEventId": f"{now}#{event}",
                            "eventId": event,
                            "kind": kind,
                            "actorId": actor.id,
                            "actorType": actor.type,
                            "reason": reason,
                            "before": before,
                            "after": after,
                            "createdAt": now,
                            "operationId": op,
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(entityId) "
                    "AND attribute_not_exists(timestampEventId)",
                }
            }
        )
        from app.events.schema import Event, new_event
        from app.integrations.database.dynamodb_events import event_action

        kinds = []
        if kind.startswith("ASSIGNMENT_"):
            if after.get("departmentId") and after.get("departmentId") != before.get(
                "departmentId"
            ):
                kinds.append("IncidentDepartmentAssigned")
            if after.get("officerId") and after.get("officerId") != before.get("officerId"):
                kinds.append("IncidentOfficerAssigned")
        elif kind == "WORK_START":
            kinds.append("IncidentWorkStarted")
        elif kind == "WORK_PROGRESS" and (
            before.get("percentage") != after.get("percentage")
            or before.get("status") != after.get("status")
        ):
            kinds.append("IncidentProgressUpdated")
        for event_kind in kinds:
            payload = (
                {"officerId": after["officerId"]} if event_kind == "IncidentOfficerAssigned" else {}
            )
            domain = new_event(event_kind, entity, correlation=op, payload=payload)
            domain = Event.parse(
                domain.model_dump(mode="json")
                | {"eventId": stable_id(f"work-domain/{op}/{entity}/{event_kind}")}
            )
            self.events.extend(event_action(self.repository.settings, domain))

    @staticmethod
    def condition(old):
        if old is None:
            return {"ConditionExpression": "attribute_not_exists(incidentId)"}
        field = "version" if "canonicalTitle" in old else "_rev"
        if "generation" in old:
            return {
                "ConditionExpression": "generation=:g AND "
                "(attribute_not_exists(result_revision) OR result_revision=:r)",
                "ExpressionAttributeValues": marshal(
                    {":g": old["generation"], ":r": old.get("result_revision", 0)}
                ),
            }
        return {
            "ConditionExpression": "#v=:v",
            "ExpressionAttributeNames": {"#v": field},
            "ExpressionAttributeValues": marshal({":v": old.get(field, 0)}),
        }

    def actions(self):
        result = []
        for key, old in self.reads.items():
            payload = {"TableName": self.repository.incidents.table, **self.condition(old)}
            if key in self.writes:
                result.append({"Put": payload | {"Item": marshal(self.writes[key])}})
            else:
                result.append({"ConditionCheck": payload | {"Key": marshal({"incidentId": key})}})
        return [*result, *self.events]


class DynamoWork:
    def __init__(self, incidents, config_version, settings):
        self.incidents, self.config_version, self.settings = incidents, config_version, settings
        self.weights = validate_weights(settings.workload_weights)
        self.clock = lambda: datetime.now(UTC)

    def process_one(self):
        return None

    @staticmethod
    def require(c, key):
        result = c.get(key)
        if result is None:
            raise IncidentError(404, "Work record not found")
        return result

    @staticmethod
    def version(value, expected):
        if (value or {}).get("version", 0) != expected:
            raise IncidentError(409, "Work version changed; refresh")

    def atomic(self, kind, entity, data, actor, callback):
        if not data.get("confirmed"):
            raise IncidentError(422, "Explicit confirmation required")
        operation = stable_id(f"work-operation/{actor.id}/{data['operationId']}")
        fingerprint = hashlib.sha256(encode([kind, entity, data, actor.id]).encode()).hexdigest()
        replay = self.incidents.operation(operation, fingerprint)
        if replay is not None:
            if actor.type == "OFFICER":
                self.detail(entity, actor.id)
            return replay
        c = Context(self)
        meta = c.get("work-meta") or {}
        result = callback(c, operation)
        c.put("work-meta", meta)
        c.put(f"operation#{operation}", {"fingerprint": fingerprint, "result": result})
        actions = c.actions()
        if (
            len(actions) > 95
            or len(encode(actions).encode()) > 3_000_000
            or any(len(encode(a).encode()) > 380_000 for a in actions)
        ):
            raise IncidentError(
                413, "Work operation exceeds atomic envelope; no partial writes attempted"
            )
        try:
            self.incidents.call(
                "transact_write_items",
                TransactItems=actions,
                # Durable operation receipts prevent duplicate logical writes. Bind the SDK token
                # to exact wire content so a rebuilt retry cannot hit parameter-mismatch errors.
                ClientRequestToken=stable_id(
                    operation + hashlib.sha256(encode(actions).encode()).hexdigest()
                ),
            )
        except Exception as error:
            replay = self.incidents.operation(operation, fingerprint)
            if replay is not None:
                return replay
            raise IncidentError(
                409, "Work transaction conflicted; retry SAME operation ID"
            ) from error
        return result

    def coherent(self, callback):
        c = Context(self)
        before = c.get("work-meta") or {}
        result = callback(c)
        after = self.incidents.read("work-meta") or {}
        if before.get("_rev", 0) != after.get("_rev", 0):
            raise IncidentError(409, "Municipal work changed during read; refresh")
        return result

    def configuration(self, c):
        return [
            self.require(c, f"work-department#{i}") for i in c.ids("work-config", "departments")
        ]

    def _rules(self, c):
        return [self.require(c, f"work-rule#{i}") for i in c.ids("work-rules", "rules")]

    def list_rules(self):
        return self.coherent(lambda c: {"items": self._rules(c)})

    def seed(self, data, actor):
        def write(c, op):
            codes = {d["code"] for d in self.configuration(c)}
            added = []
            for code, (name, categories) in DEFAULTS.items():
                if code in codes or c.get(f"work-code#{code}"):
                    continue
                identity, now = str(uuid4()), self.clock().isoformat()
                c.put(
                    f"work-department#{identity}",
                    {
                        "id": identity,
                        "code": code,
                        "name": name,
                        "description": "Editable fictional demonstration department",
                        "active": True,
                        "areas": [],
                        "version": 1,
                        "createdAt": now,
                        "updatedAt": now,
                    },
                )
                c.put(f"work-code#{code}", {"departmentId": identity})
                c.add("work-config", "departments", identity, 100)
                for category in categories:
                    key = f"{category}#{identity}"
                    c.put(
                        f"work-rule#{key}",
                        {
                            "id": str(uuid4()),
                            "category": category,
                            "departmentId": identity,
                            "precedence": 100,
                            "active": True,
                            "version": 1,
                        },
                    )
                    c.add("work-rules", "rules", key, 1000)
                added.append(code)
            c.audit(
                "configuration", "DEFAULTS_SEEDED", {}, {"added": added}, actor, data["reason"], op
            )
            return {"added": added}

        return self.atomic("SEED", "configuration", data, actor, write)

    def departments(self):
        return self.coherent(
            lambda c: {
                "items": [
                    d
                    | {"officerCount": None, "activeIncidents": None, "highCriticalIncidents": None}
                    for d in self.configuration(c)
                ],
                "providerNote": "Cloud global aggregates require controlled materialization",
            }
        )

    def save_department(self, identity, data, actor):
        def write(c, op):
            before = c.get(f"work-department#{identity}")
            self.version(before, data["expectedVersion"])
            claim = c.get(f"work-code#{data['code']}")
            if claim and claim["departmentId"] != identity:
                raise IncidentError(409, "Department code already exists")
            if before and (before["areas"] != data["areas"] or not data["active"]):
                for key in c.ids(f"work-department-ledger#{identity}", "incidents"):
                    i, a, _ = self.state(c, key)
                    if i["status"] == "OPEN" and a["departmentId"] == identity:
                        raise IncidentError(
                            409, "Reassign active work before changing department constraints"
                        )
            now = self.clock().isoformat()
            after = {k: data[k] for k in ("code", "name", "description", "active", "areas")}
            after |= {
                "id": identity,
                "version": data["expectedVersion"] + 1,
                "createdAt": (before or {}).get("createdAt", now),
                "updatedAt": now,
            }
            c.put(f"work-department#{identity}", after)
            c.put(f"work-code#{data['code']}", {"departmentId": identity})
            c.add("work-config", "departments", identity, 100)
            c.audit(identity, "DEPARTMENT_UPDATED", before or {}, after, actor, data["reason"], op)
            return after

        return self.atomic("DEPARTMENT", identity, data, actor, write)

    def save_rule(self, data, actor):
        def write(c, op):
            self.require(c, f"work-department#{data['departmentId']}")
            key = f"{data['category']}#{data['departmentId']}"
            before = c.get(f"work-rule#{key}")
            self.version(before, data["expectedVersion"])
            after = {k: data[k] for k in ("category", "departmentId", "precedence", "active")}
            after |= {
                "id": (before or {}).get("id", str(uuid4())),
                "version": data["expectedVersion"] + 1,
            }
            c.put(f"work-rule#{key}", after)
            c.add("work-rules", "rules", key, 1000)
            c.audit(
                "configuration",
                "ROUTING_RULE_UPDATED",
                before or {},
                after,
                actor,
                data["reason"],
                op,
            )
            return after

        return self.atomic("RULE", "configuration", data, actor, write)

    def save_membership(self, dept, data, actor):
        def write(c, op):
            d = self.require(c, f"work-department#{dept}")
            u = self.require(c, f"work-officer#{data['officerId']}")
            if data["active"] and not (
                d["active"] and u.get("role") == "OFFICER" and u.get("active") and u.get("verified")
            ):
                raise IncidentError(422, "Trusted active verified OFFICER profile is required")
            key = f"work-member#{dept}#{data['officerId']}"
            before = c.get(key)
            self.version(before, data["expectedVersion"])
            if before and any(
                before.get(k) != data[k] for k in ("active", "availability", "capacity", "areas")
            ):
                for identity in c.ids(f"work-officer-ledger#{data['officerId']}", "incidents"):
                    i, a, _ = self.state(c, identity)
                    if (
                        i["status"] == "OPEN"
                        and a["officerId"] == data["officerId"]
                        and a["departmentId"] == dept
                    ):
                        raise IncidentError(
                            409, "Reassign active work before changing membership constraints"
                        )
            result = {
                k: data[k] for k in ("officerId", "active", "availability", "capacity", "areas")
            }
            result |= {
                "id": (before or {}).get("id", str(uuid4())),
                "departmentId": dept,
                "version": data["expectedVersion"] + 1,
            }
            c.put(key, result)
            c.add(f"work-members#{dept}", "officers", data["officerId"], 30)
            c.add(f"work-officer-departments#{data['officerId']}", "departments", dept, 30)
            c.audit(dept, "MEMBERSHIP_UPDATED", before or {}, result, actor, data["reason"], op)
            return result

        return self.atomic("MEMBERSHIP", dept, data, actor, write)

    def remove_membership(self, dept, officer, data, actor):
        def write(c, op):
            key = f"work-member#{dept}#{officer}"
            before = self.require(c, key)
            self.version(before, data["expectedVersion"])
            for identity in c.ids(f"work-officer-ledger#{officer}", "incidents"):
                i, a, _ = self.state(c, identity)
                if (
                    i["status"] == "OPEN"
                    and a["officerId"] == officer
                    and a["departmentId"] == dept
                ):
                    raise IncidentError(409, "Reassign active work before removing membership")
            after = before | {"active": False, "version": before["version"] + 1}
            c.put(key, after)
            c.audit(dept, "MEMBERSHIP_REMOVED", before, after, actor, data["reason"], op)
            return after

        return self.atomic("REMOVE_MEMBERSHIP", f"{dept}/{officer}", data, actor, write)

    def officer_directory(self, after="", limit=50):
        def read(c):
            ids = sorted(i for i in c.ids("work-officers", "officers") if i > after)
            values = [self.require(c, f"work-officer#{i}") for i in ids[:limit]]
            return {
                "items": [
                    {"officerId": v["officerId"], "displayName": v["displayName"]}
                    for v in values
                    if v.get("active") and v.get("verified") and v.get("role") == "OFFICER"
                ],
                "nextAfter": ids[limit - 1] if len(ids) > limit else None,
            }

        return self.coherent(read)

    def provision_officer_profile(self, profile, data, actor):
        """Trusted provisioning interface, not an HTTP role-grant endpoint.

        Identity is the Cognito sub. This projection does not grant a Cognito group/privilege.
        A future provisioning/lifecycle producer must synchronize it and increment work-meta.
        """
        if actor.type != "ADMIN" or profile.get("role") != "OFFICER":
            raise IncidentError(403, "Trusted OFFICER profile provisioning only")
        from uuid import UUID

        try:
            identity = str(UUID(str(profile["officerId"])))
        except (ValueError, KeyError, TypeError) as error:
            raise IncidentError(422, "A Cognito subject UUID is required") from error
        if any(type(profile.get(k)) is not bool for k in ("active", "verified")):
            raise IncidentError(422, "Explicit account eligibility flags are required")
        if (
            not isinstance(profile.get("displayName"), str)
            or not 1 <= len(profile["displayName"]) <= 100
        ):
            raise IncidentError(422, "A bounded officer display name is required")

        def write(c, op):
            key = f"work-officer#{identity}"
            before = c.get(key) or {}
            after = {
                k: profile[k] for k in ("officerId", "role", "active", "verified", "displayName")
            }
            after["officerId"] = identity
            c.put(key, after)
            c.add("work-officers", "officers", identity, 500)
            c.audit(
                "configuration", "TRUSTED_OFFICER_PROFILE", before, after, actor, data["reason"], op
            )
            return after

        return self.atomic("PROFILE", identity, data, actor, write)

    def state(self, c, identity):
        i = self.require(c, identity)
        if "canonicalTitle" not in i:
            raise IncidentError(404, "Incident not found")
        raw = c.get(f"work#{identity}") or {}
        a = copy.deepcopy(raw.get("assignment", empty_assignment(identity)))
        if a["departmentId"] and (
            raw.get("sourceVersion") != i["version"] or i["status"] != "OPEN"
        ):
            a |= {
                "departmentId": None,
                "officerId": None,
                "status": "NEEDS_REVIEW",
                "method": "REVIEW_LOCK",
                "explanation": [
                    "Canonical revision changed; old allocation is historical. "
                    "Review membership audit."
                ],
            }
        if a["officerId"]:
            profile = c.get(f"work-officer#{a['officerId']}") or {}
            member = c.get(f"work-member#{a['departmentId']}#{a['officerId']}") or {}
            if not (
                profile.get("active")
                and profile.get("verified")
                and profile.get("role") == "OFFICER"
                and member.get("active")
            ):
                a |= {
                    "officerId": None,
                    "status": "NEEDS_REVIEW",
                    "explanation": ["Officer eligibility changed; administrator review required"],
                }
        return i, a, raw

    def priority(self, c, i):
        p = c.get(f"priority#{i['incidentId']}") or {}
        fresh = bool(
            p.get("result")
            and not p.get("needs_recalculation", True)
            and p.get("config_version") == self.config_version
            and p.get("source_version") == i["version"]
            and p.get("next_due", 0) > self.clock().timestamp()
        )
        return p, fresh

    def _workload(self, c, officer, exclude=None):
        units = count = pending = 0
        for identity in c.ids(f"work-officer-ledger#{officer}", "incidents"):
            if identity == exclude:
                continue
            i, a, _ = self.state(c, identity)
            if i["status"] != "OPEN" or a["officerId"] != officer:
                continue
            p, fresh = self.priority(c, i)
            units += (
                self.weights[p["result"]["priorityBand"]] if fresh else self.weights["CRITICAL"]
            )
            count += 1
            pending += not fresh
        return {"workload": units, "activeIncidents": count, "pendingPriorities": pending}

    def workload_read(self, officer):
        return self.coherent(lambda c: self._workload(c, officer))

    def _officers(self, c, dept, exclude=None):
        result = []
        for identity in c.ids(f"work-members#{dept}", "officers"):
            m = self.require(c, f"work-member#{dept}#{identity}")
            u = self.require(c, f"work-officer#{identity}")
            result.append(
                m
                | {
                    "displayName": u["displayName"],
                    "eligibleAccount": bool(
                        u.get("active") and u.get("verified") and u.get("role") == "OFFICER"
                    ),
                    **self._workload(c, identity, exclude),
                }
            )
        return result

    def _recommend(self, c, i, a):
        if not a["departmentId"]:
            return {
                "ranked": [],
                "excluded": [],
                "mode": self.settings.assignment_mode,
                "assignmentChanged": False,
                "message": "Confirm a responsible department first",
            }
        d = self.require(c, f"work-department#{a['departmentId']}")
        if not d["active"] or not covered(d["areas"], i["latitude"], i["longitude"]):
            raise IncidentError(409, "Department jurisdiction requires review")
        p, fresh = self.priority(c, i)
        units = self.weights[p["result"]["priorityBand"]] if fresh else self.weights["CRITICAL"]
        return recommend(
            self._officers(c, d["id"], i["incidentId"]), units, i["latitude"], i["longitude"]
        ) | {
            "incomingUnits": units,
            "priorityStale": not fresh,
            "mode": self.settings.assignment_mode,
            "assignmentChanged": False,
        }

    def authorize(self, c, i, a, officer):
        if i["status"] != "OPEN" or a["officerId"] != officer:
            raise IncidentError(404, "Assigned incident not found")
        m = self.require(c, f"work-member#{a['departmentId']}#{officer}")
        u = self.require(c, f"work-officer#{officer}")
        d = self.require(c, f"work-department#{a['departmentId']}")
        if not (
            m["active"]
            and d["active"]
            and u.get("role") == "OFFICER"
            and u.get("active")
            and u.get("verified")
            and m["availability"] in ("AVAILABLE", "BUSY")
            and covered(m["areas"], i["latitude"], i["longitude"])
            and covered(d["areas"], i["latitude"], i["longitude"])
        ):
            raise IncidentError(404, "Assigned incident no longer eligible")

    def detail(self, identity, officer=None, include_admin=True):
        def read(c):
            i, a, _ = self.state(c, identity)
            if officer:
                self.authorize(c, i, a, officer)
            p, fresh = self.priority(c, i)
            result = {
                "incidentId": identity,
                "title": i["canonicalTitle"],
                "category": i["category"],
                "latitude": i["latitude"],
                "longitude": i["longitude"],
                "incidentStatus": i["status"],
                "incidentVersion": i["version"],
                "assignment": a,
                "priority": p.get("result"),
                "priorityStale": not fresh,
                "department": self.require(c, f"work-department#{a['departmentId']}")
                if a["departmentId"]
                else None,
            }
            if not officer and include_admin:
                result |= {
                    "suggestedRouting": route(
                        i["category"],
                        i["latitude"],
                        i["longitude"],
                        self.configuration(c),
                        self._rules(c),
                    ),
                    "recommendations": self._recommend(c, i, a),
                }
            return result

        return self.coherent(read)

    def _ledger(self, c, key, identity, keep):
        values = c.ids(key, "incidents")
        if keep:
            if identity not in values:
                if len(values) >= 30:
                    raise IncidentError(
                        409, "Cloud officer ledger bound30 reached; reconcile before adding work"
                    )
                values.append(identity)
        else:
            values = [i for i in values if i != identity]
        c.put(key, {"incidents": values})

    def _save_assignment(self, c, identity, i, before, a, raw, actor, reason, op, kind, note=None):
        now = self.clock().isoformat()
        a |= {"version": before["version"] + 1, "updatedAt": now}
        p, fresh = self.priority(c, i)
        rank = work_rank(p["result"], identity) if fresh else f"1#pending#{identity}"
        value = {
            "canonicalIncidentId": identity,
            "assignment": a,
            "sourceVersion": i["version"],
            "status": "WORK#OPEN",
            "prioritySortKey": rank,
        }
        # Remove stale ledger entries, including allocations invalidated by a P7 revision.
        old = raw.get("assignment", before)
        if old["officerId"] and old["officerId"] != a["officerId"]:
            self._ledger(c, f"work-officer-ledger#{old['officerId']}", identity, False)
        if old["departmentId"] and old["departmentId"] != a["departmentId"]:
            ledger = f"work-department-ledger#{old['departmentId']}"
            c.put(ledger, {"incidents": [v for v in c.ids(ledger, "incidents") if v != identity]})
        if a["departmentId"]:
            value["departmentId"] = f"WORK#DEPT#{a['departmentId']}"
            c.add(f"work-department-ledger#{a['departmentId']}", "incidents", identity, 200)
        if a["officerId"]:
            value |= {"catalogPartition": f"WORK#OFFICER#{a['officerId']}", "catalogSortKey": rank}
            self._ledger(c, f"work-officer-ledger#{a['officerId']}", identity, True)
        c.put(f"work#{identity}", value)
        c.audit(
            identity,
            kind,
            raw.get("assignment", before),
            a | ({"note": note} if note else {}),
            actor,
            reason,
            op,
        )
        return a

    def assign(self, identity, kind, data, actor):
        def write(c, op):
            i, a, raw = self.state(c, identity)
            if i["status"] != "OPEN":
                raise IncidentError(409, "Only canonical OPEN incidents accept work")
            self.version(i, data["expectedIncidentVersion"])
            self.version(a, data["expectedAssignmentVersion"])
            before = copy.deepcopy(a)
            if kind == "ROUTE":
                if a["officerId"]:
                    raise IncidentError(
                        409,
                        "Unassign or explicitly reassign existing officer work before rerouting",
                    )
                decision = route(
                    i["category"],
                    i["latitude"],
                    i["longitude"],
                    self.configuration(c),
                    self._rules(c),
                )
                a |= {
                    "departmentId": decision["departmentId"],
                    "officerId": None,
                    "ruleVersion": decision["ruleVersion"],
                    "method": "AUTO_DEPARTMENT",
                    "explanation": decision["explanation"],
                    "status": "NEEDS_REVIEW"
                    if decision["review"] or before["method"] == "REVIEW_LOCK"
                    else "DEPARTMENT_ASSIGNED",
                }
                if data.get("mode") == "CONSERVATIVE_AUTO_ASSIGN":
                    if self.settings.assignment_mode != "CONSERVATIVE_AUTO_ASSIGN":
                        raise IncidentError(422, "Conservative allocation is not enabled")
                    candidates = self._recommend(c, i, a)["ranked"]
                    p, fresh = self.priority(c, i)
                    if (
                        a["status"] != "NEEDS_REVIEW"
                        and fresh
                        and not p["result"]["urgentHazard"]
                        and len(candidates) == 1
                    ):
                        o = candidates[0]
                        if o["capacity"] is not None and not o["pendingPriorities"]:
                            a |= {
                                "officerId": o["officerId"],
                                "status": "OFFICER_ASSIGNED",
                                "method": "AUTO_OFFICER",
                            }
            else:
                if kind == "DEPARTMENT":
                    a |= {"departmentId": data.get("departmentId"), "officerId": None}
                elif kind == "OFFICER":
                    if not data.get("officerId"):
                        raise IncidentError(422, "Select an officer")
                    a["officerId"] = data["officerId"]
                elif kind == "REASSIGN":
                    a |= {
                        "departmentId": data.get("departmentId"),
                        "officerId": data.get("officerId"),
                    }
                elif kind == "UNASSIGN":
                    a["officerId"] = None
                a["status"] = (
                    "OFFICER_ASSIGNED"
                    if a["officerId"]
                    else "DEPARTMENT_ASSIGNED"
                    if a["departmentId"]
                    else "UNASSIGNED"
                )
                a["method"] = "MANUAL_ADMIN" if not before["departmentId"] else "REASSIGNMENT"
                if data.get("review"):
                    a |= {"officerId": None, "status": "NEEDS_REVIEW"}
            if a["departmentId"]:
                d = self.require(c, f"work-department#{a['departmentId']}")
                if not d["active"] or not covered(d["areas"], i["latitude"], i["longitude"]):
                    raise IncidentError(422, "Inactive or out-of-jurisdiction department")
            if a["officerId"]:
                if not a["departmentId"]:
                    raise IncidentError(422, "Officer requires responsible department")
                candidates = self._recommend(c, i, a)
                if not any(o["officerId"] == a["officerId"] for o in candidates["ranked"]):
                    officers = self._officers(c, a["departmentId"], identity)
                    selected = [
                        o | {"capacity": None} for o in officers if o["officerId"] == a["officerId"]
                    ]
                    if not (
                        data.get("capacityOverride")
                        and actor.type == "ADMIN"
                        and recommend(selected, 0, i["latitude"], i["longitude"])["ranked"]
                    ):
                        raise IncidentError(
                            422, "Officer is unavailable, ineligible or over weighted capacity"
                        )
                    a["explanation"] = [
                        "Administrator explicitly overrode experimental weighted capacity"
                    ]
            a |= {"percentage": 0, "assignedAt": self.clock().isoformat()}
            return self._save_assignment(
                c, identity, i, before, a, raw, actor, data["reason"], op, f"ASSIGNMENT_{kind}"
            )

        return self.atomic(kind, identity, data, actor, write)

    def progress(self, identity, kind, data, actor):
        def write(c, op):
            i, a, raw = self.state(c, identity)
            self.authorize(c, i, a, actor.id)
            self.version(i, data["expectedIncidentVersion"])
            self.version(a, data["expectedAssignmentVersion"])
            if a["status"] != ("OFFICER_ASSIGNED" if kind == "START" else "IN_PROGRESS"):
                raise IncidentError(409, "Invalid work progress transition")
            if data["percentage"] < a["percentage"]:
                raise IncidentError(422, "Progress cannot decrease; request review")
            before = copy.deepcopy(a)
            a |= {
                "status": "NEEDS_REVIEW" if data["requestReview"] else "IN_PROGRESS",
                "percentage": data["percentage"],
            }
            return self._save_assignment(
                c,
                identity,
                i,
                before,
                a,
                raw,
                actor,
                data["reason"],
                op,
                f"WORK_{kind}",
                data["note"],
            )

        return self.atomic(kind, identity, data, actor, write)

    def department_detail(self, identity):
        def read(c):
            d = self.require(c, f"work-department#{identity}")
            officers = self._officers(c, identity)
            return d | {
                "officers": officers,
                "rules": [r for r in self._rules(c) if r["departmentId"] == identity],
                "workload": {
                    "activeIncidents": None,
                    "unassignedIncidents": None,
                    "weightedWorkload": sum(o["workload"] for o in officers),
                    "overCapacity": [
                        o["officerId"]
                        for o in officers
                        if o["capacity"] and o["workload"] > o["capacity"]
                    ],
                    "policy": "Global officer ledger workload; no automatic rebalancing. "
                    "Fresh global/department aggregates unavailable.",
                },
            }

        return self.coherent(read)

    def department_exists(self, identity):
        return self.coherent(lambda c: self.require(c, f"work-department#{identity}")["id"])

    def summary(self):
        def read(c):
            departments = self.configuration(c)
            return {
                "totalDepartments": len(departments),
                "activeDepartments": sum(d["active"] for d in departments),
                "officers": None,
                "availableOfficers": None,
                "activeIncidents": None,
                "unassigned": None,
                "assigned": None,
                "inProgress": None,
                "needsReview": None,
            }

        return self.coherent(read)

    def history(self, entity, limit=20, after=None, officer=None):
        if officer:
            self.detail(entity, officer)
        args = {
            "TableName": self.incidents.audit_table,
            "KeyConditionExpression": "entityId=:entity",
            "ExpressionAttributeValues": marshal({":entity": f"work#{entity}"}),
            "Limit": limit,
            "ConsistentRead": True,
        }
        if after:
            args["ExclusiveStartKey"] = marshal(
                {"entityId": f"work#{entity}", "timestampEventId": after[0] + "#" + after[1]}
            )
        response = self.incidents.call("query", **args)
        rows = [
            json.loads(json.dumps(unmarshal(item), default=float))
            for item in response.get("Items", [])
        ]
        if officer:
            rows = [
                r
                for r in rows
                if r["actorId"] == officer and r["kind"] in ("WORK_START", "WORK_PROGRESS")
            ]
        last = (
            unmarshal(response["LastEvaluatedKey"])["timestampEventId"].rsplit("#", 1)
            if response.get("LastEvaluatedKey")
            else None
        )
        return {"items": rows, "after": last}

    def queue(
        self, query, after=None, revision=None, valid_until=None, officer=None, unassigned=False
    ):
        now = self.clock().timestamp()
        current = int((self.incidents.read("work-meta") or {}).get("_rev", 0))
        if revision is not None and (
            revision != current or valid_until is None or valid_until <= now
        ):
            raise IncidentError(409, "Work queue changed or aged; restart first page")
        index, partition, key_name, sort_name = (
            "ByStatusPriority",
            "WORK#OPEN",
            "status",
            "prioritySortKey",
        )
        if officer:
            index, partition, key_name, sort_name = (
                "ByCatalog",
                f"WORK#OFFICER#{officer}",
                "catalogPartition",
                "catalogSortKey",
            )
        elif query.get("departmentId"):
            index, partition, key_name = (
                "ByDepartmentPriority",
                f"WORK#DEPT#{query['departmentId']}",
                "departmentId",
            )
        try:
            last = json.loads(after[-1]) if after else None
            if last is not None and (
                not isinstance(last, dict)
                or set(last) != {"incidentId", key_name, sort_name}
                or any(not isinstance(v, str) or len(v) > 512 for v in last.values())
                or last[key_name] != partition
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError) as error:
            raise IncidentError(400, "Invalid cloud work cursor") from error
        items, visited, limit = [], 0, query.get("limit", 20)
        expiry = min(valid_until or now + 60, now + 60)
        while len(items) < limit and visited < 200:
            args = {
                "TableName": self.incidents.table,
                "IndexName": index,
                "KeyConditionExpression": "#partition=:partition",
                "ExpressionAttributeNames": {"#partition": key_name},
                "ExpressionAttributeValues": marshal({":partition": partition}),
                "Limit": 1,
            }
            if last:
                args["ExclusiveStartKey"] = marshal(last)
            response = self.incidents.call("query", **args)
            visited += 1
            for entry in response.get("Items", []):
                indexed = unmarshal(entry)
                raw = self.incidents.read(indexed["incidentId"])
                if (
                    not raw
                    or raw.get(key_name) != partition
                    or raw.get(sort_name) != indexed[sort_name]
                ):
                    continue
                identity = raw["canonicalIncidentId"]
                try:
                    state = self.detail(identity, officer, False)
                except IncidentError as error:
                    if error.status == 404:
                        continue
                    raise
                a = state["assignment"]
                if state["incidentStatus"] != "OPEN" or (
                    unassigned and a["officerId"] and a["status"] != "NEEDS_REVIEW"
                ):
                    continue
                if any(
                    query.get(k) is not None and a[field] != query[k]
                    for k, field in (
                        ("departmentId", "departmentId"),
                        ("officerId", "officerId"),
                        ("status", "status"),
                    )
                ):
                    continue
                p = state["priority"]
                if query.get("category") and state["category"] != query["category"]:
                    continue
                if query.get("assignedAfter") and (
                    not a["assignedAt"] or a["assignedAt"] < query["assignedAfter"]
                ):
                    continue
                if query.get("band") and (
                    state["priorityStale"] or p["priorityBand"] != query["band"]
                ):
                    continue
                if query.get("urgent") is not None and (
                    state["priorityStale"] or p["urgentHazard"] != query["urgent"]
                ):
                    continue
                if state["priorityStale"] and not raw["prioritySortKey"].startswith("1#pending#"):
                    continue  # Do not place an expired score at an obsolete GSI rank.
                if not state["priorityStale"] and raw["prioritySortKey"] != work_rank(p, identity):
                    continue
                state.pop("suggestedRouting", None)
                state.pop("recommendations", None)
                items.append(state | {"departmentName": (state["department"] or {}).get("name")})
            last = (
                unmarshal(response["LastEvaluatedKey"])
                if response.get("LastEvaluatedKey")
                else None
            )
            if not last:
                break
        workload = self.workload_read(officer) if officer else None
        if int((self.incidents.read("work-meta") or {}).get("_rev", 0)) != current:
            raise IncidentError(409, "Work queue changed during query; refresh")
        return {
            "items": items,
            "after": [0, 0, 0, 0, encode(last)] if last else None,
            "queueRevision": current,
            "validUntil": expiry,
            "stats": {
                k: None
                for k in ("assigned", "inProgress", "high", "critical", "urgent", "pendingPriority")
            },
            "consistency": "Eventual GSI discovery; strong eligibility/rank validation; "
            "no snapshot completeness guarantee",
            **({"workload": workload} if officer else {}),
        }
