import io
from unittest.mock import MagicMock
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.core.config import Settings
from app.integrations.database.dynamodb_complaints import DynamoComplaints, marshal
from app.integrations.storage.base import StorageCollision, StorageUnavailable
from app.integrations.storage.local_evidence import LocalEvidence
from app.integrations.storage.s3_evidence import S3Evidence
from app.models.complaint import Complaint, ComplaintImage
from app.repositories.complaint_repository import RepositoryUnavailable, RepositoryUncertain
from app.services.complaint_factory import build_complaint_service


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="test",
        local_db_path=tmp_path / "auth.db",
        complaints_table_name="test-complaints",
        evidence_bucket_name="test-evidence",
    )


def complaint(owner="test-owner"):
    cid, iid = str(uuid4()), str(uuid4())
    timestamp = "2026-10-19T12:00:00.000Z"
    return Complaint(
        complaintId=cid,
        citizenId=owner,
        title="Broken streetlight at the crossing",
        description="A streetlight is not working near the pedestrian crossing.",
        category="BROKEN_STREETLIGHT",
        reportedSeverity="MEDIUM",
        latitude=12.9,
        longitude=77.5,
        createdAt=timestamp,
        updatedAt=timestamp,
        images=[
            ComplaintImage(
                imageId=iid,
                storageKey=f"complaints/{cid}/{iid}.jpg",
                fileSize=100,
                createdAt=timestamp,
                url=f"/complaints/{cid}/images/{iid}",
            )
        ],
    )


def payload(item):
    return item.model_dump(mode="json") | {
        "images": [image.model_dump() | {"storageKey": image.storageKey} for image in item.images]
    }


def sdk(service):
    return boto3.client(
        service,
        region_name="ap-south-1",
        aws_access_key_id="unit-test",
        aws_secret_access_key="unit-test",
    )


def test_cloud_provider_selection_is_lazy_and_missing_configuration_fails_closed(
    settings, monkeypatch
):
    monkeypatch.setattr(
        boto3, "client", MagicMock(side_effect=AssertionError("No SDK client at startup"))
    )
    cloud = settings.model_copy(
        update={"complaint_provider": "dynamodb", "evidence_provider": "s3"}
    )
    service = build_complaint_service(cloud)
    assert isinstance(service.repository, DynamoComplaints) and isinstance(
        service.storage, S3Evidence
    )
    with pytest.raises(ValueError, match="no local fallback"):
        build_complaint_service(cloud.model_copy(update={"evidence_bucket_name": None}))
    assert not boto3.client.called


@pytest.mark.parametrize(
    "updates", [{"complaint_provider": "dynamodb"}, {"evidence_provider": "s3"}]
)
def test_local_configuration_rejects_cloud_providers(updates):
    with pytest.raises(ValueError, match="providers"):
        Settings(_env_file=None, app_env="local", **updates)


def test_dynamodb_get_uses_consistent_reads_and_enforces_owner(settings):
    item = complaint()
    client = sdk("dynamodb")
    with Stubber(client) as stub:
        for _ in range(2):
            stub.add_response(
                "get_item",
                {"Item": marshal(payload(item))},
                {
                    "TableName": settings.complaints_table_name,
                    "Key": marshal({"complaintId": item.complaintId}),
                    "ConsistentRead": True,
                },
            )
        repository = DynamoComplaints(settings, client)
        assert (
            repository.get(item.complaintId, item.citizenId).images[0].storageKey
            == item.images[0].storageKey
        )
        assert repository.get(item.complaintId, "other-owner") is None
        stub.assert_no_pending_responses()


def test_dynamodb_create_uses_conditional_atomic_record_idempotency_and_summary(settings):
    item = complaint()
    client = sdk("dynamodb")
    with Stubber(client) as stub:
        stub.add_response(
            "get_item",
            {},
            {"TableName": settings.complaints_table_name, "Key": ANY, "ConsistentRead": True},
        )
        stub.add_response(
            "update_item",
            {},
            {
                "TableName": settings.complaints_table_name,
                "Key": ANY,
                "UpdateExpression": ANY,
                "ConditionExpression": ANY,
                "ExpressionAttributeNames": ANY,
                "ExpressionAttributeValues": ANY,
            },
        )
        stub.add_response(
            "transact_write_items",
            {},
            {
                "TransactItems": [
                    {
                        "Put": {
                            "TableName": settings.complaints_table_name,
                            "Item": marshal(
                                payload(item)
                                | {
                                    "internalGeoCell": "g05:2058:5150",
                                    "internalGeoSortKey": item.complaintId,
                                    "reporterEligible": True,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(complaintId)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": settings.complaints_table_name,
                            "Item": ANY,
                            "ConditionExpression": "attribute_not_exists(complaintId)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": settings.complaints_table_name,
                            "Key": marshal({"complaintId": f"summary#{item.citizenId}"}),
                            "UpdateExpression": "ADD #total :one, #submitted :one",
                            "ExpressionAttributeNames": {
                                "#total": "total",
                                "#submitted": "submitted",
                            },
                            "ExpressionAttributeValues": marshal({":one": 1}),
                        }
                    },
                    {
                        "Put": {
                            "TableName": settings.complaints_table_name,
                            "Item": marshal(
                                {
                                    "complaintId": f"matching-job#{item.complaintId}",
                                    "sourceId": item.complaintId,
                                    "state": "PENDING",
                                    "attempts": 0,
                                    "availableAt": 0,
                                    "updatedAt": item.createdAt,
                                    "matchingPartition": "JOBS",
                                    "matchingSortKey": item.complaintId,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(complaintId)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": settings.complaints_table_name,
                            "Item": marshal(
                                {
                                    "complaintId": f"clustering-job#{item.complaintId}",
                                    "sourceId": item.complaintId,
                                    "state": "PENDING",
                                    "attempts": 0,
                                    "availableAt": 0,
                                    "rerunRequested": False,
                                    "updatedAt": item.createdAt,
                                    "matchingPartition": "CLUSTERING_JOBS",
                                    "matchingSortKey": item.complaintId,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(complaintId)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": settings.complaints_table_name,
                            "Item": marshal(
                                {
                                    "complaintId": "owner-region#" + item.complaintId,
                                    "sourceId": item.complaintId,
                                    "internalGeoCell": item.citizenId + "#r5:20:51",
                                    "internalGeoSortKey": item.complaintId,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(complaintId)",
                        }
                    },
                ],
                "ClientRequestToken": item.complaintId,
            },
        )
        assert DynamoComplaints(settings, client).create(item, str(uuid4()), "fingerprint") == (
            item,
            True,
        )
        stub.assert_no_pending_responses()


def test_dynamodb_query_uses_keys_only_index_batch_get_and_continuation(settings):
    item = complaint()
    key = {
        "citizenId": item.citizenId,
        "complaintId": item.complaintId,
        "createdAt": item.createdAt,
    }
    client = sdk("dynamodb")
    with Stubber(client) as stub:
        arguments = {
            "TableName": settings.complaints_table_name,
            "IndexName": "ByCitizen",
            "KeyConditionExpression": "citizenId=:citizen",
            "ExpressionAttributeValues": marshal({":citizen": item.citizenId}),
            "ScanIndexForward": False,
            "Limit": 1,
        }
        stub.add_response(
            "query", {"Items": [marshal(key)], "LastEvaluatedKey": marshal(key)}, arguments
        )
        stub.add_response(
            "batch_get_item",
            {"Responses": {settings.complaints_table_name: [marshal(payload(item))]}},
            {
                "RequestItems": {
                    settings.complaints_table_name: {
                        "Keys": [marshal({"complaintId": item.complaintId})],
                        "ConsistentRead": True,
                    }
                }
            },
        )
        repository = DynamoComplaints(settings, client)
        page = repository.list(item.citizenId, 1, None)
        assert page.items == [item] and page.nextCursor
        stub.add_response("query", {"Items": []}, arguments | {"ExclusiveStartKey": marshal(key)})
        assert repository.list(item.citizenId, 1, page.nextCursor).items == []
        stub.assert_no_pending_responses()


def test_dynamodb_retries_unprocessed_keys_boundedly(settings):
    item = complaint()
    client = MagicMock()
    client.query.return_value = {"Items": [marshal({"complaintId": item.complaintId})]}
    pending = {
        settings.complaints_table_name: {
            "Keys": [marshal({"complaintId": item.complaintId})],
            "ConsistentRead": True,
        }
    }
    client.batch_get_item.return_value = {"UnprocessedKeys": pending}
    with pytest.raises(RepositoryUnavailable):
        DynamoComplaints(settings, client).list(item.citizenId, 20, None)
    assert client.batch_get_item.call_count == 3
    assert not client.scan.called


def test_dynamodb_unknown_commit_is_not_reported_as_definite_failure(settings):
    client = MagicMock()
    client.get_item.return_value = {}
    client.transact_write_items.side_effect = EndpointConnectionError(
        endpoint_url="https://example.invalid"
    )
    with pytest.raises(RepositoryUncertain):
        DynamoComplaints(settings, client).create(complaint(), str(uuid4()), "fingerprint")


def test_dynamodb_successful_commit_with_lost_response_reconciles(settings):
    item, key = complaint(), str(uuid4())
    client = MagicMock()
    client.get_item.side_effect = [
        {},
        {"Item": marshal({"fingerprint": "same", "target": item.complaintId})},
        {"Item": marshal(payload(item))},
    ]
    client.transact_write_items.side_effect = EndpointConnectionError(
        endpoint_url="https://example.invalid"
    )
    assert DynamoComplaints(settings, client).create(item, key, "same") == (item, True)


def test_dynamodb_conditional_rate_limit_persists_in_database(settings):
    client = MagicMock()
    client.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        DynamoComplaints(settings, client).rate_limit("owner")
    assert error.value.status_code == 429
    assert client.update_item.call_count == 2


def test_s3_private_put_get_delete_with_sdk_stubs(settings):
    item = complaint()
    key = item.images[0].storageKey
    data = b"sanitized-jpeg-bytes"
    body = StreamingBody(io.BytesIO(data), len(data))
    client = sdk("s3")
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": settings.evidence_bucket_name,
                "Key": key,
                "Body": data,
                "ContentType": "image/jpeg",
                "ServerSideEncryption": "AES256",
                "CacheControl": "private, no-store",
                "IfNoneMatch": "*",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": body, "ContentType": "image/jpeg", "ContentLength": len(data)},
            {"Bucket": settings.evidence_bucket_name, "Key": key},
        )
        stub.add_response(
            "delete_object", {}, {"Bucket": settings.evidence_bucket_name, "Key": key}
        )
        storage = S3Evidence(settings.evidence_bucket_name, settings.max_upload_bytes, client)
        storage.put(key, data)
        assert storage.get(key) == data
        assert body._raw_stream.closed
        storage.delete(key)
        stub.assert_no_pending_responses()


def test_s3_errors_and_oversized_response_are_safe(settings):
    key = complaint().images[0].storageKey
    client = MagicMock()
    client.put_object.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
    storage = S3Evidence(settings.evidence_bucket_name, 100, client)
    with pytest.raises(StorageUnavailable):
        storage.put(key, b"x")
    body = StreamingBody(io.BytesIO(b"x" * 101), 101)
    client.get_object.return_value = {
        "ContentType": "image/jpeg",
        "ContentLength": 101,
        "Body": body,
    }
    with pytest.raises(StorageUnavailable):
        storage.get(key)
    assert body._raw_stream.closed


@pytest.mark.parametrize(
    "key",
    [
        "../private.txt",
        "/etc/passwd",
        "complaints/../../etc.jpg",
        "complaints/a/b.jpg",
        "C:\\private\\secret.jpg",
    ],
)
def test_both_storage_adapters_reject_traversal(settings, key):
    for storage in (
        LocalEvidence(settings.local_evidence_root, 100),
        S3Evidence(settings.evidence_bucket_name, 100, MagicMock()),
    ):
        for operation in (
            lambda storage=storage: storage.put(key, b"x"),
            lambda storage=storage: storage.get(key),
            lambda storage=storage: storage.delete(key),
        ):
            with pytest.raises(StorageUnavailable):
                operation()


def test_local_storage_exclusive_write_and_symlink_refusal(settings, monkeypatch):
    from pathlib import Path

    storage = LocalEvidence(settings.local_evidence_root, 100)
    key = complaint().images[0].storageKey
    storage.put(key, b"first")
    with pytest.raises(StorageCollision):
        storage.put(key, b"replacement")
    assert storage.get(key) == b"first"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == storage.root or original(path))
    with pytest.raises(StorageUnavailable):
        storage.get(key)


def test_local_storage_removes_partial_file_when_sync_fails(settings, monkeypatch):
    import os

    key = complaint().images[0].storageKey
    storage = LocalEvidence(settings.local_evidence_root, 100)

    def fail(_):
        raise OSError("Storage unavailable")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(StorageUnavailable):
        storage.put(key, b"private")
    assert not storage.path(key).exists()


def test_public_asset_evidence_roots_are_rejected():
    from pathlib import Path

    public = Path(__file__).resolve().parents[2] / "frontend" / "public" / "evidence"
    with pytest.raises(ValueError, match="public frontend"):
        Settings(_env_file=None, app_env="local", local_evidence_root=public)
