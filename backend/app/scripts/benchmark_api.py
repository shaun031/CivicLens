"""Controlled ASGI HTTP benchmark: isolated SQLite/evidence, no external server or AWS."""

import argparse
import io
import json
import math
import platform
import sqlite3
import statistics
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.scripts.benchmark_analytics import seed


def summary(samples, errors, seconds):
    ordered = sorted(samples)
    return {
        "requests": len(samples),
        "errors": errors,
        "errorRate": errors / len(samples),
        "medianMs": round(statistics.median(ordered), 3),
        "p95Ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        "throughputPerSecond": round(len(samples) / seconds, 3),
        "concurrency": 1,
    }


def benchmark(samples=15):
    if not 5 <= samples <= 30:
        raise ValueError("Use 5–30 samples for this bounded local demonstration benchmark")
    with TemporaryDirectory(prefix="civiclens-api-benchmark-") as folder:
        settings = Settings(
            _env_file=None,
            app_env="test",
            debug=False,
            log_level="ERROR",
            local_db_path=Path(folder) / "test.db",
            complaint_rate_limit=100,
        )
        app = create_app(settings)
        data = seed(app)
        password = "Synthetic API benchmark passphrase 2048"
        auth = app.state.auth_service
        for email, role in (
            ("benchmark@example.com", Role.CITIZEN),
            ("reviewer@example.com", Role.ADMIN),
        ):
            auth.register(
                RegisterInput(
                    display_name="Benchmark synthetic account",
                    email=email,
                    password=password,
                    confirm_password=password,
                ),
                role,
            )
        measurements = {}

        def measure(name, callback, count=samples):
            times, errors, result = [], 0, None
            beginning = perf_counter()
            for _ in range(count):
                started = perf_counter()
                result = callback()
                times.append((perf_counter() - started) * 1000)
                errors += result.status_code < 200 or result.status_code >= 300
            measurements[name] = summary(times, errors, perf_counter() - beginning)
            return result

        headers = {"Origin": "http://localhost:5173"}
        with TestClient(app, base_url="http://localhost:8000", headers=headers) as client:
            measure(
                "authentication",
                lambda: client.post(
                    "/api/auth/login", json={"email": "benchmark@example.com", "password": password}
                ),
                5,
            )
            image = io.BytesIO()
            Image.new("RGB", (256, 128), "blue").save(image, "PNG")
            photo = image.getvalue()
            fields = {
                "title": "Synthetic bounded road defect report",
                "description": "Synthetic road defect for isolated local API timing measurements.",
                "category": "POTHOLE",
                "reportedSeverity": "HIGH",
                "latitude": "12.9716",
                "longitude": "77.5946",
            }

            def submit(images=False):
                parts = [(k, (None, v)) for k, v in fields.items()]
                if images:
                    parts.append(("images", ("fixture.png", photo, "image/png")))
                return client.post(
                    "/api/complaints", files=parts, headers={"Idempotency-Key": str(uuid4())}
                )

            measure("complaintWithoutImages", submit, 5)
            created = measure("complaintWithImage", lambda: submit(True), 5).json()
            measure("complaintSearch", lambda: client.get("/api/complaints?q=synthetic&limit=20"))
            measure("complaintList", lambda: client.get("/api/complaints?limit=20"))
            measure("dashboardSummary", lambda: client.get("/api/complaints/summary"))
            measure(
                "complaintDetails", lambda: client.get("/api/complaints/" + created["complaintId"])
            )
            measure("notifications", lambda: client.get("/api/notifications"))
            measure(
                "nearbyPublishedIssues",
                lambda: client.get(
                    "/api/public/issues/nearby",
                    params={"latitude": 12.97, "longitude": 77.59, "radiusMeters": 1000},
                ),
            )
            assert (
                client.post(
                    "/api/auth/login", json={"email": "reviewer@example.com", "password": password}
                ).status_code
                == 200
            )
            with auth.store.connection() as db:
                incident = db.execute(
                    "SELECT incident_id FROM incidents WHERE status='OPEN' LIMIT 1"
                ).fetchone()[0]
                work = dict(
                    db.execute(
                        "SELECT a.*,i.version AS incident_version FROM incident_assignments a "
                        "JOIN incidents i USING(incident_id) WHERE i.status='OPEN' "
                        "AND a.status='IN_PROGRESS' LIMIT 1"
                    ).fetchone()
                )
                officer = db.execute(
                    "SELECT email FROM users WHERE id=?", (work["officer_id"],)
                ).fetchone()[0]
                # The historical analytics seed models assignments directly at revision0.
                # Normalize this disposable fixture to the HTTP submission's revision>=1 contract.
                db.execute(
                    "UPDATE incident_assignments SET version=1 WHERE incident_id=?",
                    (work["incident_id"],),
                )
                work["version"] = 1
                db.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (hash_password(password), work["officer_id"]),
                )
            for name, path in {
                "duplicateCandidates": "/api/admin/duplicate-candidates",
                "incidentDetails": f"/api/admin/incidents/{incident}",
                "priorityQueue": "/api/admin/incidents/priorities",
                "adminOverview": "/api/admin/analytics/overview",
                "hotspots": "/api/admin/analytics/hotspots?south=12.9&west=77.5&north=13&east=77.7",
                "repairReview": "/api/admin/repairs/pending",
                "recurrences": "/api/admin/recurrences",
                "fairness": "/api/admin/analytics/fairness",
            }.items():
                measure(name, lambda path=path: client.get(path))
            assert (
                client.post(
                    "/api/auth/login", json={"email": officer, "password": password}
                ).status_code
                == 200
            )
            measure("officerQueue", lambda: client.get("/api/officer/incidents"))
            submitted = measure(
                "repairSubmission",
                lambda: client.post(
                    f"/api/officer/incidents/{work['incident_id']}/repair-attempts",
                    json={
                        "operationId": str(uuid4()),
                        "expectedIncidentVersion": work["incident_version"],
                        "expectedAssignmentVersion": work["version"],
                        "description": "Synthetic repair inspection for isolated API timing only.",
                        "notes": "No actual municipal work",
                        "repairedAt": datetime.now(UTC).isoformat(),
                    },
                ),
                1,
            )
            if submitted.status_code != 201:
                raise RuntimeError("Benchmark repair setup failed: " + submitted.text)
            attempt_id = submitted.json()["attemptId"]
            # Claiming completion does not resolve. Admin approval is a distinct measured operation.
            assert (
                client.post(
                    "/api/auth/login", json={"email": "reviewer@example.com", "password": password}
                ).status_code
                == 200
            )
            detail = client.get(f"/api/admin/repairs/{attempt_id}").json()
            measure(
                "repairApproval",
                lambda: client.post(
                    f"/api/admin/repairs/{attempt_id}/approve",
                    json={
                        "operationId": str(uuid4()),
                        "expectedVersion": detail["version"],
                        "expectedIncidentVersion": detail["incidentVersion"],
                        "confirmed": True,
                        "reason": "Synthetic independent inspection for disposable timing only.",
                        "approvedEvidenceIds": [],
                    },
                ),
                1,
            )
        with auth.store.connection() as db:
            plans = {}
            for name, sql, params in (
                (
                    "ownerList",
                    "SELECT complaint_id FROM complaints WHERE citizen_id=? "
                    "ORDER BY created_at DESC,complaint_id DESC LIMIT 20",
                    (created["citizenId"],),
                ),
                (
                    "officerQueue",
                    "SELECT incident_id FROM incident_assignments "
                    "WHERE officer_id=? AND status=? LIMIT 20",
                    (work["officer_id"], "IN_PROGRESS"),
                ),
                (
                    "notificationOwner",
                    "SELECT notification_id FROM notifications WHERE recipient_user_id=? "
                    "ORDER BY created_at DESC,notification_id DESC LIMIT 20",
                    (created["citizenId"],),
                ),
                (
                    "outboxClaim",
                    "SELECT event_id FROM event_outbox WHERE status=? AND available_at<=? "
                    "ORDER BY available_at,event_id LIMIT 1",
                    ("PENDING", 0),
                ),
                (
                    "repairLookup",
                    "SELECT attempt_id FROM repair_attempts WHERE incident_id=? "
                    "ORDER BY cycle DESC LIMIT 25",
                    (incident,),
                ),
            ):
                plans[name] = [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, params)]
        targets = {
            "complaintList": 500,
            "dashboardSummary": 500,
            "incidentDetails": 500,
            "nearbyPublishedIssues": 1000,
        }
        acceptance = {
            name: {
                "targetP95Ms": target,
                "status": "PASS" if measurements[name]["p95Ms"] < target else "WARNING",
            }
            for name, target in targets.items()
        }
        return {
            "status": "FAIL" if any(m["errors"] for m in measurements.values()) else "PASS",
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "sqlite": sqlite3.sqlite_version,
            },
            "dataset": data
            | {"additionalComplaints": 10, "imageInputBytes": len(photo), "imagePixels": 32768},
            "measurements": measurements,
            "queryPlans": plans,
            "acceptance": acceptance,
            "limitations": "Serial ASGI in-process HTTP pipeline, not TCP/uvicorn, concurrent "
            "load or AWS latency. Empty public/candidate/notification catalogs disclosed; "
            "seeded canonical analytics have 500 rows. Mutation n=1 p95 is NOT statistically "
            "stable. Fairness includes first cold and subsequent cached reads; no worker runs.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = benchmark(args.samples)
    encoded = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            file.write(encoded + "\n")
    print(encoded)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
