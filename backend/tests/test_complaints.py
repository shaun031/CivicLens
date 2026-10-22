import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.models.complaint import ComplaintInput
from app.repositories.complaint_repository import RepositoryUnavailable, RepositoryUncertain

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Local integration test passphrase 2048"


def image_bytes(format="PNG", exif=None):
    data = io.BytesIO()
    image = Image.new("RGB", (20, 10), "blue")
    image.save(data, format=format, **({"exif": exif} if exif else {}))
    return data.getvalue()


def fields(**updates):
    return {
        "title": "Large pothole beside the library",
        "description": "The road has a large uneven patch that is dangerous for cyclists.",
        "category": "POTHOLE",
        "reportedSeverity": "HIGH",
        "latitude": "12.9716",
        "longitude": "77.5946",
        "landmark": "Community library",
        "addressLabel": "Library Road",
        **updates,
    }


def register_login(client, email="citizen@example.com"):
    response = client.post(
        "/api/auth/register",
        json={
            "display_name": "Test Citizen",
            "email": email,
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert response.status_code == 201
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    return response.json()["id"]


@pytest.fixture
def complaint_app(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        debug=False,
        local_db_path=tmp_path / "auth.db",
        local_evidence_root=tmp_path / "private",
        complaint_rate_limit=100,
    )
    return create_app(settings)


@pytest.fixture
def complaint_client(complaint_app):
    with TestClient(complaint_app, base_url="http://localhost:8000", headers=ORIGIN) as client:
        register_login(client)
        yield client


def submit(client, data=None, images=None, key=None):
    # A form with no files must still use multipart, not URL-encoded data.
    parts = [(name, (None, value)) for name, value in (data or fields()).items()]
    parts += [("images", image) for image in (images or [])]
    return client.post(
        "/api/complaints", files=parts, headers={"Idempotency-Key": key or str(uuid4())}
    )


def test_create_persisted_owner_timestamp_status_and_summary(complaint_client, complaint_app):
    client = complaint_client
    response = submit(client)
    assert response.status_code == 201, response.text
    data = response.json()
    UUID(data["complaintId"])
    assert data["citizenId"] == client.get("/api/auth/me").json()["id"]
    assert data["status"] == "SUBMITTED" and data["incidentId"] is None
    assert data["category"] == "POTHOLE" and data["reportedSeverity"] == "HIGH"
    assert data["latitude"] == 12.9716 and data["longitude"] == 77.5946
    assert data["createdAt"].endswith("Z") and data["createdAt"] == data["updatedAt"]
    assert client.get(f"/api/complaints/{data['complaintId']}").json() == data
    assert client.get("/api/complaints").json()["items"] == [data]
    summary = client.get("/api/complaints/summary").json()
    assert summary["total"] == 1 and summary["counts"] == {"SUBMITTED": 1}
    with closing(sqlite3.connect(complaint_app.state.settings.local_db_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 1
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8


@pytest.mark.parametrize(
    "updates",
    [
        {"title": "short"},
        {"title": "x" * 151},
        {"description": "short"},
        {"description": "x" * 2001},
        {"category": "STREETLIGHT"},
        {"reportedSeverity": "URGENT"},
        {"latitude": "91"},
        {"longitude": "-181"},
        {"latitude": "NaN"},
        {"longitude": "Infinity"},
        {"citizenId": "someone-else"},
        {"status": "RESOLVED"},
        {"incidentId": "fake-incident"},
    ],
)
def test_rejects_invalid_fields(complaint_client, updates):
    assert submit(complaint_client, fields(**updates)).status_code in (400, 422)
    assert complaint_client.get("/api/complaints").json()["items"] == []


@pytest.mark.parametrize(
    "missing", ["title", "description", "category", "reportedSeverity", "latitude", "longitude"]
)
def test_missing_required_fields(complaint_client, missing):
    data = fields()
    data.pop(missing)
    assert submit(complaint_client, data).status_code == 422


@pytest.mark.parametrize(
    "category",
    [
        "POTHOLE",
        "DAMAGED_ROAD",
        "BROKEN_STREETLIGHT",
        "GARBAGE",
        "DRAINAGE",
        "PUBLIC_PROPERTY_DAMAGE",
        "OTHER",
    ],
)
def test_canonical_categories_optional_landmark(complaint_client, category):
    data = fields(category=category)
    data.pop("landmark")
    data.pop("addressLabel")
    result = submit(complaint_client, data)
    assert result.status_code == 201
    assert result.json()["landmark"] is None


def test_unauthenticated_and_privileged_roles_cannot_access_complaints(
    complaint_client, complaint_app
):
    client = complaint_client
    for role in ("OFFICER", "ADMIN"):
        with complaint_app.state.auth_service.store.connection() as db:
            db.execute("UPDATE users SET role=?", (role,))
        assert submit(client).status_code == 403
        assert client.get("/api/complaints").status_code == 403
    client.cookies.clear()
    assert submit(client).status_code == 401
    assert client.get("/api/complaints").status_code == 401


def test_csrf_json_and_idempotency_header_validation(complaint_client):
    assert complaint_client.post("/api/complaints", json=fields()).status_code == 422
    assert (
        complaint_client.post(
            "/api/complaints", json=fields(), headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 415
    )
    complaint_client.headers["Origin"] = "https://evil.example"
    assert submit(complaint_client).status_code == 403


@pytest.mark.parametrize(
    "format,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_upload_sanitizes_and_authorized_retrieval(complaint_client, complaint_app, format, mime):
    client = complaint_client
    response = submit(client, images=[("evidence.anything", image_bytes(format), mime)])
    assert response.status_code == 201, response.text
    complaint = response.json()
    image = complaint["images"][0]
    assert "storageKey" not in image
    assert image["contentType"] == "image/jpeg"
    raw = client.get("/api" + image["url"])
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/jpeg"
    assert "no-store" in raw.headers["cache-control"]
    assert raw.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(raw.content)) as stored:
        assert stored.format == "JPEG" and not stored.getexif()
    assert len(list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))) == 1
    with complaint_app.state.auth_service.store.connection() as db:
        assert db.execute("SELECT file_size FROM complaint_images").fetchone()[0] == len(
            raw.content
        )


def test_exif_gps_removed_and_orientation_applied(complaint_client):
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private camera description"
    exif[34853] = {1: "N", 2: (12.0, 34.0, 0.0)}
    response = submit(
        complaint_client, images=[("photo.jpg", image_bytes("JPEG", exif), "image/jpeg")]
    )
    assert response.status_code == 201, response.text
    raw = complaint_client.get("/api" + response.json()["images"][0]["url"])
    with Image.open(io.BytesIO(raw.content)) as stored:
        assert stored.size == (10, 20)
        assert not stored.getexif() and "exif" not in stored.info


@pytest.mark.parametrize(
    "file,status",
    [
        (("photo.gif", b"GIF89a", "image/gif"), 415),
        (("photo.png", b"not a valid image", "image/png"), 422),
        (("../../photo.png", image_bytes(), "image/png"), 422),
        (("C:\\private\\photo.png", image_bytes(), "image/png"), 422),
        (("photo.png", image_bytes(), "image/jpeg"), 415),
        (("photo.png", b"x" * 1572865, "image/png"), 413),
    ],
)
def test_invalid_images_rejected_without_records_or_files(
    complaint_client, complaint_app, file, status
):
    assert submit(complaint_client, images=[file]).status_code == status
    assert not list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))
    assert complaint_client.get("/api/complaints").json()["items"] == []


def test_image_count_pixels_and_request_limits(complaint_client, complaint_app):
    file = ("photo.png", image_bytes(), "image/png")
    assert submit(complaint_client, images=[file] * 3).status_code == 400
    complaint_app.state.settings.max_image_pixels = 100
    assert submit(complaint_client, images=[file]).status_code == 413
    response = complaint_client.post("/api/complaints", content=b"x" * 3407873)
    assert response.status_code == 413
    assert "private" not in response.text.lower()


def test_owner_isolation_for_complaints_images_cursor_and_guessed_filters(complaint_client):
    client = complaint_client
    complaint = submit(client, images=[("photo.png", image_bytes(), "image/png")]).json()
    owner_id = complaint["citizenId"]
    client.post("/api/auth/logout")
    register_login(client, "second@example.com")
    assert client.get("/api/complaints").json()["items"] == []
    assert client.get(f"/api/complaints/{complaint['complaintId']}").status_code == 404
    assert client.get("/api" + complaint["images"][0]["url"]).status_code == 404
    assert client.get("/api/complaints", params={"citizenId": owner_id}).status_code == 422
    assert client.get(f"/api/complaints/{uuid4()}").json() == {"detail": "Complaint not found."}


def test_idempotent_retry_and_conflicting_content(complaint_client):
    key = str(uuid4())
    first = submit(complaint_client, key=key)
    retry = submit(complaint_client, key=key)
    assert first.status_code == retry.status_code == 201
    assert first.json() == retry.json()
    assert (
        submit(
            complaint_client, fields(title="A different infrastructure report"), key=key
        ).status_code
        == 409
    )
    assert len(complaint_client.get("/api/complaints").json()["items"]) == 1


def test_two_images_have_stable_creation_read_and_replay_metadata(complaint_client, complaint_app):
    photos = [
        ("one.png", image_bytes("PNG"), "image/png"),
        ("two.webp", image_bytes("WEBP"), "image/webp"),
    ]
    key = str(uuid4())
    first = submit(complaint_client, images=photos, key=key)
    assert first.status_code == 201
    assert len(first.json()["images"]) == 2
    assert submit(complaint_client, images=photos, key=key).json() == first.json()
    assert (
        complaint_client.get(f"/api/complaints/{first.json()['complaintId']}").json()
        == first.json()
    )
    assert len(list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))) == 2


def test_real_version_one_migration_keeps_credentials_and_live_session(
    complaint_client, complaint_app
):
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        previous = tuple(db.execute("SELECT id,password_hash FROM users").fetchone())
        # This is ONLY the disposable fixture database, recreating the true pre-Phase-4 schema.
        db.executescript(
            "DROP TABLE complaint_requests; DROP TABLE complaint_images; "
            "DROP TABLE complaints; PRAGMA user_version=1;"
        )
    store.initialize()
    with store.connection() as db:
        assert tuple(db.execute("SELECT id,password_hash FROM users").fetchone()) == previous
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert complaint_client.get("/api/auth/me").status_code == 200
    assert submit(complaint_client).status_code == 201


def test_local_evidence_audit_is_read_only_and_reports_missing_and_old_orphans(
    complaint_client, complaint_app, monkeypatch, capsys
):
    import os
    import time

    from app.scripts.evidence_audit import main

    complaint = submit(complaint_client, images=[("photo.png", image_bytes(), "image/png")]).json()
    storage = complaint_app.state.complaint_service.storage
    with complaint_app.state.auth_service.store.connection() as db:
        reference = db.execute("SELECT storage_key FROM complaint_images").fetchone()[0]
    storage.delete(reference)
    orphan = f"complaints/{uuid4()}/{uuid4()}.jpg"
    storage.put(orphan, b"orphan")
    os.utime(storage.path(orphan), (time.time() - 172800, time.time() - 172800))
    monkeypatch.setattr(
        "app.scripts.evidence_audit.get_settings",
        lambda: complaint_app.state.settings.model_copy(update={"app_env": "local"}),
    )
    monkeypatch.setattr("sys.argv", ["evidence_audit"])
    main()
    output = capsys.readouterr().out
    assert "MISSING referenced" in output and "UNREFERENCED candidate" in output
    assert "Nothing changed" in output
    assert storage.get(orphan) == b"orphan"
    assert complaint_client.get(f"/api/complaints/{complaint['complaintId']}").status_code == 200


def test_pagination_stable_order_and_cursor_validation(complaint_client, complaint_app):
    ids = [submit(complaint_client).json()["complaintId"] for _ in range(5)]
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute("UPDATE complaints SET created_at='2026-10-19T12:00:00.000Z'")
    found, cursor = [], None
    for _ in range(3):
        page = complaint_client.get(
            "/api/complaints", params={"limit": 2, **({"cursor": cursor} if cursor else {})}
        ).json()
        found += [item["complaintId"] for item in page["items"]]
        cursor = page["nextCursor"]
    assert found == sorted(ids, reverse=True) and cursor is None
    assert complaint_client.get("/api/complaints?cursor=malformed").status_code == 400
    assert complaint_client.get("/api/complaints?limit=10000").status_code == 422


def test_database_and_storage_failure_cleanup(complaint_client, complaint_app, monkeypatch):
    service = complaint_app.state.complaint_service

    def fail(*args):
        raise RepositoryUnavailable

    monkeypatch.setattr(service.repository, "create", fail)
    response = submit(complaint_client, images=[("photo.png", image_bytes(), "image/png")])
    assert response.status_code == 503 and "draft" in response.text
    assert not list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))
    assert complaint_client.get("/api/complaints").json()["items"] == []


def test_unexpected_errors_do_not_expose_private_paths_in_response_or_logs(
    complaint_client, complaint_app, monkeypatch, caplog
):
    secret = "private-sensitive-evidence-path.jpg"

    def fail(*args):
        raise RuntimeError(secret)

    monkeypatch.setattr(complaint_app.state.complaint_service.repository, "get", fail)
    # TestClient's default raises escaped exceptions: returning 500 proves it was absorbed safely.
    response = complaint_client.get(f"/api/complaints/{uuid4()}")
    assert response.status_code == 500 and response.json() == {"detail": "Internal server error"}
    assert secret not in response.text and secret not in caplog.text
    assert "unexpected_error" in caplog.text


def test_uncertain_commit_preserves_private_objects_for_reconciliation(
    complaint_client, complaint_app, monkeypatch
):
    def fail(*args):
        raise RepositoryUncertain

    monkeypatch.setattr(complaint_app.state.complaint_service.repository, "create", fail)
    assert (
        submit(complaint_client, images=[("photo.png", image_bytes(), "image/png")]).status_code
        == 503
    )
    assert len(list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))) == 1
    assert complaint_client.get("/api/complaints").json()["items"] == []


def test_persistent_rate_limit_does_not_block_same_request_replay(complaint_client, complaint_app):
    complaint_app.state.settings.complaint_rate_limit = 1
    key = str(uuid4())
    assert submit(complaint_client, key=key).status_code == 201
    assert submit(complaint_client, key=key).status_code == 201
    response = submit(complaint_client)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_complaint_and_photo_survive_logout_login_and_new_backend(complaint_client, complaint_app):
    response = submit(complaint_client, images=[("photo.png", image_bytes(), "image/png")]).json()
    complaint_client.post("/api/auth/logout")
    assert (
        complaint_client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    path = f"/api/complaints/{response['complaintId']}"
    assert complaint_client.get(path).status_code == 200
    new_app = create_app(complaint_app.state.settings)
    with TestClient(new_app, base_url="http://localhost:8000", headers=ORIGIN) as restarted:
        assert (
            restarted.post(
                "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        assert restarted.get(path).json() == response
        assert restarted.get("/api" + response["images"][0]["url"]).status_code == 200


def test_concurrent_same_request_creates_only_one_record(complaint_client, complaint_app):
    owner = complaint_client.get("/api/auth/me").json()["id"]
    data = ComplaintInput.model_validate(fields())
    key = str(uuid4())

    def create(_):
        from app.services.evidence_service import Upload

        return complaint_app.state.complaint_service.create(
            owner, data, [Upload(image_bytes(), "photo.png", "image/png")], key, str(uuid4())
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, range(4)))
    assert len({item.complaintId for item in results}) == 1
    assert len(list(complaint_app.state.settings.local_evidence_root.rglob("*.jpg"))) == 1


def test_streamed_actual_size_is_bounded_even_with_small_content_length(complaint_client):
    response = complaint_client.post(
        "/api/complaints",
        content=iter([b"x" * 1800000, b"y" * 1800000]),
        headers={"Content-Length": "1"},
    )
    assert response.status_code == 413


def test_evidence_key_collision_never_deletes_existing_private_data(
    complaint_client, complaint_app, monkeypatch
):
    cid, iid = uuid4(), uuid4()
    key = f"complaints/{cid}/{iid}.jpg"
    storage = complaint_app.state.complaint_service.storage
    storage.put(key, b"pre-existing-object")
    generated = iter([cid, iid])
    monkeypatch.setattr("app.services.complaint_service.uuid4", lambda: next(generated))
    assert (
        submit(complaint_client, images=[("photo.png", image_bytes(), "image/png")]).status_code
        == 503
    )
    assert storage.get(key) == b"pre-existing-object"
    assert complaint_client.get("/api/complaints").json()["items"] == []


def test_animated_images_are_rejected(complaint_client):
    stream = io.BytesIO()
    Image.new("RGB", (20, 10), "blue").save(
        stream,
        "WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (20, 10), "red")],
        duration=100,
        loop=0,
    )
    assert (
        submit(
            complaint_client, images=[("animation.webp", stream.getvalue(), "image/webp")]
        ).status_code
        == 422
    )


def test_http_api_v2_binary_multipart_and_evidence_response(complaint_client, complaint_app):
    import base64
    import json

    from mangum import Mangum

    parts = [(name, (None, value)) for name, value in fields().items()]
    parts.append(("images", ("photo.png", image_bytes(), "image/png")))
    import httpx

    encoded = httpx.Request("POST", "http://localhost/api/complaints", files=parts)
    body = encoded.read()
    event = {
        "version": "2.0",
        "routeKey": "POST /api/complaints",
        "rawPath": "/api/complaints",
        "rawQueryString": "",
        "headers": {
            "host": "localhost",
            "x-forwarded-proto": "http",
            "origin": "http://localhost:5173",
            "content-type": encoded.headers["content-type"],
            "idempotency-key": str(uuid4()),
            "cookie": "civiclens_session=" + complaint_client.cookies.get("civiclens_session"),
        },
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": "POST",
                "path": "/api/complaints",
                "sourceIp": "127.0.0.1",
                "protocol": "HTTP/1.1",
            },
        },
        "isBase64Encoded": True,
        "body": base64.b64encode(body).decode(),
    }
    adapter = Mangum(complaint_app, lifespan="off")
    created = adapter(event, {})
    assert created["statusCode"] == 201
    data = json.loads(created["body"])
    path = "/api" + data["images"][0]["url"]
    event.update(
        rawPath=path,
        routeKey="GET /api/complaints/{complaintId}/images/{imageId}",
        body="",
        isBase64Encoded=False,
    )
    event["requestContext"]["http"].update(method="GET", path=path)
    response = adapter(event, {})
    assert response["statusCode"] == 200 and response["isBase64Encoded"]
    assert base64.b64decode(response["body"]).startswith(b"\xff\xd8")


def test_additive_migration_preserves_accounts_sessions_and_complaints(
    complaint_client, complaint_app
):
    complaint = submit(complaint_client).json()
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        before = tuple(db.execute("SELECT id,password_hash FROM users").fetchone())
        db.execute("PRAGMA user_version=1")
    store.initialize()
    with store.connection() as db:
        assert tuple(db.execute("SELECT id,password_hash FROM users").fetchone()) == before
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
    assert complaint_client.get("/api/auth/me").status_code == 200
    assert complaint_client.get(f"/api/complaints/{complaint['complaintId']}").status_code == 200
