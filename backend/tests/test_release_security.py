"""Phase13 regression group: real isolated app, no AWS/network services."""

import asyncio
import re
from uuid import uuid4

import pytest
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client

from app.core.body_limit import ComplaintBodyLimit


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/reset-password"),
        ("PATCH", "/api/profile"),
        ("POST", f"/api/admin/repairs/{uuid4()}/approve"),
        ("DELETE", f"/api/admin/incidents/{uuid4()}/priority/override"),
    ],
)
def test_ordinary_api_requests_are_bounded(complaint_client, method, path):
    response = complaint_client.request(
        method, path, content=b"x" * 65537, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_streamed_limit_does_not_trust_missing_content_length():
    called, sent = [], []
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 40000, "more_body": True},
            {"type": "http.request", "body": b"x" * 40000, "more_body": False},
            {"type": "http.disconnect"},
        ]
    )

    async def app(scope, receive, send):
        called.append(True)

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(
        ComplaintBodyLimit(app, max_bytes=3407872)(
            {"type": "http", "method": "PATCH", "path": "/api/profile", "headers": []},
            receive,
            send,
        )
    )
    assert not called
    assert sent[0]["status"] == 413


@pytest.mark.parametrize("length", ["-1", "not-an-integer", "1.5"])
def test_invalid_lengths_controlled_on_json_routes(complaint_client, length):
    response = complaint_client.post(
        "/api/auth/login", content=b"{}", headers={"Content-Length": length}
    )
    assert response.status_code == 400
    assert "Traceback" not in response.text


def test_security_headers_on_validation_authentication_and_not_found(complaint_client):
    for path in ("/api/admin/incidents", "/api/does-not-exist", "/api/complaints/not-a-uuid"):
        response = complaint_client.get(path)
        assert response.status_code in (403, 404, 422)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Request-ID"]


def test_all_private_read_routes_enforce_identity_and_staff_roles(complaint_app, complaint_client):
    client = complaint_client
    paths = complaint_app.openapi()["paths"]
    staff_paths = [
        p
        for p, methods in paths.items()
        if "get" in methods and p.startswith(("/api/admin/", "/api/officer/"))
    ]
    assert len(staff_paths) >= 40
    for path in staff_paths:
        actual = re.sub(r"\{[^}]+\}", str(uuid4()), path)
        response = client.get(actual)
        assert response.status_code == 403, (path, response.status_code, response.text)
    client.post("/api/auth/logout")
    private = [
        p
        for p, methods in paths.items()
        if "get" in methods
        and p.startswith("/api/")
        and not p.startswith("/api/public/")
        and p != "/api/health"
    ]
    for path in private:
        actual = re.sub(r"\{[^}]+\}", str(uuid4()), path)
        response = client.get(actual)
        assert response.status_code == 401, (path, response.status_code, response.text)


def test_notification_filter_contract_matches_frontend():
    from pathlib import Path
    from typing import get_args

    from app.api.routes.workflows import NotificationType

    path = Path(__file__).resolve().parents[2] / "frontend/src/types/notification.ts"
    live = path.read_text(encoding="utf-8").split("} as const", 1)[0]
    names = set(re.findall(r"^  ([A-Z_]+):", live, flags=re.MULTILINE))
    assert set(get_args(NotificationType)) == names
    assert {"REPAIR_VERIFICATION_UPDATE", "OFFICER_REPAIR_UPDATE"} <= names


def test_cloud_intelligence_fails_closed_without_local_fallback(tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from app.models.user import Principal, Role

    database = tmp_path / "must-not-exist.db"
    settings = Settings(
        _env_file=None,
        app_env="aws",
        debug=False,
        cors_origins=[],
        cognito_issuer="https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Offline",
        cognito_client_id="offlineclient",
        cognito_domain="https://offline.auth.ap-south-1.amazoncognito.com",
        complaints_table_name="offline-complaints",
        evidence_bucket_name="offline-evidence",
        workflow_table_name="offline-operations",
        local_db_path=database,
    )
    app = create_app(settings)
    # Unit seam for verified identity only; persistence is deliberately NOT mocked as successful.
    app.state.identity_provider.authenticate = lambda _: Principal(
        id=str(uuid4()),
        email="offline@example.com",
        display_name="Offline Reviewer",
        role=Role.ADMIN,
        provider="cognito",
    )
    with TestClient(app, base_url="https://localhost") as client:
        response = client.get("/api/admin/repairs/pending")
        assert response.status_code == 503
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Request-ID"]
    assert not database.exists()
