"""Bounded, conditional transaction adapter; no SDK client creation or transport at import.

Membership remains on Complaints. A bounded incident manifest is maintained IN THE SAME transaction
and strongly checked, never used as a second independently writable membership authority.
"""

import json
import time
from dataclasses import asdict
from uuid import uuid4

from botocore.exceptions import ClientError

from app.algorithms.duplicate_detection.models import canonical_pair
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.models.incident import Incident, IncidentError, Member, stable_id
from app.repositories.complaint_repository import RepositoryUnavailable
from app.repositories.duplicate_candidate_repository import timestamp


class DynamoIncidents:
    def __init__(self, complaints, matching):
        self.complaints, self.matching = complaints, matching
        self.table = complaints.settings.incidents_table_name
        self.audit_table = complaints.settings.audit_events_table_name

    def call(self, method, **kwargs):
        if not self.table:
            raise IncidentError(
                503, "INCIDENTS_TABLE_NAME is required for cloud incident operations"
            )
        try:
            return self.matching.call(method, **kwargs)
        except RepositoryUnavailable as error:
            # The shared P6 adapter wraps SDK errors. Preserve conditional conflicts so
            # the bounded lease/enqueue protocol can distinguish a race from an outage.
            cause = error.__cause__
            if isinstance(cause, ClientError) and cause.response["Error"]["Code"] == (
                "ConditionalCheckFailedException"
            ):
                raise cause from None
            raise

    def read(self, identity):
        response = self.call(
            "get_item",
            TableName=self.table,
            Key=marshal({"incidentId": identity}),
            ConsistentRead=True,
        )
        return (
            json.loads(json.dumps(unmarshal(response["Item"]), default=float))
            if response.get("Item")
            else None
        )

    def load(self, identity):
        item = self.read(identity)
        return (
            Incident.model_validate(
                {key: item[key] for key in Incident.model_fields if key in item}
            )
            if item and "canonicalTitle" in item
            else None
        )

    def member(self, identity):
        item = self.matching.read(identity)
        if not item or "citizenId" not in item:
            return None
        return Member(
            self.complaints.hydrate(item),
            bool(item.get("reporterEligible", False) and item["status"] != "REJECTED"),
        )

    def members(self, identity, limit=30):
        item = self.read(identity)
        if not item:
            return []
        ids = item.get("memberIds", [])
        if (
            len(ids) > limit
            or len(set(ids)) != len(ids)
            or item.get("totalComplaintCount", len(ids)) != len(ids)
        ):
            raise IncidentError(
                409, "Incident membership manifest requires controlled reconciliation"
            )
        # Strong reads are authoritative, not an eventually-consistent GSI count.
        members = [self.member(key) for key in ids]
        if any(m is None or m.complaint.incidentId != identity for m in members):
            raise IncidentError(409, "Incident membership changed; reconcile before changing it")
        return sorted(members, key=lambda m: (m.complaint.createdAt, m.complaint.complaintId))

    def operation(self, identity, fingerprint):
        item = self.read(f"operation#{identity}")
        if item and item["fingerprint"] != fingerprint:
            raise IncidentError(409, "Operation ID was already used with different input")
        return item["result"] if item else None

    @staticmethod
    def membership_condition(member):
        complaint = member.complaint
        names = {"#status": "status"}
        values = {":status": complaint.status, ":eligible": member.eligible_reporter}
        condition = "#status=:status AND "
        if complaint.incidentId is None:
            condition += "(attribute_not_exists(incidentId) OR attribute_type(incidentId,:null))"
            values[":null"] = "NULL"
        else:
            condition += "incidentId=:previous"
            values[":previous"] = complaint.incidentId
        # Rejected reports have eligibility false regardless of their immutable submission flag.
        if complaint.status != "REJECTED":
            condition += " AND " + (
                "reporterEligible=:eligible"
                if member.eligible_reporter
                else "(attribute_not_exists(reporterEligible) OR reporterEligible=:eligible)"
            )
        else:
            values.pop(":eligible")
        return condition, names, values

    def commit(self, plan):
        if not self.audit_table:
            raise IncidentError(503, "AUDIT_EVENTS_TABLE_NAME is required for incident changes")
        replay = self.operation(plan.operation_id, plan.fingerprint)
        if replay is not None:
            return replay
        observed = {m.complaint.complaintId: m for m in plan.observed}
        changes = {change.complaint_id: change for change in plan.changes}
        transaction = []
        for identity, incident in plan.after.items():
            before = plan.before[identity]
            members = {
                key for key, member in observed.items() if member.complaint.incidentId == identity
            }
            for change in plan.changes:
                if change.previous_incident_id == identity:
                    members.discard(change.complaint_id)
                if change.new_incident_id == identity:
                    members.add(change.complaint_id)
            if len(members) != incident.totalComplaintCount or len(members) > 30:
                raise IncidentError(409, "Incomplete bounded membership snapshot")
            payload = incident.model_dump(mode="json") | {
                "memberIds": sorted(members),
                "catalogPartition": "INCIDENTS",
                "catalogSortKey": f"{incident.createdAt}#{identity}",
            }
            put = {
                "TableName": self.table,
                "Item": marshal(payload),
                "ConditionExpression": "#version=:version"
                if before
                else "attribute_not_exists(incidentId)",
            }
            if before:
                put.update(
                    ExpressionAttributeNames={"#version": "version"},
                    ExpressionAttributeValues=marshal({":version": before.version}),
                )
            transaction.append({"Put": put})
        for identity, member in observed.items():
            condition, names, values = self.membership_condition(member)
            common = {
                "TableName": self.complaints.table,
                "Key": marshal({"complaintId": identity}),
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
            }
            if identity in changes:
                values[":target"] = changes[identity].new_incident_id
                transaction.append(
                    {
                        "Update": common
                        | {
                            "UpdateExpression": "SET incidentId=:target",
                            "ExpressionAttributeValues": marshal(values),
                        }
                    }
                )
            else:
                transaction.append(
                    {"ConditionCheck": common | {"ExpressionAttributeValues": marshal(values)}}
                )
        result = plan.after[plan.result_incident_id].model_dump(mode="json")
        if plan.operation == "AUTOMATIC_LINK":
            ids = sorted(observed)
            for index, first in enumerate(ids):
                for second in ids[index + 1 :]:
                    candidate_id, _, _ = canonical_pair(first, second)
                    transaction.append(
                        {
                            "ConditionCheck": {
                                "TableName": self.complaints.table,
                                "Key": marshal({"complaintId": f"duplicate#{candidate_id}"}),
                                "ConditionExpression": "attribute_not_exists(complaintId) "
                                "OR reviewStatus<>:dismissed",
                                "ExpressionAttributeValues": marshal({":dismissed": "DISMISSED"}),
                            }
                        }
                    )
        transaction.append(
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(
                        {
                            "incidentId": f"operation#{plan.operation_id}",
                            "fingerprint": plan.fingerprint,
                            "result": result,
                            "createdAt": plan.created_at,
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(incidentId)",
                }
            }
        )
        for identity, incident in plan.after.items():
            payload = {
                "before": plan.before[identity].model_dump(mode="json")
                if plan.before[identity]
                else None,
                "after": incident.model_dump(mode="json"),
                "changes": [asdict(c) for c in plan.changes],
            }
            transaction.append(
                {
                    "Put": {
                        "TableName": self.audit_table,
                        "Item": marshal(
                            {
                                "entityId": f"incident#{identity}",
                                "timestampEventId": plan.created_at
                                + "#"
                                + stable_id(plan.operation_id + identity),
                                "eventId": stable_id(f"audit/{plan.operation_id}/{identity}"),
                                "operationId": plan.operation_id,
                                "operation": plan.operation,
                                "actorId": plan.actor.id,
                                "actorType": plan.actor.type,
                                "reason": plan.reason,
                                "createdAt": plan.created_at,
                                "evidence": payload,
                            }
                        ),
                        "ConditionExpression": "attribute_not_exists(entityId) "
                        "AND attribute_not_exists(timestampEventId)",
                    }
                }
            )
        metrics = self.metric_delta(plan)
        transaction.append(
            {
                "Update": {
                    "TableName": self.table,
                    "Key": marshal({"incidentId": "summary#incidents"}),
                    "UpdateExpression": "ADD " + ",".join(f"#{key} :{key}" for key in metrics),
                    "ExpressionAttributeNames": {f"#{key}": key for key in metrics},
                    "ExpressionAttributeValues": marshal(
                        {f":{key}": value for key, value in metrics.items()}
                    ),
                }
            }
        )
        if plan.operation == "RECHECK":
            for member in plan.observed:
                source = member.complaint.complaintId
                for prefix, partition in (
                    ("matching-job", "JOBS"),
                    ("clustering-job", "CLUSTERING_JOBS"),
                ):
                    transaction.append(
                        {
                            "Update": {
                                "TableName": self.complaints.table,
                                "Key": marshal({"complaintId": f"{prefix}#{source}"}),
                                "UpdateExpression": "SET #state=:pending,availableAt=:zero,"
                                "matchingPartition=:partition,"
                                "matchingSortKey=:source,updatedAt=:now",
                                "ConditionExpression": "#state<>:running",
                                "ExpressionAttributeNames": {"#state": "state"},
                                "ExpressionAttributeValues": marshal(
                                    {
                                        ":pending": "PENDING",
                                        ":zero": 0,
                                        ":partition": partition,
                                        ":source": source,
                                        ":now": plan.created_at,
                                        ":running": "RUNNING",
                                    }
                                ),
                            }
                        }
                    )
        # Application envelope deliberately stays below future provider limits. Never chunk a merge.
        from app.integrations.database.dynamodb_priority import dirty_priority_actions

        transaction.extend(dirty_priority_actions(self, plan))
        from app.integrations.database.dynamodb_work import work_invalidation_actions

        transaction.extend(work_invalidation_actions(self, plan))
        from app.integrations.database.dynamodb_events import incident_event_actions

        transaction.extend(incident_event_actions(self, plan))
        if (
            len(transaction) > 95
            or len(json.dumps(transaction, default=str).encode()) > 3_000_000
            or any(
                len(json.dumps(action, default=str).encode()) > 380_000 for action in transaction
            )
        ):
            raise IncidentError(
                413, "Incident operation exceeds the atomic envelope; use a smaller correction"
            )
        try:
            self.call(
                "transact_write_items",
                TransactItems=transaction,
                ClientRequestToken=plan.operation_id,
            )
        except Exception as error:
            replay = self.operation(plan.operation_id, plan.fingerprint)
            if replay is not None:
                return replay
            raise IncidentError(
                409, "Transaction conflicted or outcome unavailable; retry the SAME operation ID"
            ) from error
        return result

    @staticmethod
    def metric_delta(plan):
        def metrics(incident):
            active = bool(incident and incident.status == "OPEN")
            return [
                int(active),
                int(active and incident.totalComplaintCount == 1),
                int(active and incident.totalComplaintCount > 1),
                incident.totalComplaintCount if active else 0,
                int(bool(incident and incident.status == "MERGED")),
            ]

        keys = (
            "activeIncidents",
            "singleReportIncidents",
            "multiReportIncidents",
            "linkedComplaints",
            "mergedIncidentRecords",
        )
        delta = dict.fromkeys(keys, 0)
        for identity, after in plan.after.items():
            for key, old, new in zip(
                keys, metrics(plan.before[identity]), metrics(after), strict=True
            ):
                delta[key] += new - old
        delta["splitOperations"] = int(plan.operation == "SPLIT")
        delta["correctionOperations"] = int(plan.operation in ("SPLIT", "UNLINK", "CORRECTION"))
        return delta

    def catalog(self, filters, limit, after):
        items, last, visited = [], after, 0
        while len(items) < limit and visited < 200:
            arguments = {
                "TableName": self.table,
                "IndexName": "ByCatalog",
                "KeyConditionExpression": "catalogPartition=:partition",
                "ExpressionAttributeValues": marshal({":partition": "INCIDENTS"}),
                "ScanIndexForward": filters.get("sort", "newest") == "oldest",
                "Limit": 1,
            }
            if last:
                arguments["ExclusiveStartKey"] = marshal(
                    {
                        "incidentId": last[1],
                        "catalogPartition": "INCIDENTS",
                        "catalogSortKey": f"{last[0]}#{last[1]}",
                    }
                )
            response = self.call("query", **arguments)
            rows = response.get("Items", [])
            if not rows:
                return items, None
            key = unmarshal(rows[0])
            identity = key["incidentId"]
            incident = self.load(identity)
            created = key["catalogSortKey"].split("#", 1)[0]
            last = [created, identity]
            visited += 1
            if (
                incident
                and all(
                    not filters.get(field) or filters[field] == getattr(incident, field)
                    for field in ("category", "status")
                )
                and (
                    not filters.get("q")
                    or filters["q"].casefold() in incident.canonicalTitle.casefold()
                )
            ):
                items.append(
                    incident.model_dump(mode="json")
                    | {"reviewNeeded": self.review_needed(identity)}
                )
            if not response.get("LastEvaluatedKey"):
                return items, None
        return items, last

    def review_needed(self, identity):
        # Derived from the last bounded clustering run, not a fabricated live global total.
        for member in self.members(identity):
            job = self.job(member.complaint.complaintId)
            if job and (job.get("report") or {}).get("recommendations"):
                return True
        return False

    def history(self, identity, limit, after):
        arguments = {
            "TableName": self.audit_table,
            "KeyConditionExpression": "entityId=:entity",
            "ExpressionAttributeValues": marshal({":entity": f"incident#{identity}"}),
            "ConsistentRead": True,
            "Limit": limit,
        }
        if after:
            arguments["ExclusiveStartKey"] = marshal(
                {"entityId": f"incident#{identity}", "timestampEventId": after[1]}
            )
        response = self.call("query", **arguments)
        items = [
            json.loads(json.dumps(unmarshal(row), default=float))
            for row in response.get("Items", [])
        ]
        next_key = (
            [items[-1]["createdAt"], items[-1]["timestampEventId"]]
            if items and response.get("LastEvaluatedKey")
            else None
        )
        return items, next_key

    def summary(self):
        item = self.read("summary#incidents") or {}
        return {
            key: item.get(key, 0)
            for key in (
                "activeIncidents",
                "singleReportIncidents",
                "multiReportIncidents",
                "linkedComplaints",
                "mergedIncidentRecords",
                "splitOperations",
                "correctionOperations",
            )
        } | {
            "pendingClusteringReviews": None,
            "pendingReviewNote": "Global review count unavailable from eventual work indexes",
        }

    def enqueue(self, source, attempt=0):
        key = marshal({"complaintId": f"clustering-job#{source}"})
        try:
            self.call(
                "update_item",
                TableName=self.complaints.table,
                Key=key,
                UpdateExpression="SET #state=:pending,availableAt=:zero,rerunRequested=:false,"
                "matchingPartition=:partition,matchingSortKey=:source,updatedAt=:now",
                ConditionExpression="attribute_not_exists(#state) OR #state<>:running",
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues=marshal(
                    {
                        ":pending": "PENDING",
                        ":zero": 0,
                        ":false": False,
                        ":partition": "CLUSTERING_JOBS",
                        ":source": source,
                        ":now": timestamp(),
                        ":running": "RUNNING",
                    }
                ),
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            try:
                self.call(
                    "update_item",
                    TableName=self.complaints.table,
                    Key=key,
                    UpdateExpression="SET rerunRequested=:true",
                    ConditionExpression="#state=:running",
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues=marshal({":true": True, ":running": "RUNNING"}),
                )
            except ClientError as race:
                if (
                    race.response["Error"]["Code"] == "ConditionalCheckFailedException"
                    and attempt < 2
                ):
                    return self.enqueue(source, attempt + 1)
                raise

    def claim(self, source=None):
        if source:
            ids = [source]
        else:
            response = self.call(
                "query",
                TableName=self.complaints.table,
                IndexName="MatchingWork",
                KeyConditionExpression="matchingPartition=:partition",
                ExpressionAttributeValues=marshal({":partition": "CLUSTERING_JOBS"}),
                Limit=32,
            )
            ids = [
                unmarshal(row)["complaintId"].removeprefix("clustering-job#")
                for row in response.get("Items", [])
            ]
        for identity in ids:
            job = self.matching.read(f"clustering-job#{identity}")
            if (
                not job
                or job["state"] not in ("PENDING", "RUNNING", "RETRY")
                or job.get("availableAt", 0) > time.time()
            ):
                continue
            token = str(uuid4())
            try:
                self.complaints.client.update_item(
                    TableName=self.complaints.table,
                    Key=marshal({"complaintId": f"clustering-job#{identity}"}),
                    UpdateExpression="SET #state=:running,leaseToken=:token,availableAt=:lease,"
                    "rerunRequested=:false,updatedAt=:now ADD attempts :one",
                    ConditionExpression="#state=:previous AND availableAt<=:time",
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues=marshal(
                        {
                            ":running": "RUNNING",
                            ":token": token,
                            ":lease": time.time() + 120,
                            ":false": False,
                            ":now": timestamp(),
                            ":one": 1,
                            ":previous": job["state"],
                            ":time": time.time(),
                        }
                    ),
                )
                return identity, token
            except ClientError as error:
                if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
        return None

    def finish_job(self, source, token, report):
        job = self.matching.read(f"clustering-job#{source}") or {}
        rerun = job.get("rerunRequested", False)
        self.call(
            "update_item",
            TableName=self.complaints.table,
            Key=marshal({"complaintId": f"clustering-job#{source}"}),
            UpdateExpression="SET #state=:state,availableAt=:zero,report=:report,updatedAt=:now "
            + (
                "REMOVE errorCategory"
                if rerun
                else "REMOVE errorCategory,matchingPartition,matchingSortKey"
            ),
            ConditionExpression="leaseToken=:token AND rerunRequested=:rerun AND #state=:running",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues=marshal(
                {
                    ":state": "PENDING" if rerun else "COMPLETE",
                    ":zero": 0,
                    ":report": report,
                    ":now": timestamp(),
                    ":token": token,
                    ":rerun": rerun,
                    ":running": "RUNNING",
                }
            ),
        )

    def fail_job(self, source, token, error):
        self.call(
            "update_item",
            TableName=self.complaints.table,
            Key=marshal({"complaintId": f"clustering-job#{source}"}),
            UpdateExpression="SET #state=:retry,availableAt=:time,errorCategory=:error",
            ConditionExpression="leaseToken=:token AND #state=:running",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues=marshal(
                {
                    ":retry": "RETRY",
                    ":time": time.time() + 60,
                    ":error": error,
                    ":token": token,
                    ":running": "RUNNING",
                }
            ),
        )

    def job(self, source):
        job = self.matching.read(f"clustering-job#{source}")
        return (
            {
                key: job.get(key)
                for key in ("state", "attempts", "report", "errorCategory", "updatedAt")
            }
            if job
            else None
        )

    def candidates(self, source, limit):
        job = self.matching.job(source)
        report = (job or {}).get("report") or {}
        ids = report.get("candidateIds", [])
        return ids[:limit], len(ids) > limit or "candidateIds" not in report or report.get(
            "incomplete", False
        )
