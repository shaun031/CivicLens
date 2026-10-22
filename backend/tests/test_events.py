import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import register_login, submit
from test_discovery import login_staff
from test_incidents import ADMIN, correction, create
from test_work_allocation import common

from app.events.schema import Event, new_event, utcnow
from app.main import create_app


def drain(app):
    runner = app.state.workflow_service
    for _ in range(10):
        if not any(runner.batch(20).values()):
            return
    pytest.fail("Event processing did not terminate within bounded10 batches")


@pytest.mark.parametrize(
    "change",
    [
        {"eventType": "Unregistered"},
        {"eventVersion": 2},
        {"eventVersion": True},
        {"eventId": None},
        {"aggregateId": "invalid"},
        {"occurredAt": "2026-10-20T00:00:00"},
        {"payload": {"email": "secret@example.com"}},
        {"source": "other"},
        {"payload": {"description": "secret" * 1000}},
        {"aggregateType": "INCIDENT"},
    ],
)
def test_schema_rejects_invalid_or_private_events(change):
    event = new_event("ComplaintSubmitted", str(uuid4())).model_dump(mode="json")
    with pytest.raises(ValueError):
        Event.parse(event | change)


def test_schema_valid_and_raw_size():
    event = new_event("ComplaintSubmitted", str(uuid4()))
    assert Event.parse(event.model_dump_json()) == event
    with pytest.raises(ValueError):
        Event.parse(" " * 2049)
    data = event.model_dump(mode="json")
    del data["eventId"]
    with pytest.raises(ValueError):
        Event.parse(data)


def test_handler_registry_rejects_ambiguous_duplicate_and_unsupported_version():
    from app.events.registry import HandlerRegistry

    registry = HandlerRegistry()
    registry.register("triage", lambda event, message: "accepted")
    with pytest.raises(ValueError):
        registry.register("triage", lambda event, message: None)
    with pytest.raises(ValueError):
        registry.register("notify", lambda event, message: None, version=2)
    assert registry.dispatch(new_event("ComplaintSubmitted", str(uuid4())), {}) == "accepted"


def test_event_depth_and_causation_cycles_are_bounded():
    from app.events.schema import check_causation

    identities = [str(uuid4()) for _ in range(10)]
    chain = dict(zip(identities, identities[1:], strict=False))
    event = new_event("WorkflowFailed", str(uuid4()), cause=identities[0])
    with pytest.raises(ValueError):
        check_causation(event, chain.get)
    with pytest.raises(ValueError):
        check_causation(event, lambda identity: identities[0])


def test_on_time_response_survives_later_reassignment(complaint_client, complaint_app):
    from test_work_allocation import setup

    app, client = complaint_app, complaint_client
    _, identity, _, _, _ = setup(app, client)
    repo, sla = app.state.workflow_service.repository, app.state.sla_service
    baseline = utcnow()
    with repo.store.connection() as db:
        db.execute("UPDATE sla_policies SET response_hours=1,resolution_hours=2")
        db.execute(
            "UPDATE incident_assignments SET assigned_at=? WHERE incident_id=?",
            ((baseline + timedelta(hours=3)).isoformat(), identity),
        )
        db.execute(
            "UPDATE incident_priority SET next_due=? WHERE incident_id=?",
            ((baseline + timedelta(days=100)).timestamp(), identity),
        )
    repo.clock = lambda: baseline + timedelta(hours=4)
    assert sla.check(identity)["overdue"] == ["RESOLUTION"]


def test_transactional_outbox_rollback_and_creation(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    identity = submit(client).json()["complaintId"]
    store = app.state.auth_service.store
    with store.connection() as db:
        row = db.execute("SELECT * FROM event_outbox WHERE aggregate_id=?", (identity,)).fetchone()
        assert row["event_type"] == "ComplaintSubmitted"
        assert json.loads(row["payload"]) == {}
    with pytest.raises(RuntimeError), store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE complaints SET status='UNDER_REVIEW' WHERE complaint_id=?", (identity,))
        event = new_event("WorkflowFailed", identity)
        app.state.workflow_service.repository.put(db, event)
        raise RuntimeError("Simulated rolled-back business transaction")
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM event_outbox").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT status FROM complaints WHERE complaint_id=?", (identity,)
            ).fetchone()[0]
            == "SUBMITTED"
        )


def test_real_triage_notifications_restart_and_duplicate_delivery(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    app.state.work_service.repository.seed(common(), ADMIN)
    identity = submit(client).json()["complaintId"]
    drain(app)
    repo = app.state.workflow_service.repository
    workflow = repo.listing("workflow")["items"][0]
    assert workflow["status"] == "COMPLETED"
    assert len(repo.detail(workflow["workflow_id"])["steps"]) == 6
    member = app.state.incident_service.require_member(identity)
    assert member.complaint.incidentId
    assert app.state.duplicate_detection_service.repository.job(identity)["state"] == "COMPLETE"
    assert not app.state.priority_service.detail(member.complaint.incidentId)["stale"]
    assert app.state.work_service.detail(member.complaint.incidentId)["assignment"]["departmentId"]
    assert client.get("/api/notifications/unread-count").json()["unreadCount"] >= 1
    items = client.get("/api/notifications").json()["items"]
    assert any(n["type"] == "COMPLAINT_RECEIVED" for n in items)
    assert all(not n["isSimulated"] for n in items)
    original = len(items)
    with repo.store.connection() as db:
        row = db.execute(
            "SELECT * FROM event_outbox WHERE event_type='ComplaintSubmitted'"
        ).fetchone()
        event = repo.envelope(row)
        db.execute(
            "UPDATE event_queue SET state='PENDING',available_at=0 WHERE event_id=?",
            (str(event.eventId),),
        )
    drain(app)
    assert len(client.get("/api/notifications").json()["items"]) == original
    restarted = create_app(app.state.settings)
    assert (
        restarted.state.workflow_service.repository.detail(workflow["workflow_id"])["status"]
        == "COMPLETED"
    )
    notification = items[0]["notificationId"]
    assert client.patch(f"/api/notifications/{notification}/read").status_code == 200
    assert client.post("/api/notifications/mark-all-read").json() == {"unreadCount": 0}


def test_notifications_privacy_filters_and_admin_scope(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    submit(client)
    drain(app)
    first = client.get("/api/notifications").json()["items"][0]
    client.post("/api/auth/logout")
    register_login(client, "other@example.com")
    assert client.get("/api/notifications").json()["items"] == []
    assert client.patch(f"/api/notifications/{first['notificationId']}/read").status_code == 404
    assert client.get("/api/admin/workflows").status_code == 403
    assert client.get("/api/notifications?type=NOT_REAL").status_code == 422
    assert client.get("/api/notifications?recipientId=someone").json()["items"] == []
    login_staff(app, client)
    assert client.get("/api/notifications").json()["items"] == []
    assert client.get("/api/admin/workflows/summary").status_code == 200
    assert client.get("/api/admin/workflows").json()["items"]


def test_retry_persists_steps_and_crash_lease_recovers(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    runner = app.state.workflow_service
    identity = submit(client).json()["complaintId"]

    def fault(step):
        if step == "RecalculatePriority":
            raise OSError("Injected temporary downstream error with private data")

    runner.fault = fault
    runner.batch(10)
    repo = runner.repository
    workflow = repo.listing("workflow")["items"][0]
    assert workflow["status"] == "WAITING_RETRY"
    steps = repo.detail(workflow["workflow_id"])["steps"]
    assert sum(s["status"] == "COMPLETED" for s in steps) == 3
    assert any(s["step"] == "RecalculatePriority" and s["status"] == "FAILED" for s in steps)
    with repo.store.connection() as db:
        db.execute(
            "UPDATE event_queue SET "
            "state='RUNNING',lease_token='dead-worker',available_at=0 WHERE "
            "consumer='triage'"
        )
    restarted = create_app(app.state.settings)
    restarted.state.workflow_service.repository.clock = lambda: utcnow() + timedelta(minutes=3)
    drain(restarted)
    assert repo.detail(workflow["workflow_id"])["status"] in (
        "COMPLETED",
        "COMPLETED_WITH_REVIEW_REQUIRED",
    )
    with repo.store.connection() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM complaints WHERE complaint_id=?", (identity,)
            ).fetchone()[0]
            == 1
        )
        assert db.execute("SELECT count(*) FROM incidents WHERE status='OPEN'").fetchone()[0] == 1


def test_queue_concurrent_claim_dispatch_retry_and_dead_letter(complaint_client, complaint_app):
    repo = complaint_app.state.workflow_service.repository
    identity = submit(complaint_client).json()["complaintId"]
    clock = utcnow()
    repo.clock = lambda: clock

    def broken_transport(event):
        raise OSError("Network unavailable")

    assert repo.dispatch_one(broken_transport)
    assert repo.claim() is None
    clock += timedelta(seconds=3)
    assert repo.dispatch_one()
    with ThreadPoolExecutor(max_workers=2) as workers:
        messages = list(workers.map(lambda _: repo.claim(), range(2)))
    assert sum(m is not None for m in messages) == 1
    clock += timedelta(seconds=121)
    recovered = repo.claim()
    assert recovered["attempts"] == 2
    assert recovered["lease_token"] != next(m for m in messages if m)["lease_token"]
    repo.fail(recovered, permanent=True)
    dead = repo.listing("dead")["items"][0]
    assert dead["error_category"] == "PERMANENT_EVENT_ERROR"
    assert "envelope" not in dead
    assert repo.summary()["queue"]["DEAD"] == 1
    assert identity


def test_sla_before_at_after_rerun_and_acknowledgement(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    identity = submit(client).json()["complaintId"]
    drain(app)
    runner = app.state.workflow_service
    incident = app.state.incident_service.require_member(identity).complaint.incidentId
    sla, repo = app.state.sla_service, runner.repository
    baseline = utcnow()
    with repo.store.connection() as db:
        db.execute(
            "UPDATE sla_checks SET opened_at=? WHERE incident_id=?",
            (baseline.isoformat(), incident),
        )
        db.execute(
            "UPDATE incident_priority SET next_due=? WHERE incident_id=?",
            ((baseline + timedelta(days=100)).timestamp(), incident),
        )
        db.execute("UPDATE sla_policies SET response_hours=1,resolution_hours=2")
    repo.clock = lambda: baseline + timedelta(minutes=59)
    assert sla.check(incident)["overdue"] == []
    repo.clock = lambda: baseline + timedelta(hours=1)
    assert sla.check(incident)["overdue"] == ["RESPONSE"]
    assert len(sla.check(incident)["newEscalations"]) == 0
    repo.clock = lambda: baseline + timedelta(hours=2, seconds=1)
    assert sla.check(incident)["overdue"] == ["RESPONSE", "RESOLUTION"]
    assert len(sla.escalations()["items"]) == 2
    login_staff(app, client)
    drain(app)
    assert (
        len(
            [
                n
                for n in client.get("/api/notifications").json()["items"]
                if n["type"] == "INCIDENT_OVERDUE"
            ]
        )
        == 2
    )
    assert (
        client.put(
            "/api/admin/sla/policies/LOW",
            json=common(expectedVersion=1, priorityBand="LOW", responseHours=-1, resolutionHours=2),
        ).status_code
        == 422
    )
    escalation = sla.escalations()["items"][0]
    assert (
        client.post(
            f"/api/admin/sla/escalations/{escalation['escalation_id']}/acknowledge", json=common()
        ).status_code
        == 200
    )
    assert sla.escalations()["items"][0]["status"] == "ACKNOWLEDGED"
    change = common(expectedVersion=1, priorityBand="LOW", responseHours=2, resolutionHours=4)
    first = client.put("/api/admin/sla/policies/LOW", json=change)
    assert first.status_code == 200
    assert client.put("/api/admin/sla/policies/LOW", json=change).json() == first.json()


def test_bounded_retry_dlq_redrive_confirmation_and_receipt(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    submit(client)
    runner = app.state.workflow_service
    runner.fault = lambda step: (_ for _ in ()).throw(OSError("private injected failure"))
    for _ in range(5):
        runner.batch(20)
        with runner.repository.store.connection() as db:
            db.execute("UPDATE event_queue SET available_at=0 WHERE state='RETRY'")
    repo = runner.repository
    dead = repo.listing("dead")["items"][0]
    assert dead["attempts"] == 5
    workflow = repo.listing("workflow")["items"][0]
    assert workflow["status"] == "FAILED"
    login_staff(app, client)
    url = f"/api/admin/workflows/dead-letters/{dead['message_id']}/redrive"
    assert client.post(url, json=common(confirmed=False)).status_code == 422
    body = common()
    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 200
    with repo.store.connection() as db:
        assert (
            db.execute(
                "SELECT redrives FROM event_queue WHERE message_id=?", (dead["message_id"],)
            ).fetchone()[0]
            == 1
        )
    runner.fault = None
    drain(app)
    assert repo.detail(workflow["workflow_id"])["status"] == "COMPLETED_WITH_REVIEW_REQUIRED"


def test_notification_pagination_read_filters_origin_and_invalid_cursor(
    complaint_client, complaint_app
):
    app, client = complaint_app, complaint_client
    submit(client)
    drain(app)
    user = client.get("/api/auth/me").json()["id"]
    repo = app.state.workflow_service.repository
    for _ in range(5):
        event = new_event("ComplaintSubmitted", str(uuid4()))
        repo.notify(
            event,
            user,
            "COMPLAINT_RECEIVED",
            "Safe title",
            "Safe message",
            "COMPLAINT",
            str(event.aggregateId),
            "/citizen/complaints",
        )
    seen, cursor = [], None
    for _ in range(4):
        response = client.get(
            "/api/notifications", params={"limit": 2, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200
        body = response.json()
        seen.extend(n["notificationId"] for n in body["items"])
        cursor = body["nextCursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 6
    assert (
        client.patch(
            f"/api/notifications/{seen[0]}/read", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    client.patch(f"/api/notifications/{seen[0]}/read")
    assert len(client.get("/api/notifications?read=true").json()["items"]) == 1
    assert client.get("/api/notifications?cursor=bad").status_code == 400


def test_sla_resolved_merged_exclusion_and_reopen_cycle(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    report = submit(client).json()["complaintId"]
    drain(app)
    identity = app.state.incident_service.require_member(report).complaint.incidentId
    repo, sla = app.state.workflow_service.repository, app.state.sla_service
    baseline = utcnow()
    with repo.store.connection() as db:
        db.execute(
            "UPDATE incidents SET status='RESOLVED',resolved_at=?,updated_at=? WHERE incident_id=?",
            (baseline.isoformat(), baseline.isoformat(), identity),
        )
    assert sla.check(identity)["excluded"] == "RESOLVED"
    with repo.store.connection() as db:
        db.execute(
            "UPDATE incidents SET status='OPEN',resolved_at=NULL,updated_at=? WHERE incident_id=?",
            (baseline.isoformat(), identity),
        )
    app.state.priority_service.calculate(identity)
    assert sla.check(identity)["overdue"] == []
    with repo.store.connection() as db:
        assert (
            db.execute("SELECT cycle FROM sla_checks WHERE incident_id=?", (identity,)).fetchone()[
                0
            ]
            == baseline.isoformat()
        )
    _, target = create(client, app)
    source = app.state.incident_service.require(identity).model_dump(mode="json")
    app.state.incident_service.mutate("MERGE", correction(source, target), ADMIN)
    assert sla.check(identity)["excluded"] == "MERGED"


def test_officer_progress_and_verified_hazard_notifications(complaint_client, complaint_app):
    from test_complaints import PASSWORD
    from test_priority_workflow import action as priority_action
    from test_work_allocation import action as work_action
    from test_work_allocation import setup

    from app.models.incident import Actor

    app, client = complaint_app, complaint_client
    work, identity, _, officer, email = setup(app, client)
    work.assign(identity, "OFFICER", work_action(work, identity, officerId=officer), ADMIN)
    drain(app)
    assert work.detail(identity)["assignment"]["officerId"] == officer
    client.post("/api/auth/logout")
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    items = client.get("/api/notifications").json()["items"]
    assert sum(n["type"] == "OFFICER_ASSIGNED" for n in items) == 1
    work.progress(
        identity,
        "START",
        work_action(work, identity)
        | {
            "note": "Field team inspected the site and safely began work",
            "percentage": 10,
            "requestReview": False,
        },
        Actor(officer, "OFFICER"),
    )
    drain(app)
    assert not any(
        n["type"] == "WORK_STARTED" for n in client.get("/api/notifications").json()["items"]
    )
    login_staff(app, client)
    member = app.state.incident_service.members(identity)[0].complaint.complaintId
    priority = app.state.priority_service
    priority.change(
        identity,
        "HAZARD",
        priority_action(priority, identity, flag=True, evidenceReferences=[member]),
        ADMIN,
    )
    drain(app)
    assert (
        sum(
            n["type"] == "URGENT_HAZARD_REVIEW"
            for n in client.get("/api/notifications").json()["items"]
        )
        == 1
    )
