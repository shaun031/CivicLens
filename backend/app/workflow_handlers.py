"""Offline-testable AWS entry points. Clients/app construction occur only during invocation."""

import json

from botocore.exceptions import ClientError

from app.events.schema import Event
from app.models.incident import IncidentError, stable_id
from app.services.workflow_service import STEPS


def application():
    from app.main import create_app

    return create_app()


def sqs_handler(event, context, app=None, states=None):
    app = app or application()
    runner, failures = app.state.workflow_service, []
    repo = runner.repository
    for record in event.get("Records", [])[:10]:
        message_id = record.get("messageId", "invalid")
        try:
            value = json.loads(record["body"])
            # EventBridge-to-SQS default envelope. Direct event fixtures also supported.
            domain = Event.parse(value.get("detail", value))
            identity = repo.enqueue(domain)
            if domain.eventType == "ComplaintSubmitted":
                repo.prepare_execution(identity)
                if states is None:
                    import boto3

                    states = boto3.client("stepfunctions")
                arn = app.state.settings.triage_state_machine_arn
                if not arn:
                    raise RuntimeError("Triage state machine is not configured")
                row = repo.load("message#" + identity)
                try:
                    states.start_execution(
                        stateMachineArn=arn,
                        name=f"triage-{domain.eventId}-{row['redrives']}",
                        input=json.dumps({"event": domain.model_dump(mode="json")}, sort_keys=True),
                    )
                except ClientError as error:
                    if error.response["Error"]["Code"] != "ExecutionAlreadyExists":
                        raise
            else:
                message = repo.claim(identity)
                if message:
                    runner.consume(message)
                row = repo.load("message#" + identity)
                if row["state"] not in ("COMPLETE", "DEAD"):
                    raise RuntimeError("Event awaits durable retry")
        except Exception:
            # Malformed records are retried to the native SQS DLQ; never silently acknowledged.
            failures.append({"itemIdentifier": message_id})
    # Oversized fixture batches fail remaining messages rather than discarding them.
    failures.extend(
        {"itemIdentifier": r.get("messageId", "invalid")} for r in event.get("Records", [])[10:]
    )
    return {"batchItemFailures": failures}


class TransientWorkflowError(Exception):
    pass


class PermanentWorkflowError(Exception):
    pass


def step_handler(event, context, app=None):
    try:
        return run_step(event, context, app)
    except (PermanentWorkflowError, TransientWorkflowError):
        raise
    except (ValueError, KeyError, TypeError):
        raise PermanentWorkflowError("INVALID_WORKFLOW_INPUT") from None
    except IncidentError as error:
        if error.status in (400, 403, 404, 413, 422):
            raise PermanentWorkflowError("INVALID_DOMAIN_TRANSITION") from None
        raise TransientWorkflowError("WORKFLOW_STATE_CHANGED") from None
    except Exception:
        raise TransientWorkflowError("WORKFLOW_STEP_TEMPORARILY_UNAVAILABLE") from None


def run_step(event, context, app=None):
    app = app or application()
    runner, repo = app.state.workflow_service, app.state.workflow_service.repository
    domain, step = Event.parse(event["event"]), event["step"]
    if step == "CompleteWorkflow" and event.get("execution", {}).get("alreadyCompleted"):
        return {"terminated": True, "alreadyCompleted": True}
    if step not in (*STEPS, "CompleteWorkflow", "RecordFailure"):
        raise ValueError("Unsupported workflow stage")
    identity = repo.enqueue(domain)
    state = event.get("execution")
    if step == "RecordFailure" and not state:
        pending = repo.load("message#" + identity)
        if pending and pending["state"] == "RUNNING":
            repo.fail(pending, permanent=event.get("errorCategory") == "PermanentWorkflowError")
        return {"recorded": True}
    if state:
        message = repo.load("message#" + identity)
        if message and message["state"] == "COMPLETE":
            if step == "CompleteWorkflow":
                return {"terminated": True, "alreadyCompleted": True}
            return {
                "event": domain.model_dump(mode="json"),
                "execution": {"eligible": False, "alreadyCompleted": True},
            }
        if message["lease_token"] != state["leaseToken"]:
            raise RuntimeError("Workflow lease was superseded")
    else:
        message = repo.claim(identity)
        if not message:
            existing = repo.load("message#" + identity)
            if existing and existing["state"] == "COMPLETE":
                return {
                    "event": domain.model_dump(mode="json"),
                    "execution": {"eligible": False, "alreadyCompleted": True},
                }
            raise RuntimeError("Workflow message is not currently claimable")
    workflow_id = stable_id("IncidentTriageWorkflow/1/" + str(domain.aggregateId))
    if step == "RecordFailure":
        repo.fail(message, permanent=event.get("errorCategory") == "PermanentWorkflowError")
        return {"recorded": True}
    if step == "CompleteWorkflow":
        if not state.get("alreadyCompleted"):
            repo.workflow_finish(workflow_id, message, cancelled=not state.get("eligible", True))
            runner.observe_analytics(domain)
            repo.ack(message, domain)
        return {"workflowId": workflow_id, "terminated": True}
    workflow = (
        repo.workflow_begin(domain, message) if not state else repo.load("workflow#" + workflow_id)
    )
    if workflow["status"] in ("COMPLETED", "COMPLETED_WITH_REVIEW_REQUIRED", "CANCELLED"):
        repo.ack(message, domain)
        return {
            "event": domain.model_dump(mode="json"),
            "execution": {"eligible": False, "alreadyCompleted": True},
        }
    if message["attempts"] > message["max_attempts"]:
        repo.fail(message)
        raise PermanentWorkflowError("RETRY_BUDGET_EXHAUSTED")
    result = repo.step(workflow_id, step)
    if result is None:
        repo.step_start(workflow_id, step, message)
        result = runner.stage(step, domain, workflow)
        repo.step(workflow_id, step, result, message)
    return {
        "event": domain.model_dump(mode="json"),
        "execution": {
            "workflowId": workflow_id,
            "leaseToken": message["lease_token"],
            "eligible": result.get("eligible", (state or {}).get("eligible", True)),
            "reviewRequired": bool(workflow.get("review_required") or result.get("reviewRequired")),
        },
    }


def scheduled_handler(event, context, app=None):
    from app.services.sla_service import scheduled_checks

    app = app or application()
    size = min(20, max(1, int(event.get("batchSize", 20))))
    # Retries, outbox and stale leases share the same bounded persistence/services.
    work = app.state.workflow_service
    dispatched = sum(work.repository.dispatch_one() for _ in range(size))
    recovered = int(bool(work.process_one()))  # At most one heavyweight recovered triage per run.
    legacy = int(bool(app.state.duplicate_detection_service.process_one())) + int(
        bool(app.state.incident_service.process_one())
    )
    return {
        "dispatched": dispatched,
        "recovered": recovered,
        "legacyMatchingClustering": legacy,
        **scheduled_checks(work, app.state.sla_service, size),
    }
