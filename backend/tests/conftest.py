from pathlib import Path

import pytest
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.main import create_app


def pytest_collection_modifyitems(items):
    security_files = {
        "test_auth.py",
        "test_cognito.py",
        "test_intelligence_security.py",
        "test_release_security.py",
    }
    for item in items:
        name = item.name.lower()
        if item.path.name in security_files or any(
            word in name
            for word in (
                "authorization",
                "ownership",
                "privacy",
                "upload",
                "injection",
                "forbidden",
                "unauthenticated",
                "csrf",
                "cors",
                "expired",
                "secret",
                "evidence",
            )
        ):
            item.add_marker(pytest.mark.security)
        if item.path.name == "test_release_concurrency.py" or any(
            word in name for word in ("concurr", "parallel", "race", "racing", "simultaneous")
        ):
            item.add_marker(pytest.mark.concurrency)
        if "contract" in name or item.path.name == "test_release_security.py":
            item.add_marker(pytest.mark.contracts)


@pytest.fixture(autouse=True)
def forbid_live_aws(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Live AWS transport is forbidden in local tests")

    monkeypatch.setattr("botocore.endpoint.Endpoint.make_request", blocked)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(app_env="test", debug=False, local_db_path=tmp_path / "auth.db")


@pytest.fixture
def application(test_settings: Settings) -> FastAPI:
    app = create_app(test_settings)
    app.state.auth_service.store.initialize()
    app.dependency_overrides[get_settings] = lambda: test_settings
    return app
