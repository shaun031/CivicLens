import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.permissions import PORTAL_ROLES
from app.core.security import random_token, token_hash, verify_password
from app.main import create_app
from app.models.user import Role
from app.schemas.auth import RegisterInput

pytestmark = pytest.mark.anyio
ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def password() -> str:
    return random_token()


@pytest.fixture
async def client(application: FastAPI):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://localhost:8000",
        headers=ORIGIN,
    ) as session:
        yield session


def registration(password: str, email: str = "citizen@example.com") -> dict[str, str]:
    return {
        "display_name": "Demo Citizen",
        "email": email,
        "password": password,
        "confirm_password": password,
    }


async def register_and_login(client: httpx.AsyncClient, password: str) -> None:
    assert (await client.post("/api/auth/register", json=registration(password))).status_code == 201
    assert (
        await client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": password}
        )
    ).status_code == 200


async def test_registration_password_hash_uniqueness_and_safe_response(
    client, application, password
):
    response = await client.post(
        "/api/auth/register", json=registration(password, "Citizen@EXAMPLE.COM")
    )
    assert response.status_code == 201
    assert response.json()["role"] == "CITIZEN"
    assert response.json()["email"] == "citizen@example.com"
    assert "password" not in response.text and password not in response.text
    with application.state.auth_service.store.connection() as db:
        row = db.execute("SELECT * FROM users").fetchone()
        assert row["password_hash"].startswith("$argon2id$")
        assert verify_password(row["password_hash"], password)
    assert (await client.post("/api/auth/register", json=registration(password))).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"email": "not-an-email"},
        {"password": "short", "confirm_password": "short"},
        {"confirm_password": "different value"},
        {"role": "ADMIN"},
        {"role": "OFFICER"},
        {"is_active": True},
        {"password": "aaaaaaaaaaaa", "confirm_password": "aaaaaaaaaaaa"},
    ],
)
async def test_invalid_registration_and_role_injection(client, password, change):
    payload = registration(password) | change
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert password not in response.text


async def test_session_cookie_restore_fixation_logout_and_hash_only_storage(
    client, application, password
):
    await register_and_login(client, password)
    first = client.cookies.get("civiclens_session")
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    login = await client.post(
        "/api/auth/login", json={"email": "citizen@example.com", "password": password}
    )
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api" in cookie
    token = client.cookies.get("civiclens_session")
    assert token != first
    with application.state.auth_service.store.connection() as db:
        stored = db.execute("SELECT token_hash FROM sessions").fetchall()
        assert len(stored) == 1
        assert stored[0][0] == token_hash(token)
    with pytest.raises(Exception) as error:
        application.state.auth_service.authenticate(first)
    assert error.value.status_code == 401
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    client.cookies.set("civiclens_session", token)
    assert (await client.get("/api/auth/me")).status_code == 401


@pytest.mark.parametrize("change", ["expired", "inactive", "unverified"])
async def test_expired_and_disabled_sessions_are_rejected(client, application, password, change):
    await register_and_login(client, password)
    with application.state.auth_service.store.connection() as db:
        if change == "expired":
            db.execute("UPDATE sessions SET expires_at=0")
        else:
            db.execute(
                f"UPDATE users SET {'is_active' if change == 'inactive' else 'is_verified'}=0"
            )
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_unknown_and_invalid_password_fail_generically_and_rate_limit(client, password):
    await register_and_login(client, password)
    wrong = await client.post(
        "/api/auth/login", json={"email": "citizen@example.com", "password": "incorrect"}
    )
    unknown = await client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": "incorrect"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    for _ in range(4):
        assert (
            await client.post(
                "/api/auth/login", json={"email": "citizen@example.com", "password": "incorrect"}
            )
        ).status_code == 401
    limited = await client.post(
        "/api/auth/login", json={"email": "citizen@example.com", "password": "incorrect"}
    )
    assert limited.status_code == 429 and "retry-after" in limited.headers


@pytest.mark.parametrize("column", ["is_active", "is_verified"])
async def test_inactive_or_unverified_login_rejected(client, application, password, column):
    await client.post("/api/auth/register", json=registration(password))
    with application.state.auth_service.store.connection() as db:
        db.execute(f"UPDATE users SET {column}=0")
    response = await client.post(
        "/api/auth/login", json={"email": "citizen@example.com", "password": password}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


async def test_origin_csrf_and_profile_privilege_protection(client, password):
    assert (
        await client.post(
            "/api/auth/register",
            json=registration(password),
            headers={"Origin": "https://evil.example"},
        )
    ).status_code == 403
    await register_and_login(client, password)
    assert (await client.patch("/api/profile", json={"display_name": "Updated Name"})).json()[
        "display_name"
    ] == "Updated Name"
    for field, value in {
        "role": "ADMIN",
        "is_active": True,
        "is_verified": True,
        "id": "another",
    }.items():
        assert (
            await client.patch("/api/profile", json={"display_name": "Name", field: value})
        ).status_code == 422
    assert (
        await client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    ).status_code == 403
    assert (await client.get("/api/auth/me")).status_code == 200
    client.headers.pop("Origin")
    assert (await client.post("/api/auth/logout")).status_code == 403


@pytest.mark.parametrize("role", list(Role))
async def test_role_matrix_enforced_from_database(client, application, password, role):
    service = application.state.auth_service
    user = service.register(RegisterInput(**registration(password)), role)
    assert (
        await client.post("/api/auth/login", json={"email": user.email, "password": password})
    ).status_code == 200
    for portal, roles in PORTAL_ROLES.items():
        response = await client.get(
            f"/api/portal/{portal}", headers={"X-Role": "ADMIN", "X-User-Id": user.id}
        )
        assert response.status_code == (200 if role in roles else 403)


async def test_all_protected_endpoints_require_authentication(client):
    for path in ["/api/auth/me", "/api/portal/citizen", "/api/portal/officer", "/api/portal/admin"]:
        assert (await client.get(path, headers={"X-Role": "ADMIN"})).status_code == 401


async def test_reset_outbox_single_use_and_session_invalidation(client, application, password):
    await register_and_login(client, password)
    unknown = await client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    response = await client.post("/api/auth/forgot-password", json={"email": "citizen@example.com"})
    assert unknown.status_code == response.status_code == 202
    assert unknown.json() == response.json()
    outbox = application.state.auth_service.store.path.parent / "outbox"
    message = json.loads(next(outbox.glob("*.json")).read_text())
    token = parse_qs(urlsplit(message["reset_url"]).fragment)["token"][0]
    assert token not in response.text
    assert (await client.get("/api/auth/outbox")).status_code == 404
    new_password = random_token()
    payload = {"token": token, "password": new_password, "confirm_password": new_password}
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 200
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": password}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": new_password}
        )
    ).status_code == 200


async def test_expired_reset_token_is_rejected(client, application, password):
    await client.post("/api/auth/register", json=registration(password))
    service = application.state.auth_service
    service.request_reset("citizen@example.com")
    entry = json.loads(next((service.store.path.parent / "outbox").glob("*.json")).read_text())
    token = parse_qs(urlsplit(entry["reset_url"]).fragment)["token"][0]
    with service.store.connection() as db:
        db.execute("UPDATE password_resets SET expires_at=0")
    assert (
        await client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": password, "confirm_password": password},
        )
    ).status_code == 400


async def test_https_sets_secure_cookie_and_unicode_password_works(tmp_path):
    settings = Settings(_env_file=None, app_env="test", local_db_path=tmp_path / "secure.db")
    app = create_app(settings)
    app.state.auth_service.store.initialize()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://localhost", headers=ORIGIN
    ) as client:
        password = random_token() + "🌿é"
        await client.post("/api/auth/register", json=registration(password))
        response = await client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": password}
        )
        assert response.status_code == 200
        assert "secure" in response.headers["set-cookie"].lower()
        assert (await client.get("/api/auth/me")).status_code == 200
