"""Trusted test-only provisioning through the existing AuthService, never an HTTP backdoor."""

import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.models.user import Role  # noqa: E402
from app.schemas.auth import RegisterInput  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402


def main():
    path = Path(os.environ["CIVICLENS_BROWSER_DB_PATH"]).resolve()
    if path.parent != (BACKEND / "data").resolve() or not re.fullmatch(
        r"phase5-browser-[0-9a-f-]{36}\.db", path.name
    ):
        raise SystemExit("Refused: only a dedicated Phase 5 browser fixture database is allowed.")
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_provider="local",
        local_db_path=path,
        local_evidence_root=path.parent / f"{path.stem}-evidence",
        complaint_provider="sqlite",
        evidence_provider="local",
    )
    service = AuthService(settings)
    service.store.initialize()
    password = os.environ["BROWSER_ADMIN_PASSWORD"]
    role = Role(os.environ.get("BROWSER_STAFF_ROLE", "ADMIN"))
    if role not in (Role.ADMIN, Role.OFFICER, Role.CITIZEN):
        raise SystemExit("Only ADMIN/OFFICER/CITIZEN fixture provisioning is supported")
    user = service.register(
        RegisterInput(
            display_name="Browser Review Administrator"
            if role == Role.ADMIN
            else "Browser Field Officer"
            if role == Role.OFFICER
            else "Design Review Citizen",
            email=os.environ["BROWSER_ADMIN_EMAIL"],
            password=password,
            confirm_password=password,
        ),
        role,
    )
    if os.environ.get("BROWSER_CREATE_SESSION") == "1":
        # Optional trusted fixture setup, not an HTTP authentication bypass.
        # This script is hard-guarded to a dedicated UUID browser database above.
        # The public registration/login/rate-limit tests still exercise HTTP normally.
        _, token = service.login(
            os.environ["BROWSER_ADMIN_EMAIL"],
            password,
            ip="trusted-browser-fixture:" + user.id,
            previous_token=None,
        )
        print(json.dumps({"id": user.id, "session": token}))
    else:
        print(user.id)


if __name__ == "__main__":
    main()
