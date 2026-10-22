"""Disposable real SQLite transactions plus bounded 1000-report analytics; no developer data."""

import json
import statistics
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.analytics.filters import AnalyticsFilters
from app.analytics.reporting import csv_report
from app.core.config import Settings
from app.main import create_app
from app.models.complaint import ComplaintInput
from app.scripts.benchmark_analytics import seed


def measured(operation):
    start = time.perf_counter()
    value = operation()
    return value, (time.perf_counter() - start) * 1000


def main():
    with tempfile.TemporaryDirectory(prefix="civiclens-intelligence-") as folder:
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                log_level="ERROR",
                local_db_path=Path(folder) / "synthetic.db",
            )
        )
        dataset = seed(app)
        service = app.state.civic_intelligence_service
        store = app.state.auth_service.store
        admin = str(uuid4())
        now = datetime.now(UTC)
        with store.connection() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,'Synthetic Reviewer','unused','ADMIN',1,1,?,?,NULL)",
                (admin, f"reviewer-{admin}@example.com", now.isoformat(), now.isoformat()),
            )
            assignments = [
                dict(r)
                for r in db.execute(
                    "SELECT a.*,i.version AS incident_version FROM incident_assignments a "
                    "JOIN incidents i USING(incident_id) WHERE i.status='OPEN' "
                    "AND a.status='IN_PROGRESS' LIMIT 50"
                )
            ]
        samples = {
            key: []
            for key in (
                "repairAndRequestGeneration",
                "verificationResponse",
                "adminApproval",
                "recurrenceCheck",
                "fairnessCold",
                "fairnessCached",
                "reportExport",
                "eventProcessing",
            )
        }
        attempts = []
        for row in assignments[:20]:
            payload = {
                "operationId": str(uuid4()),
                "expectedIncidentVersion": row["incident_version"],
                "expectedAssignmentVersion": row["version"],
                "description": "Synthetic independently inspected completed repair "
                "for disposable benchmark.",
                "notes": "Not actual municipal work",
                "repairedAt": now.isoformat(),
            }
            attempt, elapsed = measured(
                lambda row=row, payload=payload: service.upload_action(
                    "submit",
                    row["incident_id"],
                    payload,
                    {"id": row["officer_id"], "role": "OFFICER"},
                    [],
                )
            )
            samples["repairAndRequestGeneration"].append(elapsed)
            attempts.append(attempt)
            with store.connection() as db:
                request = dict(
                    db.execute(
                        "SELECT * FROM repair_verification_requests WHERE attempt_id=? LIMIT 1",
                        (attempt["attemptId"],),
                    ).fetchone()
                )
            _, elapsed = measured(
                lambda request=request: service.upload_action(
                    "respond",
                    request["request_id"],
                    {
                        "operationId": str(uuid4()),
                        "expectedVersion": 1,
                        "result": "CONFIRMED_FIXED",
                        "feedback": "Synthetic observation",
                    },
                    {"id": request["citizen_id"], "role": "CITIZEN"},
                    [],
                )
            )
            samples["verificationResponse"].append(elapsed)
            detail = service.repository.detail(attempt["attemptId"], {"id": admin, "role": "ADMIN"})
            _, elapsed = measured(
                lambda attempt=attempt, detail=detail: service.decision(
                    attempt["attemptId"],
                    "approve",
                    {
                        "operationId": str(uuid4()),
                        "expectedVersion": detail["version"],
                        "expectedIncidentVersion": detail["incidentVersion"],
                        "confirmed": True,
                        "reason": "Independent synthetic administrator field verification "
                        "reviewed evidence and feedback for benchmark only.",
                        "approvedEvidenceIds": [],
                    },
                    {"id": admin, "role": "ADMIN"},
                )
            )
            samples["adminApproval"].append(elapsed)
        today = now.date()
        filters = AnalyticsFilters(
            start=today - timedelta(days=89), end=today, south=12.9, west=77.5, north=13, east=77.8
        )
        _, elapsed = measured(lambda: service.fairness(filters))
        samples["fairnessCold"].append(elapsed)
        for _ in range(5):
            _, elapsed = measured(lambda: service.fairness(filters))
            samples["fairnessCached"].append(elapsed)
        content, elapsed = measured(
            lambda: csv_report(service.report("geographic-service-comparison", filters))
        )
        samples["reportExport"].append(elapsed)
        # A real later singleton probes the newly verified history, including scoring.
        with store.connection() as db:
            previous = dict(
                db.execute(
                    "SELECT * FROM incidents WHERE incident_id=?", (attempts[0]["incidentId"],)
                ).fetchone()
            )
            citizen = db.execute("SELECT id FROM users WHERE role='CITIZEN' LIMIT 1").fetchone()[0]
        probe = app.state.complaint_service.create(
            citizen,
            ComplaintInput.model_validate(
                {
                    "title": "Synthetic incident recurrence",
                    "description": "Synthetic analytics benchmark only road pothole surface repair",
                    "category": "POTHOLE",
                    "reportedSeverity": "LOW",
                    "latitude": previous["latitude"],
                    "longitude": previous["longitude"],
                }
            ),
            [],
            str(uuid4()),
            str(uuid4()),
        )
        current = app.state.incident_service.ensure_singleton(probe.complaintId)
        candidate_count = 0
        for _ in range(3):
            result, elapsed = measured(
                lambda: service.check_recurrence(
                    current["incidentId"],
                    {"operationId": str(uuid4())},
                    {"id": admin, "role": "ADMIN"},
                )
            )
            candidate_count = len(result["recurrenceIds"])
            samples["recurrenceCheck"].append(elapsed)
        _, elapsed = measured(lambda: app.state.workflow_service.batch(100))
        samples["eventProcessing"].append(elapsed)
        print(
            json.dumps(
                {
                    "dataset": dataset,
                    "completedRepairTransactions": len(attempts),
                    "laterRecurrenceProbeReports": 1,
                    "historicalCandidatesScoredPerCheck": candidate_count,
                    "medianMilliseconds": {
                        k: round(statistics.median(v), 3) for k, v in samples.items()
                    },
                    "samples": {k: len(v) for k, v in samples.items()},
                    "csvBytes": len(content),
                    "limitations": "Temporary SQLite, no upload/network latency; repair submission "
                    "includes request generation; recurrence includes a real later singleton "
                    "and bounded candidate scoring; not AWS throughput.",
                },
                allow_nan=False,
            )
        )


if __name__ == "__main__":
    main()
