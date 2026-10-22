import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_complaints import ORIGIN, fields, register_login, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import login_staff

from app.main import create_app
from app.models.user import Role
from app.repositories.auth_store import AuthStore
from app.scripts.evaluate_matching import synthetic_image


def pair(client, images=False):
    photos = [("evidence.jpg", synthetic_image(), "image/jpeg")] if images else []
    first = submit(client, fields(), photos).json()
    register_login(client, f"second-{uuid4()}@example.com")
    second = submit(client, fields(latitude="12.97161"), photos).json()
    return first, second


def process(app, complaint):
    service = app.state.duplicate_detection_service
    service.repository.enqueue(complaint["complaintId"])
    report = service.process_one(complaint["complaintId"])
    assert report and "errorCategory" not in report, report
    return report


def test_private_matching_admin_dismiss_review_restart_and_unchanged_complaints(
    complaint_client, complaint_app
):
    client, app = complaint_client, complaint_app
    first, second = pair(client)
    before = client.get(f"/api/complaints/{second['complaintId']}").json()
    report = process(app, second)
    assert report["compared"] == 1 and not report["incomplete"]
    assert client.get("/api/admin/duplicate-candidates").status_code == 403
    assert client.get(f"/api/complaints/{first['complaintId']}").status_code == 404
    login_staff(app, client)
    response = client.get("/api/admin/duplicate-candidates")
    assert response.status_code == 200, response.text
    candidate = response.json()["items"][0]
    assert candidate["classification"] == "STRONG_CANDIDATE"
    assert candidate["imageScore"] is None and candidate["effectiveWeights"]["image"] == 0
    identity = candidate["candidateId"]
    url = f"/api/admin/duplicate-candidates/{identity}"
    detail = client.get(url).json()
    assert len(detail["complaints"]) == 2
    assert "citizenId" not in json.dumps(detail)
    # Phase 7 initializes the processed report without accepting its P6 suggestion.
    assert (
        next(c for c in detail["complaints"] if c["complaintId"] == second["complaintId"])[
            "incidentId"
        ]
        is not None
    )
    assert client.post(url + "/dismiss").json()["reviewStatus"] == "DISMISSED"
    assert client.post(url + "/reviewed").json()["reviewStatus"] == "REVIEWED_POSSIBLE_DUPLICATE"
    assert (
        client.post(url + "/dismiss", headers={"Origin": "https://evil.invalid"}).status_code == 403
    )
    process(app, first)
    assert client.get(url).json()["reviewStatus"] == "REVIEWED_POSSIBLE_DUPLICATE"
    # Actual persisted schema and factory restart, separate from process-restart integration.
    restarted = create_app(app.state.settings)
    with TestClient(restarted, base_url="http://localhost:8000", headers=ORIGIN):
        process(restarted, second)
    with app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM duplicate_candidates").fetchone()[0] == 1
        assert (
            db.execute("SELECT COUNT(*) FROM complaints WHERE incident_id IS NOT NULL").fetchone()[
                0
            ]
            == 2
        )
        assert (
            db.execute(
                "SELECT title,description,status,created_at FROM complaints WHERE complaint_id=?",
                (second["complaintId"],),
            ).fetchone()[0]
            == before["title"]
        )


@pytest.mark.parametrize(
    "role,expected", [(None, 401), (Role.CITIZEN, 403), (Role.OFFICER, 403), (Role.ADMIN, 200)]
)
def test_all_duplicate_endpoints_deny_unrelated_roles(complaint_app, role, expected):
    app = complaint_app
    with TestClient(app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        if role:
            login_staff(app, client, role)
        identity = str(uuid4())
        for method, path in (
            ("get", "/duplicate-candidates"),
            ("get", f"/duplicate-candidates/{identity}"),
            ("get", f"/complaints/{identity}/duplicate-candidates"),
            ("post", f"/complaints/{identity}/duplicate-check"),
            ("post", f"/duplicate-candidates/{identity}/dismiss"),
            ("post", f"/duplicate-candidates/{identity}/reviewed"),
            ("get", f"/duplicate-candidates/{identity}/complaints/{identity}/images/{identity}"),
        ):
            response = getattr(client, method)("/api/admin" + path)
            assert response.status_code == (
                expected if expected != 200 or path == "/duplicate-candidates" else 404
            )


def test_private_evidence_cache_pair_scope_and_corrupt_missing_fallback(
    complaint_client, complaint_app
):
    first, second = pair(complaint_client, True)
    service = complaint_app.state.duplicate_detection_service
    process(complaint_app, second)
    login_staff(complaint_app, complaint_client)
    candidate = complaint_client.get("/api/admin/duplicate-candidates").json()["items"][0]
    detail = complaint_client.get(
        f"/api/admin/duplicate-candidates/{candidate['candidateId']}"
    ).json()
    image = detail["complaints"][0]["images"][0]
    response = complaint_client.get("/api" + image["url"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "storageKey" not in response.text and "storageKey" not in json.dumps(detail)
    wrong = image["url"].replace(detail["complaints"][0]["complaintId"], str(uuid4()))
    assert complaint_client.get("/api" + wrong).status_code == 404
    original_get = service.storage.get
    service.storage.get = lambda key: (_ for _ in ()).throw(AssertionError("Cache must be used"))
    process(complaint_app, first)
    service.storage.get = original_get
    with service.repository.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM image_fingerprints").fetchone()[0] == 2
        db.execute("DELETE FROM image_fingerprints")
    service.storage.get = lambda key: b"corrupt evidence"
    process(complaint_app, first)
    assert service.repository.candidate(candidate["candidateId"])["imageScore"] is None
    service.storage.get = original_get


def test_jobs_atomic_fail_safe_retry_lease_recovery_and_pair_concurrency(
    complaint_client, complaint_app, monkeypatch
):
    first, second = pair(complaint_client)
    service = complaint_app.state.duplicate_detection_service
    assert service.repository.job(first["complaintId"])["state"] == "PENDING"
    original = service.repository.nearby
    monkeypatch.setattr(
        service.repository, "nearby", lambda *args: (_ for _ in ()).throw(RuntimeError("fail"))
    )
    assert service.process_one(first["complaintId"])["state"] == "RETRY"
    assert service.repository.load(first["complaintId"]) is not None
    assert service.repository.job(first["complaintId"])["errorCategory"] == "RuntimeError"
    monkeypatch.setattr(service.repository, "nearby", original)
    service.repository.enqueue(first["complaintId"])
    claim = service.repository.claim(first["complaintId"])
    assert claim and service.repository.claim(first["complaintId"]) is None
    with service.repository.store.connection() as db:
        db.execute(
            "UPDATE matching_jobs SET available_at=0 WHERE source_id=?", (first["complaintId"],)
        )
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(
            pool.map(lambda row: service.process_one(row["complaintId"]), (first, second))
        )
    assert all(report and report.get("compared") == 1 for report in reports)
    with service.repository.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM duplicate_candidates").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE duplicate_candidates SET combined_score=2")


def test_indexed_private_neighbor_cells_filtering_truncation_and_admin_recheck(
    complaint_client, complaint_app
):
    first = submit(complaint_client, fields(latitude="12.99999")).json()
    second = submit(complaint_client, fields(latitude="13.00001")).json()
    submit(complaint_client, fields(latitude="13.00002", category="GARBAGE"))
    service = complaint_app.state.duplicate_detection_service
    assert process(complaint_app, second)["compared"] == 1
    third = submit(complaint_client, fields(latitude="13.00003")).json()
    service.config = replace(service.config, candidate_limit=1)
    assert process(complaint_app, second)["incomplete"]
    login_staff(complaint_app, complaint_client)
    response = complaint_client.post(
        f"/api/admin/complaints/{first['complaintId']}/duplicate-check"
    )
    assert response.status_code == 200
    assert response.json()["processing"]["state"] == "INCOMPLETE"
    service.config = replace(service.config, candidate_limit=100)
    process(complaint_app, third)
    url = "/api/admin/duplicate-candidates"
    response = complaint_client.get(url, params={"limit": 1, "sort": "score"}).json()
    assert len(response["items"]) == 1 and response["nextCursor"]
    assert (
        complaint_client.get(
            url, params={"limit": 1, "sort": "date", "cursor": response["nextCursor"]}
        ).status_code
        == 400
    )
    assert complaint_client.get(url, params={"minScore": 0.9, "maxScore": 0.1}).status_code == 422
    assert complaint_client.get(url, params={"reviewStatus": "DISMISSED"}).json()["items"] == []
    assert complaint_client.get(url, params={"q": "'; DROP TABLE users;--"}).json()["items"] == []
    assert (
        complaint_client.get(
            f"/api/admin/complaints/{third['complaintId']}/duplicate-candidates"
        ).status_code
        == 200
    )
    with service.repository.store.connection() as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM complaints INDEXED BY "
            "complaints_internal_geography WHERE latitude BETWEEN ? AND ?",
            (12.99, 13.01),
        ).fetchall()
        assert "SEARCH" in plan[0][3] and "complaints_internal_geography" in plan[0][3]


def test_version3_migration_preserves_records_and_backfills_work(complaint_client, complaint_app):
    complaint = submit(complaint_client).json()
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        records = [tuple(row) for row in db.execute("SELECT * FROM complaints")]
        db.executescript(
            "DROP TRIGGER complaints_matching_outbox; DROP TABLE image_fingerprints; "
            "DROP TABLE duplicate_candidates; DROP TABLE matching_jobs; "
            "DROP INDEX complaints_internal_geography; PRAGMA user_version=3;"
        )
    AuthStore(store.path).initialize()
    AuthStore(store.path).initialize()
    with store.connection() as db:
        assert [tuple(row) for row in db.execute("SELECT * FROM complaints")] == records
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert (
            db.execute("SELECT source_id FROM matching_jobs").fetchone()[0]
            == complaint["complaintId"]
        )
