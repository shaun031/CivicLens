from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import HTTPException

from app.core.config import Settings
from app.integrations.database.dynamodb_complaints import DynamoComplaints, marshal, unmarshal
from app.models.complaint import Complaint, ComplaintPage
from app.models.discovery import Bounds, Nearby, PublicationReview, PublicIssue, SearchFilters
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.geography import cells_for_bounds, geo_cell


@pytest.fixture
def cloud():
    settings = Settings(
        _env_file=None,
        app_env="test",
        complaints_table_name="TestComplaints",
        audit_events_table_name="TestAudit",
    )
    client = MagicMock()
    return DynamoComplaints(settings, client)


def complaint(**changes):
    return Complaint(
        complaintId=str(uuid4()),
        citizenId="owner",
        title="Pothole beside community library",
        description="The damaged road surface creates a risk to cyclists.",
        category="POTHOLE",
        reportedSeverity="HIGH",
        latitude=12.972,
        longitude=77.595,
        createdAt="2026-10-19T10:00:00.000Z",
        updatedAt="2026-10-19T10:00:00.000Z",
        **changes,
    )


def public_item(public_id=None, **changes):
    public_id = public_id or str(uuid4())
    return {
        "complaintId": f"public#{public_id}",
        "publicIssueId": public_id,
        "publicationStatus": "PUBLISHED",
        "category": "POTHOLE",
        "status": "SUBMITTED",
        "summary": "Reviewed damaged road surface near a junction",
        "latitude": 12.972,
        "longitude": 77.595,
        "publishedAt": "2026-10-19T11:00:00.000Z",
        **changes,
    }


def box():
    return Bounds(minLatitude=12.96, maxLatitude=12.98, minLongitude=77.59, maxLongitude=77.60)


def test_sparse_cell_queries_batch_get_and_duplicate_candidate_removal(cloud):
    item = public_item()
    cloud.client.query.return_value = {
        "Items": [marshal({"complaintId": item["complaintId"]})],
        "ScannedCount": 1,
    }
    cloud.client.batch_get_item.return_value = {"Responses": {cloud.table: [marshal(item)]}}
    result = cloud.discovery.public_page(box(), None, None, 20, None)
    assert len(result.items) == 1
    assert len(cloud.client.query.call_args_list) == len(cells_for_bounds(box()))
    for call in cloud.client.query.call_args_list:
        assert call.kwargs["IndexName"] == "PublicGeography"
        assert call.kwargs["KeyConditionExpression"] == "publicGeoCell=:cell"
        assert call.kwargs["Limit"] <= 100
    keys = cloud.client.batch_get_item.call_args.kwargs["RequestItems"][cloud.table]
    assert keys["ConsistentRead"] is True and len(keys["Keys"]) == 1
    cloud.client.scan.assert_not_called()
    assert "citizenId" not in result.model_dump_json()


def test_stale_gsi_cannot_reveal_unpublished_or_withdrawn_record(cloud):
    cloud.client.query.return_value = {"Items": [marshal({"complaintId": "public#old"})]}
    cloud.client.batch_get_item.return_value = {
        "Responses": {
            cloud.table: [marshal({"complaintId": "public#old", "publicationStatus": "PRIVATE"})]
        }
    }
    assert cloud.discovery.public_page(box(), None, None, 20, None).items == []


def test_cloud_candidate_continuation_and_unprocessed_retry(cloud):
    item = public_item()
    first, *remaining = cells_for_bounds(box())
    continuation = marshal(
        {
            "complaintId": item["complaintId"],
            "publicGeoCell": first,
            "publicGeoSortKey": item["publicIssueId"],
        }
    )
    cloud.client.query.side_effect = [
        {"Items": [], "LastEvaluatedKey": continuation},
        {"Items": [marshal({"complaintId": item["complaintId"]})]},
    ] + [{"Items": []} for _ in remaining]
    pending = {
        cloud.table: {
            "Keys": [marshal({"complaintId": item["complaintId"]})],
            "ConsistentRead": True,
        }
    }
    cloud.client.batch_get_item.side_effect = [
        {"Responses": {}, "UnprocessedKeys": pending},
        {"Responses": {cloud.table: [marshal(item)]}},
    ]
    assert len(cloud.discovery.public_page(box(), None, None, 20, None).items) == 1
    assert cloud.client.query.call_args_list[1].kwargs["ExclusiveStartKey"] == continuation
    assert cloud.client.batch_get_item.call_count == 2


def test_cloud_geo_pagination_distance_order_filters_and_context(cloud, monkeypatch):
    items = [
        PublicIssue.model_validate(public_item(public_id=str(uuid4()), latitude=12.972 + i * 0.003))
        for i in range(3)
    ]
    monkeypatch.setattr(cloud.discovery, "_candidates", lambda _: list(reversed(items)))
    query = Nearby(latitude=12.972, longitude=77.595, radiusMeters=500)
    first = cloud.discovery.nearby_page(query, None, None, 1, None)
    second = cloud.discovery.nearby_page(query, None, None, 1, first.nextCursor)
    assert first.items[0].distanceMeters == pytest.approx(0)
    assert 300 < second.items[0].distanceMeters < 350 and second.nextCursor is None
    assert cloud.discovery.nearby_page(query, "GARBAGE", None, 10, None).items == []
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.nearby_page(query, "POTHOLE", None, 1, first.nextCursor)
    assert caught.value.status_code == 400


def test_publication_transaction_sparse_projection_and_atomic_audit(cloud):
    original = complaint().model_dump(mode="json")
    original["publication"] = {
        "citizenRequestedPublication": True,
        "publicationStatus": "PENDING_REVIEW",
    }
    cloud.client.get_item.return_value = {"Item": marshal(original)}
    review = PublicationReview(
        decision="APPROVE",
        publicSummary="Reviewed road damage near community junction",
        publicLatitude=12.972321,
        publicLongitude=77.595432,
        reviewedForPrivacy=True,
    )
    result = cloud.discovery.review_publication(original["complaintId"], "admin-id", review)
    assert result.publicationStatus == "PUBLISHED" and result.publicLatitude == 12.972
    transaction = cloud.client.transact_write_items.call_args.kwargs["TransactItems"]
    update, projection, regional, audit = transaction
    assert "#revision" in update["Update"]["ConditionExpression"]
    assert update["Update"]["ExpressionAttributeNames"]["#revision"] == "publicationRevision"
    item = unmarshal(projection["Put"]["Item"])
    assert item["publicGeoCell"] == geo_cell(12.972, 77.595)
    assert item["publicGeoSortKey"] == result.publicIssueId
    assert not set(item) & {"citizenId", "description", "images", "storageKey", "title"}
    regional_item = unmarshal(regional["Put"]["Item"])
    assert regional_item == {
        "complaintId": "public-region#" + result.publicIssueId,
        "sourceId": original["complaintId"],
        "publicGeoCell": "r5:20:51",
        "publicGeoSortKey": result.publicIssueId,
    }
    assert audit["Put"]["TableName"] == "TestAudit"
    audit_item = unmarshal(audit["Put"]["Item"])
    assert audit_item["actorId"] == "admin-id" and audit_item["action"] == "APPROVE"
    assert audit_item["entityId"] == original["complaintId"]


@pytest.mark.parametrize("decision", ["UNPUBLISH", "REJECT"])
def test_unpublication_removes_sparse_attributes_atomically(cloud, decision):
    original = complaint().model_dump(mode="json")
    public_id = str(uuid4())
    original["publication"] = {
        "citizenRequestedPublication": True,
        "publicationStatus": "PUBLISHED",
        "publicIssueId": public_id,
    }
    cloud.client.get_item.return_value = {"Item": marshal(original)}
    cloud.discovery.review_publication(
        original["complaintId"], "administrator", PublicationReview(decision=decision)
    )
    tombstone = unmarshal(
        cloud.client.transact_write_items.call_args.kwargs["TransactItems"][1]["Put"]["Item"]
    )
    assert tombstone["complaintId"] == "public#" + public_id and "publicGeoCell" not in tombstone
    assert "summary" not in tombstone
    assert unmarshal(
        cloud.client.transact_write_items.call_args.kwargs["TransactItems"][2]["Put"]["Item"]
    ) == {"complaintId": "public-region#" + public_id}


def test_cloud_owner_cannot_self_approve_or_request_for_other_owner(cloud):
    original = complaint().model_dump(mode="json")
    cloud.client.get_item.return_value = {"Item": marshal(original)}
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.request_publication(original["complaintId"], "other-owner", True)
    assert caught.value.status_code == 404
    cloud.client.transact_write_items.assert_not_called()


def test_cloud_conflict_and_missing_audit_never_claim_success(cloud):
    original = complaint().model_dump(mode="json")
    cloud.client.get_item.return_value = {"Item": marshal(original)}
    cloud.settings.audit_events_table_name = None
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.request_publication(original["complaintId"], "owner", True)
    assert caught.value.status_code == 503
    cloud.client.transact_write_items.assert_not_called()
    cloud.settings.audit_events_table_name = "TestAudit"
    cloud.client.transact_write_items.side_effect = ClientError(
        {"Error": {"Code": "TransactionCanceledException"}}, "TransactWriteItems"
    )
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.request_publication(original["complaintId"], "owner", True)
    assert caught.value.status_code == 409


def test_cloud_network_failure_is_safe_and_query_limit_is_bounded(cloud):
    cloud.client.query.side_effect = EndpointConnectionError(
        endpoint_url="https://private.internal"
    )
    with pytest.raises(RepositoryUnavailable):
        cloud.discovery.public_page(box(), None, None, 20, None)
    cloud.client.query.side_effect = None
    cloud.client.query.return_value = {"Items": [], "ScannedCount": 2001}
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.public_page(box(), None, None, 20, None)
    assert caught.value.status_code == 422
    cloud.client.scan.assert_not_called()


def test_cloud_search_and_summary_owner_catalog_no_scan(cloud, monkeypatch):
    first = complaint()
    second = first.model_copy(update={"complaintId": str(uuid4()), "category": "GARBAGE"})
    monkeypatch.setattr(
        cloud.discovery, "_catalog", lambda citizen: [first, second] if citizen == "owner" else []
    )
    query = SearchFilters(q="LIBRARY", category="POTHOLE", reportedSeverity="HIGH", sortOrder="asc")
    assert cloud.discovery.search("owner", 20, None, query).items == [first]
    assert cloud.discovery.search("stranger", 20, None, query).items == []
    summary = cloud.discovery.summary("owner")
    assert (
        summary.total == 2 and summary.counts == {"SUBMITTED": 2} and len(summary.byCategory) == 2
    )
    cloud.client.scan.assert_not_called()


def test_catalog_enforces_owner_work_limit_without_silent_truncation(cloud, monkeypatch):
    item = complaint()
    cloud.settings.cloud_owner_query_limit = 100
    monkeypatch.setattr(
        cloud,
        "list",
        lambda citizen, limit, cursor: ComplaintPage(items=[item] * 100, nextCursor="continuation"),
    )
    with pytest.raises(HTTPException) as caught:
        list(cloud.discovery._catalog("owner"))
    assert caught.value.status_code == 422


def test_public_detail_uses_strong_primary_read_and_rechecks_status(cloud):
    item = public_item()
    cloud.client.get_item.return_value = {"Item": marshal(item)}
    assert cloud.discovery.public_details(item["publicIssueId"]).summary == item["summary"]
    assert cloud.client.get_item.call_args.kwargs["ConsistentRead"] is True
    item["publicationStatus"] = "PRIVATE"
    cloud.client.get_item.return_value = {"Item": marshal(item)}
    assert cloud.discovery.public_details(item["publicIssueId"]) is None


def test_public_quota_uses_bounded_persistent_hashed_identity(cloud):
    cloud.discovery.public_rate("203.0.113.5")
    args = cloud.client.update_item.call_args.kwargs
    assert "203.0.113.5" not in str(args) and "#window" in args["ConditionExpression"]
    cloud.client.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )
    with pytest.raises(HTTPException) as caught:
        cloud.discovery.public_rate("203.0.113.5")
    assert caught.value.status_code == 429


def test_internal_publication_revision_does_not_break_private_get_or_leak(cloud):
    original = complaint().model_dump(mode="json")
    original["publicationRevision"] = 3
    original["publication"] = {
        "citizenRequestedPublication": True,
        "publicationStatus": "PENDING_REVIEW",
    }
    cloud.client.get_item.return_value = {"Item": marshal(original)}
    result = cloud.get(original["complaintId"], "owner")
    assert result.publication["publicationStatus"] == "PENDING_REVIEW"
    assert "publicationRevision" not in result.model_dump_json()
