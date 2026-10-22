from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.security import random_token
from app.scripts.create_local_user import main
from app.services.auth_service import AuthService


@pytest.mark.parametrize("role", ["CITIZEN", "OFFICER", "ADMIN"])
def test_trusted_local_cli_provisions_without_printing_password(tmp_path, role, capsys):
    settings = Settings(_env_file=None, app_env="local", local_db_path=tmp_path / "auth.db")
    password = random_token()
    with (
        patch("app.scripts.create_local_user.get_settings", return_value=settings),
        patch("builtins.input", side_effect=[f"{role.lower()}@example.com", f"Local {role}", role]),
        patch("app.scripts.create_local_user.getpass", return_value=password),
    ):
        main()
    assert password not in capsys.readouterr().out
    with AuthService(settings).store.connection() as db:
        assert db.execute("SELECT role FROM users").fetchone()[0] == role


def test_cli_refuses_nonlocal_environment():
    settings = Settings(_env_file=None, app_env="test")
    with (
        patch("app.scripts.create_local_user.get_settings", return_value=settings),
        pytest.raises(SystemExit, match="Refused"),
    ):
        main()
