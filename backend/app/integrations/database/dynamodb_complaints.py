import hashlib
import json
import time
from decimal import Decimal

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.core.config import Settings
from app.models.complaint import Complaint, ComplaintPage, ComplaintSummary
from app.repositories.complaint_repository import RepositoryUnavailable, RepositoryUncertain
from app.utils.cursors import decode_cursor, encode_cursor
from app.utils.geography import geo_cell

serializer, deserializer = TypeSerializer(), TypeDeserializer()


def marshal(item: dict) -> dict:
    safe = json.loads(json.dumps(item), parse_float=Decimal)
    return {key: serializer.serialize(value) for key, value in safe.items()}


def unmarshal(item: dict) -> dict:
    return {key: deserializer.deserialize(value) for key, value in item.items()}


class DynamoComplaints:
    """Only ByCitizen Query/Get/BatchGet and conditional writes; no Scan or import-time client."""

    def __init__(self, settings: Settings, client=None):
        if not settings.complaints_table_name:
            raise ValueError("COMPLAINTS_TABLE_NAME is required for DynamoDB")
        self.settings, self.table, self._client = settings, settings.complaints_table_name, client
        from app.integrations.database.dynamodb_discovery import DynamoDiscovery

        self.discovery = DynamoDiscovery(self)

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

    def read(self, key: str) -> dict | None:
        try:
            response = self.client.get_item(
                TableName=self.table, Key=marshal({"complaintId": key}), ConsistentRead=True
            )
            return unmarshal(response["Item"]) if response.get("Item") else None
        except (ClientError, BotoCoreError) as error:
            raise RepositoryUnavailable from error

    @staticmethod
    def request_id(citizen: str, key: str) -> str:
        return "request#" + hashlib.sha256(f"{citizen}:{key}".encode()).hexdigest()

    def request(self, citizen: str, key: str, fingerprint: str) -> Complaint | None:
        item = self.read(self.request_id(citizen, key))
        if item is None:
            return None
        if item["fingerprint"] != fingerprint:
            raise HTTPException(409, "This request key was already used with different content.")
        result = self.get(item["target"], citizen)
        if result is None:
            raise RepositoryUncertain
        return result

    def rate_limit(self, citizen: str) -> None:
        now = int(time.time())
        window = now // self.settings.complaint_rate_window
        key = marshal({"complaintId": "rate#" + hashlib.sha256(citizen.encode()).hexdigest()})
        try:
            try:
                self.client.update_item(
                    TableName=self.table,
                    Key=key,
                    UpdateExpression="SET #window=:window, attempts=:one",
                    ConditionExpression="attribute_not_exists(#window) OR #window<>:window",
                    ExpressionAttributeNames={"#window": "window"},
                    ExpressionAttributeValues=marshal({":window": window, ":one": 1}),
                )
            except ClientError as error:
                if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                self.client.update_item(
                    TableName=self.table,
                    Key=key,
                    UpdateExpression="SET attempts=attempts+:one",
                    ConditionExpression="#window=:window AND attempts<:limit",
                    ExpressionAttributeNames={"#window": "window"},
                    ExpressionAttributeValues=marshal(
                        {":window": window, ":one": 1, ":limit": self.settings.complaint_rate_limit}
                    ),
                )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise HTTPException(
                    429,
                    "Complaint submission limit reached. Try again later.",
                    headers={
                        "Retry-After": str((window + 1) * self.settings.complaint_rate_window - now)
                    },
                ) from error
            raise RepositoryUnavailable from error
        except BotoCoreError as error:
            raise RepositoryUnavailable from error

    def create(self, complaint: Complaint, key: str, fingerprint: str) -> tuple[Complaint, bool]:
        existing = self.request(complaint.citizenId, key, fingerprint)
        if existing:
            return existing, False
        self.rate_limit(complaint.citizenId)
        payload = complaint.model_dump(mode="json")
        # Image metadata is embedded in the one complaint item, below the 400 KiB item limit.
        payload["images"] = [
            image.model_dump() | {"storageKey": image.storageKey} for image in complaint.images
        ]
        payload["internalGeoCell"] = geo_cell(complaint.latitude, complaint.longitude)
        payload["internalGeoSortKey"] = complaint.complaintId
        # Server-only eligibility snapshot: HTTP creation requires an active verified CITIZEN.
        payload["reporterEligible"] = True
        job = {
            "Put": {
                "TableName": self.table,
                "Item": marshal(
                    {
                        "complaintId": f"matching-job#{complaint.complaintId}",
                        "sourceId": complaint.complaintId,
                        "state": "PENDING",
                        "attempts": 0,
                        "availableAt": 0,
                        "updatedAt": complaint.createdAt,
                        "matchingPartition": "JOBS",
                        "matchingSortKey": complaint.complaintId,
                    }
                ),
                "ConditionExpression": "attribute_not_exists(complaintId)",
            }
        }
        transaction = [
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(payload),
                    "ConditionExpression": "attribute_not_exists(complaintId)",
                }
            },
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(
                        {
                            "complaintId": self.request_id(complaint.citizenId, key),
                            "target": complaint.complaintId,
                            "fingerprint": fingerprint,
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(complaintId)",
                }
            },
            {
                "Update": {
                    "TableName": self.table,
                    "Key": marshal({"complaintId": f"summary#{complaint.citizenId}"}),
                    "UpdateExpression": "ADD #total :one, #submitted :one",
                    "ExpressionAttributeNames": {"#total": "total", "#submitted": "submitted"},
                    "ExpressionAttributeValues": marshal({":one": 1}),
                }
            },
            job,
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(
                        {
                            "complaintId": f"clustering-job#{complaint.complaintId}",
                            "sourceId": complaint.complaintId,
                            "state": "PENDING",
                            "attempts": 0,
                            "availableAt": 0,
                            "rerunRequested": False,
                            "updatedAt": complaint.createdAt,
                            "matchingPartition": "CLUSTERING_JOBS",
                            "matchingSortKey": complaint.complaintId,
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(complaintId)",
                }
            },
        ]
        from datetime import datetime

        from app.events.schema import Event, new_event
        from app.integrations.database.dynamodb_events import event_action
        from app.models.incident import stable_id

        event = new_event(
            "ComplaintSubmitted",
            complaint.complaintId,
            now=datetime.fromisoformat(complaint.createdAt.replace("Z", "+00:00")),
        )
        event = Event.parse(
            event.model_dump(mode="json")
            | {"eventId": stable_id("submitted/" + complaint.complaintId)}
        )
        transaction.extend(event_action(self.settings, event))
        from app.integrations.database.dynamodb_nearby import region_projection

        transaction.append(
            {
                "Put": {
                    "TableName": self.table,
                    "Item": marshal(region_projection(complaint)),
                    "ConditionExpression": "attribute_not_exists(complaintId)",
                }
            }
        )
        try:
            self.client.transact_write_items(
                TransactItems=transaction, ClientRequestToken=complaint.complaintId
            )
            return complaint, True
        except (ClientError, BotoCoreError) as error:
            try:
                existing = self.request(complaint.citizenId, key, fingerprint)
                if existing:
                    return existing, existing.complaintId == complaint.complaintId
            except RepositoryUnavailable as unknown:
                raise RepositoryUncertain from unknown
            if (
                isinstance(error, ClientError)
                and error.response["Error"]["Code"] == "TransactionCanceledException"
            ):
                raise RepositoryUnavailable from error  # DynamoDB canceled the whole transaction.
            raise RepositoryUncertain from error  # Never delete evidence after an ambiguous commit.

    def get(self, complaint_id: str, citizen: str) -> Complaint | None:
        item = self.read(complaint_id)
        return self.hydrate(item) if item and item.get("citizenId") == citizen else None

    @staticmethod
    def hydrate(item: dict) -> Complaint:
        # Internal optimistic-concurrency state is not part of the private API contract.
        return Complaint.model_validate(
            {
                key: value
                for key, value in item.items()
                if key
                not in (
                    "publicationRevision",
                    "internalGeoCell",
                    "internalGeoSortKey",
                    "reporterEligible",
                )
            }
        )

    def list(self, citizen: str, limit: int, cursor: str | None, filters=None) -> ComplaintPage:
        if filters is not None:
            return self.discovery.search(citizen, limit, cursor, filters)
        key = decode_cursor(cursor, citizen, "dynamodb")
        arguments = {
            "TableName": self.table,
            "IndexName": "ByCitizen",
            "KeyConditionExpression": "citizenId=:citizen",
            "ExpressionAttributeValues": marshal({":citizen": citizen}),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if key:
            arguments["ExclusiveStartKey"] = marshal(key)
        try:
            response = self.client.query(**arguments)
            keys = [{"complaintId": item["complaintId"]} for item in response.get("Items", [])]
            found = []
            # KEYS_ONLY GSI: explicitly fetch full records, with bounded unprocessed-key retries.
            pending = {self.table: {"Keys": keys, "ConsistentRead": True}} if keys else {}
            for _ in range(3):
                if not pending:
                    break
                batch = self.client.batch_get_item(RequestItems=pending)
                found.extend(batch.get("Responses", {}).get(self.table, []))
                pending = batch.get("UnprocessedKeys", {})
            if pending:
                raise RepositoryUnavailable
            items = [
                self.hydrate(unmarshal(item))
                for item in found
                if unmarshal(item).get("citizenId") == citizen
            ]
            items.sort(key=lambda item: (item.createdAt, item.complaintId), reverse=True)
            next_cursor = (
                encode_cursor(citizen, "dynamodb", unmarshal(response["LastEvaluatedKey"]))
                if response.get("LastEvaluatedKey")
                else None
            )
            return ComplaintPage(items=items, nextCursor=next_cursor)
        except (ClientError, BotoCoreError) as error:
            raise RepositoryUnavailable from error

    def summary(self, citizen: str, days: int = 30) -> ComplaintSummary:
        return self.discovery.summary(citizen, days)
