from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_complaints import PASSWORD, fields, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import login_staff
from test_work_allocation import action, common, setup

from app.algorithms.recurrence import evaluate
from app.analytics.fairness import compare_areas
from app.analytics.filters import AnalyticsFilters
from app.models.incident import Actor, IncidentError
from app.schemas.work import ProgressAction


def prepared(app, client):
    repo, incident, department, officer, email = setup(app, client)
    repo.assign(
        incident,
        "OFFICER",
        action(repo, incident, officerId=officer),
        Actor("trusted-test-admin", "ADMIN"),
    )
    state = repo.detail(incident)
    progress = ProgressAction.model_validate(
        common(
            expectedIncidentVersion=state["incidentVersion"],
            expectedAssignmentVersion=state["assignment"]["version"],
            percentage=0,
            note="Starting repair inspection",
        )
    )
    repo.progress(incident, "START", progress.model_dump(mode="json"), Actor(officer, "OFFICER"))
    state = repo.detail(incident)
    citizen = client.get("/api/auth/me").json()["id"]
    data = {
        "operationId": str(uuid4()),
        "expectedIncidentVersion": state["incidentVersion"],
        "expectedAssignmentVersion": state["assignment"]["version"],
        "description": "Repair completed and inspected at the original reported location.",
        "notes": "Internal officer notes remain private.",
        "repairedAt": datetime.now(UTC).isoformat(),
    }
    return incident, {"id": officer, "role": "OFFICER"}, {"id": citizen, "role": "CITIZEN"}, data


def admin(app, client):
    login_staff(app, client)
    user = client.get("/api/auth/me").json()
    return {"id": user["id"], "role": "ADMIN"}


def decision(detail, **extra):
    return {
        "operationId": str(uuid4()),
        "expectedVersion": detail["version"],
        "expectedIncidentVersion": detail["incidentVersion"],
        "confirmed": True,
        "reason": (
            "Independent administrator site inspection verified the "
            "actual physical repair and reviewed all available feedback."
        ),
        "approvedEvidenceIds": [],
        **extra,
    }


def test_repair_full_cycle_and_reopening(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, data = prepared(app, client)
    service = app.state.civic_intelligence_service
    result = service.upload_action("submit", incident, data, officer, [])
    assert service.upload_action("submit", incident, data, officer, []) == result
    assert app.state.incident_service.repository.load(incident).status == "OPEN"
    requests = service.repository.requests(citizen)["items"]
    assert len(requests) == 1 and requests[0]["canRespond"]
    response = {
        "operationId": str(uuid4()),
        "expectedVersion": 1,
        "result": "CONFIRMED_FIXED",
        "feedback": "Road looks repaired.",
    }
    service.upload_action("respond", requests[0]["requestId"], response, citizen, [])
    assert app.state.incident_service.repository.load(incident).status == "OPEN"
    reviewer = admin(app, client)
    detail = service.repository.detail(result["attemptId"], reviewer)
    assert detail["recommendation"] == "CONFIRMATION_SUPPORT"
    payload = decision(detail)
    approved = service.decision(result["attemptId"], "approve", payload, reviewer)
    assert service.decision(result["attemptId"], "approve", payload, reviewer) == approved
    assert app.state.incident_service.repository.load(incident).status == "RESOLVED"
    fairness = service.fairness(AnalyticsFilters())
    assert fairness["areas"][0]["verifiedResolutionRate"] == 1
    assert fairness["areas"][0]["verifiedResolutions"] == 1
    detail = service.repository.detail(result["attemptId"], reviewer)
    service.decision(result["attemptId"], "reopen", decision(detail), reviewer)
    assert app.state.incident_service.repository.load(incident).status == "OPEN"
    assert service.repository.detail(result["attemptId"], reviewer)["state"] == "REOPENED"
    assert app.state.work_service.detail(incident)["assignment"]["status"] == "NEEDS_REVIEW"
    assert not app.state.priority_service.detail(incident)["stale"]
    with app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM repair_verifications").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT count(*) FROM event_outbox WHERE event_type='IncidentVerifiedResolved'"
            ).fetchone()[0]
            == 1
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("answer", ["CONFIRMED_FIXED", "STILL_BROKEN", "UNSURE"])
def test_answers_do_not_resolve_and_duplicates_rejected(complaint_app, complaint_client, answer):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, data = prepared(app, client)
    service = app.state.civic_intelligence_service
    result = service.upload_action("submit", incident, data, officer, [])
    request = service.repository.requests(citizen)["items"][0]
    payload = {"operationId": str(uuid4()), "expectedVersion": 1, "result": answer, "feedback": ""}
    one = service.upload_action("respond", request["requestId"], payload, citizen, [])
    assert service.upload_action("respond", request["requestId"], payload, citizen, []) == one
    payload.update(operationId=str(uuid4()), expectedVersion=2)
    with pytest.raises(IncidentError):
        service.upload_action("respond", request["requestId"], payload, citizen, [])
    reviewer = admin(app, client)
    detail = service.repository.detail(result["attemptId"], reviewer)
    assert detail["responses"][answer] == 1
    assert app.state.incident_service.repository.load(incident).status == "OPEN"
    if answer == "STILL_BROKEN":
        assert detail["recommendation"] == "DISPUTE_REQUIRES_REVIEW"
        service.decision(result["attemptId"], "request-rework", decision(detail), reviewer)
        assert app.state.incident_service.repository.load(incident).status == "OPEN"


def test_concurrent_admin_decisions_only_one_wins(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, data = prepared(app, client)
    service = app.state.civic_intelligence_service
    result = service.upload_action("submit", incident, data, officer, [])
    reviewer = admin(app, client)
    detail = service.repository.detail(result["attemptId"], reviewer)

    def run(_):
        try:
            return service.decision(result["attemptId"], "approve", decision(detail), reviewer)[
                "state"
            ]
        except IncidentError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ["CONFLICT", "VERIFIED_RESOLVED"]


def test_officer_http_submission_and_authorization(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, data = prepared(app, client)
    assert (
        client.post(f"/api/officer/incidents/{incident}/repair-attempts", json=data).status_code
        == 403
    )
    with app.state.auth_service.store.connection() as db:
        email = db.execute("SELECT email FROM users WHERE id=?", (officer["id"],)).fetchone()[0]
    client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    response = client.post(f"/api/officer/incidents/{incident}/repair-attempts", json=data)
    assert response.status_code == 201, response.text
    assert client.get("/api/admin/repairs/pending").status_code == 403
    assert client.get("/api/admin/analytics/fairness").status_code == 403


def test_recurrence_requires_verified_resolution_and_review(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    incident, officer, citizen, data = prepared(app, client)
    service = app.state.civic_intelligence_service
    attempt = service.upload_action("submit", incident, data, officer, [])
    reviewer = admin(app, client)
    detail = service.repository.detail(attempt["attemptId"], reviewer)
    service.decision(attempt["attemptId"], "approve", decision(detail), reviewer)
    # Independent account and P7 singleton; never force a duplicate merge.
    email = f"recurrence-{uuid4()}@example.com"
    client.post(
        "/api/auth/register",
        json={
            "display_name": "New Reporter",
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    report = submit(client, fields()).json()
    current = app.state.incident_service.ensure_singleton(report["complaintId"])["incidentId"]
    result = service.check_recurrence(current, {"operationId": str(uuid4())}, reviewer)
    assert len(result["recurrenceIds"]) == 1
    recurrence = service.repository.recurrence_detail(result["recurrenceIds"][0])
    assert (
        recurrence["newReportedAt"] == app.state.incident_service.require(current).firstReportedAt
    )
    assert recurrence["state"] == "POTENTIAL_RECURRENCE"
    with pytest.raises(IncidentError):
        service.repository.review_recurrence(
            recurrence["recurrenceId"],
            "confirm",
            {
                "operationId": str(uuid4()),
                "expectedVersion": 1,
                "reason": "Reviewed actual infrastructure identity",
                "physicalIdentityConfirmed": False,
            },
            reviewer,
        )
    service.repository.review_recurrence(
        recurrence["recurrenceId"],
        "confirm",
        {
            "operationId": str(uuid4()),
            "expectedVersion": 1,
            "reason": "Reviewed actual infrastructure identity",
            "physicalIdentityConfirmed": True,
        },
        reviewer,
    )
    assert app.state.incident_service.repository.load(current).status == "OPEN"
    assert app.state.incident_service.repository.load(incident).status == "RESOLVED"
    fairness = service.fairness(AnalyticsFilters())
    assert sum(area["confirmedRecurrenceIncidents"] for area in fairness["areas"]) == 1
    assert fairness["areas"][0]["verifiedResolutionRate"] == 0.5


@pytest.mark.parametrize(
    "delta,category,offset,eligible",
    [
        (1, "POTHOLE", 0, True),
        (-1, "POTHOLE", 0, False),
        (0, "POTHOLE", 0, False),
        (1, "GARBAGE", 0, False),
        (1, "POTHOLE", 1, False),
    ],
)
def test_recurrence_safeguards(delta, category, offset, eligible):
    at = datetime(2026, 1, 1, tzinfo=UTC)
    previous = {
        "canonical_title": "Large pothole near college entrance",
        "canonical_description": "Dangerous pothole damages road near entrance",
        "latitude": 12.0,
        "longitude": 77.0,
        "category": "POTHOLE",
    }
    current = previous | {
        "created_at": (at + timedelta(days=delta)).isoformat(),
        "category": category,
        "latitude": 12.0 + offset,
    }
    result = evaluate(previous, current, at.isoformat())
    assert result["eligible"] == eligible
    assert 0 <= result["score"] <= 1
    assert result["state"] != "CONFIRMED_RECURRENCE"


def fairness_row(identity, lat, response=24, overdue=False):
    return {
        "incident_id": identity,
        "latitude": lat,
        "longitude": 77.0,
        "status": "OPEN",
        "sla": {"RESOLUTION": "MISSED"},
        "workStartHours": response,
        "ageDays": 10,
        "overdue": overdue,
        "band": "HIGH",
        "department_id": "dept",
        "resolved_at": None,
    }


def test_fairness_denominators_and_small_samples():
    from app.schemas.civic_intelligence import FairnessReview

    # A valid clipped edge cell may have its un-clipped origin below -90/-180.
    edge = FairnessReview.model_validate(
        {
            "operationId": str(uuid4()),
            "areaId": "grid:0.007:-12858:-25715",
            "state": "UNDER_ADMIN_REVIEW",
            "notes": "Review valid clipped polar grid boundary",
            "context": {},
        }
    )
    assert edge.areaId == "grid:0.007:-12858:-25715"
    rows = [fairness_row(str(i), 12.0, 24, False) for i in range(10)] + [
        fairness_row(str(i + 10), 12.1, 96, True) for i in range(10)
    ]
    result = compare_areas(rows, {"repairs": [], "recurrences": []}, 0.01)
    assert len(result["areas"]) == 2
    assert result["areas"][1]["status"] == "POTENTIAL_SERVICE_DISPARITY"
    assert result["areas"][1]["overdueRate"] == 1
    assert result["areas"][0]["verifiedResolutionRate"] == 0
    small = compare_areas(rows[:1], {"repairs": [], "recurrences": []}, 0.01)
    assert small["areas"][0]["status"] == "INSUFFICIENT_DATA"
    assert "discrimination" in " ".join(result["limitations"])


def test_fairness_http_reports_and_review_persistence(complaint_app, complaint_client):
    app, client = complaint_app, complaint_client
    prepared(app, client)
    admin(app, client)
    value = client.get("/api/admin/analytics/fairness")
    assert value.status_code == 200, value.text
    assert value.json()["areas"][0]["status"] == "INSUFFICIENT_DATA"
    for kind in (
        "geographic-service-comparison",
        "sla-disparity",
        "unresolved-backlog-distribution",
        "recurring-infrastructure-failures",
        "repair-verification-outcomes",
    ):
        response = client.get("/api/admin/analytics/reports/" + kind)
        assert response.status_code == 200, response.text
        response = client.post("/api/admin/analytics/reports/" + kind + "/csv")
        assert response.status_code == 200, response.text
    payload = {
        "operationId": str(uuid4()),
        "expectedVersion": 0,
        "areaId": value.json()["areas"][0]["areaId"],
        "context": {},
        "state": "UNDER_ADMIN_REVIEW",
        "notes": "Investigate coverage and missing observations",
    }
    response = client.post("/api/admin/analytics/fairness/reviews", json=payload)
    assert response.status_code == 201, response.text
    assert (
        client.get("/api/admin/analytics/fairness/reviews").json()["items"][0]["notes"]
        == payload["notes"]
    )


def test_fairness_compare_uses_real_filters_and_rejects_invalid_area(
    complaint_app, complaint_client
):
    from test_incidents import create

    app, client = complaint_app, complaint_client
    create(client, app, latitude="12.95")
    create(client, app, latitude="12.99")
    admin(app, client)
    areas = client.get("/api/admin/analytics/fairness").json()["areas"]
    assert len(areas) == 2
    result = client.get(
        "/api/admin/analytics/fairness/compare",
        params={"first": areas[0]["areaId"], "second": areas[1]["areaId"], "category": "POTHOLE"},
    )
    assert result.status_code == 200, result.text
    assert len(result.json()["areas"]) == 2
    result = client.get(
        "/api/admin/analytics/fairness/compare",
        params={"first": areas[0]["areaId"], "second": areas[0]["areaId"]},
    )
    assert result.status_code == 422
    result = client.post(
        "/api/admin/analytics/fairness/reviews",
        json={
            "operationId": str(uuid4()),
            "expectedVersion": 0,
            "areaId": "grid:nan:0:0",
            "state": "UNDER_ADMIN_REVIEW",
            "notes": "Invalid grid identity must not be accepted",
            "context": {},
        },
    )
    assert result.status_code == 422
