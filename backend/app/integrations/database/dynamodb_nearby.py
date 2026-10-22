"""Bounded parent-cell GSI queries and strong primary revalidation. Never Scan."""

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.models.discovery import NearbyIssue, NearbyIssuePage
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.context_cursor import pack_cursor, unpack_cursor
from app.utils.geography import (
    haversine,
    inside_bounds,
    nearby_bounds,
    region_cell,
    regions_for_bounds,
)


def region_projection(complaint):
    return {
        "complaintId": "owner-region#" + complaint.complaintId,
        "sourceId": complaint.complaintId,
        "internalGeoCell": complaint.citizenId
        + "#"
        + region_cell(complaint.latitude, complaint.longitude),
        "internalGeoSortKey": complaint.complaintId,
    }


def strong_rows(base, keys):
    result = []
    for offset in range(0, len(keys), 100):
        pending = {
            base.table: {
                "Keys": [marshal({"complaintId": key}) for key in keys[offset : offset + 100]],
                "ConsistentRead": True,
            }
        }
        for _ in range(3):
            response = base.client.batch_get_item(RequestItems=pending)
            result.extend(
                unmarshal(row) for row in response.get("Responses", {}).get(base.table, [])
            )
            pending = response.get("UnprocessedKeys", {})
            if not pending:
                break
        if pending:
            raise RepositoryUnavailable
    return result


def nearby_page(discovery, owner, query, category, status, limit, cursor):
    base = discovery.complaints
    if not base.settings.cloud_discovery_regions_ready:
        raise HTTPException(
            503,
            "Regional discovery requires a verified complete projection bootstrap/backfill. "
            "No scan or incomplete result was substituted.",
        )
    context = {
        "provider": "dynamo-radius-v1",
        "owner": owner,
        "query": query.model_dump(),
        "category": category,
        "status": status,
    }
    key = unpack_cursor(cursor, context, (2,))
    bounds = nearby_bounds(query)
    sources, evaluated = set(), 0
    try:
        for cell in regions_for_bounds(bounds):
            lookups = [("PublicGeography", "publicGeoCell", cell)]
            if owner is not None:
                lookups.append(("InternalGeography", "internalGeoCell", owner + "#" + cell))
            for index, attribute, partition in lookups:
                continuation = None
                while True:
                    args = {
                        "TableName": base.table,
                        "IndexName": index,
                        "KeyConditionExpression": f"{attribute}=:cell",
                        "ExpressionAttributeValues": marshal({":cell": partition}),
                        "Limit": min(100, base.settings.discovery_candidate_limit + 1 - evaluated),
                    }
                    if continuation:
                        args["ExclusiveStartKey"] = continuation
                    response = base.client.query(**args)
                    evaluated += int(response.get("ScannedCount", len(response.get("Items", []))))
                    if evaluated > base.settings.discovery_candidate_limit:
                        raise HTTPException(
                            422,
                            "Too many geographic candidates. Reduce the radius; "
                            "no incomplete page was returned.",
                        )
                    region_keys = [
                        unmarshal(item)["complaintId"] for item in response.get("Items", [])
                    ]
                    for item in strong_rows(base, region_keys):
                        if item.get("sourceId"):
                            sources.add(item["sourceId"])
                    continuation = response.get("LastEvaluatedKey")
                    if not continuation:
                        break
        items = []
        for row in strong_rows(base, sorted(sources)):
            own = owner is not None and row.get("citizenId") == owner
            publication = row.get("publication", {})
            published = publication.get("publicationStatus") == "PUBLISHED"
            if row.get("status") == "REJECTED" or (
                not own and (not published or not row.get("reporterEligible", False))
            ):
                continue
            latitude, longitude = (
                (row["latitude"], row["longitude"])
                if own
                else (publication.get("publicLatitude"), publication.get("publicLongitude"))
            )
            if (
                latitude is None
                or longitude is None
                or not inside_bounds(float(latitude), float(longitude), bounds)
            ):
                continue
            if (category and row["category"] != category) or (status and row["status"] != status):
                continue
            distance = haversine(query.latitude, query.longitude, float(latitude), float(longitude))
            if distance > query.radiusMeters + 1e-7:
                continue
            identity = row["complaintId"] if own else publication.get("publicIssueId")
            if not identity:
                continue
            items.append(
                NearbyIssue(
                    issueId=identity,
                    title=row["title"] if own else publication["publicSummary"],
                    category=row["category"],
                    status=row["status"],
                    latitude=latitude,
                    longitude=longitude,
                    distanceMeters=distance,
                    createdAt=row["createdAt"] if own else publication["publishedAt"],
                    dateLabel="Reported" if own else "Published",
                    isOwn=own,
                    isPublic=published,
                    detailsUrl=("/citizen/complaints/" if own else "/issues/") + identity,
                )
            )

        def ordering(item):
            return (item.distanceMeters, item.issueId)

        items.sort(key=ordering)
        if key:
            try:
                items = [item for item in items if ordering(item) > tuple(key)]
            except TypeError as error:
                raise HTTPException(400, "Invalid pagination key.") from error
        page = items[:limit]
        return NearbyIssuePage(
            items=page,
            nextCursor=pack_cursor(context, list(ordering(page[-1])))
            if len(items) > limit
            else None,
        )
    except (ClientError, BotoCoreError) as error:
        raise RepositoryUnavailable from error
