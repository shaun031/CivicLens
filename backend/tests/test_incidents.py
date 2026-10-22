import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_complaints import ORIGIN, fields, register_login, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import login_staff

from app.main import create_app
from app.models.incident import Actor, IncidentError
from app.models.user import Role
from app.scripts.evaluate_matching import synthetic_image
from app.services.incident_reconciliation import reconcile

ADMIN = Actor("trusted-test-admin", "ADMIN")


def test_clustering_lease_recovery_rerun_and_stale_worker_cannot_finish(
    complaint_client, complaint_app
):
    item = submit(complaint_client).json()
    repository = complaint_app.state.incident_service.repository
    identity = item["complaintId"]
    first = repository.claim(identity)
    assert first and repository.claim(identity) is None
    repository.enqueue(identity)  # Recheck requested during a running lease must survive.
    repository.finish_job(identity, first[1], {"decision": "REVIEW_ONLY"})
    assert repository.job(identity)["state"] == "PENDING"
    second = repository.claim(identity)
    with repository.store.connection() as db:
        db.execute("UPDATE clustering_jobs SET available_at=0 WHERE source_id=?", (identity,))
    third = repository.claim(identity)
    assert second[1] != third[1]
    repository.finish_job(identity, second[1], {"decision": "STALE"})
    assert repository.job(identity)["state"] == "RUNNING"
    repository.fail_job(identity, third[1], "InjectedFailure")
    assert repository.job(identity)["state"] == "RETRY"
    assert repository.claim(identity) is None
    repository.enqueue(identity)
    assert (
        complaint_app.state.incident_service.process_one(identity)["decision"]
        == "KEEP_SEPARATE_REVIEW"
    )
    assert repository.job(identity)["state"] == "COMPLETE"


def test_simultaneous_singleton_creation_has_one_incident_and_one_event(
    complaint_client, complaint_app
):
    item = submit(complaint_client).json()
    service = complaint_app.state.incident_service
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.ensure_singleton(item["complaintId"]), range(4)))
    assert len({r["incidentId"] for r in results}) == 1
    with service.repository.store.connection() as db:
        assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM incident_membership_events").fetchone()[0] == 1


def test_conflicting_admin_merges_have_one_winner_without_partial_memberships(
    complaint_client, complaint_app
):
    service = complaint_app.state.incident_service
    report, source = create(complaint_client, complaint_app)
    _, one = create(complaint_client, complaint_app)
    _, two = create(complaint_client, complaint_app)
    barrier = threading.Barrier(2)

    def change(target):
        barrier.wait(5)
        try:
            return service.mutate("MERGE", correction(source, target), ADMIN)
        except IncidentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, [one, two]))
    assert len([r for r in results if isinstance(r, dict)]) == 1 and 409 in results
    assert service.require_member(report["complaintId"]).complaint.incidentId in {
        one["incidentId"],
        two["incidentId"],
    }
    assert sorted(len(service.members(i["incidentId"])) for i in [source, one, two]) == [0, 1, 2]


def test_member_cap_and_independent_reconciliation_cursors(complaint_client, complaint_app):
    service = complaint_app.state.incident_service
    _, a = create(complaint_client, complaint_app)
    _, b = create(complaint_client, complaint_app)
    _, c = create(complaint_client, complaint_app)
    service.config = replace(service.config, max_members=2)
    merged = service.mutate("MERGE", correction(b, a), ADMIN)
    with pytest.raises(IncidentError, match="bounded"):
        service.mutate("MERGE", correction(c, merged), ADMIN)
    report = reconcile(service, limit=1)
    second = reconcile(
        service,
        limit=1,
        after=report["nextComplaintAfter"],
        incident_after=report["nextIncidentAfter"],
    )
    assert second["nextComplaintAfter"] > report["nextComplaintAfter"]
    assert second["nextIncidentAfter"] > report["nextIncidentAfter"]


def create(client, app, *, another=False, images=False, **changes):
    if another:
        register_login(client, f"citizen-{uuid4()}@example.com")
    photos = [("evidence.jpg", synthetic_image(), "image/jpeg")] if images else []
    complaint = submit(client, fields(**changes), photos).json()
    assert "complaintId" in complaint, complaint
    incident = app.state.incident_service.ensure_singleton(complaint["complaintId"])
    return complaint, incident


def correction(source, target=None, **changes):
    return {
        "operationId": str(uuid4()),
        "sourceIncidentId": source["incidentId"],
        "expectedSourceVersion": source["version"],
        "confirmed": True,
        "reason": "Administrator inspected and confirmed the physical defect",
        **(
            {
                "targetIncidentId": target["incidentId"],
                "expectedTargetVersion": target["version"],
                "physicalIssueConfirmed": True,
            }
            if target
            else {}
        ),
        **changes,
    }


def test_singleton_preserves_complaint_evidence_idempotency_and_safe_owner_summary(
    complaint_client, complaint_app
):
    client, app = complaint_client, complaint_app
    complaint = submit(client, fields(), [("photo.jpg", synthetic_image(), "image/jpeg")]).json()
    before = app.state.complaint_service.repository.get(
        complaint["complaintId"], complaint["citizenId"]
    )
    incident = app.state.incident_service.ensure_singleton(complaint["complaintId"])
    assert app.state.incident_service.ensure_singleton(complaint["complaintId"]) == incident
    after = app.state.complaint_service.repository.get(
        complaint["complaintId"], complaint["citizenId"]
    )
    assert before.model_dump(exclude={"incidentId"}) == after.model_dump(exclude={"incidentId"})
    assert incident["totalComplaintCount"] == incident["uniqueReporterCount"] == 1
    assert incident["latitude"] == complaint["latitude"] and incident["status"] == "OPEN"
    response = client.get(f"/api/complaints/{complaint['complaintId']}/incident")
    assert response.status_code == 200
    assert set(response.json()) == {"incidentId", "category", "status", "processing"}
    assert (
        "totalComplaintCount" not in response.text and "canonicalDescription" not in response.text
    )
    assert (
        client.get(
            f"/api/complaints/{complaint['complaintId']}/images/{complaint['images'][0]['imageId']}"
        ).status_code
        == 200
    )
    with app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM incident_membership_events").fetchone()[0] == 1


def test_manual_merge_split_unlink_move_counts_history_aliases_and_restart(
    complaint_client, complaint_app
):
    client, app = complaint_client, complaint_app
    service = app.state.incident_service
    a, first = create(client, app, images=True)
    b, second = create(client, app, another=True, images=True)
    c, third = create(client, app)  # Same reporter as B.
    merged = service.mutate("MERGE", correction(second, first), ADMIN)
    data = correction(third, merged)
    combined = service.mutate("MERGE", data, ADMIN)
    assert combined["totalComplaintCount"] == 3 and combined["uniqueReporterCount"] == 2
    assert service.mutate("MERGE", data, ADMIN) == combined
    assert service.resolve(second["incidentId"])[0].incidentId == first["incidentId"]
    split = service.mutate(
        "SPLIT", correction(combined, complaintIds=[b["complaintId"], c["complaintId"]]), ADMIN
    )
    assert split["totalComplaintCount"] == 2 and split["uniqueReporterCount"] == 1
    detached = service.mutate("UNLINK", correction(split, complaintIds=[c["complaintId"]]), ADMIN)
    assert detached["totalComplaintCount"] == detached["uniqueReporterCount"] == 1
    remaining = service.require(split["incidentId"]).model_dump(mode="json")
    moved = service.mutate(
        "MANUAL_LINK", correction(detached, remaining, complaintId=c["complaintId"]), ADMIN
    )
    assert moved["totalComplaintCount"] == 2 and moved["uniqueReporterCount"] == 1
    assert service.require(first["incidentId"]).totalComplaintCount == 1
    with service.repository.store.connection() as db:
        assert db.execute("SELECT count(*) FROM complaints").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM complaint_images").fetchone()[0] == 2
        assert (
            db.execute(
                "SELECT count(*) FROM incident_membership_events WHERE operation='MERGE'"
            ).fetchone()[0]
            == 2
        )
        assert all(row[0] == "SUBMITTED" for row in db.execute("SELECT status FROM complaints"))
    restarted = create_app(app.state.settings)
    with TestClient(restarted, base_url="http://localhost:8000", headers=ORIGIN):
        assert (
            restarted.state.incident_service.require(moved["incidentId"]).totalComplaintCount == 2
        )
        assert restarted.state.incident_service.repository.history(first["incidentId"], 50, None)[0]


@pytest.mark.parametrize(
    "change",
    [
        "category",
        "distance",
        "source_version",
        "target_version",
        "confirmed",
        "physical",
        "reason",
        "cycle",
    ],
)
def test_manual_safety_rejections_are_atomic(complaint_client, complaint_app, change):
    service = complaint_app.state.incident_service
    _, a = create(complaint_client, complaint_app)
    _, b = create(
        complaint_client,
        complaint_app,
        category="GARBAGE" if change == "category" else "POTHOLE",
        latitude="13.0" if change == "distance" else "12.97161",
    )
    data = correction(b, a)
    if change == "source_version":
        data["expectedSourceVersion"] += 1
    if change == "target_version":
        data["expectedTargetVersion"] += 1
    if change == "confirmed":
        data["confirmed"] = False
    if change == "physical":
        data["physicalIssueConfirmed"] = False
    if change == "reason":
        data["reason"] = "short"
    if change == "cycle":
        data["targetIncidentId"] = b["incidentId"]
    with pytest.raises(IncidentError):
        service.mutate("MERGE", data, ADMIN)
    assert service.require(a["incidentId"]).totalComplaintCount == 1
    assert service.require(b["incidentId"]).totalComplaintCount == 1


def test_reporters_are_distinct_verified_active_citizens_and_repaired(
    complaint_client, complaint_app
):
    service = complaint_app.state.incident_service
    complaints = [create(complaint_client, complaint_app) for _ in range(3)]
    target = complaints[0][1]
    for _, source in complaints[1:]:
        target = service.mutate("MERGE", correction(source, target), ADMIN)
    assert target["totalComplaintCount"] == 3 and target["uniqueReporterCount"] == 1
    c, source = create(complaint_client, complaint_app, another=True)
    target = service.mutate("MERGE", correction(source, target), ADMIN)
    assert target["uniqueReporterCount"] == 2
    with service.repository.store.connection() as db:
        db.execute("UPDATE users SET is_verified=0 WHERE id=?", (c["citizenId"],))
    report = reconcile(service, limit=100, repair=True)
    assert report["repaired"]
    assert service.require(target["incidentId"]).uniqueReporterCount == 1
    assert reconcile(service, limit=100)["issues"] == []


@pytest.mark.parametrize(
    "mode,images,expected",
    [
        ("REVIEW_ONLY", True, False),
        ("CONSERVATIVE_AUTO_LINK", True, True),
        ("CONSERVATIVE_AUTO_LINK", False, False),
    ],
)
def test_modes_strict_auto_and_missing_images(
    complaint_client, complaint_app, mode, images, expected
):
    client, app = complaint_client, complaint_app
    a, first = create(client, app, images=images)
    b, second = create(client, app, another=True, images=images, latitude="12.97161")
    matching, service = app.state.duplicate_detection_service, app.state.incident_service
    service.config = replace(service.config, mode=mode)
    matching.process_one(b["complaintId"])
    report = service.process_one(b["complaintId"])
    assert report and "errorCategory" not in report, report
    linked = (
        service.require_member(a["complaintId"]).complaint.incidentId
        == service.require_member(b["complaintId"]).complaint.incidentId
    )
    assert linked == expected
    if expected:
        assert report["decision"] == "AUTOMATIC_LINK"
        assert service.require(first["incidentId"]).uniqueReporterCount == 2
        assert service.require(second["incidentId"]).status == "SUPERSEDED"


@pytest.mark.parametrize(
    "safeguard",
    [
        "dismissed",
        "competing",
        "nearby_distinct",
        "resolved",
        "stale_model",
        "incomplete",
        "transitive",
    ],
)
def test_auto_safeguards_keep_reports_separate(complaint_client, complaint_app, safeguard):
    app, client = complaint_app, complaint_client
    a, first = create(client, app, images=True)
    b, second = create(
        client,
        app,
        images=True,
        latitude="12.97177" if safeguard == "nearby_distinct" else "12.97161",
    )
    service, matching = app.state.incident_service, app.state.duplicate_detection_service
    service.config = replace(service.config, mode="CONSERVATIVE_AUTO_LINK")
    if safeguard == "competing":
        create(client, app, images=True, latitude="12.97162")
    if safeguard == "transitive":
        c, third = create(client, app, images=True, latitude="12.97168")
        service.mutate("MERGE", correction(third, first), ADMIN)
        with service.repository.store.connection() as db:
            db.execute(
                "UPDATE complaints SET latitude=12.97152 WHERE complaint_id=?", (b["complaintId"],)
            )
    matching.process_one(b["complaintId"])
    if safeguard == "dismissed":
        ids, _ = service.repository.candidates(b["complaintId"], 100)
        matching.repository.review(ids[0], "DISMISSED", ADMIN.id)
    if safeguard == "resolved":
        with service.repository.store.connection() as db:
            db.execute(
                "UPDATE incidents SET status='RESOLVED',resolved_at=updated_at WHERE incident_id=?",
                (first["incidentId"],),
            )
    if safeguard == "stale_model":
        with service.repository.store.connection() as db:
            db.execute(
                "UPDATE duplicate_candidates "
                "SET payload=json_set(payload,'$.modelVersion','old-model')"
            )
    if safeguard == "incomplete":
        with service.repository.store.connection() as db:
            db.execute(
                "UPDATE matching_jobs SET state='INCOMPLETE' WHERE source_id=?", (b["complaintId"],)
            )
    report = service.process_one(b["complaintId"])
    assert report and "errorCategory" not in report, report
    assert service.require_member(b["complaintId"]).complaint.incidentId == second["incidentId"]


def test_rollback_idempotency_fingerprint_concurrency_and_lock_retry(
    complaint_client, complaint_app
):
    service = complaint_app.state.incident_service
    a, first = create(complaint_client, complaint_app)
    b, second = create(complaint_client, complaint_app)
    with service.repository.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_incident_audit BEFORE INSERT ON incident_membership_events "
            "BEGIN SELECT RAISE(ABORT,'injected rollback'); END"
        )
    request = correction(second, first)
    with pytest.raises(IncidentError):
        service.mutate("MERGE", request, ADMIN)
    assert service.require_member(b["complaintId"]).complaint.incidentId == second["incidentId"]
    with service.repository.store.connection() as db:
        db.execute("DROP TRIGGER fail_incident_audit")

    def merge():
        try:
            return service.mutate("MERGE", request, ADMIN)
        except IncidentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: merge(), range(2)))
    assert all(isinstance(result, dict) for result in results)
    assert service.require(first["incidentId"]).totalComplaintCount == 2
    with pytest.raises(IncidentError):
        service.mutate(
            "MERGE", request | {"reason": "Different input reusing an operation ID"}, ADMIN
        )
    c, third = create(complaint_client, complaint_app)
    started = threading.Event()

    def locked():
        with service.repository.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            started.set()
            time.sleep(0.4)

    with ThreadPoolExecutor(max_workers=2) as pool:
        lock = pool.submit(locked)
        started.wait(2)
        result = service.mutate(
            "MERGE",
            correction(third, service.require(first["incidentId"]).model_dump(mode="json")),
            ADMIN,
        )
        lock.result()
    assert result["totalComplaintCount"] == 3


@pytest.mark.parametrize(
    "role,expected", [(None, 401), (Role.CITIZEN, 403), (Role.OFFICER, 403), (Role.ADMIN, 200)]
)
def test_incident_endpoint_rbac(complaint_app, role, expected):
    with TestClient(complaint_app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        if role:
            login_staff(complaint_app, client, role)
        identity = str(uuid4())
        for path in ("/api/admin/incidents", "/api/admin/incidents/summary"):
            assert client.get(path).status_code == expected
        for path in (
            f"/api/admin/incidents/{identity}",
            f"/api/admin/incidents/{identity}/complaints",
            f"/api/admin/incidents/{identity}/history",
        ):
            assert client.get(path).status_code == (404 if role == Role.ADMIN else expected)
        data = {
            "operationId": str(uuid4()),
            "sourceIncidentId": identity,
            "expectedSourceVersion": 1,
            "confirmed": True,
            "reason": "Authorized correction test reason",
            "complaintIds": [identity],
        }
        for kind in ("split", "unlink-complaint"):
            assert client.post(
                f"/api/admin/incidents/{identity}/{kind}", json=data
            ).status_code == (404 if role == Role.ADMIN else expected)


def test_admin_apis_private_photos_csrf_versions_pagination_and_analytics(
    complaint_client, complaint_app
):
    client, app = complaint_client, complaint_app
    a, first = create(client, app, images=True)
    b, second = create(client, app, another=True, images=True)
    assert client.get(f"/api/complaints/{a['complaintId']}/incident").status_code == 404
    login_staff(app, client)
    request = correction(second, first)
    assert (
        client.post(
            "/api/admin/incidents/merge", json=request, headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    result = client.post("/api/admin/incidents/merge", json=request)
    assert result.status_code == 200, result.text
    assert client.post("/api/admin/incidents/merge", json=request).json() == result.json()
    identity = result.json()["incidentId"]
    members = client.get(f"/api/admin/incidents/{identity}/complaints").json()["items"]
    assert len(members) == 2 and "citizenId" not in json.dumps(members)
    assert "storageKey" not in json.dumps(members)
    assert client.get("/api" + members[0]["images"][0]["url"]).status_code == 200
    assert (
        client.get(f"/api/admin/incidents/{second['incidentId']}").json()["incidentId"] == identity
    )
    summary = client.get("/api/admin/incidents/summary").json()
    assert summary["activeIncidents"] == summary["multiReportIncidents"] == 1
    assert summary["linkedComplaints"] == 2 and summary["mergedIncidentRecords"] == 1
    page = client.get("/api/admin/incidents", params={"status": "MERGED", "limit": 1}).json()
    assert page["items"][0]["incidentId"] == second["incidentId"]
    assert client.get(f"/api/admin/incidents/{identity}/history").json()["items"]
    assert (
        client.post(
            f"/api/admin/incidents/{identity}/split",
            json=correction(first, complaintIds=[b["complaintId"]]),
        ).status_code
        == 409
    )


def test_cli_dry_run_backfill_resume_reconcile_and_checksum(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    a = submit(client).json()
    b = submit(client).json()
    settings = app.state.settings
    env = os.environ | {
        "APP_ENV": "test",
        "AUTH_PROVIDER": "local",
        "COMPLAINT_PROVIDER": "sqlite",
        "EVIDENCE_PROVIDER": "local",
        "LOCAL_DB_PATH": str(settings.local_db_path),
        "LOCAL_EVIDENCE_ROOT": str(settings.local_evidence_root),
        "DEBUG": "false",
    }

    def command(module, *arguments):
        result = subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr
        return [json.loads(line) for line in result.stdout.splitlines()]

    before = hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest()
    assert command("app.scripts.cluster_existing_complaints", "--dry-run")[0]["unassigned"] == 2
    assert command("app.scripts.reconcile_incidents", "--dry-run")[0]["complaintsChecked"] == 2
    assert hashlib.sha256(settings.local_db_path.read_bytes()).hexdigest() == before
    page = command("app.scripts.cluster_existing_complaints", "--limit", "1")[-1]
    assert page["processed"] == 1
    assert (
        command(
            "app.scripts.cluster_existing_complaints", "--limit", "1", "--after", page["nextAfter"]
        )[-1]["processed"]
        == 1
    )
    assert (
        app.state.incident_service.require_member(a["complaintId"]).complaint.incidentId
        != app.state.incident_service.require_member(b["complaintId"]).complaint.incidentId
    )
    assert command("app.scripts.reconcile_incidents")[0]["issues"] == []


def test_reconcile_counts_invalid_references_empty_incidents_and_cycles(
    complaint_client, complaint_app
):
    service = complaint_app.state.incident_service
    a, first = create(complaint_client, complaint_app)
    b, second = create(complaint_client, complaint_app)
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE incidents SET total_complaint_count=9,unique_reporter_count=0 "
            "WHERE incident_id=?",
            (first["incidentId"],),
        )
    assert reconcile(service, limit=100, repair=True)["repaired"]
    assert service.require(first["incidentId"]).totalComplaintCount == 1
    with service.repository.store.connection() as db:
        db.execute("DROP TRIGGER complaints_valid_incident_update")
        db.execute(
            "UPDATE complaints SET incident_id=? WHERE complaint_id=?",
            (str(uuid4()), b["complaintId"]),
        )
    result = reconcile(service, limit=100, repair=True)
    assert any(row["kind"] == "INVALID_ACTIVE_REFERENCE" for row in result["repaired"])
    assert service.require_member(b["complaintId"]).complaint.incidentId != second["incidentId"]
    assert service.require(second["incidentId"]).status == "SUPERSEDED"


def test_phase4_to5_additive_migration_preserves_all_original_rows(complaint_client, complaint_app):
    submit(complaint_client, fields(), [("evidence.jpg", synthetic_image(), "image/jpeg")])
    store = complaint_app.state.auth_service.store
    tables = ("users", "sessions", "complaints", "complaint_images", "complaint_requests")
    with store.connection() as db:
        original = {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")] for table in tables
        }
        # Only this disposable fixture reconstructs the immediate pre-Phase7 schema.
        db.executescript(
            "DROP TRIGGER complaints_clustering_outbox; "
            "DROP TRIGGER complaints_valid_incident_insert; "
            "DROP TRIGGER complaints_valid_incident_update; "
            "DROP TABLE incident_membership_events; DROP TABLE incident_audit; "
            "DROP TABLE incident_operations; DROP TABLE clustering_jobs; DROP TABLE incidents; "
            "PRAGMA user_version=4;"
        )
    store.initialize()
    store.initialize()
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert original == {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")] for table in tables
        }
        assert db.execute("SELECT count(*) FROM clustering_jobs").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 0


def test_alias_cycles_are_bounded_and_reported_not_silently_repaired(
    complaint_client, complaint_app
):
    service = complaint_app.state.incident_service
    _, first = create(complaint_client, complaint_app)
    _, second = create(complaint_client, complaint_app)
    with service.repository.store.connection() as db:
        for old, target in [(first, second), (second, first)]:
            db.execute(
                "UPDATE incidents SET status='MERGED',total_complaint_count=0,"
                "unique_reporter_count=0,merged_into_incident_id=? WHERE incident_id=?",
                (target["incidentId"], old["incidentId"]),
            )
    with pytest.raises(IncidentError, match="cycle"):
        service.resolve(first["incidentId"])
    issues = reconcile(service)["issues"]
    assert len([i for i in issues if i["kind"] == "ALIAS_OR_MEMBERSHIP_ERROR"]) == 2


def test_clustering_failure_keeps_saved_report_and_photos_then_recovers(
    complaint_client, complaint_app, monkeypatch
):
    service = complaint_app.state.incident_service
    item, incident = create(complaint_client, complaint_app, images=True)
    original = service.recommendations
    monkeypatch.setattr(service, "recommendations", MagicFailure())
    report = service.process_one(item["complaintId"])
    assert report == {"state": "RETRY", "errorCategory": "RuntimeError"}
    assert service.require(incident["incidentId"]).totalComplaintCount == 1
    assert complaint_client.get("/api" + item["images"][0]["url"]).status_code == 200
    monkeypatch.setattr(service, "recommendations", original)
    service.repository.enqueue(item["complaintId"])
    assert service.process_one(item["complaintId"])["decision"] == "KEEP_SEPARATE_REVIEW"


class MagicFailure:
    def __call__(self, *args):
        raise RuntimeError("Injected clustering failure after durable submission")


def test_dismissal_during_auto_commit_is_transactionally_honored(
    complaint_client, complaint_app, monkeypatch
):
    service = complaint_app.state.incident_service
    a, first = create(complaint_client, complaint_app, images=True)
    b, second = create(complaint_client, complaint_app, another=True, images=True)
    service.config = replace(service.config, mode="CONSERVATIVE_AUTO_LINK")
    service.matching.process_one(b["complaintId"])
    candidate = service.repository.candidates(b["complaintId"], 5)[0][0]
    commit = service.repository.commit

    def concurrent_review(plan):
        if plan.operation == "AUTOMATIC_LINK":
            service.matching.repository.review(candidate, "DISMISSED", ADMIN.id)
        return commit(plan)

    monkeypatch.setattr(service.repository, "commit", concurrent_review)
    assert service.process_one(b["complaintId"])["state"] == "RETRY"
    assert service.require_member(a["complaintId"]).complaint.incidentId == first["incidentId"]
    assert service.require_member(b["complaintId"]).complaint.incidentId == second["incidentId"]
    service.repository.enqueue(b["complaintId"])
    assert service.process_one(b["complaintId"])["decision"] == "KEEP_SEPARATE_REVIEW"


def test_evidence_budget_exhaustion_holds_for_review(complaint_client, complaint_app, monkeypatch):
    service = complaint_app.state.incident_service
    _, first = create(complaint_client, complaint_app, images=True)
    b, _ = create(complaint_client, complaint_app, images=True)
    service.config = replace(service.config, mode="CONSERVATIVE_AUTO_LINK")
    service.matching.process_one(b["complaintId"])
    monkeypatch.setattr("app.services.incident_service.MAX_SCORE_SNAPSHOT_BYTES", 1)
    report = service.process_one(b["complaintId"])
    assert report["incomplete"] and report["decision"] == "KEEP_SEPARATE_REVIEW"
    assert report["recommendations"][0]["evidence"] == []
    assert service.require(first["incidentId"]).totalComplaintCount == 1
