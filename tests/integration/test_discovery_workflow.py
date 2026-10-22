"""Real HTTP, existing trusted admin provisioning, two citizens and an OS-process restart."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.services.auth_service import AuthService

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_search_publication_geography_and_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    database = tmp_path / "discovery.db"
    evidence = tmp_path / "private"
    settings = Settings(
        _env_file=None, app_env="test", local_db_path=database, local_evidence_root=evidence
    )
    service = AuthService(settings)
    service.store.initialize()
    password = f"Integration secure passphrase {uuid4()}"
    admin_email = f"admin-{uuid4()}@example.com"
    service.register(
        RegisterInput(
            display_name="Trusted Integration Admin",
            email=admin_email,
            password=password,
            confirm_password=password,
        ),
        Role.ADMIN,
    )
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "DEBUG": "false",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "LOCAL_DB_PATH": str(database),
        "LOCAL_EVIDENCE_ROOT": str(evidence),
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
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert process.poll() is None, "Isolated discovery API exited during startup"
            try:
                if httpx.get(f"http://localhost:{port}/api/health", timeout=0.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("Isolated discovery API did not start")

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

    def register(client, email):
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "display_name": "Integration Citizen",
                    "email": email,
                    "password": password,
                    "confirm_password": password,
                },
            ).status_code
            == 201
        )
        login(client, email)

    def login(client, email):
        assert (
            client.post("/api/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )

    def submit(client, index):
        fields = {
            "title": f"Road surface damage near market {index}",
            "description": "Private notes about damaged paving near a community market.",
            "category": "POTHOLE" if index < 2 else "DRAINAGE",
            "reportedSeverity": "HIGH",
            "latitude": "12.972",
            "longitude": "77.595",
        }
        response = client.post(
            "/api/complaints",
            files=[(key, (None, value)) for key, value in fields.items()],
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201, response.text
        return response.json()["complaintId"]

    region = {
        "minLatitude": 12.96,
        "maxLatitude": 12.99,
        "minLongitude": 77.58,
        "maxLongitude": 77.61,
    }
    first_email, other_email = (
        f"citizen-a-{uuid4()}@example.com",
        f"citizen-b-{uuid4()}@example.com",
    )
    try:
        start()
        with httpx.Client(
            base_url=f"http://localhost:{port}",
            headers={"Origin": "http://localhost:5173"},
            timeout=20,
        ) as client:
            register(client, first_email)
            ids = [submit(client, index) for index in range(3)]
            filters = {
                "q": "MARKET",
                "category": "POTHOLE",
                "status": "SUBMITTED",
                "reportedSeverity": "HIGH",
                "sortOrder": "asc",
                "limit": 1,
            }
            page = client.get("/api/complaints", params=filters).json()
            assert page["total"] == 2 and len(page["items"]) == 1 and page["nextCursor"]
            next_page = client.get(
                "/api/complaints", params=filters | {"cursor": page["nextCursor"]}
            ).json()
            assert next_page["items"][0]["complaintId"] != page["items"][0]["complaintId"]
            summary = client.get("/api/complaints/summary").json()
            assert summary["total"] == 3 and summary["counts"] == {"SUBMITTED": 3}
            assert sum(item["count"] for item in summary["byCategory"]) == 3
            client.post("/api/auth/logout")
            register(client, other_email)
            other_id = submit(client, 0)
            assert client.get(f"/api/complaints/{ids[0]}").status_code == 404
            assert client.get("/api/complaints/summary").json()["total"] == 1
            client.post("/api/auth/logout")
            login(client, first_email)
            assert client.get(f"/api/complaints/{other_id}").status_code == 404
            assert (
                client.patch(
                    f"/api/complaints/{ids[0]}/publication-request", json={"requested": True}
                ).status_code
                == 200
            )
            assert client.get("/api/public/issues", params=region).json()["items"] == []
            client.post("/api/auth/logout")
            login(client, admin_email)
            reviewed = client.patch(
                f"/api/admin/complaints/{ids[0]}/publication",
                json={
                    "decision": "APPROVE",
                    "publicSummary": "Reviewed paving damage near the community junction",
                    "publicLatitude": 12.972,
                    "publicLongitude": 77.595,
                    "reviewedForPrivacy": True,
                },
            )
            assert reviewed.status_code == 200, reviewed.text
            public_id = reviewed.json()["publicIssueId"]
            public = client.get("/api/public/issues", params=region).json()["items"]
            assert len(public) == 1 and "citizenId" not in public[0] and "images" not in public[0]
            nearby = client.get(
                "/api/public/issues/nearby",
                params={"latitude": 12.972, "longitude": 77.595, "radiusMeters": 250},
            ).json()["items"]
            assert len(nearby) == 1 and nearby[0]["distanceMeters"] == 0
            assert (
                client.patch(
                    f"/api/admin/complaints/{ids[0]}/publication", json={"decision": "UNPUBLISH"}
                ).status_code
                == 200
            )
            assert client.get("/api/public/issues", params=region).json()["items"] == []
            assert client.get(f"/api/public/issues/{public_id}").status_code == 404
        stop()
        start()
        with httpx.Client(
            base_url=f"http://localhost:{port}",
            headers={"Origin": "http://localhost:5173"},
            timeout=20,
        ) as client:
            login(client, first_email)
            assert client.get("/api/complaints/summary").json()["total"] == 3
            assert (
                client.get(f"/api/complaints/{ids[0]}").json()["publication"]["publicationStatus"]
                == "PRIVATE"
            )
            assert client.get(f"/api/public/issues/{public_id}").status_code == 404
            assert client.get("/api/public/issues", params=region).json()["items"] == []
        with service.store.connection() as db:
            assert db.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 4
            assert db.execute("SELECT COUNT(*) FROM publication_audit").fetchone()[0] == 3
    finally:
        stop()
