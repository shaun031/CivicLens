import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_complaints import ORIGIN
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import login_staff
from test_incidents import ADMIN, correction, create

from app.main import create_app
from app.models.incident import IncidentError
from app.models.user import Role
from app.repositories.priority_repository import PriorityCommit


def action(service, identity, **updates):
    state = service.detail(identity)
    return {
        "operationId": str(uuid4()),
        "expectedIncidentVersion": state["incidentVersion"],
        "expectedPriorityRevision": state["priorityRevision"],
        "confirmed": True,
        "reason": "Administrator inspected supporting evidence and recorded an assessment",
        **updates,
    }


def test_singleton_priority_safe_owner_and_admin_assessments(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    report, incident = create(client, app, images=True)
    service = app.state.priority_service
    identity = incident["incidentId"]
    before = client.get(f"/api/complaints/{report['complaintId']}").json()
    assert service.detail(identity)["stale"]
    raw = service.calculate(identity)["priority"]
    assert 0 <= raw["calculatedScore"] <= 100 and raw["factors"]["reporters"]["rawValue"] == 1
    assert raw["factors"]["severity"]["status"] == "PROVISIONAL"
    assert client.get(f"/api/admin/incidents/{identity}/priority").status_code == 403
    login_staff(app, client)
    data = action(
        service, identity, score=8, status="VERIFIED", evidenceReferences=[report["complaintId"]]
    )
    url = f"/api/admin/incidents/{identity}/severity"
    response = client.patch(url, json=data)
    assert response.status_code == 200, response.text
    assert response.json()["priority"]["factors"]["severity"]["normalizedValue"] == 8
    assert client.patch(url, json=data).json() == response.json()
    stale = client.patch(url, json=data | {"operationId": str(uuid4())})
    assert stale.status_code == 409
    assert (
        client.patch(url, json=data | {"reason": "Changed reason reusing operation ID"}).status_code
        == 409
    )
    data = action(
        service,
        identity,
        score=7,
        status="VERIFIED",
        evidenceReferences=[report["images"][0]["imageId"]],
    )
    response = client.patch(f"/api/admin/incidents/{identity}/public-impact", json=data)
    assert response.status_code == 200
    assert response.json()["priority"]["factors"]["publicImpact"]["normalizedValue"] == 7
    history = client.get(f"/api/admin/incidents/{identity}/priority/history").json()["items"]
    assert {"RECALCULATE", "SEVERITY", "PUBLIC_IMPACT"} <= {e["kind"] for e in history}
    assert all("snapshot" in e for e in history)
    with app.state.auth_service.store.connection() as db:
        stored = db.execute(
            "SELECT title,status FROM complaints WHERE complaint_id=?", (report["complaintId"],)
        ).fetchone()
        assert stored[0] == before["title"] and stored[1] == before["status"]


def test_merge_split_repeated_accounts_assessment_invalidation_and_no_duplicate_history(
    complaint_client, complaint_app
):
    app, client = complaint_app, complaint_client
    service, incidents = app.state.priority_service, app.state.incident_service
    a, first = create(client, app)
    b, second = create(client, app)
    c, third = create(client, app, another=True)
    identity = first["incidentId"]
    service.change(
        identity,
        "SEVERITY",
        action(
            service, identity, score=9, status="VERIFIED", evidenceReferences=[a["complaintId"]]
        ),
        ADMIN,
    )
    service.change(identity, "OVERRIDE", action(service, identity, score=90), ADMIN)
    merged = incidents.mutate("MERGE", correction(second, first), ADMIN)
    assert service.detail(identity)["stale"]
    result = service.calculate(identity)["priority"]
    assert result["factors"]["reporters"]["rawValue"] == 1
    assert result["overrideStatus"] == "REVIEW_REQUIRED"
    assert result["factors"]["severity"]["status"] == "NEEDS_REVIEW"
    merged = incidents.mutate("MERGE", correction(third, merged), ADMIN)
    result = service.calculate(identity)["priority"]
    assert result["factors"]["reporters"]["rawValue"] == 2
    d, fourth = create(client, app, another=True)
    merged = incidents.mutate("MERGE", correction(fourth, merged), ADMIN)
    assert service.calculate(identity)["priority"]["factors"]["reporters"]["rawValue"] == 3
    split = incidents.mutate("SPLIT", correction(merged, complaintIds=[c["complaintId"]]), ADMIN)
    assert service.detail(identity)["stale"] and service.detail(split["incidentId"])["stale"]
    assert service.calculate(identity)["priority"]["factors"]["reporters"]["rawValue"] == 2
    assert service.calculate(split["incidentId"])["priority"]["overrideStatus"] == "NONE"
    fixed = datetime.now(UTC)
    service.clock = lambda: fixed
    service.calculate(identity)
    before = len(service.repository.history(identity, 50, None)[0])
    service.calculate(identity)
    assert len(service.repository.history(identity, 50, None)[0]) == before


def test_aging_freezes_reopens_and_expiring_override_restores_current_formula(
    complaint_client, complaint_app
):
    report, incident = create(complaint_client, complaint_app)
    service = complaint_app.state.priority_service
    identity, now = incident["incidentId"], datetime(2026, 1, 1, tzinfo=UTC)
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incidents SET first_reported_at=?,updated_at=? WHERE incident_id=?",
            (now.isoformat(), now.isoformat(), identity),
        )
    service.clock = lambda: now
    assert service.calculate(identity)["priority"]["unresolvedDays"] == 0
    now += timedelta(days=15)
    assert service.calculate(identity)["priority"]["factors"]["aging"]["normalizedValue"] == 5
    service.change(
        identity,
        "OVERRIDE",
        action(service, identity, score=80, expiresAt=(now + timedelta(days=1)).isoformat()),
        ADMIN,
    )
    now += timedelta(days=2)
    result = service.calculate(identity)["priority"]
    assert (
        result["overrideStatus"] == "EXPIRED"
        and result["effectiveScore"] == result["calculatedScore"]
    )
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incidents SET status='RESOLVED',resolved_at=?,updated_at=?,"
            "version=version+1 WHERE incident_id=?",
            (now.isoformat(), now.isoformat(), identity),
        )
    now += timedelta(days=10)
    assert service.calculate(identity)["priority"]["unresolvedDays"] == pytest.approx(17)
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incidents SET status='OPEN',resolved_at=NULL,updated_at=?,"
            "version=version+1 WHERE incident_id=?",
            (now.isoformat(), identity),
        )
    now += timedelta(days=3)
    assert service.calculate(identity)["priority"]["unresolvedDays"] == pytest.approx(20)


def test_hazard_override_queue_filter_and_invalidated_pagination(complaint_client, complaint_app):
    service = complaint_app.state.priority_service
    a, first = create(complaint_client, complaint_app)
    b, second = create(complaint_client, complaint_app)
    for incident in (first, second):
        service.calculate(incident["incidentId"])
    service.change(
        first["incidentId"], "OVERRIDE", action(service, first["incidentId"], score=99), ADMIN
    )
    response = service.change(
        second["incidentId"],
        "HAZARD",
        action(service, second["incidentId"], flag=True, evidenceReferences=[b["complaintId"]]),
        ADMIN,
    )
    assert response["priority"]["urgentHazard"] and response["priority"]["effectiveScore"] == 100
    login_staff(complaint_app, complaint_client)
    url = "/api/admin/incidents/priorities?limit=1"
    page = complaint_client.get(url).json()
    assert page["items"][0]["incident"]["incidentId"] == second["incidentId"]
    oldest = complaint_client.get("/api/admin/incidents/priorities?sort=oldest&limit=1").json()
    assert oldest["items"][0]["incident"]["incidentId"] == second["incidentId"]
    assert (
        complaint_client.get(
            "/api/admin/incidents/priorities?sort=oldest&limit=1&cursor=" + oldest["nextCursor"]
        ).status_code
        == 200
    )
    next_page = complaint_client.get(url + "&cursor=" + page["nextCursor"])
    assert next_page.status_code == 200 and len(next_page.json()["items"]) == 1
    service.change(
        first["incidentId"], "REMOVE_OVERRIDE", action(service, first["incidentId"]), ADMIN
    )
    assert complaint_client.get(url + "&cursor=" + page["nextCursor"]).status_code == 409
    assert (
        len(
            complaint_client.get(
                "/api/admin/incidents/priorities?urgent=true&band=CRITICAL"
            ).json()["items"]
        )
        == 1
    )
    summary = complaint_client.get("/api/admin/incidents/priorities/summary").json()
    assert summary["activeIncidents"] == 2 and summary["urgentHazards"] == 1
    assert summary["needsAssessment"] == 2  # Unassessed controls, not merely fresh-score counts.


def test_concurrent_controls_rollback_and_restart(complaint_client, complaint_app):
    report, incident = create(complaint_client, complaint_app)
    service, identity = complaint_app.state.priority_service, incident["incidentId"]
    data = action(
        service, identity, score=7, status="VERIFIED", evidenceReferences=[report["complaintId"]]
    )
    with service.repository.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_priority_history BEFORE INSERT ON priority_history "
            "BEGIN SELECT RAISE(ABORT,'Injected failure'); END"
        )
    with pytest.raises(IncidentError):
        service.change(identity, "SEVERITY", data, ADMIN)
    assert service.detail(identity)["priorityRevision"] == 0
    with service.repository.store.connection() as db:
        db.execute("DROP TRIGGER fail_priority_history")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: service.change(identity, "SEVERITY", data, ADMIN), range(2))
        )
    assert results[0] == results[1]
    restarted = create_app(complaint_app.state.settings)
    with TestClient(restarted, base_url="http://localhost:8000", headers=ORIGIN):
        assert (
            restarted.state.priority_service.detail(identity)["controls"]["severity"]["score"] == 7
        )
        assert len(restarted.state.priority_service.repository.history(identity, 50, None)[0]) == 1


def test_recalculation_jobs_eligibility_config_failure_and_lease_recovery(
    complaint_client, complaint_app, monkeypatch
):
    report, incident = create(complaint_client, complaint_app)
    service, identity = complaint_app.state.priority_service, incident["incidentId"]
    service.calculate(identity)
    with service.repository.store.connection() as db:
        db.execute("UPDATE users SET is_verified=0 WHERE id=?", (report["citizenId"],))
    assert service.detail(identity)["stale"]
    assert service.process_one()["priority"]["factors"]["reporters"]["rawValue"] == 0
    service.config = replace(service.config, weights=(0.5, 0.25, 0.15, 0.1))
    assert service.detail(identity)["stale"]
    assert service.process_one()["priority"]["algorithmVersion"] == service.config.version
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incident_priority SET needs_recalculation=1 WHERE incident_id=?", (identity,)
        )
    prepare = service.prepare
    monkeypatch.setattr(
        service, "prepare", lambda *args: (_ for _ in ()).throw(RuntimeError("injected"))
    )
    assert service.process_one()["state"] == "RETRY"
    monkeypatch.setattr(service, "prepare", prepare)
    assert service.process_one() is None
    with service.repository.store.connection() as db:
        db.execute("UPDATE incident_priority SET available_at=0 WHERE incident_id=?", (identity,))
    assert service.process_one()["priority"]


@pytest.mark.parametrize(
    "role,expected", [(None, 401), (Role.CITIZEN, 403), (Role.OFFICER, 403), (Role.ADMIN, 200)]
)
def test_priority_all_routes_rbac(complaint_app, role, expected):
    with TestClient(complaint_app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        if role:
            login_staff(complaint_app, client, role)
        identity = str(uuid4())
        for path in ("/api/admin/incidents/priorities", "/api/admin/incidents/priorities/summary"):
            assert client.get(path).status_code == expected
        for suffix in ("priority", "priority/history"):
            assert client.get(f"/api/admin/incidents/{identity}/{suffix}").status_code == (
                404 if role == Role.ADMIN else expected
            )
        data = {
            "operationId": str(uuid4()),
            "expectedIncidentVersion": 1,
            "expectedPriorityRevision": 0,
            "confirmed": True,
            "reason": "Valid administrative correction reason",
        }
        for method, suffix, extras in (
            ("post", "priority/recalculate", {}),
            ("patch", "severity", {"score": 4, "status": "PROVISIONAL"}),
            ("patch", "public-impact", {"score": 4, "status": "PROVISIONAL"}),
            ("patch", "hazard-review", {"flag": False}),
            ("post", "priority/override", {"score": 60}),
            ("delete", "priority/override", {}),
        ):
            response = client.request(
                method, f"/api/admin/incidents/{identity}/{suffix}", json=data | extras
            )
            assert response.status_code == (404 if role == Role.ADMIN else expected), response.text


def test_cli_read_only_backfill_and_resume(complaint_client, complaint_app):
    _, incident = create(complaint_client, complaint_app)
    path = complaint_app.state.settings.local_db_path
    environment = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "LOCAL_DB_PATH": str(path),
        "LOCAL_EVIDENCE_ROOT": str(complaint_app.state.settings.local_evidence_root),
    }
    command = [sys.executable, "-m", "app.scripts.recalculate_priorities", "--batch-size", "1"]
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    dry = subprocess.run(
        command + ["--dry-run"], env=environment, capture_output=True, text=True, check=True
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert json.loads(dry.stdout.splitlines()[-1])["processed"] == 1
    subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert not complaint_app.state.priority_service.detail(incident["incidentId"])["stale"]
    run = subprocess.run(
        command + ["--stale-only"], env=environment, capture_output=True, text=True, check=True
    )
    assert json.loads(run.stdout.splitlines()[-1])["skipped"] == 1


def test_schema5_migration_preserves_accounts_incidents_memberships_and_evidence(
    complaint_client, complaint_app
):
    create(complaint_client, complaint_app, images=True)
    store = complaint_app.state.auth_service.store
    tables = (
        "users",
        "sessions",
        "complaints",
        "complaint_images",
        "incidents",
        "incident_operations",
        "incident_membership_events",
        "incident_audit",
    )
    with store.connection() as db:
        before = {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")] for table in tables
        }
        triggers = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'priority_%'"
            )
        ]
        for name in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        db.executescript(
            "DROP TABLE priority_history; DROP TABLE incident_priority; "
            "DROP TABLE priority_meta; PRAGMA user_version=5;"
        )
    store.initialize()
    store.initialize()
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert before == {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")] for table in tables
        }
        assert (
            db.execute(
                "SELECT count(*) FROM incident_priority WHERE needs_recalculation=1"
            ).fetchone()[0]
            == 1
        )


def test_older_calculation_cannot_replace_newer_result_and_time_invalidates_cursor(
    complaint_client, complaint_app
):
    service = complaint_app.state.priority_service
    _, incident = create(complaint_client, complaint_app)
    create(complaint_client, complaint_app)
    identity = incident["incidentId"]
    snapshot = service.repository.snapshot(identity)
    fixed = datetime.now(UTC)
    service.clock = lambda: fixed
    result, facts, fingerprint, due = service.prepare(snapshot, snapshot.record["controls"], fixed)
    old = PriorityCommit(
        snapshot,
        result,
        snapshot.record["controls"],
        fingerprint,
        facts,
        due,
        ADMIN,
        "Earlier calculation snapshot",
    )
    service.calculate(identity)
    with pytest.raises(IncidentError, match="changed"):
        service.repository.commit(old)
    other = next(i for i in service.repository.batch("", 50) if i != identity)
    service.calculate(other)
    login_staff(complaint_app, complaint_client)
    page = complaint_client.get("/api/admin/incidents/priorities?limit=1").json()
    assert page["nextCursor"]
    fixed += timedelta(seconds=61)
    assert (
        complaint_client.get(
            "/api/admin/incidents/priorities?limit=1&cursor=" + page["nextCursor"]
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "kind,extra",
    [
        ("severity", {"status": "VERIFIED", "score": 8, "evidenceReferences": []}),
        ("severity", {"status": "PROVISIONAL", "score": 7}),
        ("severity", {"status": "UNASSESSED", "score": 3}),
        ("severity", {"status": "VERIFIED", "score": 11}),
        ("public-impact", {"status": "PROVISIONAL", "score": -1}),
        ("hazard-review", {"flag": True}),
        ("priority/override", {"score": 101}),
        ("priority/override", {"score": 70, "expiresAt": "invalid"}),
        ("priority/override", {"score": 70, "expiresAt": "2027-01-01T00:00:00"}),
        ("priority/override", {"score": 70, "expiresAt": "2000-01-01T00:00:00Z"}),
    ],
)
def test_invalid_controls_rejected_without_partial_state(
    complaint_client, complaint_app, kind, extra
):
    _, incident = create(complaint_client, complaint_app)
    service, identity = complaint_app.state.priority_service, incident["incidentId"]
    login_staff(complaint_app, complaint_client)
    method = "post" if kind == "priority/override" else "patch"
    response = complaint_client.request(
        method, f"/api/admin/incidents/{identity}/{kind}", json=action(service, identity, **extra)
    )
    assert response.status_code == 422, response.text
    assert service.detail(identity)["priorityRevision"] == 0


def test_foreign_evidence_csrf_and_citizen_privacy(complaint_client, complaint_app):
    a, first = create(complaint_client, complaint_app)
    b, second = create(complaint_client, complaint_app, another=True)
    service, identity = complaint_app.state.priority_service, first["incidentId"]
    assert complaint_client.get(f"/api/complaints/{a['complaintId']}/incident").status_code == 404
    login_staff(complaint_app, complaint_client)
    data = action(
        service, identity, status="VERIFIED", score=8, evidenceReferences=[b["complaintId"]]
    )
    url = f"/api/admin/incidents/{identity}/severity"
    assert complaint_client.patch(url, json=data).status_code == 422
    data["evidenceReferences"] = [a["complaintId"]]
    assert (
        complaint_client.patch(
            url, json=data, headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert service.detail(identity)["priorityRevision"] == 0
    assert (
        complaint_client.get(f"/api/public/incidents/{second['incidentId']}/priority").status_code
        == 404
    )
