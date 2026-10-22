"""Actual thread races at the local transactional boundaries, not sequential imitations."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from test_civic_intelligence import admin, decision, prepared
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import fields, submit
from test_incidents import ADMIN, correction, create
from test_work_allocation import action, common

from app.models.incident import Actor, IncidentError
from app.schemas.work import ProgressAction
from app.scripts.audit_local_data import audit


def race(first, second):
    barrier = Barrier(2)

    def call(callback):
        barrier.wait(timeout=5)
        try:
            return {"success": True, "result": callback()}
        except IncidentError as error:
            return {"success": False, "status": error.status}

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(call, (first, second)))


def test_feedback_racing_approval_never_loses_an_accepted_response(complaint_app, complaint_client):
    app = complaint_app
    incident, officer, citizen, data = prepared(app, complaint_client)
    service = app.state.civic_intelligence_service
    result = service.upload_action("submit", incident, data, officer, [])
    request = service.repository.requests(citizen)["items"][0]
    reviewer = admin(app, complaint_client)
    detail = service.repository.detail(result["attemptId"], reviewer)
    outcomes = race(
        lambda: service.upload_action(
            "respond",
            request["requestId"],
            {
                "operationId": str(uuid4()),
                "expectedVersion": detail["version"],
                "result": "STILL_BROKEN",
                "feedback": "Physical issue still remains",
            },
            citizen,
            [],
        ),
        lambda: service.decision(result["attemptId"], "approve", decision(detail), reviewer),
    )
    assert sum(o["success"] for o in outcomes) == 1
    final = service.repository.detail(result["attemptId"], reviewer)
    if outcomes[0]["success"]:
        assert final["responses"]["STILL_BROKEN"] == 1
        assert final["incidentStatus"] == "OPEN"
    else:
        assert final["incidentStatus"] == "RESOLVED" and final["responses"]["STILL_BROKEN"] == 0
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_officer_progress_racing_reassignment_keeps_version_and_authorization_fences(
    complaint_app, complaint_client
):
    app = complaint_app
    incident, officer, _, _ = prepared(app, complaint_client)
    repo = app.state.work_service.repository
    current = repo.detail(incident)
    progress = ProgressAction.model_validate(
        common(
            expectedIncidentVersion=current["incidentVersion"],
            expectedAssignmentVersion=current["assignment"]["version"],
            percentage=30,
            note="Crew observed and recorded actual field progress",
        )
    ).model_dump(mode="json")
    unassign = action(repo, incident)
    outcomes = race(
        lambda: repo.progress(incident, "PROGRESS", progress, Actor(officer["id"], "OFFICER")),
        lambda: repo.assign(incident, "UNASSIGN", unassign, ADMIN),
    )
    assert sum(o["success"] for o in outcomes) == 1
    assert all(o["success"] or o["status"] in (403, 404, 409) for o in outcomes)
    final = repo.detail(incident)["assignment"]
    assert final["version"] == current["assignment"]["version"] + 1
    if outcomes[0]["success"]:
        assert final["percentage"] == 30 and final["officerId"] == officer["id"]
    else:
        assert final["officerId"] is None
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_analytics_snapshot_racing_merge_is_one_consistent_membership_epoch(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    _, first = create(client, app)
    _, second = create(client, app)
    service = app.state.incident_service
    results = race(
        lambda: app.state.analytics_service.repository.snapshot(),
        lambda: service.mutate("MERGE", correction(second, first), ADMIN),
    )
    assert all(r["success"] for r in results)
    snapshot = results[0]["result"]
    active = {i["incident_id"] for i in snapshot["incidents"]}
    referenced = {c["incident_id"] for c in snapshot["complaints"]}
    assert active == referenced and len(active) in (1, 2)
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_split_racing_priority_recalculation_does_not_publish_a_fresh_old_membership_score(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    _, first = create(client, app)
    report, second = create(client, app)
    service = app.state.incident_service
    merged = service.mutate("MERGE", correction(second, first), ADMIN)
    identity = merged["incidentId"]
    app.state.priority_service.calculate(identity)
    outcomes = race(
        lambda: service.mutate(
            "SPLIT", correction(merged, complaintIds=[report["complaintId"]]), ADMIN
        ),
        lambda: app.state.priority_service.calculate(identity),
    )
    assert outcomes[0]["success"]
    assert outcomes[1]["success"] or outcomes[1]["status"] == 409
    detail = app.state.priority_service.detail(identity)
    with app.state.auth_service.store.connection() as db:
        row = db.execute(
            "SELECT p.source_version,p.needs_recalculation,i.version FROM "
            "incident_priority p JOIN incidents i USING(incident_id) "
            "WHERE incident_id=?",
            (identity,),
        ).fetchone()
    assert detail["stale"] or row[0] == row[2] and row[1] == 0
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_two_citizens_reporting_same_problem_concurrently_preserve_both_reports(
    complaint_app, complaint_client
):
    from app.models.complaint import ComplaintInput
    from app.schemas.auth import RegisterInput

    app = complaint_app
    first = complaint_client.get("/api/auth/me").json()["id"]
    second = app.state.auth_service.register(
        RegisterInput(
            display_name="Second independent fixture account",
            email="second@example.com",
            password="Synthetic second account passphrase 2048",
            confirm_password="Synthetic second account passphrase 2048",
        )
    ).id
    data = ComplaintInput.model_validate(fields())

    def create_report(owner):
        report = app.state.complaint_service.create(owner, data, [], str(uuid4()), str(uuid4()))
        app.state.incident_service.ensure_singleton(report.complaintId)
        return report

    results = race(lambda: create_report(first), lambda: create_report(second))
    assert all(r["success"] for r in results)
    reports = [r["result"] for r in results]
    assert len({r.complaintId for r in reports}) == 2
    assert {r.citizenId for r in reports} == {first, second}
    # Review-only mode does not guess physical identity or inflate a merged reporter count.
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_merge_racing_new_complaint_does_not_drop_original_or_new_membership(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    _, first = create(client, app)
    _, second = create(client, app)

    def new_report():
        response = submit(client)
        assert response.status_code == 201
        report = response.json()
        app.state.incident_service.ensure_singleton(report["complaintId"])
        return report

    outcomes = race(
        lambda: app.state.incident_service.mutate("MERGE", correction(second, first), ADMIN),
        new_report,
    )
    assert all(o["success"] for o in outcomes)
    with app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM complaints").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM incidents WHERE status='OPEN'").fetchone()[0] == 2
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"


def test_replayed_membership_event_racing_priority_has_one_receipt_and_no_repeat_history(
    complaint_app, complaint_client
):
    from app.events.schema import new_event

    app = complaint_app
    _, incident = create(complaint_client, app)
    identity = incident["incidentId"]
    priority, runner = app.state.priority_service, app.state.workflow_service
    priority.calculate(identity)
    event = new_event("IncidentMembershipChanged", identity)
    runner.repository.enqueue(event)
    outcomes = race(runner.process_one, lambda: priority.calculate(identity))
    assert all(o["success"] or o["status"] == 409 for o in outcomes)
    # Once any transient conflict is recoverable, replay itself remains idempotent.
    runner.repository.enqueue(event)
    with runner.repository.store.connection() as db:
        before = db.execute(
            "SELECT count(*) FROM priority_history WHERE incident_id=?", (identity,)
        ).fetchone()[0]
    runner.process_one()
    with runner.repository.store.connection() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM priority_history WHERE incident_id=?", (identity,)
            ).fetchone()[0]
            == before
        )
        assert (
            db.execute(
                "SELECT count(*) FROM event_receipts WHERE event_id=?", (str(event.eventId),)
            ).fetchone()[0]
            == 1
        )
    assert audit(app.state.settings.local_db_path)["status"] == "PASS"
