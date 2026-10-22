from unittest.mock import MagicMock

import pytest
from botocore.stub import ANY, Stubber
from test_complaint_adapters import sdk
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_incident_adapters import adapter
from test_incidents import ADMIN, create
from test_priority_workflow import action

from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.dynamodb_priority import DynamoPriority, ranking_key
from app.models.incident import IncidentError


def captured_plan(client, app, monkeypatch):
    report, incident = create(client, app)
    service = app.state.priority_service
    captured = []
    commit = service.repository.commit

    def save(plan):
        captured.append(plan)
        return commit(plan)

    monkeypatch.setattr(service.repository, "commit", save)
    service.change(
        incident["incidentId"],
        "SEVERITY",
        action(
            service,
            incident["incidentId"],
            score=8,
            status="VERIFIED",
            evidenceReferences=[report["complaintId"]],
        ),
        ADMIN,
    )
    return captured[0]


def test_priority_sdk_transaction_strong_guards_receipt_audit_and_ranking_keys(
    complaint_client, complaint_app, monkeypatch
):
    plan = captured_plan(complaint_client, complaint_app, monkeypatch)
    client, calls = sdk("dynamodb"), []
    client.meta.events.register(
        "before-parameter-build.dynamodb.TransactWriteItems",
        lambda params, **kw: calls.append(params.copy()),
    )
    with Stubber(client) as stub:
        stub.add_response(
            "get_item", {}, {"TableName": "incidents", "Key": ANY, "ConsistentRead": True}
        )
        stub.add_response(
            "transact_write_items",
            {},
            {"TransactItems": ANY, "ClientRequestToken": plan.operation_id},
        )
        base = adapter(complaint_app, lambda method, **kw: getattr(client, method)(**kw))
        repository = DynamoPriority(base)
        result = repository.commit(plan)
        assert result["priority"]["calculatedScore"] == plan.result["calculatedScore"]
        stub.assert_no_pending_responses()
    actions = calls[0]["TransactItems"]
    assert len(actions) == 8 and len(calls) == 1  # P9 queue keys update in this same transaction.
    sidecar = next(
        a["Put"]
        for a in actions
        if "Put" in a and unmarshal(a["Put"]["Item"]).get("canonicalIncidentId")
    )
    item = unmarshal(sidecar["Item"])
    assert item["status"] == "PRIORITY#OPEN"
    assert item["prioritySortKey"] == ranking_key(plan.result, plan.snapshot.incident.incidentId)
    assert "generation=:generation" in sidecar["ConditionExpression"]
    assert "result_revision=:calculation" in sidecar["ConditionExpression"]
    assert item["controls"]["severity"]["score"] == 8
    assert len([a for a in actions if "ConditionCheck" in a]) == 2
    assert any("Put" in a and a["Put"]["TableName"] == "audit" for a in actions)


def test_priority_conflict_receipt_replay_and_no_partial_oversize_write(
    complaint_client, complaint_app, monkeypatch
):
    plan = captured_plan(complaint_client, complaint_app, monkeypatch)
    response = {"priority": plan.result, "priorityRevision": 1}
    call = MagicMock(
        side_effect=[
            {},
            RuntimeError("response lost"),
            {"Item": marshal({"fingerprint": plan.request_fingerprint, "result": response})},
        ]
    )
    repository = DynamoPriority(adapter(complaint_app, call))
    assert repository.commit(plan) == response
    assert [c.args[0] for c in call.call_args_list] == [
        "get_item",
        "transact_write_items",
        "get_item",
    ]
    call.reset_mock(side_effect=True)
    call.side_effect = [{}]
    plan.reason = "x" * 390000
    with pytest.raises(IncidentError, match="atomic envelope"):
        repository.commit(plan)
    assert call.call_count == 1


@pytest.mark.parametrize("sort", ["priority", "oldest"])
def test_dynamo_priority_queue_uses_existing_gsi_strong_reloads_and_continuation(
    complaint_client, complaint_app, monkeypatch, sort
):
    plan = captured_plan(complaint_client, complaint_app, monkeypatch)
    identity = plan.snapshot.incident.incidentId
    priority = plan.result
    key = {
        "incidentId": f"priority#{identity}",
        "status": "PRIORITY#OPEN",
        "prioritySortKey": ranking_key(priority, identity),
    }
    if sort == "oldest":
        key = {
            "incidentId": f"priority#{identity}",
            "catalogPartition": "PRIORITY#OPEN",
            "catalogSortKey": f"1#{plan.snapshot.incident.firstReportedAt}#{identity}",
        }
    sidecar = {
        "canonicalIncidentId": identity,
        "result": priority,
        "needs_recalculation": False,
        "source_version": plan.snapshot.incident.version,
        "config_version": priority["algorithmVersion"],
        "next_due": 10**12,
    }
    call = MagicMock(side_effect=[{"Items": [marshal(key)], "LastEvaluatedKey": marshal(key)}])
    base = adapter(complaint_app, call)
    base.load = MagicMock(return_value=plan.snapshot.incident)
    repository = DynamoPriority(base)
    reads = []

    def read(key):
        reads.append(key)
        return {"queueRevision": 7} if key == "priority-meta" else sidecar

    repository.read = read
    items, after, revision, _ = repository.queue(
        {"status": "OPEN", "sort": sort}, 1, None, None, 1, priority["algorithmVersion"]
    )
    assert len(items) == 1 and after[-1] == identity and revision == 7
    query = call.call_args.kwargs
    assert query["IndexName"] == ("ByCatalog" if sort == "oldest" else "ByStatusPriority")
    assert query["Limit"] == 1
    assert unmarshal(query["ExpressionAttributeValues"])[":partition"] == "PRIORITY#OPEN"
    assert reads == ["priority-meta", f"priority#{identity}", "priority-meta"]
    with pytest.raises(IncidentError, match="queue changed"):
        repository.queue({}, 1, None, 6, 1, priority["algorithmVersion"])


def test_ranking_representation_hazard_score_age_and_id_order():
    def key(hazard=False, score=50, age=10, identity="b"):
        return ranking_key(
            {"urgentHazard": hazard, "effectiveScore": score, "unresolvedSeconds": age}, identity
        )

    assert key(True, 0) < key(False, 100)
    assert key(score=90) < key(score=40)
    assert key(age=100) < key(age=10)
    assert key(identity="a") < key(identity="b")
