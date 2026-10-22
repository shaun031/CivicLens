"""Disposable DB recovery/diagnostics and API contract regressions."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_civic_intelligence import prepared
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import image_bytes, submit

from app.main import create_app
from app.repositories.auth_store import AuthStore
from app.scripts.audit_local_data import audit, read_only
from app.scripts.backup_local import backup, evidence_keys, verify
from app.scripts.evaluate_civiclens import family_interval, routing_experiment
from app.services.evidence_service import Upload


def test_read_only_diagnostic_and_backups_preserve_all_evidence(
    complaint_app, complaint_client, tmp_path
):
    app, client = complaint_app, complaint_client
    report = submit(client, images=[("private.png", image_bytes(), "image/png")]).json()
    incident, officer, citizen, payload = prepared(app, client)
    service = app.state.civic_intelligence_service
    attempt = service.upload_action(
        "submit", incident, payload, officer, [Upload(image_bytes(), "repair.png", "image/png")]
    )
    request = service.repository.requests(citizen)["items"][0]
    service.upload_action(
        "respond",
        request["requestId"],
        {"operationId": str(uuid4()), "expectedVersion": 1, "result": "UNSURE", "feedback": ""},
        citizen,
        [Upload(image_bytes(), "feedback.png", "image/png")],
    )
    source = app.state.settings.local_db_path
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    assert audit(source)["status"] == "PASS"
    destination = tmp_path / "backup"
    result = backup(source, app.state.settings.local_evidence_root, destination, quiesced=True)
    assert result["evidenceObjects"] == 3
    assert verify(destination)["status"] == "PASS"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    # Restore into NEW fixture paths, never over a live DB. Authentication/photo metadata survive.
    restored = create_app(
        app.state.settings.model_copy(
            update={
                "local_db_path": destination / "database.sqlite3",
                "local_evidence_root": destination / "evidence",
            }
        )
    )
    restored.state.auth_service.store.initialize()
    with restored.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM repair_verifications").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT count(*) FROM repair_attempts WHERE attempt_id=?", (attempt["attemptId"],)
            ).fetchone()[0]
            == 1
        )
        assert len(evidence_keys(db)) == 3
        assert db.execute(
            "SELECT citizen_id FROM complaints WHERE complaint_id=?", (report["complaintId"],)
        ).fetchone()
    with pytest.raises(FileExistsError):
        backup(source, app.state.settings.local_evidence_root, destination, quiesced=True)
    with pytest.raises(ValueError, match="Stop CivicLens"):
        backup(source, app.state.settings.local_evidence_root, tmp_path / "unsafe")
    # Corruption is detected, not silently accepted as a valid restoration.
    image = next((destination / "evidence").rglob("*.jpg"))
    image.write_bytes(b"controlled corruption in disposable backup")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify(destination)


def test_read_only_database_refuses_writes_and_missing_database(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    AuthStore(path).initialize()
    db = read_only(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM users")
    finally:
        db.close()
    with pytest.raises(FileNotFoundError):
        audit(tmp_path / "never-created.db")
    assert not (tmp_path / "never-created.db").exists()
    # SQLite's context manager commits/rolls back; it does NOT close the connection.
    # Verify the historical dry-run command closes its owned read handle on Windows.
    import sys

    from app.core.config import Settings
    from app.scripts import recheck_duplicates

    closed = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def close(self):
            closed.append(True)
            super().close()

    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **kw: original_connect(*a, **kw, factory=TrackingConnection)
    )
    monkeypatch.setattr(
        recheck_duplicates,
        "Settings",
        lambda: Settings(_env_file=None, app_env="test", local_db_path=path),
    )
    monkeypatch.setattr(sys, "argv", ["recheck_duplicates", "--dry-run"])
    recheck_duplicates.main()
    assert closed == [True]


def test_diagnostics_detect_count_drift_without_repairing(complaint_app, complaint_client):
    incident, _, _, _ = prepared(complaint_app, complaint_client)
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        db.execute("UPDATE incidents SET total_complaint_count=2 WHERE incident_id=?", (incident,))
    result = audit(store.path)
    assert result["status"] == "FAIL"
    assert result["checks"]["canonicalMemberCounts"]["violations"] == 1
    with store.connection() as db:
        assert (
            db.execute(
                "SELECT total_complaint_count FROM incidents WHERE incident_id=?", (incident,)
            ).fetchone()[0]
            == 2
        )


def test_reinitializing_additive_migrations_preserves_rows(complaint_app, complaint_client):
    incident, _, _, _ = prepared(complaint_app, complaint_client)
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        tables = [
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("complaint_search")
        ]
        before = {t: db.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    store.initialize()
    store.initialize()
    with store.connection() as db:
        assert {
            t: db.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables
        } == before
        assert db.execute("SELECT incident_id FROM incidents WHERE incident_id=?", (incident,))
    assert audit(store.path)["status"] == "PASS"


def test_parallel_notifications_create_one_business_side_effect(complaint_app, complaint_client):
    from app.events.schema import new_event

    app, client = complaint_app, complaint_client
    report = submit(client).json()
    event = new_event("ComplaintSubmitted", report["complaintId"])
    repo = app.state.workflow_service.repository

    def notify(_):
        repo.notify(
            event,
            report["citizenId"],
            "COMPLAINT_RECEIVED",
            "Complaint received",
            "Private synthetic test",
            "COMPLAINT",
            report["complaintId"],
            "/citizen/complaints",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(notify, range(8)))
    with repo.store.connection() as db:
        assert db.execute("SELECT count(*) FROM notifications").fetchone()[0] == 1
    assert audit(repo.store.path)["status"] == "PASS"


def test_research_bootstrap_is_seeded_and_routing_eligibility_explicit():
    from app.scripts.evaluate_intelligence import fairness_quality_experiment, repair_experiment

    rows = [
        {
            "group": str(i),
            "label": "DUPLICATE" if i % 2 else "NOT_DUPLICATE",
            "proposed": bool(i % 2),
        }
        for i in range(8)
    ]
    assert family_interval(rows, "proposed") == family_interval(rows, "proposed")
    routing = routing_experiment()
    assert routing["routingAccuracy"] == 1
    assert routing["allocationSimulation"]["invalidAssignments"] == 0
    assert routing["allocationSimulation"]["afterEligibleWorkload"] == {"a": 10, "b": 10}
    assert repair_experiment()["verificationResponseCoverage"] == 0.75
    experiments = fairness_quality_experiment()["cases"]
    assert len(experiments) == 6
    for case in experiments:
        if case["secondAreaMissingResponseAndSla"]:
            second = next(a for a in case["areas"] if a["missingWorkStart"])
            assert second["medianWorkStartHours"] is None and second["overdueRate"] is None
            assert not second["dataSufficient"]


def test_evidence_audit_does_not_misclassify_repair_objects(
    complaint_app, complaint_client, monkeypatch, capsys
):
    import sys

    from app.scripts import evidence_audit

    app = complaint_app
    incident, officer, _, payload = prepared(app, complaint_client)
    app.state.civic_intelligence_service.upload_action(
        "submit", incident, payload, officer, [Upload(image_bytes(), "repair.png", "image/png")]
    )
    settings = app.state.settings.model_copy(update={"app_env": "local"})
    monkeypatch.setattr(evidence_audit, "get_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["evidence_audit", "--minimum-age-hours", "1"])
    evidence_audit.main()
    output = capsys.readouterr().out
    assert "1 referenced, 1 stored" in output
    assert "UNREFERENCED" not in output and "MISSING" not in output
