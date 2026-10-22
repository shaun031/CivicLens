"""Real Uvicorn/SQLite/private-files workflow, including process restart; never developer data."""

import io
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image

BACKEND = Path(__file__).resolve().parents[2] / "backend"


def test_full_private_complaint_workflow_with_process_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    database = tmp_path / "isolated.db"
    evidence = tmp_path / "private-evidence"
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "DEBUG": "false",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "COOKIE_SECURE": "false",
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
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("Isolated API exited during startup")
            try:
                if httpx.get(f"http://localhost:{port}/api/health", timeout=0.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("Isolated API did not start in time")

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

    password = f"Local test passphrase {uuid4()}"
    email = f"first-{uuid4()}@example.com"
    origin = {"Origin": "http://localhost:5173"}
    try:
        start()
        with httpx.Client(
            base_url=f"http://localhost:{port}", headers=origin, timeout=20
        ) as client:
            registration = {
                "display_name": "Integration Citizen",
                "email": email,
                "password": password,
                "confirm_password": password,
            }
            assert client.post("/api/auth/register", json=registration).status_code == 201
            assert (
                client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            image = io.BytesIO()
            Image.new("RGB", (32, 24), "green").save(image, "PNG")
            data = {
                "title": "Pothole near the public library",
                "description": "A large pothole makes the road unsafe "
                "for people cycling past the library.",
                "category": "POTHOLE",
                "reportedSeverity": "HIGH",
                "latitude": "12.94",
                "longitude": "80.14",
                "landmark": "Library entrance",
                "addressLabel": "Sample Library Road",
            }
            key = str(uuid4())
            response = client.post(
                "/api/complaints",
                data=data,
                files=[("images", ("road.png", image.getvalue(), "image/png"))],
                headers={"Idempotency-Key": key},
            )
            assert response.status_code == 201
            complaint = response.json()
            cid = complaint["complaintId"]
            photo_url = "/api" + complaint["images"][0]["url"]
            assert client.get("/api/complaints").json()["items"][0]["complaintId"] == cid
            assert client.get(f"/api/complaints/{cid}").json()["landmark"] == data["landmark"]
            assert client.get(photo_url).status_code == 200
            with sqlite3.connect(database) as db:
                row = db.execute(
                    "SELECT complaint_id,latitude,longitude FROM complaints"
                ).fetchone()
                assert row == (cid, 12.94, 80.14)
                storage_key = db.execute("SELECT storage_key FROM complaint_images").fetchone()[0]
            assert (evidence / storage_key).is_file()
            assert client.post("/api/auth/logout").status_code == 204
            assert client.get(photo_url).status_code == 401
            assert (
                client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            assert client.get(f"/api/complaints/{cid}").json() == complaint
            client.post("/api/auth/logout")
            other_email = f"second-{uuid4()}@example.com"
            assert (
                client.post(
                    "/api/auth/register", json=registration | {"email": other_email}
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/auth/login", json={"email": other_email, "password": password}
                ).status_code
                == 200
            )
            assert client.get(f"/api/complaints/{cid}").status_code == 404
            assert client.get(photo_url).status_code == 404
            assert client.get("/api/complaints").json()["items"] == []
        stop()
        start()  # An actual OS process restart, not just a second connection or factory.
        with httpx.Client(
            base_url=f"http://localhost:{port}", headers=origin, timeout=20
        ) as client:
            assert (
                client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            assert client.get(f"/api/complaints/{cid}").json() == complaint
            assert client.get(photo_url).status_code == 200
            replay = client.post(
                "/api/complaints",
                data=data,
                files=[("images", ("road.png", image.getvalue(), "image/png"))],
                headers={"Idempotency-Key": key},
            )
            assert replay.status_code == 201 and replay.json()["complaintId"] == cid
            assert client.get("/api/complaints/summary").json()["total"] == 1
    finally:
        stop()
