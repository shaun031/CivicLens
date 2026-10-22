from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from test_complaint_adapters import complaint, payload
from test_complaint_adapters import settings as settings

from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.image_similarity import fingerprint
from app.algorithms.duplicate_detection.matching_engine import match
from app.integrations.database.dynamodb_complaints import DynamoComplaints, marshal, unmarshal
from app.integrations.database.dynamodb_duplicates import DynamoDuplicateRepository
from app.repositories.complaint_repository import RepositoryUnavailable
from app.repositories.duplicate_candidate_repository import match_input
from app.scripts.evaluate_matching import synthetic_image


def repository(settings):
    client = MagicMock()
    complaints = DynamoComplaints(settings, client)
    return DynamoDuplicateRepository(complaints), client


def test_internal_private_neighbor_query_not_public_or_scan_and_hydration(settings):
    repo, client = repository(settings)
    source, candidate = complaint(), complaint("other-owner")
    source.latitude, source.longitude = 12.99999, 77.59999
    candidate.latitude, candidate.longitude = 13.00001, 77.60001
    item = payload(candidate) | {
        "internalGeoCell": "g05:2060:5152",
        "internalGeoSortKey": candidate.complaintId,
    }
    client.query.return_value = {"Items": [marshal({"complaintId": candidate.complaintId})]}
    client.get_item.return_value = {"Item": marshal(item)}
    rows, truncated = repo.nearby(match_input(source), MatchingConfig())
    assert len(rows) == 1 and rows[0].publication["publicationStatus"] == "PRIVATE"
    assert not truncated and client.query.call_count >= 2
    for call in client.query.call_args_list:
        assert call.kwargs["IndexName"] == "InternalGeography"
        assert call.kwargs["Limit"] <= 101
    assert not client.scan.called
    assert "internalGeoCell" not in rows[0].model_dump()


def test_dense_cloud_retrieval_truncates_and_does_not_return_false_exhaustive(settings):
    repo, client = repository(settings)
    source, candidate = complaint(), complaint()
    client.query.return_value = {
        "Items": [marshal({"complaintId": candidate.complaintId})] * 3,
        "LastEvaluatedKey": marshal({"complaintId": candidate.complaintId}),
    }
    client.get_item.return_value = {"Item": marshal(payload(candidate))}
    _, truncated = repo.nearby(match_input(source), MatchingConfig(candidate_limit=1))
    assert truncated and client.query.call_count == 1
    with pytest.raises(RepositoryUnavailable):
        repo.nearby(replace(match_input(source), latitude=90), MatchingConfig())
    assert not client.scan.called


def test_atomic_pair_upsert_preserves_review_and_conditional_job_lease(settings):
    repo, client = repository(settings)
    result = match(match_input(complaint()), match_input(complaint()), MatchingConfig())
    token = str(uuid4())
    repo.finish(
        result.sourceComplaintId,
        token,
        [result],
        {"incomplete": False, "configVersion": result.configVersion},
    )
    args = client.transact_write_items.call_args.kwargs
    assert args["ClientRequestToken"] == token and len(args["TransactItems"]) == 2
    pair, job = [item["Update"] for item in args["TransactItems"]]
    assert unmarshal(pair["Key"])["complaintId"] == "duplicate#" + result.candidateId
    assert "reviewStatus=if_not_exists" in pair["UpdateExpression"]
    assert "leaseToken=:token" in job["ConditionExpression"]
    assert unmarshal(job["ExpressionAttributeValues"])[":state"] == "COMPLETE"
    with pytest.raises(RepositoryUnavailable):
        repo.finish(
            result.sourceComplaintId,
            token,
            [result] * 91,
            {"incomplete": False, "configVersion": result.configVersion},
        )


def test_fingerprint_cache_and_queue_claim_conditional_conflict(settings):
    repo, client = repository(settings)
    value = fingerprint(synthetic_image())
    repo.cache("immutable-image", value)
    item = unmarshal(client.put_item.call_args.kwargs["Item"])
    assert item["complaintId"].startswith("fingerprint#dhash64-v1#")
    client.get_item.return_value = {"Item": marshal(item)}
    assert repo.cached("immutable-image") == value
    source = str(uuid4())
    client.get_item.return_value = {
        "Item": marshal(
            {
                "complaintId": "matching-job#" + source,
                "state": "PENDING",
                "attempts": 0,
                "availableAt": 0,
            }
        )
    }
    claim = repo.claim(source)
    assert claim and claim[0] == source
    assert "availableAt<=:time" in client.update_item.call_args.kwargs["ConditionExpression"]
    client.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )
    assert repo.claim(source) is None
    assert not client.scan.called


def test_cloud_catalog_safe_cap_no_scan_and_retry_on_transport_error(settings):
    repo, client = repository(settings)
    client.query.return_value = {"Items": []}
    assert (
        repo.catalog({"minScore": 0, "maxScore": 1, "sort": "score", "offset": 0, "limit": 20})
        == []
    )
    assert client.query.call_args.kwargs["IndexName"] == "MatchingWork"
    assert not client.scan.called
    client.query.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "Query"
    )
    with pytest.raises(RepositoryUnavailable):
        repo.catalog({"minScore": 0, "maxScore": 1, "sort": "score", "offset": 0, "limit": 20})
