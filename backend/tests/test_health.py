import httpx
import pytest
from fastapi import FastAPI


@pytest.mark.anyio
async def test_health_endpoint_returns_expected_payload(application: FastAPI) -> None:
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "civiclens-api",
        "environment": "test",
    }


def test_application_imports() -> None:
    from app.main import app

    assert app.title == "CivicLens API"


def test_lambda_adapter_imports_without_aws_calls() -> None:
    from app.lambda_handler import handler

    assert callable(handler)
