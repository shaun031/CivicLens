"""Offline SDK fixtures: every operation is shape-checked by botocore Stubber."""

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import submit

from app.events.schema import new_event
from app.integrations.database.dynamodb_complaints import marshal, unmarshal
from app.integrations.database.dynamodb_events import DynamoEvents, DynamoSLA, event_action
from app.integrations.events import EventBridgePublisher, SNSPublisher
from app.services.workflow_service import STEPS
from app.workflow_handlers import sqs_handler, step_handler


def sdk(service):
    return boto3.client(
        service,
        region_name="us-east-1",
        aws_access_key_id="offline",
        aws_secret_access_key="offline",
    )


class DurableFixture:
    def __init__(self):
        self.items, self.client = {}, sdk("dynamodb")

    def validate(self, method, args, result):
        with Stubber(self.client) as stub:
            stub.add_response(method, result, args)
            value = getattr(self.client, method)(**args)
            stub.assert_no_pending_responses()
            return value

    def get_item(self, **args):
        item = self.items.get(unmarshal(args["Key"])["pk"])
        return self.validate("get_item", args, {"Item": marshal(item)} if item else {})

    def put_item(self, **args):
        item = json.loads(json.dumps(unmarshal(args["Item"]), default=float))
        revision = (self.items.get(item["pk"]) or {}).get("revision", 0)
        expected = unmarshal(args.get("ExpressionAttributeValues", {})).get(":r", 0)
        if revision != expected:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        result = self.validate("put_item", args, {})
        self.items[item["pk"]] = copy.deepcopy(item)
        return result

    def transact_write_items(self, **args):
        result = self.validate("transact_write_items", args, {})
        snapshot = copy.deepcopy(self.items)
        try:
            for action in args["TransactItems"]:
                if "Put" in action:
                    self.put_item(**action["Put"])
        except Exception:
            self.items = snapshot
            raise
        return result

    def query(self, **args):
        values = unmarshal(args["ExpressionAttributeValues"])
        records = sorted(
            (
                i
                for i in self.items.values()
                if i.get("queue") == values[":q"]
                and (":d" not in values or i["due"] <= values[":d"])
            ),
            key=lambda i: i["due"],
            reverse=not args["ScanIndexForward"],
        )
        if args.get("ExclusiveStartKey"):
            cursor = unmarshal(args["ExclusiveStartKey"])["due"]
            records = (
                [i for i in records if i["due"] > cursor]
                if args["ScanIndexForward"]
                else [i for i in records if i["due"] < cursor]
            )
        selected = records[: args["Limit"]]
        response = {
            "Items": [marshal({k: i[k] for k in ("pk", "sk", "queue", "due")}) for i in selected]
        }
        if len(records) > len(selected):
            response["LastEvaluatedKey"] = response["Items"][-1]
        return self.validate("query", args, response)


def test_eventbridge_acceptance_and_transient_failure():
    event, client = new_event("ComplaintSubmitted", str(uuid4())), sdk("events")
    expected = {
        "Entries": [
            {
                "EventBusName": "civiclens-demo-domain",
                "Source": "civiclens.domain",
                "DetailType": "ComplaintSubmitted",
                "Detail": event.model_dump_json(),
                "Time": event.occurredAt,
            }
        ]
    }
    with Stubber(client) as stub:
        stub.add_response(
            "put_events",
            {"FailedEntryCount": 1, "Entries": [{"ErrorCode": "InternalFailure"}]},
            expected,
        )
        with pytest.raises(RuntimeError):
            EventBridgePublisher("civiclens-demo-domain", client).publish(event)
        stub.add_response(
            "put_events", {"FailedEntryCount": 0, "Entries": [{"EventId": str(uuid4())}]}, expected
        )
        assert EventBridgePublisher("civiclens-demo-domain", client).publish(event)["accepted"]


def test_sns_requires_opt_in_and_records_confirmed_publication():
    event, client = new_event("IncidentOverdue", str(uuid4())), sdk("sns")
    publisher = SNSPublisher("arn:aws:sns:us-east-1:123456789012:alerts", client, True)
    assert publisher.publish(event)["status"] == "SKIPPED"
    with Stubber(client) as stub:
        stub.add_response(
            "publish",
            {"MessageId": str(uuid4())},
            {
                "TopicArn": publisher.topic,
                "Subject": "CivicLens operational review",
                "Message": ANY,
            },
        )
        assert publisher.publish(event, eligible=True, opted_in=True)["status"] == "PUBLISHED"
        with pytest.raises(ValueError):
            publisher.publish(
                new_event("ComplaintSubmitted", str(uuid4())), eligible=True, opted_in=True
            )


def test_dynamo_queue_claim_receipt_and_dispatch(complaint_app):
    fixture = DurableFixture()
    settings = complaint_app.state.settings.model_copy(
        update={"workflow_table_name": "test-operations"}
    )
    repo = DynamoEvents(settings, SimpleNamespace(complaints=SimpleNamespace(client=fixture)))
    event = new_event("ComplaintSubmitted", str(uuid4()))
    identity = repo.enqueue(event)
    assert repo.enqueue(event) == identity
    message = repo.claim(identity)
    assert message and repo.claim(identity) is None
    repo.ack(message, event)
    assert repo.completed(event, "triage") and repo.claim(identity) is None
    fixture.put_item(**event_action(settings, event)[0]["Put"])
    assert repo.dispatch_one(lambda value: None)
    assert repo.load("outbox#" + str(event.eventId))["status"] == "DISPATCHED"
    stored = fixture.items["outbox#" + str(event.eventId)]
    stored.update(queue="outbox", due=repo.due_key(0, str(event.eventId)))
    stored["data"]["status"] = "PENDING"
    stored["data"]["available_at"] = 0
    stored["data"]["event"]["eventVersion"] = 2
    assert repo.dispatch_one(lambda event: None)
    assert repo.listing("dead")["items"][0]["error_category"] == "PERMANENT_EVENT_ERROR"


def test_sqs_partial_failure_and_step_sequence_share_business_services(
    complaint_client, complaint_app
):
    app, client = complaint_app, complaint_client
    report = submit(client).json()["complaintId"]
    fixture = DurableFixture()
    app.state.settings = app.state.settings.model_copy(
        update={
            "workflow_table_name": "test-operations",
            "incidents_table_name": "test-incidents",
            "triage_state_machine_arn": "arn:aws:states:us-east-1:123456789012:stateMachine:triage",
        }
    )
    runner = app.state.workflow_service
    runner.repository = DynamoEvents(
        app.state.settings, SimpleNamespace(complaints=SimpleNamespace(client=fixture))
    )
    event = new_event("ComplaintSubmitted", report)
    states = sdk("stepfunctions")
    with Stubber(states) as stub:
        stub.add_response(
            "start_execution",
            {
                "executionArn": "arn:aws:states:us-east-1:123456789012:execution:triage:fixture",
                "startDate": event.occurredAt,
            },
            {
                "stateMachineArn": app.state.settings.triage_state_machine_arn,
                "name": f"triage-{event.eventId}-0",
                "input": json.dumps({"event": event.model_dump(mode="json")}, sort_keys=True),
            },
        )
        result = sqs_handler(
            {
                "Records": [
                    {
                        "messageId": "good",
                        "body": json.dumps({"detail": event.model_dump(mode="json")}),
                    },
                    {"messageId": "invalid", "body": "{}"},
                ]
            },
            None,
            app,
            states,
        )
        assert result == {"batchItemFailures": [{"itemIdentifier": "invalid"}]}
    value = {"event": event.model_dump(mode="json")}
    for stage in (*STEPS, "CompleteWorkflow"):
        value = step_handler(value | {"step": stage}, None, app)
    assert value["terminated"]
    repo = runner.repository
    workflow = repo.listing("workflow")["items"][0]
    assert workflow["status"] == "COMPLETED_WITH_REVIEW_REQUIRED"
    assert len(repo.detail(workflow["workflow_id"])["steps"]) == 6
    assert repo.notifications(
        app.state.incident_service.require_member(report).complaint.citizenId
    )["items"]
    from datetime import timedelta

    from app.events.schema import utcnow

    incident = app.state.incident_service.require_member(report).complaint.incidentId
    now = utcnow()
    repo.save(
        "sla#" + incident,
        {
            "incident_id": incident,
            "cycle": now.isoformat(),
            "opened_at": (now - timedelta(days=40)).isoformat(),
        },
        "sla-due",
        repo.due_key(0, incident),
    )
    monitor = DynamoSLA(runner)
    assert monitor.sweep()["results"][0]["overdue"] == ["RESPONSE", "RESOLUTION"]
    assert len(monitor.escalations()["items"]) == 2
    assert monitor.sweep()["checked"] == 0
    change = {
        "operationId": str(uuid4()),
        "confirmed": True,
        "reason": "Synthetic policy verification",
        "expectedVersion": 0,
        "priorityBand": "LOW",
        "responseHours": 2,
        "resolutionHours": 4,
        "urgent": False,
    }
    first = monitor.save("LOW", change, "trusted-admin")
    assert monitor.save("LOW", change, "trusted-admin") == first
