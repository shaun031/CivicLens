import csv
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import submit
from test_discovery import login_staff
from test_incidents import ADMIN, correction, create
from test_work_allocation import action, setup

from app.analytics.filters import AnalyticsFilters
from app.analytics.geographic import hotspots
from app.analytics.reporting import csv_report, report, safe_cell
from app.events.schema import new_event
from app.models.incident import IncidentError
from app.models.user import Role
from app.services.analytics_service import VIEWS


@pytest.mark.parametrize(
    "latitude,longitude,cell", [(90, 180, "899:1799"), (-90, -180, "-900:-1800"), (0.3, 0.3, "3:3")]
)
def test_geo_endpoint_and_decimal_boundary_cells(latitude, longitude, cell):
    from app.analytics.geographic import cell_key

    assert ":".join(map(str, cell_key({"latitude": latitude, "longitude": longitude}, 0.1))) == cell


@pytest.mark.parametrize("start,end", [("0001-01-01", "0001-01-02"), ("9999-12-30", "9999-12-31")])
def test_extreme_dates_rejected_without_datetime_overflow(start, end):
    with pytest.raises(ValueError):
        AnalyticsFilters(start=start, end=end).window("UTC", datetime.now(UTC))


def query(app, view="overview", **filters):
    return app.state.analytics_service.view(view, AnalyticsFilters(**filters))


@pytest.mark.parametrize("view", VIEWS)
def test_empty_analytics_is_real_zero_or_unavailable(complaint_client, complaint_app, view):
    filters = {"south": 12.9, "west": 77.5, "north": 13, "east": 77.6} if view == "hotspots" else {}
    value = query(complaint_app, view, **filters)
    assert value["dataFreshness"]["mode"] == "DIRECT_SNAPSHOT"
    assert value["reportingTimezone"] == "UTC"
    if view == "overview":
        assert value["totalComplaints"] == value["totalIncidents"] == 0
    elif view == "response-times":
        assert value["recordedResolution"]["meanHours"] is None
    elif view == "sla":
        assert value["responseCompliance"]["rate"] is None


def test_multiple_reports_one_canonical_incident_and_merge_split(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    _, a = create(client, app)
    report_b, b = create(client, app)
    assert query(app)["totalComplaints"] == query(app)["totalIncidents"] == 2
    app.state.incident_service.mutate("MERGE", correction(b, a), ADMIN)
    overview = query(app)
    assert overview["totalComplaints"] == 2 and overview["totalIncidents"] == 1
    assert overview["uniqueReporters"] == 1
    distribution = query(app, "incidents")
    assert distribution["multiReport"] == 1 and distribution["averageReports"] == 2
    current = app.state.incident_service.resolve(a["incidentId"])[0]
    payload = correction(current.model_dump(mode="json"), complaintIds=[report_b["complaintId"]])
    app.state.incident_service.mutate("SPLIT", payload, ADMIN)
    assert query(app)["totalIncidents"] == 2


def test_rejected_ineligible_reporters_and_unlinked_reports(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    one = submit(client).json()
    assert query(app)["totalComplaints"] == 1 and query(app)["totalIncidents"] == 0
    with app.state.auth_service.store.connection() as db:
        db.execute(
            "UPDATE complaints SET status='REJECTED' WHERE complaint_id=?", (one["complaintId"],)
        )
    assert query(app)["totalComplaints"] == 0


def test_authoritative_priority_stale_override_and_workload(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    repo, identity, department, officer, _ = setup(app, client, capacity=None)
    app.state.priority_service.calculate(identity)
    with repo.store.connection() as db:
        db.execute(
            "UPDATE incident_priority SET priority_band='CRITICAL',calculated_score=47,"
            "effective_score=99,urgent_hazard=1,override_status='ACTIVE',next_due=? "
            "WHERE incident_id=?",
            ((datetime.now(UTC) + timedelta(days=1)).timestamp(), identity),
        )
    assert query(app)["criticalIncidents"] == 1
    priority = query(app, "priorities")
    assert priority["meanCalculatedScore"] == 47 and priority["verifiedUrgentHazards"] == 1
    payload = action(repo, identity, departmentId=department, officerId=officer)
    repo.assign(identity, "OFFICER", payload, ADMIN)
    officers = query(app, "officers")["items"]
    assert officers[0]["weightedWorkload"] == 4 and officers[0]["utilization"] is None
    with repo.store.connection() as db:
        db.execute(
            "UPDATE incident_priority SET needs_recalculation=1 WHERE incident_id=?", (identity,)
        )
    assert query(app)["criticalIncidents"] == 0
    assert query(app)["dataFreshness"]["stalePriorityCount"] == 1
    assert query(app, "officers")["items"][0]["weightedWorkload"] == 4


@pytest.mark.parametrize("grouping,expected", [("daily", 3), ("weekly", 1), ("monthly", 1)])
def test_timezone_buckets_zero_filling(grouping, expected, complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    submit(client)
    app.state.settings.analytics_timezone = "Asia/Kolkata"
    with app.state.auth_service.store.connection() as db:
        db.execute("UPDATE complaints SET created_at='2026-01-05T20:00:00+00:00'")
    value = query(app, "complaint-trends", start="2026-01-05", end="2026-01-07", grouping=grouping)
    assert sum(r["count"] for r in value["series"]) == 1
    assert len(value["series"]) == expected
    if grouping == "daily":
        assert value["series"][1]["date"] == "2026-01-06" and value["series"][1]["count"] == 1


@pytest.mark.parametrize(
    "filters",
    [
        {"south": 0},
        {"south": 0, "west": 0, "north": 10, "east": 1},
        {"south": 1, "west": 1, "north": 0, "east": 2},
        {"grid": float("nan")},
        {"south": 0, "west": 0, "north": 1, "east": 1, "grid": 0.001},
        {"minWorkload": 10, "maxWorkload": 1},
        {"priority": "WRONG"},
    ],
)
def test_invalid_bounded_filters(filters):
    with pytest.raises(ValueError):
        AnalyticsFilters(**filters)


def test_date_range_department_area_errors(complaint_client, complaint_app):
    for filters in (
        {"start": "2020-01-01", "end": "2026-01-01"},
        {"start": "2026-01-10", "end": "2026-01-01"},
        {"department": str(uuid4())},
        {"area": "unknown"},
    ):
        with pytest.raises(IncidentError) as caught:
            query(complaint_app, **filters)
        assert caught.value.status == 422


def test_geo_incident_vs_report_counts_filters_and_privacy(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    _, a = create(client, app)
    _, b = create(client, app)
    app.state.incident_service.mutate("MERGE", correction(b, a), ADMIN)
    bounds = {"south": 12.9, "west": 77.5, "north": 13, "east": 77.6}
    value = query(app, "hotspots", **bounds)
    assert sum(c["incidentCount"] for c in value["cells"]) == 1
    assert sum(c["reportCount"] for c in value["cells"]) == 2
    assert query(app, "hotspots", **bounds, category="GARBAGE")["cells"] == []
    encoded = json.dumps(value)
    for private in ("citizen_id", "password", "description", "storage_key", "citizen@example.com"):
        assert private not in encoded


def test_boundary_grid_deterministic_and_no_double_count():
    rows = [
        {
            "latitude": 0.0,
            "longitude": 0.0,
            "status": "OPEN",
            "band": "LOW",
            "score": 20,
            "overdue": False,
        }
    ]
    result = hotspots(rows, [], 0.01, [-1, -1, 1, 1])
    assert len(result) == 1 and result[0]["incidentCount"] == 1 and result[0]["cell"] == "0:0"


def test_sla_current_distinct_overdue_and_response_denominator(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    _, identity, _, _, _ = setup(app, client)
    baseline = datetime.now(UTC)
    with app.state.auth_service.store.connection() as db:
        db.execute("UPDATE sla_policies SET response_hours=1,resolution_hours=2")
        db.execute(
            "UPDATE incident_priority SET next_due=? WHERE incident_id=?",
            ((baseline + timedelta(days=100)).timestamp(), identity),
        )
    app.state.workflow_service.repository.clock = lambda: baseline + timedelta(hours=4)
    app.state.analytics_service.clock = lambda: baseline + timedelta(hours=4)
    sla = app.state.sla_service
    sla.check(identity)
    sla.check(identity)
    value = query(app, "sla")
    assert value["overdueIncidents"] == 1
    assert value["distinctEscalatedIncidents"] == 1 and value["escalationCount"] == 1
    assert value["responseCompliance"]["met"] == 1
    assert value["responseCompliance"]["denominator"] == 1


def test_progress_is_not_resolution_or_historical_backlog(complaint_client, complaint_app):
    _, incident = create(complaint_client, complaint_app)
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute(
            "UPDATE incident_assignments SET percentage=100 WHERE incident_id=?",
            (incident["incidentId"],),
        )
    assert query(complaint_app)["resolvedIncidents"] == 0
    assert query(complaint_app, "response-times")["recordedResolution"]["sampleSize"] == 0
    assert query(complaint_app, "backlog")["historicalBacklog"] is None


def test_event_checkpoints_rebuild_revision_fence_and_no_domain_changes(
    complaint_client, complaint_app
):
    app = complaint_app
    _, incident = create(complaint_client, app)
    service = app.state.analytics_service
    create(complaint_client, app)
    page = query(app, "incidents", limit=1)
    import base64

    cursor = json.loads(
        base64.urlsafe_b64decode(page["nextCursor"] + "=" * (-len(page["nextCursor"]) % 4))
    )
    cursor["key"] = [1]
    invalid = base64.urlsafe_b64encode(json.dumps(cursor).encode()).decode().rstrip("=")
    with pytest.raises(IncidentError) as invalid_cursor:
        query(app, "incidents", limit=1, cursor=invalid)
    assert invalid_cursor.value.status == 400
    event = new_event("IncidentMembershipChanged", incident["incidentId"])
    assert service.repository.observe(event) and not service.repository.observe(event)
    filters = AnalyticsFilters()
    with app.state.auth_service.store.connection() as db:
        before = [tuple(r) for r in db.execute("SELECT * FROM incidents")]
        revision = db.execute("SELECT revision FROM analytics_meta").fetchone()[0]
    assert service.rebuild(filters, ["overview"], True)["results"][0]["saved"] is False
    assert service.rebuild(filters, ["overview"])["operationalRecordsModified"] is False
    assert service.rebuild(filters, ["overview"])["results"][0]["matchesPrevious"]
    with app.state.auth_service.store.connection() as db:
        assert before == [tuple(r) for r in db.execute("SELECT * FROM incidents")]
        db.execute("UPDATE incidents SET updated_at=updated_at")
    with pytest.raises(IncidentError):
        service.repository.save_snapshot("test", revision, {}, datetime.now(UTC).isoformat())


@pytest.mark.parametrize("value", ["=1+1", " +SUM(A1)", "\t@cmd", "-1", "\r=1", "\n+1"])
def test_csv_formula_protection(value):
    assert safe_cell(value).startswith("'")


def test_reports_are_allowlisted_bounded_escaped_and_no_private_fields(
    complaint_client, complaint_app
):
    submit(complaint_client)
    preview = report(complaint_app.state.analytics_service, "citywide", AnalyticsFilters())
    raw = csv_report(preview).decode("utf-8-sig")
    assert "totalComplaints,1" in raw and "reportingTimezone,UTC" in raw
    assert "citizen@example.com" not in raw and "description" not in raw
    assert list(csv.reader(io.StringIO(raw)))
    with pytest.raises(IncidentError):
        report(complaint_app.state.analytics_service, "users", AnalyticsFilters())


def test_api_admin_ownership_export_origin_and_audit(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    assert client.get("/api/admin/analytics/overview").status_code == 403
    assert client.post("/api/admin/analytics/reports/citywide/csv").status_code == 403
    login_staff(app, client, Role.OFFICER)
    assert client.get("/api/admin/analytics/officers").status_code == 403
    login_staff(app, client)
    response = client.get("/api/admin/analytics/overview")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/admin/analytics/overview?sql=DROP").status_code == 422
    assert client.get("/api/admin/analytics/hotspots").status_code == 422
    exported = client.post("/api/admin/analytics/reports/citywide/csv")
    assert exported.status_code == 200, exported.text
    assert "attachment" in exported.headers["content-disposition"]
    assert (
        client.post(
            "/api/admin/analytics/reports/citywide/csv", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    with app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM analytics_export_audit").fetchone()[0] == 1


def test_source_and_csv_limits_fail_explicitly(complaint_client, complaint_app):
    from app.repositories.analytics_repository import SQLiteAnalytics

    assert safe_cell("\v=1").startswith("'")
    assert safe_cell("\ufeff\t+1").startswith("'")

    submit(complaint_client)
    submit(complaint_client)
    with (
        complaint_app.state.auth_service.store.connection() as db,
        pytest.raises(IncidentError) as error,
    ):
        SQLiteAnalytics.rows(db, "SELECT complaint_id FROM complaints ORDER BY complaint_id", 1)
    assert error.value.status == 413
    preview = report(complaint_app.state.analytics_service, "citywide", AnalyticsFilters())
    preview["rows"][0]["value"] = "x" * 1048576
    with pytest.raises(IncidentError) as error:
        csv_report(preview)
    assert error.value.status == 413


def test_noncritical_event_failure_does_not_fail_operational_consumer(
    complaint_client, complaint_app
):
    from types import SimpleNamespace

    report_id = submit(complaint_client).json()["complaintId"]
    runner = complaint_app.state.workflow_service
    event = new_event("WorkflowFailed", report_id)
    runner.repository.enqueue(event)

    def broken(_):
        raise RuntimeError("Synthetic analytics storage interruption")

    runner.analytics = SimpleNamespace(observe=broken)
    assert runner.process_one()
    with runner.repository.store.connection() as db:
        assert (
            db.execute(
                "SELECT state FROM event_queue WHERE event_id=?", (str(event.eventId),)
            ).fetchone()[0]
            == "COMPLETE"
        )


def test_analytics_cli_dryrun_hash_unchanged_and_source_checkpoints_monotonic(
    complaint_client, complaint_app
):
    import hashlib
    import os
    import subprocess
    import sys
    from pathlib import Path

    app = complaint_app
    repo = app.state.analytics_service.repository
    identity = str(uuid4())
    now = datetime.now(UTC)
    repo.observe(new_event("IncidentStatusChanged", identity, now=now))
    repo.observe(new_event("IncidentStatusChanged", identity, now=now - timedelta(days=1)))
    with repo.store.connection() as db:
        assert (
            db.execute("SELECT observed_event_at FROM analytics_meta").fetchone()[0]
            == now.isoformat()
        )
    path = app.state.settings.local_db_path
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "DEBUG": "false",
        "LOG_LEVEL": "ERROR",
        "LOCAL_DB_PATH": str(path),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.scripts.rebuild_analytics",
            "--dry-run",
            "--aggregation",
            "overview",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert '"operationalRecordsModified": false' in result.stdout
