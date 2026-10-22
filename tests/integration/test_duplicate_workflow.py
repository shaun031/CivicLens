"""Real HTTP, automatic local worker, private cross-owner matching and process restart."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.models.incident import Actor
from app.models.user import Role
from app.repositories.work_repository import SQLiteWork
from app.schemas.auth import RegisterInput
from app.services.auth_service import AuthService

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_automatic_private_matching_review_and_process_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    settings = Settings(
        _env_file=None,
        app_env="local",
        debug=False,
        local_db_path=tmp_path / "phase6.db",
        local_evidence_root=tmp_path / "evidence",
    )
    auth = AuthService(settings)
    auth.store.initialize()
    password = f"Phase six integration secure passphrase {uuid4()}"
    admin = f"admin-{uuid4()}@example.com"
    auth.register(
        RegisterInput(
            display_name="Trusted Test Administrator",
            email=admin,
            password=password,
            confirm_password=password,
        ),
        Role.ADMIN,
    )
    officer_email = f"officer-{uuid4()}@example.com"
    officer = auth.register(
        RegisterInput(
            display_name="Integration Field Officer",
            email=officer_email,
            password=password,
            confirm_password=password,
        ),
        Role.OFFICER,
    )
    work = SQLiteWork(auth.store, "fixture", settings)

    def work_action(**extra):
        return {
            "operationId": str(uuid4()),
            "confirmed": True,
            "reason": "Trusted integration inspection and municipal allocation decision",
            **extra,
        }

    work.seed(work_action(), Actor("trusted-integration-admin", "ADMIN"))
    department = next(d for d in work.departments()["items"] if d["code"] == "ROAD_MAINTENANCE")
    work.save_membership(
        department["id"],
        work_action(
            expectedVersion=0,
            officerId=officer.id,
            active=True,
            availability="AVAILABLE",
            capacity=20,
            areas=[],
        ),
        Actor("trusted-integration-admin", "ADMIN"),
    )
    environment = os.environ | {
        "APP_ENV": "local",
        "AUTH_PROVIDER": "local",
        "DEBUG": "false",
        "LOCAL_DB_PATH": str(settings.local_db_path),
        "LOCAL_EVIDENCE_ROOT": str(settings.local_evidence_root),
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "MATCHING_WORKER_ENABLED": "true",
        "CORS_ORIGINS": "http://localhost:5173",
        "LOG_LEVEL": "ERROR",
    }
    process = None

    def start():
        nonlocal process
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            assert process.poll() is None
            try:
                if httpx.get(f"http://localhost:{port}/api/health", timeout=0.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("Isolated Phase 6 server did not start")

    def stop():
        nonlocal process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process = None

    def login(client, email):
        assert (
            client.post("/api/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )

    def citizen(client):
        email = f"citizen-{uuid4()}@example.com"
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "display_name": "Synthetic Citizen",
                    "email": email,
                    "password": password,
                    "confirm_password": password,
                },
            ).status_code
            == 201
        )
        login(client, email)

    def submit(client, title, latitude="12.97", category="POTHOLE"):
        fields = {
            "title": title,
            "description": title + " Dangerous road traffic needs inspection.",
            "category": category,
            "reportedSeverity": "HIGH",
            "latitude": latitude,
            "longitude": "77.59",
        }
        response = client.post(
            "/api/complaints",
            files=[(key, (None, value)) for key, value in fields.items()],
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        assert response.json()["incidentId"] is None
        return response.json()["complaintId"]

    origin = {"Origin": "http://localhost:5173"}
    try:
        start()
        with httpx.Client(
            base_url=f"http://localhost:{port}", headers=origin, timeout=30
        ) as client:
            citizen(client)
            first = submit(client, "Large pothole near college gate")
            client.post("/api/auth/logout")
            citizen(client)
            second = submit(client, "Big hole on road near university entrance", "12.97001")
            distinct = submit(client, "Large pothole near college gate", "12.97017")
            garbage = submit(client, "Garbage beside college gate entrance", "12.97001", "GARBAGE")
            assert client.get(f"/api/complaints/{first}").status_code == 404
            assert client.get("/api/admin/duplicate-candidates").status_code == 403
            client.post("/api/auth/logout")
            login(client, admin)
            deadline = time.monotonic() + 30
            rows = []
            while time.monotonic() < deadline:
                response = client.get(f"/api/admin/complaints/{second}/duplicate-candidates")
                assert response.status_code == 200, response.text
                rows = response.json()["items"]
                if response.json()["processing"]["state"] == "COMPLETE" and rows:
                    break
                time.sleep(0.2)
            target = next(
                row
                for row in rows
                if {row["sourceComplaintId"], row["possibleDuplicateId"]} == {first, second}
            )
            assert target["imageScore"] is None and target["combinedScore"] > 0.6
            identity = target["candidateId"]
            assert (
                client.post(f"/api/admin/complaints/{distinct}/duplicate-check").status_code == 200
            )
            distinct_rows = client.get(
                f"/api/admin/complaints/{distinct}/duplicate-candidates"
            ).json()["items"]
            assert distinct_rows and all(
                row["classification"] != "STRONG_CANDIDATE" for row in distinct_rows
            )
            assert (
                client.post(f"/api/admin/complaints/{garbage}/duplicate-check").status_code == 200
            )
            assert (
                client.get(f"/api/admin/complaints/{garbage}/duplicate-candidates").json()["items"]
                == []
            )
            detail = client.get(f"/api/admin/duplicate-candidates/{identity}").json()
            memberships = [row["incidentId"] for row in detail["complaints"]]
            assert all(memberships) and len(set(memberships)) == 2
            assert (
                client.post(f"/api/admin/duplicate-candidates/{identity}/dismiss").json()[
                    "reviewStatus"
                ]
                == "DISMISSED"
            )
            source, destination = [row["incident"] for row in detail["complaints"]]
            merge = {
                "operationId": str(uuid4()),
                "sourceIncidentId": source["incidentId"],
                "expectedSourceVersion": source["version"],
                "targetIncidentId": destination["incidentId"],
                "expectedTargetVersion": destination["version"],
                "confirmed": True,
                "physicalIssueConfirmed": True,
                "reason": "Trusted administrator reviewed both physical reports",
            }
            merged_response = client.post("/api/admin/incidents/merge", json=merge)
            assert merged_response.status_code == 200, merged_response.text
            merged = merged_response.json()
            assert merged["totalComplaintCount"] == merged["uniqueReporterCount"] == 2

            def priority_change(method, suffix, extra):
                for _ in range(5):
                    state = client.get(
                        f"/api/admin/incidents/{merged['incidentId']}/priority"
                    ).json()
                    response = client.request(
                        method,
                        f"/api/admin/incidents/{merged['incidentId']}/{suffix}",
                        json={
                            "operationId": str(uuid4()),
                            "expectedIncidentVersion": state["incidentVersion"],
                            "expectedPriorityRevision": state["priorityRevision"],
                            "confirmed": True,
                            "reason": "Trusted administrator inspected current report evidence",
                            **extra,
                        },
                    )
                    if response.status_code != 409:
                        assert response.status_code == 200, response.text
                        return response.json()
                raise AssertionError("Priority inputs repeatedly conflicted")

            priority_change(
                "patch",
                "severity",
                {"score": 8, "status": "VERIFIED", "evidenceReferences": [first]},
            )
            priority_change(
                "patch",
                "public-impact",
                {"score": 7, "status": "VERIFIED", "evidenceReferences": [second]},
            )
            priority_change("post", "priority/override", {"score": 91})
            assessed = priority_change(
                "patch", "hazard-review", {"flag": True, "evidenceReferences": [first]}
            )
            assert assessed["priority"]["effectiveScore"] == 100
            assert assessed["priority"]["calculatedScore"] < 100
            # The real worker may finish a pending route after hazard/priority edits.
            # A 409 is the intended optimistic fence, not permission to remove it.
            # Re-read and explicitly retry a known-rejected operation; never retry other errors.
            for _ in range(5):
                assignment = client.get(
                    f"/api/admin/incidents/{merged['incidentId']}/assignment"
                ).json()
                assigned = client.post(
                    f"/api/admin/incidents/{merged['incidentId']}/reassign",
                    json=work_action(
                        expectedIncidentVersion=assignment["incidentVersion"],
                        expectedAssignmentVersion=assignment["assignment"]["version"],
                        departmentId=department["id"],
                        officerId=officer.id,
                    ),
                )
                if assigned.status_code != 409:
                    break
                time.sleep(0.05)
            assert assigned.status_code == 200, assigned.text
            login(client, officer_email)
            started = client.post(
                f"/api/officer/incidents/{merged['incidentId']}/start",
                json=work_action(
                    expectedIncidentVersion=assignment["incidentVersion"],
                    expectedAssignmentVersion=assigned.json()["version"],
                    percentage=20,
                    note="Field crew inspected the road and began authorized maintenance",
                    requestReview=False,
                ),
            )
            assert started.status_code == 200, started.text
        stop()
        start()
        with httpx.Client(
            base_url=f"http://localhost:{port}", headers=origin, timeout=30
        ) as client:
            login(client, admin)
            restored_assignment = client.get(
                f"/api/admin/incidents/{merged['incidentId']}/assignment"
            ).json()
            assert restored_assignment["assignment"]["status"] == "IN_PROGRESS"
            assert restored_assignment["assignment"]["officerId"] == officer.id
            assert restored_assignment["assignment"]["percentage"] == 20
            login(client, officer_email)
            officer_queue = client.get("/api/officer/incidents").json()
            assert any(row["incidentId"] == merged["incidentId"] for row in officer_queue["items"])
            assert client.get(f"/api/officer/incidents/{merged['incidentId']}/history").json()[
                "items"
            ][0]["after"]["note"]
            login(client, admin)
            assert client.post(f"/api/admin/complaints/{second}/duplicate-check").status_code == 200
            detail = client.get(f"/api/admin/duplicate-candidates/{identity}").json()
            assert detail["reviewStatus"] == "DISMISSED" and detail["candidateId"] == identity
            assert detail["explanation"] and detail["modelVersion"]
            persisted = client.get(f"/api/admin/incidents/{merged['incidentId']}/priority").json()
            assert persisted["controls"]["severity"]["score"] == 8
            assert persisted["controls"]["publicImpact"]["score"] == 7
            assert persisted["controls"]["override"]["score"] == 91
            assert persisted["priority"]["urgentHazard"]
            priority_history = client.get(
                f"/api/admin/incidents/{merged['incidentId']}/priority/history"
            ).json()
            assert {"SEVERITY", "PUBLIC_IMPACT", "OVERRIDE", "HAZARD"} <= {
                e["kind"] for e in priority_history["items"]
            }
            assert client.post("/api/admin/incidents/merge", json=merge).json() == merged
            alias = client.get(f"/api/admin/incidents/{source['incidentId']}").json()
            assert alias["incidentId"] == merged["incidentId"]
            split_response = client.post(
                f"/api/admin/incidents/{merged['incidentId']}/split",
                json={
                    "operationId": str(uuid4()),
                    "sourceIncidentId": merged["incidentId"],
                    "expectedSourceVersion": merged["version"],
                    "confirmed": True,
                    "reason": "Correcting the reviewed association while retaining every report",
                    "complaintIds": [first],
                },
            )
            assert split_response.status_code == 200, split_response.text
            assert split_response.json()["totalComplaintCount"] == 1
            corrected = priority_change("post", "priority/recalculate", {})
            assert corrected["priority"]["overrideStatus"] == "REVIEW_REQUIRED"
            assert not corrected["priority"]["urgentHazard"]
            assert corrected["priority"]["factors"]["reporters"]["rawValue"] == 1
            history = client.get(f"/api/admin/incidents/{merged['incidentId']}/history").json()
            assert {"MERGE", "SPLIT"} <= {event["operation"] for event in history["items"]}
            login(client, officer_email)
            assert client.get(f"/api/officer/incidents/{merged['incidentId']}").status_code == 404
        with auth.store.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 4
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM complaints WHERE incident_id IS NOT NULL"
                ).fetchone()[0]
                == 4
            )
            assert (
                db.execute("SELECT count(DISTINCT incident_id) FROM complaints").fetchone()[0] == 4
            )
            assert (
                db.execute("SELECT count(*) FROM complaints WHERE status='SUBMITTED'").fetchone()[0]
                == 4
            )
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM duplicate_candidates WHERE candidate_id=?", (identity,)
                ).fetchone()[0]
                == 1
            )
    finally:
        stop()
