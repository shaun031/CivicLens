"""Bounded versioned projection preparation in the existing operations table; never Scan.

Publication is an explicit controlled rebuild step, not an HTTP raw-data ingestion endpoint.
No published/stale manifest means unavailable, never fabricated citywide zeroes.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.models.incident import IncidentError

LIMITS = {
    "incidents": 10000,
    "complaints": 20000,
    "departments": 100,
    "officers": 1000,
    "history": 50000,
    "audit": 50000,
    "escalations": 20000,
    "policies": 100,
    "priorityHistory": 50000,
    "membershipHistory": 20000,
}

FIELDS = {
    "incidents": set(
        [
            "incident_id",
            "category",
            "latitude",
            "longitude",
            "status",
            "first_reported_at",
            "created_at",
            "updated_at",
            "resolved_at",
            "version",
            "needs_recalculation",
            "source_version",
            "config_version",
            "next_due",
            "priority_band",
            "calculated_score",
            "effective_score",
            "urgent_hazard",
            "assessment_status",
            "override_status",
            "calculated_at",
            "department_id",
            "officer_id",
            "assignment_status",
            "percentage",
            "assigned_at",
            "cycle",
            "opened_at",
        ]
    ),
    "complaints": set(
        [
            "complaint_id",
            "citizen_id",
            "incident_id",
            "category",
            "reported_severity",
            "latitude",
            "longitude",
            "created_at",
        ]
    ),
    "departments": set(["id", "code", "name", "active"]),
    "officers": set(
        [
            "officer_id",
            "department_id",
            "active",
            "availability",
            "capacity",
            "display_name",
            "role",
            "is_active",
            "is_verified",
        ]
    ),
    "history": set(["event_id", "entity_id", "actor_id", "kind", "created_at", "after_state"]),
    "audit": set(
        [
            "event_id",
            "incident_id",
            "operation",
            "created_at",
            "previous_status",
            "next_status",
            "resolved_at",
        ]
    ),
    "escalations": set(["incident_id", "cycle", "milestone", "status", "created_at", "deadline"]),
    "policies": set(
        [
            "policy_id",
            "priority_band",
            "category",
            "department_id",
            "urgent",
            "response_hours",
            "resolution_hours",
            "version",
            "updated_at",
            "updated_by",
        ]
    ),
    "priorityHistory": set(["event_id", "incident_id", "kind", "created_at", "band"]),
    "membershipHistory": set(["membership_event_id", "complaint_id", "operation", "created_at"]),
}
FIELDS["incidents"].add("unresolved_seconds")
FIELDS["incidents"].add("has_priority_result")


class DynamoAnalytics:
    def __init__(self, settings, client=None):
        self.settings, self._client = settings, client
        self.table = settings.workflow_table_name
        self.pk = "analytics#" + settings.analytics_scope
        self.serializer, self.deserializer = TypeSerializer(), TypeDeserializer()

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "dynamodb",
                config=Config(
                    connect_timeout=3,
                    read_timeout=5,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self._client

    def encode(self, value):
        def number(value):
            if isinstance(value, Decimal):
                return int(value) if value == value.to_integral_value() else float(value)
            raise TypeError("Unsupported analytics DynamoDB value")

        return {
            k: self.serializer.serialize(v)
            for k, v in json.loads(
                json.dumps(value, default=number, allow_nan=False), parse_float=Decimal
            ).items()
        }

    def load(self):
        if not self.table:
            raise IncidentError(503, "Analytics projection storage is not configured")
        value = self.client.get_item(
            TableName=self.table,
            Key=self.encode({"pk": self.pk, "sk": "manifest"}),
            ConsistentRead=True,
        )
        if "Item" not in value:
            return None
        return {k: self.deserializer.deserialize(v) for k, v in value["Item"].items()}

    def snapshot(self):
        try:
            return self._snapshot()
        except (KeyError, ValueError, TypeError) as error:
            raise IncidentError(
                503, "Analytics projection is invalid; controlled rebuild required"
            ) from error

    def _snapshot(self):
        manifest = self.load()
        if not manifest or manifest.get("dirty", True) or manifest.get("version") != 1:
            raise IncidentError(
                503, "Municipal projection absent/stale; controlled rebuild required"
            )
        if (
            datetime.now(UTC) - datetime.fromisoformat(manifest["calculatedAt"])
        ).total_seconds() > 3600:
            raise IncidentError(503, "Municipal projection expired; controlled rebuild required")
        items = []
        after = None
        size = 0
        for _ in range(20):
            args = {
                "TableName": self.table,
                "KeyConditionExpression": "pk=:pk AND begins_with(sk,:prefix)",
                "ExpressionAttributeValues": self.encode(
                    {":pk": self.pk + "#" + manifest["generation"], ":prefix": "chunk#"}
                ),
                "ConsistentRead": True,
                "Limit": 25,
            }
            if after:
                args["ExclusiveStartKey"] = after
            page = self.client.query(**args)
            for raw in page.get("Items", []):
                item = {k: self.deserializer.deserialize(v) for k, v in raw.items()}
                size += len(item["body"].encode())
                if size > 5 * 1024 * 1024:
                    raise IncidentError(413, "Municipal projection exceeds5MiB")
                items.append(item)
            after = page.get("LastEvaluatedKey")
            if not after:
                break
        if after or len(items) != int(manifest["chunks"]):
            raise IncidentError(503, "Projection incomplete; no partial totals returned")
        result = {
            name: []
            for name in (
                "incidents",
                "complaints",
                "departments",
                "officers",
                "history",
                "audit",
                "escalations",
                "policies",
                "priorityHistory",
                "membershipHistory",
            )
        }
        for item in items:
            if hashlib.sha256(item["body"].encode()).hexdigest() != item.get("digest"):
                raise IncidentError(503, "Projection checksum mismatch")
            body = json.loads(item["body"])
            if body.get("collection") not in result or not isinstance(body.get("rows"), list):
                raise IncidentError(503, "Invalid analytics projection collection")
            result[body["collection"]].extend(body["rows"])
            if len(result[body["collection"]]) > LIMITS[body["collection"]]:
                raise IncidentError(413, "Analytics projection collection exceeds bounded capacity")
        current = self.load()
        if (
            not current
            or current.get("revision") != manifest["revision"]
            or current.get("generation") != manifest["generation"]
            or current.get("dirty")
        ):
            raise IncidentError(409, "Projection changed during read; refresh")
        result["meta"] = {
            "revision": int(manifest["revision"]),
            "observed_at": manifest["calculatedAt"],
            "cloudCalculatedAt": manifest["calculatedAt"],
        }
        return result

    def stage_source(self, source, generation, expected_revision, calculated_at):
        """Trusted bounded source-reader output only; restart-safe immutable generation chunks.

        This is not a public upload API or a scan-based automatic cloud backfill.
        The future cloud bootstrap must supply a reconciled complete municipal source cohort.
        """
        if set(source) - {"meta"} != set(LIMITS):
            raise IncidentError(422, "A complete reconciled source cohort is required")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", generation):
            raise IncidentError(422, "Safe generation identity required")
        now = datetime.fromisoformat(calculated_at)
        if now.tzinfo is None or now.utcoffset().total_seconds() != 0:
            raise IncidentError(422, "Aware projection timestamp required")
        bodies = []
        for collection, cap in LIMITS.items():
            rows = source.get(collection, [])
            if not isinstance(rows, list) or len(rows) > cap:
                raise IncidentError(413, "Analytics source collection exceeds bound")
            for offset in range(0, max(1, len(rows)), 50):
                body = json.dumps(
                    {"collection": collection, "rows": rows[offset : offset + 50]},
                    sort_keys=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                if len(body.encode()) > 240000:
                    raise IncidentError(413, "Projection chunk exceeds240KB; reduce reader batch")
                bodies.append(body)
        if sum(len(body.encode()) for body in bodies) > 5 * 1024 * 1024 or len(bodies) > 500:
            raise IncidentError(413, "Complete municipal cohort exceeds bounded5MiB projection")
        # Schema privacy is checked before any staged writes.
        for body in bodies:
            record = json.loads(body)
            if any(set(row) - FIELDS[record["collection"]] for row in record["rows"]):
                raise IncidentError(422, "Only allowlisted minimal projection fields are permitted")
            forbidden = {
                "email",
                "password_hash",
                "description",
                "canonical_description",
                "storage_key",
                "password",
                "note",
                "reason",
                "canonical_title",
            }
            if any(forbidden.intersection(row) for row in record["rows"]):
                raise IncidentError(
                    422, "Private source fields are not analytics projection columns"
                )
            if record["collection"] == "history":
                for row in record["rows"]:
                    if set(json.loads(row["after_state"])) - {
                        "departmentId",
                        "officerId",
                        "status",
                        "assignedAt",
                        "percentage",
                    }:
                        raise IncidentError(422, "Private history fields rejected")
        for index, body in enumerate(bodies):
            digest = hashlib.sha256(body.encode()).hexdigest()
            self.client.put_item(
                TableName=self.table,
                Item=self.encode(
                    {
                        "pk": self.pk + "#" + generation,
                        "sk": f"chunk#{index:06d}",
                        "body": body,
                        "digest": digest,
                        "version": 1,
                    }
                ),
                ConditionExpression="attribute_not_exists(pk) OR digest=:digest",
                ExpressionAttributeValues=self.encode({":digest": digest}),
            )
        self.publish(generation, expected_revision, len(bodies), calculated_at)
        return {
            "generation": generation,
            "chunks": len(bodies),
            "sourceRevision": expected_revision,
        }

    def observe(self, event):
        # Transactional receipt makes duplicate invalidation a no-op; delayed events can only mark
        # stale, never roll an entity or aggregate backwards or apply another arithmetic increment.
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": self.encode(
                                {
                                    "pk": self.pk,
                                    "sk": "event#" + str(event.eventId),
                                    "occurredAt": event.occurredAt.isoformat(),
                                    "version": 1,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table,
                            "Key": self.encode({"pk": self.pk, "sk": "manifest"}),
                            "UpdateExpression": "SET dirty=:yes ADD revision :one",
                            "ExpressionAttributeValues": self.encode({":yes": True, ":one": 1}),
                        }
                    },
                ]
            )
        except ClientError as error:
            reasons = error.response.get("CancellationReasons", [])
            if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
                return False
            raise
        return True

    def publish(self, generation, expected_revision, chunks, calculated_at):
        """Publish only a previously staged, fully reconciled generation using a revision fence."""
        if not 0 < chunks <= 500 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", generation):
            raise IncidentError(422, "Bounded projection generation/chunks required")
        self.client.put_item(
            TableName=self.table,
            Item=self.encode(
                {
                    "pk": self.pk,
                    "sk": "manifest",
                    "generation": generation,
                    "chunks": chunks,
                    "calculatedAt": calculated_at,
                    "version": 1,
                    "revision": expected_revision,
                    "dirty": False,
                }
            ),
            ConditionExpression=(
                "revision=:revision OR (attribute_not_exists(revision) AND :revision=:zero)"
            ),
            ExpressionAttributeValues=self.encode({":revision": expected_revision, ":zero": 0}),
        )

    def audit_export(self, actor, report, filters, count, now):
        from uuid import uuid4

        self.client.put_item(
            TableName=self.table,
            Item=self.encode(
                {
                    "pk": self.pk,
                    "sk": "export#" + str(uuid4()),
                    "actorId": actor,
                    "report": report,
                    "filters": json.dumps(filters, sort_keys=True),
                    "rowCount": count,
                    "generatedAt": now,
                }
            ),
        )
