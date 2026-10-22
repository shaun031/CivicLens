"""Source-only DynamoDB query preparation: no Scan, lazy SDK, strongly rechecked public data."""

import hashlib
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.sqlite_discovery import utc_now
from app.models.complaint import ComplaintPage, ComplaintSummary
from app.models.discovery import (
    Publication,
    PublicationReview,
    PublicIssue,
    PublicIssuePage,
    SearchFilters,
    search_matches,
)
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.context_cursor import pack_cursor, unpack_cursor
from app.utils.geography import cells_for_bounds, geo_cell, haversine, inside_bounds, nearby_bounds


class DynamoDiscovery:
    def __init__(self, complaints):
        self.complaints = complaints

    def _catalog(self, citizen):
        """Bounded owner Query, never a global scan or silent truncation."""
        result, cursor = [], None
        while True:
            page = self.complaints.list(citizen, 100, cursor)
            result.extend(page.items)
            if len(result) > self.complaints.settings.cloud_owner_query_limit:
                raise HTTPException(
                    422,
                    "Cloud owner search exceeds the configured demonstration limit; "
                    "a reviewed search index is required.",
                )
            cursor = page.nextCursor
            if not cursor:
                return {item.complaintId: item for item in result}.values()

    def search(self, citizen, limit, cursor, filters: SearchFilters):
        context = {
            "provider": "dynamodb-search",
            "owner": citizen,
            **filters.model_dump(mode="json"),
        }
        key = unpack_cursor(cursor, context, (3,))
        items = [
            item
            for item in self._catalog(citizen)
            if (not filters.category or item.category == filters.category)
            and (not filters.status or item.status == filters.status)
            and (not filters.reportedSeverity or item.reportedSeverity == filters.reportedSeverity)
            and (not filters.dateFrom or item.createdAt[:10] >= str(filters.dateFrom))
            and (not filters.dateTo or item.createdAt[:10] <= str(filters.dateTo))
            and search_matches(
                " ".join(
                    [item.title, item.description, item.landmark or "", item.addressLabel or ""]
                ),
                filters.q,
            )
        ]

        def ordering(item):
            return (str(getattr(item, filters.sortBy)), item.createdAt, item.complaintId)

        reverse = filters.sortOrder == "desc"
        items.sort(key=ordering, reverse=reverse)
        total = len(items)
        if key:
            try:
                items = [
                    item
                    for item in items
                    if (ordering(item) < tuple(key) if reverse else ordering(item) > tuple(key))
                ]
            except TypeError as error:
                raise HTTPException(400, "Invalid pagination key.") from error
        page = items[:limit]
        return ComplaintPage(
            items=page,
            total=total,
            nextCursor=pack_cursor(context, list(ordering(page[-1])))
            if len(items) > limit
            else None,
        )

    def summary(self, citizen, days=30):
        items = list(self._catalog(citizen))
        counts, categories, trend = {}, {}, {}
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
            categories[item.category] = categories.get(item.category, 0) + 1
            day = item.createdAt[:10]
            trend[day] = trend.get(day, 0) + 1
        return ComplaintSummary(
            total=len(items),
            counts=counts,
            byCategory=[{"category": key, "count": categories[key]} for key in sorted(categories)],
            recent=sorted(items, key=lambda item: (item.createdAt, item.complaintId), reverse=True)[
                :3
            ],
            submissionTrend=[
                {
                    "date": str(start + timedelta(days=i)),
                    "count": trend.get(str(start + timedelta(days=i)), 0),
                }
                for i in range(days)
            ]
            if items
            else [],
            trendDays=days,
        )

    def _change(self, complaint_id, actor, requested=None, review: PublicationReview | None = None):
        base = self.complaints
        original = base.read(complaint_id)
        if (
            not original
            or "citizenId" not in original
            or (review is None and original["citizenId"] != actor)
        ):
            raise HTTPException(404, "Complaint not found.")
        previous = Publication.model_validate(original.get("publication", {}))
        current = previous.model_copy(deep=True)
        revision = int(original.get("publicationRevision", 0))
        timestamp = utc_now()
        if review is None:
            action = "REQUEST" if requested else "WITHDRAW"
            current.citizenRequestedPublication = bool(requested)
            if requested and previous.publicationStatus == "PUBLISHED":
                return previous
            current.publicationStatus = "PENDING_REVIEW" if requested else "PRIVATE"
        else:
            action = review.decision
            if action == "APPROVE":
                if (
                    not previous.citizenRequestedPublication
                    or previous.publicationStatus != "PENDING_REVIEW"
                ):
                    raise HTTPException(
                        409, "Only a pending citizen publication request can be approved."
                    )
                current.publicationStatus = "PUBLISHED"
                current.publicIssueId = previous.publicIssueId or str(uuid4())
                current.publicSummary = review.publicSummary
                current.publicLatitude = round(review.publicLatitude, 3)
                current.publicLongitude = round(review.publicLongitude, 3)
                if current.publicLongitude == 180:
                    current.publicLongitude = -180.0
                current.publishedAt = timestamp
            elif action == "REJECT":
                if previous.publicationStatus not in ("PENDING_REVIEW", "PUBLISHED"):
                    raise HTTPException(409, "No active publication request to reject.")
                current.publicationStatus = "REJECTED"
            else:
                if previous.publicationStatus != "PUBLISHED":
                    raise HTTPException(409, "The issue is not published.")
                current.publicationStatus, current.citizenRequestedPublication = "PRIVATE", False
        if current.publicationStatus != "PUBLISHED":
            current.publicSummary = current.publicLatitude = current.publicLongitude = (
                current.publishedAt
            ) = None
        transaction = [
            {
                "Update": {
                    "TableName": base.table,
                    "Key": marshal({"complaintId": complaint_id}),
                    "UpdateExpression": "SET #publication=:publication, #revision=:next",
                    "ConditionExpression": "attribute_exists(complaintId) AND "
                    "(attribute_not_exists(#revision) OR #revision=:previous)",
                    "ExpressionAttributeNames": {
                        "#publication": "publication",
                        "#revision": "publicationRevision",
                    },
                    "ExpressionAttributeValues": marshal(
                        {
                            ":publication": current.model_dump(),
                            ":next": revision + 1,
                            ":previous": revision,
                        }
                    ),
                }
            }
        ]
        public_id = current.publicIssueId
        if current.publicationStatus == "PUBLISHED":
            public = PublicIssue(
                publicIssueId=public_id,
                category=original["category"],
                status=original["status"],
                summary=current.publicSummary,
                latitude=current.publicLatitude,
                longitude=current.publicLongitude,
                publishedAt=timestamp,
            )
            transaction.append(
                {
                    "Put": {
                        "TableName": base.table,
                        "Item": marshal(
                            {
                                "complaintId": f"public#{public_id}",
                                "publicationStatus": "PUBLISHED",
                                "publicGeoCell": geo_cell(public.latitude, public.longitude),
                                "publicGeoSortKey": public_id,
                                **public.model_dump(exclude_none=True),
                            }
                        ),
                    }
                }
            )
        elif public_id:
            # Replace with a nonindexed tombstone, no DeleteItem privilege is necessary.
            transaction.append(
                {
                    "Put": {
                        "TableName": base.table,
                        "Item": marshal(
                            {
                                "complaintId": f"public#{public_id}",
                                "publicationStatus": current.publicationStatus,
                            }
                        ),
                    }
                }
            )
        if public_id:
            from app.utils.geography import region_cell

            regional = {"complaintId": "public-region#" + public_id}
            if current.publicationStatus == "PUBLISHED":
                regional.update(
                    sourceId=complaint_id,
                    publicGeoCell=region_cell(current.publicLatitude, current.publicLongitude),
                    publicGeoSortKey=public_id,
                )
            transaction.append({"Put": {"TableName": base.table, "Item": marshal(regional)}})
        event_id = str(uuid4())
        if not base.settings.audit_events_table_name:
            raise HTTPException(
                503, "Publication requires configured audit storage; no unaudited change was made."
            )
        transaction.append(
            {
                "Put": {
                    "TableName": base.settings.audit_events_table_name,
                    "Item": marshal(
                        {
                            "entityId": complaint_id,
                            "timestampEventId": f"{timestamp}#{event_id}",
                            "actorId": actor,
                            "action": action,
                            "fromStatus": previous.publicationStatus,
                            "toStatus": current.publicationStatus,
                            "created": timestamp,
                        }
                    ),
                    "ConditionExpression": "attribute_not_exists(entityId)",
                }
            }
        )
        try:
            base.client.transact_write_items(TransactItems=transaction, ClientRequestToken=event_id)
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise HTTPException(
                    409, "Publication changed concurrently. Refresh before reviewing again."
                ) from error
            raise RepositoryUnavailable from error
        except BotoCoreError as error:
            raise RepositoryUnavailable from error
        return current

    def request_publication(self, complaint_id, actor, requested):
        return self._change(complaint_id, actor, requested=requested)

    def review_publication(self, complaint_id, actor, review):
        return self._change(complaint_id, actor, review=review)

    def _candidates(self, bounds):
        base, keys = self.complaints, set()
        try:
            evaluated = 0
            for cell in cells_for_bounds(bounds):
                continuation = None
                while True:
                    args = {
                        "TableName": base.table,
                        "IndexName": "PublicGeography",
                        "KeyConditionExpression": "publicGeoCell=:cell",
                        "ExpressionAttributeValues": marshal({":cell": cell}),
                        "Limit": min(100, base.settings.discovery_candidate_limit + 1 - evaluated),
                    }
                    if continuation:
                        args["ExclusiveStartKey"] = continuation
                    response = base.client.query(**args)
                    evaluated += int(response.get("ScannedCount", len(response.get("Items", []))))
                    keys.update(
                        unmarshal(item)["complaintId"] for item in response.get("Items", [])
                    )
                    if (
                        evaluated > base.settings.discovery_candidate_limit
                        or len(keys) > base.settings.discovery_candidate_limit
                    ):
                        raise HTTPException(
                            422, "Too many geographic candidates. Zoom in or reduce the radius."
                        )
                    continuation = response.get("LastEvaluatedKey")
                    if not continuation:
                        break
            # Strong primary reads defeat stale GSI entries immediately after withdrawal/unpublish.
            items = []
            key_list = sorted(keys)
            for offset in range(0, len(key_list), 100):
                pending = {
                    base.table: {
                        "Keys": [
                            marshal({"complaintId": key}) for key in key_list[offset : offset + 100]
                        ],
                        "ConsistentRead": True,
                    }
                }
                for _ in range(3):
                    response = base.client.batch_get_item(RequestItems=pending)
                    for raw in response.get("Responses", {}).get(base.table, []):
                        item = unmarshal(raw)
                        if item.get("publicationStatus") == "PUBLISHED" and inside_bounds(
                            float(item["latitude"]), float(item["longitude"]), bounds
                        ):
                            items.append(PublicIssue.model_validate(item))
                    pending = response.get("UnprocessedKeys", {})
                    if not pending:
                        break
                if pending:
                    raise RepositoryUnavailable
            return list({item.publicIssueId: item for item in items}.values())
        except (ClientError, BotoCoreError) as error:
            raise RepositoryUnavailable from error

    def public_page(self, bounds, category, status, limit, cursor, nearby=None):
        context = {
            "provider": "public-dynamodb",
            "bounds": bounds.model_dump(),
            "nearby": nearby.model_dump() if nearby else None,
            "category": category,
            "status": status,
        }
        key = unpack_cursor(cursor, context, (2,) if nearby else (1,))
        items = [
            item
            for item in self._candidates(bounds)
            if (category is None or item.category == category)
            and (status is None or item.status == status)
        ]
        if nearby:
            for item in items:
                item.distanceMeters = haversine(
                    nearby.latitude, nearby.longitude, item.latitude, item.longitude
                )
            items = [item for item in items if item.distanceMeters <= nearby.radiusMeters]
        ordering = (
            (lambda item: (item.distanceMeters, item.publicIssueId))
            if nearby
            else (lambda item: (item.publicIssueId,))
        )
        items.sort(key=ordering)
        if key:
            try:
                items = [item for item in items if ordering(item) > tuple(key)]
            except TypeError as error:
                raise HTTPException(400, "Invalid pagination key.") from error
        page = items[:limit]
        return PublicIssuePage(
            items=page,
            nextCursor=pack_cursor(context, list(ordering(page[-1])))
            if len(items) > limit
            else None,
        )

    def nearby_page(self, query, category, status, limit, cursor):
        if query.radiusMeters > 5000 or abs(query.latitude) > 85:
            from app.integrations.database.dynamodb_nearby import nearby_page

            page = nearby_page(self, None, query, category, status, limit, cursor)
            return PublicIssuePage(
                items=[
                    PublicIssue(
                        publicIssueId=i.issueId,
                        summary=i.title,
                        category=i.category,
                        status=i.status,
                        latitude=i.latitude,
                        longitude=i.longitude,
                        publishedAt=i.createdAt,
                        distanceMeters=i.distanceMeters,
                    )
                    for i in page.items
                ],
                nextCursor=page.nextCursor,
            )
        return self.public_page(nearby_bounds(query), category, status, limit, cursor, query)

    def citizen_nearby(self, owner, query, category, status, limit, cursor):
        from app.integrations.database.dynamodb_nearby import nearby_page

        return nearby_page(self, owner, query, category, status, limit, cursor)

    def latest_location(self, owner):
        cursor, checked = None, 0
        while True:
            page = self.complaints.list(owner, 100, cursor)
            for item in page.items:
                if item.status != "REJECTED":
                    return {"latitude": item.latitude, "longitude": item.longitude}
            checked += len(page.items)
            if not page.nextCursor:
                return None
            if checked >= self.complaints.settings.cloud_owner_query_limit:
                raise HTTPException(
                    422, "Latest eligible location exceeds the bounded owner query limit."
                )
            cursor = page.nextCursor

    def public_details(self, public_id):
        item = self.complaints.read(f"public#{public_id}")
        return (
            PublicIssue.model_validate(item)
            if item and item.get("publicationStatus") == "PUBLISHED"
            else None
        )

    def public_rate(self, identity):
        now = int(time.time())
        base = self.complaints
        try:
            key = marshal(
                {"complaintId": "public-rate#" + hashlib.sha256(identity.encode()).hexdigest()}
            )
            try:
                base.client.update_item(
                    TableName=base.table,
                    Key=key,
                    UpdateExpression="SET #window=:window, attempts=:one",
                    ConditionExpression="attribute_not_exists(#window) OR #window<>:window",
                    ExpressionAttributeNames={"#window": "window"},
                    ExpressionAttributeValues=marshal({":window": now // 60, ":one": 1}),
                )
            except ClientError as reset_error:
                if reset_error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                base.client.update_item(
                    TableName=base.table,
                    Key=key,
                    UpdateExpression="ADD attempts :one",
                    ConditionExpression="#window=:window AND attempts<:limit",
                    ExpressionAttributeNames={"#window": "window"},
                    ExpressionAttributeValues=marshal(
                        {
                            ":window": now // 60,
                            ":one": 1,
                            ":limit": base.settings.public_query_rate_limit,
                        }
                    ),
                )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise HTTPException(
                    429,
                    "Public query limit reached. Try again shortly.",
                    headers={"Retry-After": str(60 - now % 60)},
                ) from error
            raise RepositoryUnavailable from error
        except BotoCoreError as error:
            raise RepositoryUnavailable from error
