"""No transport: exercise real transaction construction with botocore Stubber."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from botocore.stub import ANY, Stubber
from test_complaint_adapters import sdk
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_incidents import ADMIN, correction, create

from app.integrations.database.dynamodb_complaints import DynamoComplaints, marshal, unmarshal
from app.integrations.database.dynamodb_duplicates import DynamoDuplicateRepository
from app.integrations.database.dynamodb_incidents import DynamoIncidents
from app.models.incident import IncidentError


def plan_for_merge(client, app, monkeypatch):
    service = app.state.incident_service
    _, first = create(client, app)
    _, second = create(client, app, another=True)
    captured = []
    original = service.repository.commit

    def commit(plan):
        captured.append(plan)
        return original(plan)

    monkeypatch.setattr(service.repository, "commit", commit)
    service.mutate("MERGE", correction(second, first), ADMIN)
    return captured[0]


def adapter(app, call):
    settings = app.state.settings.model_copy(
        update={
            "incidents_table_name": "incidents",
            "audit_events_table_name": "audit",
            "complaints_table_name": "complaints",
        }
    )
    complaints = DynamoComplaints(settings, MagicMock())
    matching = MagicMock()
    matching.call = call
    return DynamoIncidents(complaints, matching)


def test_cloud_merge_is_one_guarded_atomic_transaction_with_strong_idempotency(
    complaint_client, complaint_app, monkeypatch
):
    plan = plan_for_merge(complaint_client, complaint_app, monkeypatch)
    client = sdk("dynamodb")
    calls = []
    client.meta.events.register(
        "before-parameter-build.dynamodb.TransactWriteItems",
        lambda params, **kwargs: calls.append(params.copy()),
    )
    with Stubber(client) as stub:
        stub.add_response(
            "get_item",
            {},
            {
                "TableName": "incidents",
                "Key": marshal({"incidentId": f"operation#{plan.operation_id}"}),
                "ConsistentRead": True,
            },
        )
        stub.add_response(
            "transact_write_items",
            {},
            {
                "TransactItems": ANY,
                "ClientRequestToken": plan.operation_id,
            },
        )
        repository = adapter(complaint_app, lambda method, **kw: getattr(client, method)(**kw))
        result = repository.commit(plan)
        assert result["totalComplaintCount"] == result["uniqueReporterCount"] == 2
        stub.assert_no_pending_responses()
    actions = calls[0]["TransactItems"]
    assert len(actions) == 16 and len(calls) == 1  # P8 invalidation + P9 sidecars/history/revision.
    incident_puts = [
        a["Put"]
        for a in actions
        if "Put" in a
        and a["Put"]["TableName"] == "incidents"
        and "canonicalTitle" in a["Put"]["Item"]
    ]
    assert len(incident_puts) == 2
    assert all(p["ConditionExpression"] == "#version=:version" for p in incident_puts)
    assert sorted(len(unmarshal(p["Item"])["memberIds"]) for p in incident_puts) == [0, 2]
    guards = [
        a.get("ConditionCheck", a.get("Update"))
        for a in actions
        if "ConditionCheck" in a or "Update" in a
    ]
    member_guards = [g for g in guards if g["TableName"] == "complaints"]
    assert len(member_guards) == 2
    assert all("incidentId=:previous" in g["ConditionExpression"] for g in member_guards)
    assert all("reporterEligible" in g["ConditionExpression"] for g in member_guards)
    audit = [
        a["Put"]
        for a in actions
        if "Put" in a
        and a["Put"]["TableName"] == "audit"
        and unmarshal(a["Put"]["Item"])["entityId"].startswith("incident#")
    ]
    assert len(audit) == 2
    assert all(unmarshal(p["Item"])["evidence"]["changes"] for p in audit)


def test_cloud_conflict_replays_same_operation_and_never_chunks(
    complaint_client, complaint_app, monkeypatch
):
    plan = plan_for_merge(complaint_client, complaint_app, monkeypatch)
    call = MagicMock(side_effect=[{}, RuntimeError("timeout"), {}])
    repository = adapter(complaint_app, call)
    with pytest.raises(IncidentError, match="SAME operation ID"):
        repository.commit(plan)
    assert [c.args[0] for c in call.call_args_list] == [
        "get_item",
        "transact_write_items",
        "get_item",
    ]
    result = plan.after[plan.result_incident_id].model_dump(mode="json")
    call.reset_mock(side_effect=True)
    call.side_effect = [
        {},
        RuntimeError("lost response"),
        {"Item": marshal({"fingerprint": plan.fingerprint, "result": result})},
    ]
    assert repository.commit(plan) == result
    call.reset_mock(side_effect=True)
    call.side_effect = [{}]
    oversized = replace(plan, reason="x" * 390_000)
    with pytest.raises(IncidentError, match="atomic envelope"):
        repository.commit(oversized)
    assert call.call_count == 1  # only the strong replay read; zero partial writes


def test_cloud_membership_manifest_checks_authoritative_complaint_membership(complaint_app):
    repository = adapter(complaint_app, MagicMock())
    repository.read = MagicMock(return_value={"memberIds": ["missing-report"]})
    repository.member = MagicMock(return_value=None)
    with pytest.raises(IncidentError, match="reconcile"):
        repository.members("incident")
    repository.read.return_value = {"memberIds": ["duplicate", "duplicate"]}
    with pytest.raises(IncidentError, match="manifest"):
        repository.members("incident")
    repository.read.return_value = {"memberIds": [], "totalComplaintCount": 2}
    with pytest.raises(IncidentError, match="manifest"):
        repository.members("incident")


def test_cloud_enqueue_completion_race_retries_conditionally_without_lost_recheck(complaint_app):
    repository = adapter(complaint_app, MagicMock())
    client = sdk("dynamodb")
    repository.complaints._client = client
    # Real shared adapter wraps botocore errors; exercise that path, not a mock bypass.
    repository.matching = DynamoDuplicateRepository(repository.complaints)
    calls = []
    client.meta.events.register(
        "before-parameter-build.dynamodb.UpdateItem",
        lambda params, **kw: calls.append(params.copy()),
    )
    with Stubber(client) as stub:
        stub.add_client_error("update_item", "ConditionalCheckFailedException")
        stub.add_client_error("update_item", "ConditionalCheckFailedException")
        stub.add_response("update_item", {})
        repository.enqueue("report")
        stub.assert_no_pending_responses()
    assert len(calls) == 3
    assert calls[1]["ConditionExpression"] == "#state=:running"
    assert calls[2]["ConditionExpression"] == ("attribute_not_exists(#state) OR #state<>:running")


def test_cloud_automatic_membership_and_dismissal_guard_share_one_transaction(
    complaint_client, complaint_app, monkeypatch
):
    plan = replace(
        plan_for_merge(complaint_client, complaint_app, monkeypatch), operation="AUTOMATIC_LINK"
    )
    call = MagicMock(side_effect=[{}, {}])
    repository = adapter(complaint_app, call)
    repository.commit(plan)
    actions = call.call_args_list[1].kwargs["TransactItems"]
    guards = [
        a["ConditionCheck"]
        for a in actions
        if "ConditionCheck" in a and "reviewStatus" in a["ConditionCheck"]["ConditionExpression"]
    ]
    assert len(guards) == 1
    assert unmarshal(guards[0]["Key"])["complaintId"].startswith("duplicate#")
    assert unmarshal(guards[0]["ExpressionAttributeValues"])[":dismissed"] == "DISMISSED"
