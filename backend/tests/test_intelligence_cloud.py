from uuid import uuid4

import boto3
import pytest
from botocore.stub import ANY, Stubber

from app.core.config import Settings
from app.events.schema import new_event
from app.integrations.database.dynamodb_complaints import marshal
from app.integrations.database.dynamodb_intelligence import DynamoIntelligence
from app.models.incident import IncidentError


def repository():
    # Stubber intercepts every call; explicit synthetic credentials prevent credential discovery.
    client = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="offline",
        aws_secret_access_key="offline",
    )
    settings = Settings(_env_file=None, app_env="test", workflow_table_name="offline-operations")
    return DynamoIntelligence(settings, client), Stubber(client)


def test_cloud_conditional_transaction_and_outbox_without_network():
    repo, stub = repository()
    identity, operation = str(uuid4()), str(uuid4())
    key = {"pk": "intelligence-operation#" + operation, "sk": "0"}
    stub.add_response(
        "get_item", {}, {"TableName": repo.table, "Key": marshal(key), "ConsistentRead": True}
    )
    stub.add_response(
        "transact_write_items", {}, {"TransactItems": ANY, "ClientRequestToken": operation}
    )
    guard = {
        "ConditionCheck": {
            "TableName": "offline-incidents",
            "Key": marshal({"incidentId": identity}),
            "ConditionExpression": "version=:v",
            "ExpressionAttributeValues": marshal({":v": 2}),
        }
    }
    with stub:
        result = repo.commit(
            operation,
            "trusted-officer",
            [
                {
                    "kind": "attempt",
                    "id": identity,
                    "expectedVersion": 0,
                    "data": {"state": "PENDING_VERIFICATION"},
                }
            ],
            [guard],
            [new_event("RepairSubmitted", identity)],
        )
        assert not result["replayed"]
        stub.assert_no_pending_responses()


def test_cloud_conflict_is_not_synthetic_success():
    repo, stub = repository()
    identity, operation = str(uuid4()), str(uuid4())
    stub.add_response("get_item", {})
    stub.add_client_error("transact_write_items", service_error_code="TransactionCanceledException")
    guard = {
        "ConditionCheck": {
            "TableName": "offline-incidents",
            "Key": marshal({"incidentId": identity}),
            "ConditionExpression": "version=:v",
            "ExpressionAttributeValues": marshal({":v": 1}),
        }
    }
    with stub, pytest.raises(IncidentError) as error:
        repo.commit(
            operation,
            "admin",
            [{"kind": "resolution", "id": identity, "expectedVersion": 1, "data": {}}],
            [guard],
        )
    assert error.value.status == 409


@pytest.mark.parametrize(
    "kind",
    ["attempt", "request", "response", "resolution", "recurrence", "fairness-review", "audit"],
)
def test_cloud_record_access_is_strong_and_exact(kind):
    repo, stub = repository()
    identity = str(uuid4())
    stub.add_response(
        "get_item",
        {
            "Item": marshal(
                {**repo.key(kind, identity), "revision": 1, "data": {"state": "recorded"}}
            )
        },
        {"TableName": repo.table, "Key": marshal(repo.key(kind, identity)), "ConsistentRead": True},
    )
    with stub:
        assert repo.get(kind, identity)["data"]["state"] == "recorded"


def test_cloud_requires_source_guards_and_bounded_access():
    repo, _ = repository()
    with pytest.raises(ValueError):
        repo.commit(str(uuid4()), "admin", [{}], [])
    with pytest.raises(ValueError):
        repo.page("unrestricted-scan", "all")
    with pytest.raises(ValueError):
        repo.page("citizen-requests", "account", limit=51)


def test_cloud_index_pointer_rehydrates_current_record_without_scan():
    repo, stub = repository()
    identity = str(uuid4())
    pointer = {"pk": "intelligence-index#offline", "sk": "0"}
    target = repo.key("request", identity)
    stub.add_response(
        "query",
        {"Items": [marshal(pointer)]},
        {
            "TableName": repo.table,
            "IndexName": "ByQueue",
            "KeyConditionExpression": "queue=:q",
            "ExpressionAttributeValues": marshal({":q": "intelligence#citizen-requests#account"}),
            "Limit": 25,
        },
    )
    stub.add_response(
        "get_item",
        {"Item": marshal(pointer | {"target": target})},
        {"TableName": repo.table, "Key": marshal(pointer), "ConsistentRead": True},
    )
    stub.add_response(
        "get_item",
        {"Item": marshal(target | {"revision": 1, "data": {"requestId": identity}})},
        {"TableName": repo.table, "Key": marshal(target), "ConsistentRead": True},
    )
    with stub:
        value = repo.page("citizen-requests", "account")
        assert value["items"][0]["data"]["requestId"] == identity
        stub.assert_no_pending_responses()
