import copy
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from botocore.stub import ANY, Stubber
from test_complaint_adapters import sdk
from test_incidents import ADMIN
from test_work_allocation import common

from app.core.config import Settings
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.dynamodb_work import DynamoWork
from app.models.incident import Actor, IncidentError


def fake():
    records, calls, events = {}, [], []
    repository = MagicMock()
    repository.table, repository.audit_table = "incidents", "audit"
    repository.read.side_effect = lambda key: copy.deepcopy(records.get(key))

    def receipt(identity, fingerprint):
        value = records.get(f"operation#{identity}")
        if value and value["fingerprint"] != fingerprint:
            raise IncidentError(409, "Different operation fingerprint")
        return copy.deepcopy(value["result"]) if value else None

    repository.operation.side_effect = receipt

    def call(method, **kw):
        calls.append((method, kw))
        assert method == "transact_write_items"
        # Validate the actual SDK request shape with Stubber; never contact a transport.
        client = sdk("dynamodb")
        with Stubber(client) as stub:
            stub.add_response(method, {}, {"TransactItems": ANY, "ClientRequestToken": ANY})
            client.transact_write_items(**kw)
            stub.assert_no_pending_responses()
        for action in kw["TransactItems"]:
            if "Put" in action:
                value = json.loads(json.dumps(unmarshal(action["Put"]["Item"]), default=float))
                if action["Put"]["TableName"] == "audit":
                    events.append(value)
                else:
                    records[value["incidentId"]] = value
        return {}

    repository.call.side_effect = call
    settings = Settings(_env_file=None, app_env="test")
    work = DynamoWork(repository, "test-priority", settings)
    return work, records, calls, events


def configured():
    work, records, calls, events = fake()
    work.seed(common(), ADMIN)
    department = next(d for d in work.departments()["items"] if d["code"] == "ROAD_MAINTENANCE")
    officer = str(uuid4())
    work.provision_officer_profile(
        {
            "officerId": officer,
            "role": "OFFICER",
            "active": True,
            "verified": True,
            "displayName": "Cloud Test Officer",
        },
        common(),
        ADMIN,
    )
    work.save_membership(
        department["id"],
        common(
            expectedVersion=0,
            officerId=officer,
            active=True,
            availability="AVAILABLE",
            capacity=10,
            areas=[],
        ),
        ADMIN,
    )
    identity = str(uuid4())
    records[identity] = {
        "incidentId": identity,
        "canonicalTitle": "Road defect",
        "category": "POTHOLE",
        "latitude": 12.97,
        "longitude": 77.59,
        "version": 1,
        "status": "OPEN",
    }
    priority = {
        "effectiveScore": 55,
        "priorityBand": "MEDIUM",
        "urgentHazard": False,
        "unresolvedSeconds": 1000,
    }
    records[f"priority#{identity}"] = {
        "incidentId": f"priority#{identity}",
        "result": priority,
        "source_version": 1,
        "config_version": "test-priority",
        "next_due": work.clock().timestamp() + 3600,
        "needs_recalculation": False,
        "generation": 1,
        "result_revision": 1,
    }
    work.assign(
        identity,
        "ROUTE",
        common(expectedIncidentVersion=1, expectedAssignmentVersion=0, mode="MANUAL_APPROVAL"),
        ADMIN,
    )
    return work, records, calls, events, department, officer, identity


def test_cloud_config_seeding_and_trusted_membership_are_guarded_sdk_transactions():
    work, records, calls, events, department, officer, identity = configured()
    assert work.seed(common(), ADMIN)["added"] == []
    assert work.detail(identity)["assignment"]["departmentId"] == department["id"]
    assert work.detail(identity)["recommendations"]["ranked"][0]["officerId"] == officer
    assert work.officer_directory()["items"][0]["officerId"] == officer
    assert all(len(kwargs["TransactItems"]) <= 95 for _, kwargs in calls)
    assert events and all(event["actorId"] == ADMIN.id for event in events)
    assert work.process_one() is None
    # Renaming a default must not let a later seed steal its reserved historical code claim.
    work.save_department(
        department["id"],
        common(
            expectedVersion=department["version"],
            code="RENAMED_ROADS",
            name=department["name"],
            description=department["description"],
            active=True,
            areas=[],
        ),
        ADMIN,
    )
    assert work.seed(common(), ADMIN)["added"] == []
    assert records["work-code#ROAD_MAINTENANCE"]["departmentId"] == department["id"]


def test_cloud_assign_progress_capacity_ledger_and_membership_guards():
    work, records, calls, events, department, officer, identity = configured()
    state = work.detail(identity)
    data = common(
        expectedIncidentVersion=1,
        expectedAssignmentVersion=state["assignment"]["version"],
        officerId=officer,
    )
    assigned = work.assign(identity, "OFFICER", data, ADMIN)
    assert work.assign(identity, "OFFICER", data, ADMIN) == assigned
    assert work.workload_read(officer)["workload"] == 2
    assert work.detail(identity, officer)["assignment"]["status"] == "OFFICER_ASSIGNED"
    actions = calls[-1][1]["TransactItems"]
    guards = [a["ConditionCheck"] for a in actions if "ConditionCheck" in a]
    assert any("generation" in g["ConditionExpression"] for g in guards)
    assert any(unmarshal(g["Key"])["incidentId"] == identity for g in guards)
    assert any("work-member#" in unmarshal(g["Key"])["incidentId"] for g in guards)
    progress = common(
        expectedIncidentVersion=1,
        expectedAssignmentVersion=assigned["version"],
        note="Private officer inspected and began road maintenance",
        percentage=20,
        requestReview=False,
    )
    result = work.progress(identity, "START", progress, Actor(officer, "OFFICER"))
    assert result["status"] == "IN_PROGRESS" and records[identity]["status"] == "OPEN"
    assert events[-1]["after"]["note"] == progress["note"]
    with pytest.raises(IncidentError):
        work.remove_membership(department["id"], officer, common(expectedVersion=1), ADMIN)
    with pytest.raises(IncidentError):
        work.detail(identity, str(uuid4()))
    # P7 invalidation makes stored allocation historical, without deleting its audit/provenance.
    records[identity]["version"] = 2
    state = work.detail(identity)
    assert (
        state["assignment"]["officerId"] is None and state["assignment"]["status"] == "NEEDS_REVIEW"
    )
    assert work.workload_read(officer)["workload"] == 0
    with pytest.raises(IncidentError):
        work.detail(identity, officer)


def test_cloud_timeout_receipt_and_atomic_envelope_no_partial_writes():
    work, records, calls, events = fake()
    data = common()
    work.seed(data, ADMIN)
    count = len(calls)
    assert work.seed(data, ADMIN)["added"] and len(calls) == count
    with pytest.raises(IncidentError):
        work.seed(data | {"reason": "Different request reusing the existing operation ID"}, ADMIN)

    def oversized(c, operation):
        for n in range(96):
            c.put(f"oversize#{n}", {"value": n})
        return {}

    with pytest.raises(IncidentError, match="envelope"):
        work.atomic("OVERSIZE", "configuration", common(), ADMIN, oversized)
    assert len(calls) == count
    work.incidents.call.side_effect = TimeoutError("Ambiguous provider response")
    with pytest.raises(IncidentError, match="SAME operation"):
        work.atomic("EMPTY", "configuration", common(), ADMIN, lambda c, o: {})


@pytest.mark.parametrize("mode", ["officer", "department", "unassigned"])
def test_cloud_queue_queries_existing_sparse_index_and_strongly_rechecks(mode):
    work, records, calls, events, department, officer, identity = configured()
    work.assign(
        identity,
        "OFFICER",
        common(expectedIncidentVersion=1, expectedAssignmentVersion=1, officerId=officer),
        ADMIN,
    )
    raw = records[f"work#{identity}"]
    entry = {
        k: raw[k]
        for k in (
            "incidentId",
            "status",
            "prioritySortKey",
            "catalogPartition",
            "catalogSortKey",
            "departmentId",
        )
    }
    client = sdk("dynamodb")
    query = {"limit": 20}
    if mode == "department":
        query["departmentId"] = department["id"]
    index = {
        "officer": "ByCatalog",
        "department": "ByDepartmentPriority",
        "unassigned": "ByStatusPriority",
    }[mode]
    with Stubber(client) as stub:
        stub.add_response(
            "query",
            {"Items": [marshal(entry)]},
            {
                "TableName": "incidents",
                "IndexName": index,
                "KeyConditionExpression": ANY,
                "ExpressionAttributeNames": ANY,
                "ExpressionAttributeValues": ANY,
                "Limit": 1,
            },
        )
        work.incidents.call.side_effect = lambda method, **kwargs: getattr(client, method)(**kwargs)
        result = work.queue(
            query, officer=officer if mode == "officer" else None, unassigned=mode == "unassigned"
        )
        assert len(result["items"]) == (0 if mode == "unassigned" else 1)
        stub.assert_no_pending_responses()
    assert result["stats"]["assigned"] is None


def test_cloud_account_profile_cannot_be_forged_as_membership():
    work, records, calls, events = fake()
    with pytest.raises(IncidentError):
        work.provision_officer_profile(
            {"officerId": str(uuid4()), "role": "ADMIN"}, common(), ADMIN
        )
