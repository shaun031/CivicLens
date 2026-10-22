"""Run against local servers using an explicitly isolated smoke-test database."""

import argparse
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.security import random_token
from app.models.user import Role
from app.scripts.create_local_user import main as create_user


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://localhost:5173")
    args = parser.parse_args()
    if not args.database.name.startswith("phase2-smoke-"):
        parser.error("Use an isolated phase2-smoke-*.db database, also configured on the server")
    settings = Settings(app_env="local", auth_provider="local", local_db_path=args.database)
    with httpx.Client(base_url=args.backend_url, timeout=15) as direct:
        assert direct.get("/api/health").json()["environment"] == "local"
        assert direct.get("/docs").status_code == 200
    for role in Role:
        email = f"{role.value.lower()}-{uuid4().hex}@example.com"
        password = random_token()
        with httpx.Client(
            base_url=args.frontend_url,
            headers={"Origin": args.frontend_url},
            timeout=15,
        ) as client:
            assert client.get(f"/{role.value.lower()}/dashboard").status_code == 200
            if role == Role.CITIZEN:
                response = client.post(
                    "/api/auth/register",
                    json={
                        "display_name": "Smoke Citizen",
                        "email": email,
                        "password": password,
                        "confirm_password": password,
                    },
                )
                assert response.status_code == 201 and response.json()["role"] == "CITIZEN"
            else:
                with (
                    patch(
                        "app.scripts.create_local_user.get_settings",
                        return_value=settings,
                    ),
                    patch(
                        "builtins.input",
                        side_effect=[email, f"Smoke {role.value}", role.value],
                    ),
                    patch("app.scripts.create_local_user.getpass", return_value=password),
                    redirect_stdout(io.StringIO()),
                ):
                    create_user()
            assert (
                client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                ).status_code
                == 200
            )
            assert client.get("/api/auth/me").json()["role"] == role.value
            assert client.get(f"/api/portal/{role.value.lower()}").status_code == 200
            if role != Role.ADMIN:
                assert client.get("/api/portal/admin").status_code == 403
            assert (
                client.patch("/api/profile", json={"display_name": "Smoke Updated"}).status_code
                == 200
            )
            assert client.post("/api/auth/logout").status_code == 204
            assert client.get("/api/auth/me").status_code == 401
        print(
            f"{role.value}: login, profile, permitted portal, privilege checks, and logout passed."
        )
    print("Local live authentication passed. No passwords, tokens, or session IDs printed.")


if __name__ == "__main__":
    main()
