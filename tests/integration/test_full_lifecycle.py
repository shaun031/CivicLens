"""Real HTTP contracts + durable local worker across app restarts; no service mocks."""

import io
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.scripts.audit_local_data import audit

PASSWORD = "Isolated phase thirteen journey passphrase 2048"
ORIGIN = {"Origin": "http://localhost:5173"}


def action(**extra):
    return {
        "operationId": str(uuid4()),
        "confirmed": True,
        "reason": "Trusted synthetic reviewer independently inspected current evidence",
        **extra,
    }


def drain(app):
    for _ in range(40):
        if not any(app.state.workflow_service.batch(100).values()):
            break
    with app.state.auth_service.store.connection() as db:
        assert (
            db.execute("SELECT count(*) FROM event_outbox WHERE status!='DISPATCHED'").fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT count(*) FROM event_queue WHERE state!='COMPLETE'").fetchone()[0]
            == 0
        )


def test_real_http_repair_lifecycle_worker_restart_private_evidence_and_recurrence(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        debug=False,
        log_level="ERROR",
        local_db_path=tmp_path / "journey.db",
        local_evidence_root=tmp_path / "private",
    )
    app = create_app(settings)
    image = io.BytesIO()
    Image.new("RGB", (40, 20), "blue").save(image, "PNG")
    photo = image.getvalue()
    with TestClient(app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        # Only staff provisioning bypasses public registration; business changes use HTTP.
        for email, role in (
            ("admin@example.com", Role.ADMIN),
            ("officer@example.com", Role.OFFICER),
        ):
            user = app.state.auth_service.register(
                RegisterInput(
                    display_name="Trusted Test Staff",
                    email=email,
                    password=PASSWORD,
                    confirm_password=PASSWORD,
                ),
                role,
            )
            if role == Role.OFFICER:
                officer_id = user.id
        assert (
            client.post(
                "/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        assert client.post("/api/admin/departments/seed", json=action()).status_code == 200
        assert client.post("/api/auth/logout").status_code == 204
        citizen = client.post(
            "/api/auth/register",
            json={
                "display_name": "Journey Citizen",
                "email": "citizen@example.com",
                "password": PASSWORD,
                "confirm_password": PASSWORD,
            },
        )
        assert citizen.status_code == 201
        assert (
            client.post(
                "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        fields = {
            "title": "Physical pothole beside the community library",
            "description": "The physical pothole obstructs the road beside the library entrance.",
            "category": "POTHOLE",
            "reportedSeverity": "HIGH",
            "latitude": "12.9716",
            "longitude": "77.5946",
        }

        def submit():
            response = client.post(
                "/api/complaints",
                headers={"Idempotency-Key": str(uuid4())},
                files=[(k, (None, v)) for k, v in fields.items()]
                + [("images", ("private.png", photo, "image/png"))],
            )
            assert response.status_code == 201, response.text
            return response.json()

        report = submit()
        duplicate_report = submit()
        private_url = "/api" + report["images"][0]["url"]
        assert client.get(private_url).status_code == 200
        assert client.get("/api/complaints", params={"q": "library"}).json()["items"]
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get(private_url).status_code == 401
    # Complaint/outbox survive fresh app construction, rather than injecting a singleton incident.
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        drain(app)

        def login(email):
            response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
            assert response.status_code == 200, response.text

        login("citizen@example.com")
        persisted = client.get(f"/api/complaints/{report['complaintId']}").json()
        incident_id = persisted["incidentId"]
        assert incident_id
        assert client.get("/api/notifications").json()["items"]
        login("admin@example.com")
        duplicate_id = client.get(f"/api/complaints/{duplicate_report['complaintId']}")
        assert duplicate_id.status_code == 403  # ADMIN uses its dedicated inspection APIs.
        candidates = client.get("/api/admin/duplicate-candidates").json()["items"]
        assert len(candidates) == 1
        candidate = candidates[0]["candidateId"]
        comparison = client.get(f"/api/admin/duplicate-candidates/{candidate}")
        assert comparison.status_code == 200 and len(comparison.json()["complaints"]) == 2
        assert (
            client.post(f"/api/admin/duplicate-candidates/{candidate}/reviewed").status_code == 200
        )
        first = client.get(f"/api/admin/incidents/{incident_id}").json()
        other = next(
            item["incident"]
            for item in comparison.json()["complaints"]
            if item["incident"]["incidentId"] != incident_id
        )
        merged = client.post(
            "/api/admin/incidents/merge",
            json=action(
                sourceIncidentId=other["incidentId"],
                expectedSourceVersion=other["version"],
                targetIncidentId=incident_id,
                expectedTargetVersion=first["version"],
                physicalIssueConfirmed=True,
            ),
        )
        assert merged.status_code == 200, merged.text
        assert merged.json()["totalComplaintCount"] == 2
        assert merged.json()["uniqueReporterCount"] == 1
        assert client.post("/api/admin/departments/seed", json=action()).status_code == 200
        drain(app)
        allocation = client.get(f"/api/admin/incidents/{incident_id}/assignment").json()
        assert allocation["assignment"]["status"] == "NEEDS_REVIEW"
        assert allocation["assignment"]["method"] == "REVIEW_LOCK"
        department_id = allocation["suggestedRouting"]["departmentId"]
        assert department_id
        # Membership corrections deliberately suspend allocation; ADMIN reviews it explicitly.
        restored = client.post(
            f"/api/admin/incidents/{incident_id}/assign-department",
            json=action(
                expectedIncidentVersion=allocation["incidentVersion"],
                expectedAssignmentVersion=allocation["assignment"]["version"],
                departmentId=department_id,
                review=True,
            ),
        )
        assert restored.status_code == 200, restored.text
        allocation = client.get(f"/api/admin/incidents/{incident_id}/assignment").json()
        assert (
            client.post(
                f"/api/admin/departments/{department_id}/officers",
                json=action(expectedVersion=0, officerId=officer_id, capacity=20),
            ).status_code
            == 200
        )
        assigned = client.post(
            f"/api/admin/incidents/{incident_id}/assign-officer",
            json=action(
                expectedIncidentVersion=allocation["incidentVersion"],
                expectedAssignmentVersion=allocation["assignment"]["version"],
                officerId=officer_id,
            ),
        )
        assert assigned.status_code == 200, assigned.text
        login("officer@example.com")
        work = client.get(f"/api/officer/incidents/{incident_id}").json()
        start = client.post(
            f"/api/officer/incidents/{incident_id}/start",
            json=action(
                expectedIncidentVersion=work["incidentVersion"],
                expectedAssignmentVersion=work["assignment"]["version"],
                note="Field crew inspected the physical pothole before repair",
                percentage=10,
            ),
        )
        assert start.status_code == 200, start.text
        work = client.get(f"/api/officer/incidents/{incident_id}").json()
        submission = {
            "operationId": str(uuid4()),
            "expectedIncidentVersion": work["incidentVersion"],
            "expectedAssignmentVersion": work["assignment"]["version"],
            "description": "Physical pothole repaired and inspected at the original location.",
            "notes": "Private officer-only operational context",
            "repairedAt": datetime.now(UTC).isoformat(),
        }
        repair = client.post(
            f"/api/officer/incidents/{incident_id}/repair-attempts",
            files=[
                ("payload", (None, json.dumps(submission))),
                ("images", ("repair.png", photo, "image/png")),
            ],
        )
        assert repair.status_code == 201, repair.text
        attempt_id = repair.json()["attemptId"]
        assert client.get("/api/admin/repairs/pending").status_code == 403
        login("citizen@example.com")
        request = client.get("/api/citizen/verification-requests").json()["items"][0]
        assert not request["images"] and "notes" not in request
        feedback = client.post(
            f"/api/citizen/verification-requests/{request['requestId']}/respond",
            json={
                "operationId": str(uuid4()),
                "expectedVersion": request["version"],
                "result": "CONFIRMED_FIXED",
                "feedback": "Road surface looks repaired.",
            },
        )
        assert feedback.status_code == 200, feedback.text
        login("admin@example.com")
        detail = client.get(f"/api/admin/repairs/{attempt_id}").json()
        assert detail["incidentStatus"] == "OPEN"
        payload = action(
            expectedVersion=detail["version"],
            expectedIncidentVersion=detail["incidentVersion"],
            approvedEvidenceIds=[],
        )
        approved = client.post(f"/api/admin/repairs/{attempt_id}/approve", json=payload)
        assert approved.status_code == 200, approved.text
        assert (
            client.post(f"/api/admin/repairs/{attempt_id}/approve", json=payload).json()
            == approved.json()
        )
        assert client.get(f"/api/admin/incidents/{incident_id}").json()["status"] == "RESOLVED"
        drain(app)
        assert client.get("/api/admin/analytics/overview").status_code == 200
        assert client.get("/api/admin/analytics/fairness").status_code == 200
        # A genuinely later report belongs to a NEW cycle. Worker suggests, never merges history.
        login("citizen@example.com")
        response = client.post(
            "/api/complaints",
            headers={"Idempotency-Key": str(uuid4())},
            files=[(k, (None, v)) for k, v in fields.items()],
        )
        assert response.status_code == 201, response.text
        new_report = response.json()
        drain(app)
        new_id = client.get(f"/api/complaints/{new_report['complaintId']}").json()["incidentId"]
        assert new_id and new_id != incident_id
        login("admin@example.com")
        links = client.get("/api/admin/recurrences").json()["items"]
        assert any(
            v["previousIncidentId"] == incident_id and v["newIncidentId"] == new_id for v in links
        )
        assert client.get(f"/api/admin/incidents/{incident_id}/assignment-history").json()["items"]
        login("citizen@example.com")
        notifications = client.get(
            "/api/notifications", params={"type": "REPAIR_VERIFICATION_UPDATE"}
        )
        assert notifications.status_code == 200 and notifications.json()["items"]
    assert audit(settings.local_db_path)["status"] == "PASS"
