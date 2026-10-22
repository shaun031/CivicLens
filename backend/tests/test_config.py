import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_configuration_loads_explicit_values() -> None:
    settings = Settings(
        app_name="CivicLens Test",
        app_env="test",
        debug=False,
        port=8010,
        cors_origins=["http://localhost:5173"],
    )
    assert settings.app_name == "CivicLens Test"
    assert settings.app_env == "test"
    assert settings.port == 8010


def test_unsafe_production_debug_is_rejected() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(app_env="production", debug=True)


@pytest.mark.parametrize("stage", ["demo", "production"])
def test_cloud_configuration_accepts_resource_references(stage: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env=stage,
        debug=False,
        cors_origins=["https://civic.example.org"],
        complaints_table_name="complaints-reference",
        incidents_table_name="incidents-reference",
        audit_events_table_name="audit-reference",
        evidence_bucket_name="evidence-reference",
        cognito_issuer="https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Test",
        cognito_client_id="testclient",
        cognito_domain="https://civic-test.auth.ap-south-1.amazoncognito.com",
    )
    assert settings.app_env == stage
    assert settings.complaints_table_name == "complaints-reference"


def test_cors_environment_supports_json_and_comma_separated_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for value in ('["http://localhost:5173"]', "http://localhost:5173,http://127.0.0.1:5173"):
        monkeypatch.setenv("CORS_ORIGINS", value)
        settings = Settings(_env_file=None)
        assert "http://localhost:5173" in settings.cors_origins


@pytest.mark.parametrize("origin", ["*", "http://civic.example.org", "https://localhost"])
def test_unsafe_production_cors_is_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", debug=False, cors_origins=[origin])


def test_local_configuration_needs_no_cloud_resources() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "local"
    assert settings.complaints_table_name is None
    assert settings.evidence_bucket_name is None
