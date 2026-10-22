"""Source-only conditional Phase12 persistence port on the existing operations table.

The port accepts server-validated change plans, NEVER arbitrary HTTP patches. Canonical
incident/assignment/eligibility guards must join the same transaction. No SDK or AWS calls at
import; no Scan, public evidence, local fallback or synthetic cloud success.
"""

import hashlib
import json
from uuid import UUID

from botocore.exceptions import ClientError

from app.events.schema import Event
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.dynamodb_events import event_action
from app.models.incident import IncidentError

KINDS = frozenset(
    ("attempt", "request", "response", "resolution", "recurrence", "fairness-review", "audit")
)
ACCESS = frozenset(
    (
        "incident-attempts",
        "citizen-requests",
        "attempt-responses",
        "incident-recurrences",
        "scope-confirmed-recurrences",
        "area-reviews",
        "pending-repairs",
    )
)


class DynamoIntelligence:
    def __init__(self, settings, client):
        self.settings, self.client, self.table = settings, client, settings.workflow_table_name

    def call(self, method, **args):
        if not self.table:
            raise IncidentError(503, "Operations table configuration required")
        return getattr(self.client, method)(**args)

    @staticmethod
    def key(kind, identity):
        if kind not in KINDS:
            raise ValueError("Unsupported intelligence record type")
        UUID(identity)
        return {"pk": f"intelligence#{kind}#{identity}", "sk": "0"}

    def get(self, kind, identity):
        result = self.call(
            "get_item",
            TableName=self.table,
            Key=marshal(self.key(kind, identity)),
            ConsistentRead=True,
        )
        item = result.get("Item")
        return unmarshal(item) if item else None

    def page(self, access, subject, after=None, limit=25):
        if access not in ACCESS or not isinstance(subject, str) or not 1 <= len(subject) <= 128:
            raise ValueError("Invalid access pattern")
        if not 1 <= limit <= 50:
            raise ValueError("Page limit1–50 required")
        args = {
            "TableName": self.table,
            "IndexName": "ByQueue",
            "KeyConditionExpression": "queue=:q",
            "ExpressionAttributeValues": marshal({":q": f"intelligence#{access}#{subject}"}),
            "Limit": limit,
        }
        if after:
            # API layer must supply a context-bound cursor, not an unchecked table key.
            args["ExclusiveStartKey"] = after
        result = self.call("query", **args)
        items = []
        for pointer in result.get("Items", []):
            decoded = unmarshal(pointer)
            value = self.call(
                "get_item",
                TableName=self.table,
                Key=marshal({k: decoded[k] for k in ("pk", "sk")}),
                ConsistentRead=True,
            )
            if value.get("Item"):
                record = unmarshal(value["Item"])
                target = record.get("target")
                if target:
                    resolved = self.call(
                        "get_item", TableName=self.table, Key=marshal(target), ConsistentRead=True
                    )
                    if resolved.get("Item"):
                        items.append(unmarshal(resolved["Item"]))
        return {
            "items": items,
            "lastKey": result.get("LastEvaluatedKey"),
            "indexConsistency": "EVENTUAL; authorization/current membership must be rechecked",
        }

    def commit(self, operation_id, actor_id, changes, guards, events=(), indexes=()):
        UUID(operation_id)
        if not guards or not 1 <= len(changes) <= 30 or len(indexes) > 30 or len(events) > 10:
            raise ValueError("Bounded changes and canonical source guards required")
        event_contracts = [
            (e.eventType, str(e.aggregateId), e.model_dump(mode="json")["payload"]) for e in events
        ]
        fingerprint = hashlib.sha256(
            json.dumps(
                [actor_id, changes, guards, list(indexes), event_contracts],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        receipt_key = {"pk": "intelligence-operation#" + operation_id, "sk": "0"}
        receipt = self.call(
            "get_item", TableName=self.table, Key=marshal(receipt_key), ConsistentRead=True
        )
        if receipt.get("Item"):
            saved = unmarshal(receipt["Item"])
            if saved["fingerprint"] != fingerprint:
                raise IncidentError(409, "Operation ID already used with different input")
            return {"operationId": operation_id, "replayed": True}
        actions = []
        seen = set()
        for item in changes:
            key = self.key(item["kind"], item["id"])
            identity = (key["pk"], key["sk"])
            if (
                identity in seen
                or type(item["expectedVersion"]) is not int
                or item["expectedVersion"] < 0
            ):
                raise ValueError("Duplicate change or invalid version")
            seen.add(identity)
            if len(json.dumps(item["data"], allow_nan=False).encode()) > 100000:
                raise ValueError("Record exceeds100KB bound")
            version = item["expectedVersion"]
            put = {
                "TableName": self.table,
                "Item": marshal(key | {"revision": version + 1, "data": item["data"]}),
                "ConditionExpression": "revision=:v" if version else "attribute_not_exists(pk)",
            }
            if version:
                put["ExpressionAttributeValues"] = marshal({":v": version})
            actions.append({"Put": put})
        for index in indexes:
            if index["access"] not in ACCESS:
                raise ValueError("Invalid index access pattern")
            target = self.key(index["kind"], index["id"])
            identity = hashlib.sha256(json.dumps(index, sort_keys=True).encode()).hexdigest()
            # Sparse pointers reference one canonical record, not copies of business state.
            actions.append(
                {
                    "Put": {
                        "TableName": self.table,
                        "Item": marshal(
                            {
                                "pk": "intelligence-index#" + identity,
                                "sk": "0",
                                "queue": f"intelligence#{index['access']}#{index['subject']}",
                                "due": index["id"],
                                "target": target,
                                "revision": 1,
                            }
                        ),
                    }
                }
            )
        for guard in guards:
            if set(guard) != {"ConditionCheck"} or not guard["ConditionCheck"].get(
                "ConditionExpression"
            ):
                raise ValueError("Source condition check required")
            actions.append(guard)
        for event in events:
            if not isinstance(event, Event):
                raise ValueError("Versioned domain event required")
            actions.extend(event_action(self.settings, event))
        actions.append(
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(
                        receipt_key | {"fingerprint": fingerprint, "actorId": actor_id}
                    ),
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
        )
        if len(actions) > 100:
            raise ValueError("DynamoDB transaction action bound exceeded")
        try:
            self.call(
                "transact_write_items", TransactItems=actions, ClientRequestToken=operation_id
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in (
                "TransactionCanceledException",
                "ConditionalCheckFailedException",
            ):
                raise IncidentError(409, "Source/version changed; refresh and review") from error
            raise IncidentError(
                503, ("Cloud persistence unavailable; retry same operation")
            ) from error
        return {"operationId": operation_id, "replayed": False}
