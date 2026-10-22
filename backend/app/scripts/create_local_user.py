from getpass import getpass

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.services.auth_service import AuthService


def main() -> None:
    settings = get_settings()
    if settings.app_env != "local" or settings.auth_provider != "local":
        raise SystemExit(
            "Refused: local provisioning requires APP_ENV=local and local authentication."
        )
    try:
        email = input("Email: ").strip()
        name = input("Display name: ").strip()
        role = Role(input("Role (CITIZEN/OFFICER/ADMIN): ").strip().upper())
        data = RegisterInput(
            display_name=name,
            email=email,
            password=getpass("Password (12–128 characters): "),
            confirm_password=getpass("Confirm password: "),
        )
        service = AuthService(settings)
        service.store.initialize()
        user = service.register(data, role)
        print(f"Created local {user.role.value} account for {user.email}.")
    except (ValidationError, ValueError, HTTPException) as error:
        # Do not print Pydantic's repr: it may contain secret input values.
        detail = (
            error.detail
            if isinstance(error, HTTPException)
            else "Invalid input; check email, role, name, and matching passwords."
        )
        raise SystemExit(detail) from None


if __name__ == "__main__":
    main()
