"""An actual worker process is killed during triage, then restarted against its durable store."""

import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_killed_worker_recovers_completed_stages_without_duplicate_side_effects(tmp_path):
    settings = Settings(_env_file=None, app_env="test", local_db_path=tmp_path / "restart.db")
    app = create_app(settings)
    backend = Path(__file__).resolve().parents[2] / "backend"
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "DEBUG": "false",
        "LOG_LEVEL": "ERROR",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "LOCAL_DB_PATH": str(settings.local_db_path),
        "LOCAL_EVIDENCE_ROOT": str(settings.local_evidence_root),
    }
    preview_command = [
        sys.executable,
        "-m",
        "app.scripts.run_scheduled_checks",
        "--once",
        "--dry-run",
    ]
    absent = subprocess.run(
        preview_command, cwd=backend, env=environment, capture_output=True, text=True, timeout=30
    )
    assert absent.returncode == 2 and "migrate" in absent.stderr.lower()
    assert "Traceback" not in absent.stderr and not settings.local_db_path.exists()
    with TestClient(
        app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:5173"}
    ) as client:
        password = "Synthetic worker restart passphrase 1234"
        assert (
            client.post(
                "/api/auth/register",
                json={
                    "display_name": "Restart Citizen",
                    "email": "restart@example.com",
                    "password": password,
                    "confirm_password": password,
                },
            ).status_code
            == 201
        )
        client.post("/api/auth/login", json={"email": "restart@example.com", "password": password})
        parts = {
            "title": "Synthetic worker restart pothole",
            "description": "A synthetic report for durable worker interruption and recovery only.",
            "category": "POTHOLE",
            "reportedSeverity": "LOW",
            "latitude": "12.97",
            "longitude": "77.59",
        }
        from uuid import uuid4

        response = client.post(
            "/api/complaints",
            files=[(key, (None, value)) for key, value in parts.items()],
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201
        process = subprocess.Popen(
            [sys.executable, "-m", "app.scripts.run_worker", "--continuous", "--batch-size", "1"],
            cwd=backend,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 30
            observed = False
            while time.monotonic() < deadline:
                with app.state.auth_service.store.connection() as db:
                    observed = bool(
                        db.execute(
                            "SELECT 1 FROM workflow_executions WHERE status='RUNNING'"
                        ).fetchone()
                    )
                if observed:
                    break
                assert process.poll() is None
                time.sleep(0.02)
            assert observed, "Worker never persisted its running execution"
        finally:
            process.kill()
            process.wait(timeout=10)
        # Simulate lease-clock expiry, not completed-step deletion or resetting business records.
        with app.state.auth_service.store.connection() as db:
            db.execute("UPDATE event_queue SET available_at=0 WHERE state='RUNNING'")
            db.execute("UPDATE workflow_executions SET lease_until=0 WHERE status='RUNNING'")
            db.execute("UPDATE matching_jobs SET available_at=0 WHERE state='RUNNING'")
            db.execute("UPDATE clustering_jobs SET available_at=0 WHERE state='RUNNING'")
        result = subprocess.run(
            [sys.executable, "-m", "app.scripts.run_worker", "--max-batches", "10"],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        with app.state.auth_service.store.connection() as db:
            assert db.execute("SELECT count(*) FROM complaints").fetchone()[0] == 1
            assert (
                db.execute("SELECT count(*) FROM incidents WHERE status='OPEN'").fetchone()[0] == 1
            )
            assert (
                db.execute("SELECT status FROM workflow_executions").fetchone()[0]
                == "COMPLETED_WITH_REVIEW_REQUIRED"
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM workflow_steps WHERE status='COMPLETED'"
                ).fetchone()[0]
                == 6
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM notifications "
                    "WHERE notification_type='COMPLAINT_RECEIVED'"
                ).fetchone()[0]
                == 1
            )
        assert client.get("/api/notifications/unread-count").json()["unreadCount"] == 1
        import hashlib

        before = hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest()
        preview = subprocess.run(
            preview_command,
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert preview.returncode == 0, preview.stderr
        assert hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest() == before
