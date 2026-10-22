import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from test_civic_intelligence import admin, decision, prepared
from test_complaints import ORIGIN, image_bytes
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_incidents import ADMIN, correction, create
from test_work_allocation import action, common

from app.main import create_app
from app.models.incident import Actor, IncidentError
from app.schemas.work import ProgressAction
from app.services.evidence_service import Upload


def test_evidence_requires_specific_admin_approval_and_current_membership(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    exif = Image.Exif()
    exif[270] = "Private GPS-like source comment must not survive sanitization"
    upload = Upload(image_bytes(exif=exif), "repair.png", "image/png")
    result = service.upload_action("submit", incident, payload, officer, [upload])
    reviewer = admin(app, client)
    detail = service.repository.detail(result["attemptId"], reviewer)
    image = detail["images"][0]
    with pytest.raises(IncidentError):
        service.repository.evidence(incident, result["attemptId"], image["imageId"], citizen)
    request = service.repository.requests(citizen)["items"][0]
    assert request["images"] == []
    assert "notes" not in request and "feedback" not in request and "officerId" not in request
    approval = service.decision(
        result["attemptId"],
        "approve-evidence",
        decision(detail, approvedEvidenceIds=[image["imageId"]]),
        reviewer,
    )
    assert approval["approvedEvidenceIds"] == [image["imageId"]]
    assert approval["supportingEvidenceIds"] == [image["imageId"]]
    key = service.repository.evidence(incident, result["attemptId"], image["imageId"], citizen)
    with Image.open(io.BytesIO(service.complaints.storage.get(key))) as image_file:
        assert image_file.format == "JPEG" and not image_file.getexif()
    unrelated = {"id": str(uuid4()), "role": "CITIZEN"}
    with pytest.raises(IncidentError):
        service.repository.evidence(incident, result["attemptId"], image["imageId"], unrelated)
    with pytest.raises(IncidentError):
        service.repository.request_detail(request["requestId"], unrelated)
    # Corrections preserve attempts, but access/voting follows current membership.
    _, other = create(client, app, another=True)
    existing = app.state.incident_service.require(incident).model_dump(mode="json")
    app.state.incident_service.mutate("MERGE", correction(existing, other), ADMIN)
    assert service.repository.requests(citizen)["items"] == []
    with pytest.raises(IncidentError):
        service.repository.evidence(incident, result["attemptId"], image["imageId"], citizen)


@pytest.mark.parametrize(
    "upload,status",
    [
        (Upload(b"not image", "repair.txt", "text/plain"), 415),
        (Upload(b"corrupt", "repair.jpg", "image/jpeg"), 422),
        (Upload(b"x" * 1572865, "repair.jpg", "image/jpeg"), 413),
        (Upload(b"x", "../repair.jpg", "image/jpeg"), 422),
    ],
)
def test_repair_image_validation(complaint_app, complaint_client, upload, status):
    incident, officer, _, payload = prepared(complaint_app, complaint_client)
    with pytest.raises(HTTPException) as error:
        complaint_app.state.civic_intelligence_service.upload_action(
            "submit", incident, payload, officer, [upload]
        )
    assert error.value.status_code == status
    with complaint_app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM repair_attempts").fetchone()[0] == 0


def test_submission_race_has_one_attempt(complaint_app, complaint_client):
    incident, officer, _, payload = prepared(complaint_app, complaint_client)
    service = complaint_app.state.civic_intelligence_service

    def submit(_):
        try:
            return service.upload_action(
                "submit", incident, payload | {"operationId": str(uuid4())}, officer, []
            )["attemptId"]
        except IncidentError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(submit, range(2)))
    assert values.count("CONFLICT") == 1


def test_dispute_racing_approval_is_version_fenced(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    attempt = service.upload_action("submit", incident, payload, officer, [])
    reviewer = admin(app, client)
    detail = service.repository.detail(attempt["attemptId"], reviewer)
    request = service.repository.requests(citizen)["items"][0]
    service.upload_action(
        "respond",
        request["requestId"],
        {
            "operationId": str(uuid4()),
            "expectedVersion": 1,
            "result": "STILL_BROKEN",
            "feedback": "The original dangerous hole remains visible.",
        },
        citizen,
        [],
    )
    with pytest.raises(IncidentError):
        service.decision(attempt["attemptId"], "approve", decision(detail), reviewer)
    assert app.state.incident_service.require(incident).status == "OPEN"


def test_reassignment_invalidates_officer_submission_and_old_approval(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    incident, officer, _, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    attempt = service.upload_action("submit", incident, payload, officer, [])
    reviewer = admin(app, client)
    work = app.state.work_service.repository
    work.assign(incident, "UNASSIGN", action(work, incident), Actor(reviewer["id"], "ADMIN"))
    with pytest.raises(IncidentError):
        service.decision(
            attempt["attemptId"],
            "approve",
            decision(service.repository.detail(attempt["attemptId"], reviewer)),
            reviewer,
        )
    with pytest.raises(IncidentError):
        service.upload_action(
            "submit", incident, payload | {"operationId": str(uuid4())}, officer, []
        )


def test_rework_new_attempt_retains_previous_vote_and_audit(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    first = service.upload_action("submit", incident, payload, officer, [])
    reviewer = admin(app, client)
    service.decision(
        first["attemptId"],
        "request-rework",
        decision(service.repository.detail(first["attemptId"], reviewer)),
        reviewer,
    )
    state = app.state.work_service.detail(incident)
    payload.update(
        operationId=str(uuid4()), expectedAssignmentVersion=state["assignment"]["version"]
    )
    second = service.upload_action("submit", incident, payload, officer, [])
    assert first["attemptId"] != second["attemptId"]
    rows = service.repository.attempts(incident, reviewer)["items"]
    assert [r["cycle"] for r in rows] == [2, 1]
    assert rows[1]["state"] == "REWORK_REQUIRED"


def test_three_citizens_two_confirm_one_dispute_no_majority_closure(
    complaint_app, complaint_client
):
    app, client = complaint_app, complaint_client
    incident, officer, first, payload = prepared(app, client)
    department = app.state.work_service.detail(incident)["assignment"]["departmentId"]
    citizens = [first]
    target = app.state.incident_service.require(incident).model_dump(mode="json")
    for _ in range(2):
        report, source = create(client, app, another=True)
        citizens.append({"id": report["citizenId"], "role": "CITIZEN"})
        target = app.state.incident_service.mutate("MERGE", correction(source, target), ADMIN)
    # P7 correctly suspended old allocation; administrator explicitly restores eligible allocation.
    work = app.state.work_service.repository
    work.assign(incident, "DEPARTMENT", action(work, incident, departmentId=department), ADMIN)
    work.assign(incident, "OFFICER", action(work, incident, officerId=officer["id"]), ADMIN)
    state = work.detail(incident)
    work.progress(
        incident,
        "START",
        ProgressAction.model_validate(
            common(
                expectedIncidentVersion=state["incidentVersion"],
                expectedAssignmentVersion=state["assignment"]["version"],
                percentage=0,
                note="Starting corrected canonical repair",
            )
        ).model_dump(mode="json"),
        Actor(officer["id"], "OFFICER"),
    )
    state = work.detail(incident)
    payload.update(
        expectedIncidentVersion=state["incidentVersion"],
        expectedAssignmentVersion=state["assignment"]["version"],
        repairedAt=datetime.now(UTC).isoformat(),
    )
    service = app.state.civic_intelligence_service
    attempt = service.upload_action("submit", incident, payload, officer, [])
    for i, citizen in enumerate(citizens):
        request = service.repository.requests(citizen)["items"][0]
        service.upload_action(
            "respond",
            request["requestId"],
            {
                "operationId": str(uuid4()),
                "expectedVersion": request["version"],
                "result": "STILL_BROKEN" if i == 2 else "CONFIRMED_FIXED",
                "feedback": "Independent account observation",
            },
            citizen,
            [],
        )
    reviewer = admin(app, client)
    detail = service.repository.detail(attempt["attemptId"], reviewer)
    assert detail["responses"] == {"CONFIRMED_FIXED": 2, "STILL_BROKEN": 1, "UNSURE": 0}
    assert detail["recommendation"] == "DISPUTE_REQUIRES_REVIEW"
    assert app.state.incident_service.require(incident).status == "OPEN"


def test_restart_migration_notifications_and_foreign_keys(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    result = service.upload_action("submit", incident, payload, officer, [])
    reviewer = admin(app, client)
    request = service.repository.requests(citizen)["items"][0]
    service.upload_action(
        "respond",
        request["requestId"],
        {
            "operationId": str(uuid4()),
            "expectedVersion": 1,
            "result": "UNSURE",
            "feedback": "Unable to visit the site yet",
        },
        citizen,
        [],
    )
    before = service.repository.detail(result["attemptId"], reviewer)
    restarted = create_app(app.state.settings)
    with TestClient(restarted, base_url="http://localhost:8000", headers=ORIGIN):
        repo = restarted.state.civic_intelligence_service.repository
        assert repo.detail(result["attemptId"], reviewer)["responses"] == before["responses"]
        restarted.state.auth_service.store.initialize()
        # Deliver same versioned event twice through existing receipt-safe notification path.
        from app.events.schema import Event

        events = restarted.state.workflow_service.repository
        with repo.store.connection() as db:
            row = db.execute(
                "SELECT * FROM event_outbox WHERE event_type='RepairVerificationRequested'"
            ).fetchone()
            event = events.envelope(dict(row))
        restarted.state.workflow_service.notify(Event.parse(event.model_dump(mode="json")))
        restarted.state.workflow_service.notify(event)
        notifications = events.notifications(citizen["id"])["items"]
        assert sum(n["type"] == "REPAIR_VERIFICATION_UPDATE" for n in notifications) == 1
        from app.events.schema import new_event

        restarted.state.workflow_service.notify(
            new_event(
                "RepairVerificationResponded", incident, payload={"attemptId": result["attemptId"]}
            )
        )
        assert (
            sum(
                n["type"] == "REPAIR_VERIFICATION_UPDATE"
                for n in events.notifications(citizen["id"])["items"]
            )
            == 1
        )
        with repo.store.connection() as db:
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_evidence_commit_rolls_back_and_cleans_staging(complaint_app, complaint_client):
    incident, officer, _, payload = prepared(complaint_app, complaint_client)
    service = complaint_app.state.civic_intelligence_service
    with service.repository.store.connection() as db:
        db.execute(
            "CREATE TRIGGER abort_repair_audit BEFORE INSERT ON civic_intelligence_audit "
            "BEGIN SELECT RAISE(ABORT,'Injected fixture rollback'); END"
        )
    with pytest.raises(IncidentError) as error:
        service.upload_action(
            "submit", incident, payload, officer, [Upload(image_bytes(), "repair.png", "image/png")]
        )
    assert error.value.status == 409
    with service.repository.store.connection() as db:
        assert db.execute("SELECT count(*) FROM repair_attempts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM repair_evidence").fetchone()[0] == 0
    assert not list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))


def test_collision_never_deletes_existing_object(complaint_app, complaint_client, monkeypatch):
    from app.integrations.storage.base import StorageCollision

    incident, officer, _, payload = prepared(complaint_app, complaint_client)
    service = complaint_app.state.civic_intelligence_service
    deleted = []

    def collision(*_):
        raise StorageCollision("Synthetic existing key")

    monkeypatch.setattr(service.complaints.storage, "put", collision)
    monkeypatch.setattr(service.complaints.storage, "delete", deleted.append)
    with pytest.raises(IncidentError) as error:
        service.upload_action(
            "submit", incident, payload, officer, [Upload(image_bytes(), "repair.png", "image/png")]
        )
    assert error.value.status == 503 and deleted == []


def test_repair_requires_in_progress_work_and_current_version(complaint_app, complaint_client):
    incident, officer, _, payload = prepared(complaint_app, complaint_client)
    service = complaint_app.state.civic_intelligence_service
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incident_assignments SET status='OFFICER_ASSIGNED' WHERE incident_id=?",
            (incident,),
        )
    with pytest.raises(IncidentError) as error:
        service.upload_action("submit", incident, payload, officer, [])
    assert error.value.status == 409
