"""Source-only AWS adapter. Sparse internal GSIs; no Scan, clients or calls at import."""

import json
import math
import time
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError

from app.algorithms.duplicate_detection.geographic_similarity import envelope
from app.algorithms.duplicate_detection.image_similarity import FINGERPRINT_VERSION, Fingerprint
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.repositories.complaint_repository import RepositoryUnavailable
from app.repositories.duplicate_candidate_repository import timestamp
from app.utils.geography import CELL_DEGREES, cells_for_bounds


class DynamoDuplicateRepository:
    def __init__(self, complaints):
        self.complaints, self.table = complaints, complaints.table

    @property
    def client(self):
        return self.complaints.client

    def call(self, method, **kwargs):
        try:
            return getattr(self.client, method)(**kwargs)
        except (BotoCoreError, ClientError) as error:
            raise RepositoryUnavailable from error

    def read(self, key):
        item = self.complaints.read(key)
        return json.loads(json.dumps(item, default=float)) if item else None

    def load(self, source):
        item = self.read(source)
        return self.complaints.hydrate(item) if item and "citizenId" in item else None

    def nearby(self, source, config):
        area = envelope(source.latitude, source.longitude, config.radius(source.category))
        width = (area.east - area.west) % 360 if area.west > area.east else area.east - area.west
        if (math.ceil(width / CELL_DEGREES) + 1) * (
            math.ceil((area.north - area.south) / CELL_DEGREES) + 1
        ) > 16:
            raise RepositoryUnavailable("Internal geographic query too wide")
        bounds = SimpleNamespace(
            minLatitude=area.south,
            maxLatitude=area.north,
            minLongitude=area.west,
            maxLongitude=area.east,
        )
        cells = cells_for_bounds(bounds)
        # Leave room for job commit in DynamoDB's 100-action atomic transaction limit.
        limit = min(config.candidate_limit, 90)
        found, truncated, visited = {}, False, 0
        for cell in cells:
            key = None
            while True:
                args = dict(
                    TableName=self.table,
                    IndexName="InternalGeography",
                    KeyConditionExpression="internalGeoCell=:cell",
                    ExpressionAttributeValues=marshal({":cell": cell}),
                    Limit=max(1, limit + 1 - visited),
                )
                if key:
                    args["ExclusiveStartKey"] = key
                response = self.call("query", **args)
                for item in response.get("Items", []):
                    visited += 1
                    identity = unmarshal(item)["complaintId"]
                    if identity != source.complaint_id:
                        complaint = self.load(identity)  # strong read revalidates stale GSI entries
                        if complaint:
                            found[identity] = complaint
                key = response.get("LastEvaluatedKey")
                if visited > limit:
                    truncated = True
                    break
                if not key:
                    break
            if truncated:
                break
        # GSI propagation is eventual; a complete response is not a strong snapshot guarantee.
        return list(found.values())[:limit], truncated or len(found) > limit

    def cached(self, image):
        item = self.read(f"fingerprint#{FINGERPRINT_VERSION}#{image}")
        return Fingerprint(item["bits"], item["informative"]) if item else None

    def cache(self, image, value):
        self.call(
            "put_item",
            TableName=self.table,
            Item=marshal(
                {
                    "complaintId": f"fingerprint#{value.version}#{image}",
                    "bits": value.bits,
                    "informative": value.informative,
                }
            ),
        )

    def enqueue(self, source):
        try:
            self.client.update_item(
                TableName=self.table,
                Key=marshal({"complaintId": f"matching-job#{source}"}),
                UpdateExpression="SET #state=:pending, sourceId=:source, availableAt=:zero, "
                "attempts=:zero, matchingPartition=:partition, matchingSortKey=:source, "
                "updatedAt=:now",
                ConditionExpression="attribute_not_exists(#state) OR #state<>:running "
                "OR availableAt<:time",
                ExpressionAttributeNames={"#state": "state"},
                ExpressionAttributeValues=marshal(
                    {
                        ":pending": "PENDING",
                        ":source": source,
                        ":zero": 0,
                        ":partition": "JOBS",
                        ":now": timestamp(),
                        ":running": "RUNNING",
                        ":time": time.time(),
                    }
                ),
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise RepositoryUnavailable from error

    def claim(self, source=None):
        if source:
            ids = [source]
        else:
            response = self.call(
                "query",
                TableName=self.table,
                IndexName="MatchingWork",
                KeyConditionExpression="matchingPartition=:partition",
                ExpressionAttributeValues=marshal({":partition": "JOBS"}),
                Limit=32,
            )
            ids = [
                unmarshal(item)["complaintId"].removeprefix("matching-job#")
                for item in response.get("Items", [])
            ]
        for identity in ids:
            item = self.read(f"matching-job#{identity}")
            if (
                not item
                or item["state"] not in ("PENDING", "RETRY", "RUNNING")
                or item.get("availableAt", 0) > time.time()
            ):
                continue
            token = str(uuid4())
            try:
                self.client.update_item(
                    TableName=self.table,
                    Key=marshal({"complaintId": f"matching-job#{identity}"}),
                    UpdateExpression="SET #state=:running, leaseToken=:token, availableAt=:lease, "
                    "updatedAt=:now ADD attempts :one",
                    ConditionExpression="#state=:previous AND availableAt<=:time",
                    ExpressionAttributeNames={"#state": "state"},
                    ExpressionAttributeValues=marshal(
                        {
                            ":running": "RUNNING",
                            ":token": token,
                            ":lease": time.time() + 120,
                            ":now": timestamp(),
                            ":one": 1,
                            ":previous": item["state"],
                            ":time": time.time(),
                        }
                    ),
                )
                return identity, token
            except ClientError as error:
                if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise RepositoryUnavailable from error
        return None

    def finish(self, source, token, results, report):
        if len(results) > 90:
            raise RepositoryUnavailable("Too many results for one atomic commit")
        now, transaction = timestamp(), []
        for result in results:
            payload = asdict(result)
            payload.pop("timings")
            transaction.append(
                {
                    "Update": {
                        "TableName": self.table,
                        "Key": marshal({"complaintId": f"duplicate#{result.candidateId}"}),
                        "UpdateExpression": "SET payload=:payload, updatedAt=:now, "
                        "createdAt=if_not_exists(createdAt,:now), "
                        "reviewStatus=if_not_exists(reviewStatus,:pending), "
                        "matchingPartition=:partition, matchingSortKey=:sort",
                        "ExpressionAttributeValues": marshal(
                            {
                                ":payload": payload,
                                ":now": now,
                                ":pending": "PENDING_REVIEW",
                                ":partition": "CANDIDATES",
                                ":sort": result.candidateId,
                            }
                        ),
                    }
                }
            )
        transaction.append(
            {
                "Update": {
                    "TableName": self.table,
                    "Key": marshal({"complaintId": f"matching-job#{source}"}),
                    "UpdateExpression": "SET #state=:state, report=:report, configVersion=:config, "
                    "updatedAt=:now REMOVE matchingPartition,matchingSortKey,errorCategory",
                    "ConditionExpression": "leaseToken=:token AND #state=:running",
                    "ExpressionAttributeNames": {"#state": "state"},
                    "ExpressionAttributeValues": marshal(
                        {
                            ":state": "INCOMPLETE" if report["incomplete"] else "COMPLETE",
                            ":report": report,
                            ":config": report["configVersion"],
                            ":now": now,
                            ":token": token,
                            ":running": "RUNNING",
                        }
                    ),
                }
            }
        )
        self.call("transact_write_items", TransactItems=transaction, ClientRequestToken=token)

    def fail(self, source, token, category):
        self.call(
            "update_item",
            TableName=self.table,
            Key=marshal({"complaintId": f"matching-job#{source}"}),
            UpdateExpression="SET #state=:retry,availableAt=:time,errorCategory=:category",
            ConditionExpression="leaseToken=:token AND #state=:running",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues=marshal(
                {
                    ":retry": "RETRY",
                    ":time": time.time() + 60,
                    ":category": category,
                    ":token": token,
                    ":running": "RUNNING",
                }
            ),
        )

    def job(self, source):
        item = self.read(f"matching-job#{source}")
        return (
            {
                key: item.get(key)
                for key in (
                    "state",
                    "attempts",
                    "configVersion",
                    "report",
                    "updatedAt",
                    "errorCategory",
                )
            }
            if item
            else None
        )

    def candidate(self, identity):
        item = self.read(f"duplicate#{identity}")
        return (
            item["payload"]
            | {
                key: item.get(key)
                for key in ("reviewStatus", "reviewedAt", "createdAt", "updatedAt")
            }
            | {"lastCheckedAt": item["updatedAt"]}
            if item
            else None
        )

    def catalog(self, filters):
        cap = self.complaints.settings.discovery_candidate_limit
        ids, key = [], None
        while True:
            args = dict(
                TableName=self.table,
                IndexName="MatchingWork",
                KeyConditionExpression="matchingPartition=:partition",
                ExpressionAttributeValues=marshal({":partition": "CANDIDATES"}),
                Limit=min(100, cap + 1 - len(ids)),
            )
            if key:
                args["ExclusiveStartKey"] = key
            response = self.call("query", **args)
            ids.extend(
                unmarshal(item)["complaintId"].removeprefix("duplicate#")
                for item in response.get("Items", [])
            )
            key = response.get("LastEvaluatedKey")
            if len(ids) > cap:
                raise RepositoryUnavailable("Candidate review catalog exceeds safe query bound")
            if not key:
                break
        rows = []
        for identity in ids:
            candidate = self.candidate(identity)
            if (
                not candidate
                or not filters["minScore"] <= candidate["combinedScore"] <= filters["maxScore"]
            ):
                continue
            if any(
                filters.get(key) and filters[key] != candidate[key]
                for key in ("classification", "reviewStatus")
            ):
                continue
            if filters.get("complaintId") and filters["complaintId"] not in (
                candidate["sourceComplaintId"],
                candidate["possibleDuplicateId"],
            ):
                continue
            a, b = (
                self.load(candidate["sourceComplaintId"]),
                self.load(candidate["possibleDuplicateId"]),
            )
            if (
                not a
                or not b
                or (filters.get("category") and filters["category"] not in (a.category, b.category))
            ):
                continue
            if (
                filters.get("q")
                and filters["q"].casefold() not in f"{a.title} {b.title}".casefold()
            ):
                continue
            rows.append(
                candidate
                | {
                    "sourceTitle": a.title,
                    "duplicateTitle": b.title,
                    "sourceCategory": a.category,
                    "duplicateCategory": b.category,
                }
            )
        if filters["sort"] == "score":
            rows.sort(
                key=lambda row: (
                    -row["combinedScore"],
                    -row["textScore"],
                    row["distanceMeters"],
                    row["candidateId"],
                )
            )
        else:
            rows.sort(key=lambda row: row["candidateId"])
            rows.sort(key=lambda row: row["updatedAt"], reverse=True)
        return rows[filters["offset"] : filters["offset"] + filters["limit"] + 1]

    def review(self, identity, status, admin):
        self.call(
            "update_item",
            TableName=self.table,
            Key=marshal({"complaintId": f"duplicate#{identity}"}),
            UpdateExpression="SET reviewStatus=:status,reviewedBy=:admin,reviewedAt=:now",
            ConditionExpression="attribute_exists(payload)",
            ExpressionAttributeValues=marshal(
                {":status": status, ":admin": admin, ":now": timestamp()}
            ),
        )
        return self.candidate(identity)
