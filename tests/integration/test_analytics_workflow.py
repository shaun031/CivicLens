"""Real local records/services across Phase4,7,8,9,10 and11; disposable SQLite only."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.analytics.filters import AnalyticsFilters
from app.core.config import Settings
from app.main import create_app
from app.models.incident import Actor
from app.models.user import Role
from app.schemas.auth import RegisterInput


def test_municipal_analytics_end_to_end_merge_assignment_sla_export_rebuild(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            local_db_path=tmp_path / "analytics.db",
            local_evidence_root=tmp_path / "private",
        )
    )
    password = "Synthetic analytics integration passphrase 1234"
    headers = {"Origin": "http://localhost:5173"}
    staff = Actor("trusted-integration-admin", "ADMIN")
    with TestClient(app, base_url="http://localhost:8000", headers=headers) as client:
        canonical = None
        for citizen in range(5):
            email = f"synthetic-{citizen}@example.com"
            assert (
                client.post(
                    "/api/auth/register",
                    json={
                        "display_name": f"Synthetic Citizen{citizen}",
                        "email": email,
                        "password": password,
                        "confirm_password": password,
                    },
                ).status_code
                == 201
            )
            assert (
                client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            assert client.get("/api/admin/analytics/overview").status_code == 403
            for _ in range(2):
                fields = {
                    "title": "Synthetic physical pothole report",
                    "description": "Synthetic same physical defect for analytics integration only.",
                    "category": "POTHOLE",
                    "reportedSeverity": "HIGH",
                    "latitude": "12.9716",
                    "longitude": "77.5946",
                }
                created = client.post(
                    "/api/complaints",
                    files=[(k, (None, v)) for k, v in fields.items()],
                    headers={"Idempotency-Key": str(uuid4())},
                )
                assert created.status_code == 201, created.text
                report = created.json()
                source = app.state.incident_service.ensure_singleton(report["complaintId"])
                if canonical is None:
                    canonical = source
                else:
                    canonical = app.state.incident_service.mutate(
                        "MERGE",
                        {
                            "operationId": str(uuid4()),
                            "sourceIncidentId": source["incidentId"],
                            "targetIncidentId": canonical["incidentId"],
                            "expectedSourceVersion": source["version"],
                            "expectedTargetVersion": canonical["version"],
                            "confirmed": True,
                            "physicalIssueConfirmed": True,
                            "reason": "Administrator confirmed this same synthetic physical defect",
                        },
                        staff,
                    )
        admin = app.state.auth_service.register(
            RegisterInput(
                display_name="Synthetic Analytics Administrator",
                email="analytics-admin@example.com",
                password=password,
                confirm_password=password,
            ),
            Role.ADMIN,
        )
        assert (
            client.post(
                "/api/auth/login", json={"email": admin.email, "password": password}
            ).status_code
            == 200
        )
        overview = client.get("/api/admin/analytics/overview").json()
        assert overview["totalComplaints"] == 10 and overview["totalIncidents"] == 1
        assert overview["uniqueReporters"] == 5 and overview["activeIncidents"] == 1
        identity = canonical["incidentId"]
        priority = app.state.priority_service.calculate(identity)
        assert not priority["stale"]
        work = app.state.work_service.repository
        common = {
            "operationId": str(uuid4()),
            "reason": "Synthetic integration work configuration",
            "confirmed": True,
        }
        work.seed(common, staff)
        dept = next(d["id"] for d in work.departments()["items"] if d["code"] == "ROAD_MAINTENANCE")
        state = work.detail(identity)
        work.assign(
            identity,
            "DEPARTMENT",
            common
            | {
                "operationId": str(uuid4()),
                "departmentId": dept,
                "expectedIncidentVersion": state["incidentVersion"],
                "expectedAssignmentVersion": state["assignment"]["version"],
            },
            staff,
        )
        departments = client.get("/api/admin/analytics/departments").json()["items"]
        assert next(d for d in departments if d["departmentId"] == dept)["activeIncidents"] == 1
        baseline = datetime.now(UTC)
        with app.state.auth_service.store.connection() as db:
            db.execute("UPDATE sla_policies SET response_hours=1,resolution_hours=2")
            db.execute(
                "UPDATE incident_priority SET next_due=?",
                ((baseline + timedelta(days=1)).timestamp(),),
            )
        app.state.workflow_service.repository.clock = lambda: baseline + timedelta(hours=4)
        app.state.analytics_service.clock = lambda: baseline + timedelta(hours=4)
        app.state.sla_service.check(identity)
        app.state.sla_service.check(identity)
        sla = client.get("/api/admin/analytics/sla").json()
        assert (
            sla["overdueIncidents"]
            == sla["escalationCount"]
            == sla["distinctEscalatedIncidents"]
            == 1
        )
        geo = client.get(
            "/api/admin/analytics/hotspots?south=12.9&west=77.5&north=13&east=77.7"
        ).json()
        assert sum(c["incidentCount"] for c in geo["cells"]) == 1
        assert sum(c["reportCount"] for c in geo["cells"]) == 10
        exported = client.post("/api/admin/analytics/reports/citywide/csv")
        assert exported.status_code == 200 and "totalComplaints,10" in exported.text
        assert "synthetic-0@example.com" not in exported.text
        service = app.state.analytics_service
        assert (
            service.rebuild(AnalyticsFilters(), ["overview", "incidents"])[
                "operationalRecordsModified"
            ]
            is False
        )
        assert all(
            row["matchesPrevious"]
            for row in service.rebuild(AnalyticsFilters(), ["overview", "incidents"], True)[
                "results"
            ]
        )
        with app.state.auth_service.store.connection() as db:
            assert db.execute("SELECT count(*) FROM complaints").fetchone()[0] == 10
            assert (
                db.execute("SELECT count(*) FROM incidents WHERE status='OPEN'").fetchone()[0] == 1
            )
