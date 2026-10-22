"""Offline mocked SDK contracts for regional discovery; no cloud resources or credentials."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from test_discovery_cloud import complaint

from app.core.config import Settings
from app.integrations.database.dynamodb_complaints import DynamoComplaints, marshal, unmarshal
from app.models.discovery import Nearby
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.geography import nearby_bounds, regions_for_bounds


@pytest.fixture
def regional():
    settings = Settings(
        _env_file=None,
        app_env="test",
        complaints_table_name="OfflineComplaints",
        cloud_discovery_regions_ready=True,
    )
    base = DynamoComplaints(settings, MagicMock())
    own = complaint().model_dump(mode="json") | {"reporterEligible": True}
    foreign = own | {
        "complaintId": "foreign",
        "citizenId": "someone-else",
        "title": "Secret foreign title",
        "description": "Secret foreign description",
        "publication": {
            "publicationStatus": "PUBLISHED",
            "publicIssueId": "public-safe",
            "publicSummary": "Reviewed community road damage",
            "publicLatitude": 12.972,
            "publicLongitude": 77.595,
            "publishedAt": own["createdAt"],
        },
    }
    private = foreign | {
        "complaintId": "foreign-private",
        "publication": {"publicationStatus": "PRIVATE"},
    }
    rows = {row["complaintId"]: row for row in [own, foreign, private]}
    for source in list(rows):
        rows["region-" + source] = {"complaintId": "region-" + source, "sourceId": source}
    base.client.query.return_value = {
        "Items": [marshal({"complaintId": key}) for key in rows if key.startswith("region-")],
        "ScannedCount": 3,
    }

    def batch(**args):
        keys = args["RequestItems"][base.table]
        assert keys["ConsistentRead"] is True and len(keys["Keys"]) <= 100
        return {
            "Responses": {
                base.table: [
                    marshal(rows[unmarshal(key)["complaintId"]])
                    for key in keys["Keys"]
                    if unmarshal(key)["complaintId"] in rows
                ]
            }
        }

    base.client.batch_get_item.side_effect = batch
    return base, rows, own, foreign


def query(**changes):
    return Nearby(latitude=12.972, longitude=77.595, radiusMeters=200000, **changes)


def test_owner_scoped_region_keys_strong_revalidation_dedup_and_privacy(regional):
    base, rows, own, foreign = regional
    page = base.discovery.citizen_nearby("owner", query(), None, None, 100, None)
    assert len(page.items) == 2
    mine = next(i for i in page.items if i.isOwn)
    public = next(i for i in page.items if not i.isOwn)
    assert mine.issueId == own["complaintId"] and not mine.isPublic
    assert (
        public.issueId == "public-safe" and public.title == foreign["publication"]["publicSummary"]
    )
    payload = page.model_dump_json()
    assert "Secret foreign" not in payload and "foreign-private" not in payload
    assert '"citizenId"' not in payload and '"description"' not in payload
    for call in base.client.query.call_args_list:
        assert call.kwargs["Limit"] <= 100
        cell = unmarshal(call.kwargs["ExpressionAttributeValues"])[":cell"]
        if call.kwargs["IndexName"] == "InternalGeography":
            assert cell.startswith("owner#r5:")
        else:
            assert cell.startswith("r5:")
    assert base.client.query.call_count == 2 * len(regions_for_bounds(nearby_bounds(query())))
    base.client.scan.assert_not_called()
    rows[foreign["complaintId"]]["publication"]["publicationStatus"] = "PRIVATE"
    assert len(base.discovery.citizen_nearby("owner", query(), None, None, 100, None).items) == 1


def test_distance_filters_pagination_and_owner_context(regional):
    base, rows, own, _ = regional
    first = base.discovery.citizen_nearby("owner", query(), None, None, 1, None)
    second = base.discovery.citizen_nearby("owner", query(), None, None, 1, first.nextCursor)
    assert len(first.items) == len(second.items) == 1 and second.nextCursor is None
    assert first.items[0].issueId != second.items[0].issueId
    with pytest.raises(HTTPException) as error:
        base.discovery.citizen_nearby("another", query(), None, None, 1, first.nextCursor)
    assert error.value.status_code == 400
    assert base.discovery.citizen_nearby("owner", query(), "GARBAGE", None, 100, None).items == []
    assert base.discovery.citizen_nearby("owner", query(), None, "RESOLVED", 100, None).items == []
    rows[own["complaintId"]]["latitude"] = 50
    assert len(base.discovery.citizen_nearby("owner", query(), None, None, 100, None).items) == 1


def test_unbootstrapped_and_dense_regions_fail_honestly(regional):
    base, *_ = regional
    base.settings.cloud_discovery_regions_ready = False
    with pytest.raises(HTTPException) as error:
        base.discovery.citizen_nearby("owner", query(), None, None, 50, None)
    assert error.value.status_code == 503
    base.client.query.assert_not_called()
    base.settings.cloud_discovery_regions_ready = True
    base.client.query.return_value = {"Items": [], "ScannedCount": 2001}
    with pytest.raises(HTTPException) as error:
        base.discovery.citizen_nearby("owner", query(), None, None, 50, None)
    assert error.value.status_code == 422
    base.client.scan.assert_not_called()


def test_public_200km_uses_only_public_partitions_and_safe_dto(regional):
    base, *_ = regional
    page = base.discovery.nearby_page(query(), None, None, 50, None)
    assert len(page.items) == 1 and page.items[0].publicIssueId == "public-safe"
    assert all(
        call.kwargs["IndexName"] == "PublicGeography" for call in base.client.query.call_args_list
    )
    assert not set(page.items[0].model_dump()) & {
        "isOwn",
        "citizenId",
        "complaintId",
        "description",
    }


def test_unprocessed_primary_read_never_returns_partial_success(regional):
    base, *_ = regional
    base.client.batch_get_item.side_effect = None
    pending = {
        base.table: {"Keys": [marshal({"complaintId": "region-any"})], "ConsistentRead": True}
    }
    base.client.batch_get_item.return_value = {"Responses": {}, "UnprocessedKeys": pending}
    with pytest.raises(RepositoryUnavailable):
        base.discovery.citizen_nearby("owner", query(), None, None, 50, None)
    assert base.client.batch_get_item.call_count == 3
