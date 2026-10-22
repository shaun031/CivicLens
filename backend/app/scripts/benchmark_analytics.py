"""Reproducible disposable1000-report/500-incident local analytics benchmark; no AWS calls."""

import json
import statistics
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.analytics.filters import AnalyticsFilters
from app.analytics.reporting import csv_report, report
from app.core.config import Settings
from app.main import create_app
from app.models.incident import Actor
from app.services.analytics_service import VIEWS


def seed(app):
    store = app.state.auth_service.store
    store.initialize()
    settings = app.state.settings
    now = datetime.now(UTC)
    app.state.work_service.repository.seed(
        {
            "operationId": str(uuid4()),
            "reason": "Disposable synthetic analytics benchmark configuration",
            "confirmed": True,
        },
        Actor("benchmark", "ADMIN"),
    )
    citizens = [str(uuid4()) for _ in range(5)]
    officers = [str(uuid4()) for _ in range(6)]
    with store.connection() as db:
        for i, identity in enumerate(citizens + officers):
            db.execute(
                "INSERT INTO users VALUES(?,?,?,'unused',?,1,1,?,?,NULL)",
                (
                    identity,
                    f"synthetic-{i}@example.com",
                    f"Synthetic account{i}",
                    "CITIZEN" if i < 5 else "OFFICER",
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        departments = [r[0] for r in db.execute("SELECT id FROM departments ORDER BY id")]
        for i, identity in enumerate(officers):
            db.execute(
                "INSERT INTO officer_memberships VALUES(?,?,?,1,'AVAILABLE',100,'[]',1,?,?,?)",
                (
                    str(uuid4()),
                    identity,
                    departments[i],
                    now.isoformat(),
                    now.isoformat(),
                    "benchmark",
                ),
            )
        report_ids = [str(uuid4()) for _ in range(1000)]
        incident_ids = [str(uuid4()) for _ in range(500)]
        for i, identity in enumerate(report_ids):
            at = (now - timedelta(days=(i // 2) % 90, hours=1)).isoformat()
            db.execute(
                "INSERT INTO complaints(complaint_id,citizen_id,title,description,category,"
                "reported_severity,latitude,longitude,status,created_at,updated_at) "
                "VALUES(?,?,'Synthetic analytics report','Synthetic benchmark report only. "
                "No operational citizen data.','POTHOLE','HIGH',?,?,'SUBMITTED',?,?)",
                (
                    identity,
                    citizens[i % 5],
                    12.95 + (i // 2 % 10) * 0.002,
                    77.55 + (i // 20 % 10) * 0.002,
                    at,
                    at,
                ),
            )
        for i, identity in enumerate(incident_ids):
            at = (now - timedelta(days=i % 90, hours=1)).isoformat()
            resolved = i % 5 == 0
            db.execute(
                "INSERT INTO incidents VALUES(?, 'Synthetic incident', 'Synthetic analytics "
                "benchmark only','POTHOLE',?,?,?, ?,2,2,?,?,?,?,?,NULL,1)",
                (
                    identity,
                    12.95 + (i % 10) * 0.002,
                    77.55 + (i // 10 % 10) * 0.002,
                    "RESOLVED" if resolved else "OPEN",
                    report_ids[2 * i],
                    at,
                    at,
                    at,
                    at,
                    now.isoformat() if resolved else None,
                ),
            )
            db.execute(
                "UPDATE complaints SET incident_id=? WHERE complaint_id IN (?,?)",
                (identity, report_ids[2 * i], report_ids[2 * i + 1]),
            )
            band = ("LOW", "MEDIUM", "HIGH", "CRITICAL")[i % 4]
            db.execute(
                "UPDATE incident_priority SET needs_recalculation=0,source_version=1,"
                "config_version=?,next_due=?,priority_band=?,calculated_score=?,"
                "effective_score=?,urgent_hazard=?,assessment_status='PROVISIONAL',"
                "result=json_object('synthetic',1),"
                "calculated_at=? WHERE incident_id=?",
                (
                    app.state.priority_service.config.version,
                    (now + timedelta(days=1)).timestamp(),
                    band,
                    (i % 4) * 25,
                    (i % 4) * 25,
                    int(i % 4 == 3 and i % 7 == 0),
                    now.isoformat(),
                    identity,
                ),
            )
            if not resolved:
                department = departments[i % 6]
                officer = officers[i % 6] if i % 2 else None
                status = "IN_PROGRESS" if officer else "DEPARTMENT_ASSIGNED"
                db.execute(
                    "UPDATE incident_assignments SET department_id=?,officer_id=?,status=?,"
                    "assigned_at=? WHERE incident_id=?",
                    (department, officer, status, at, identity),
                )
                state = json.dumps({"departmentId": department, "status": status, "assignedAt": at})
                db.execute(
                    "INSERT INTO work_history VALUES(?,?,NULL,'ASSIGNMENT_DEPARTMENT',"
                    "'benchmark','SYSTEM','Synthetic response milestone','{}',?,?)",
                    (str(uuid4()), identity, state, at),
                )
    return {
        "complaints": 1000,
        "canonicalIncidents": 500,
        "departments": 6,
        "officers": 6,
        "priorityConfig": settings.priority_bands,
    }


def main():
    with tempfile.TemporaryDirectory(prefix="civiclens-analytics-") as directory:
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                log_level="ERROR",
                local_db_path=Path(directory) / "analytics.db",
            )
        )
        dataset = seed(app)
        today = datetime.now(UTC).date()
        filters = AnalyticsFilters(
            start=today - timedelta(days=89),
            end=today,
            south=12.9,
            west=77.5,
            north=13,
            east=77.8,
            grid=0.01,
            limit=50,
        )
        service = app.state.analytics_service
        timings = {}
        for view in VIEWS:
            samples = []
            for _ in range(3):
                started = time.perf_counter()
                service.view(view, filters)
                samples.append((time.perf_counter() - started) * 1000)
            timings[view + "MedianMs"] = round(statistics.median(samples), 3)
        started = time.perf_counter()
        content = csv_report(report(service, "departments", filters))
        timings["csvGenerationMs"] = round((time.perf_counter() - started) * 1000, 3)
        started = time.perf_counter()
        result = service.rebuild(filters, list(VIEWS))
        timings["fullRebuildMs"] = round((time.perf_counter() - started) * 1000, 3)
        with service.repository.store.connection() as db:
            plans = [
                r[3]
                for r in db.execute(
                    "EXPLAIN QUERY PLAN SELECT complaint_id FROM "
                    "complaints WHERE created_at>=? AND created_at<?",
                    (filters.start.isoformat(), (filters.end + timedelta(days=1)).isoformat()),
                )
            ]
        print(
            json.dumps(
                {
                    "dataset": dataset,
                    "measurements": timings,
                    "csvBytes": len(content),
                    "rebuiltViews": len(result["results"]),
                    "queryPlan": plans,
                    "scope": (
                        "Disposable SQLite only; includes bounded source reads; "
                        "not an AWS performance forecast"
                    ),
                },
                allow_nan=False,
            )
        )


if __name__ == "__main__":
    main()
