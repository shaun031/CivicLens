import importlib
import json
import socket
from unittest.mock import patch

import pytest
from mangum import Mangum

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize("stage", ["local", "demo", "production"])
def test_api_gateway_v2_event_uses_the_same_fastapi_app(stage: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env=stage,
        debug=False,
        cors_origins=[],
        cognito_issuer="https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Test",
        cognito_client_id="testclient",
        cognito_domain="https://civic-test.auth.ap-south-1.amazoncognito.com",
        complaints_table_name="test-complaints",
        evidence_bucket_name="test-evidence",
    )
    adapter = Mangum(create_app(settings), lifespan="off")
    event = {
        "version": "2.0",
        "routeKey": "GET /api/health",
        "rawPath": "/api/health",
        "rawQueryString": "",
        "headers": {"host": "local.test", "x-forwarded-proto": "https"},
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": "GET",
                "path": "/api/health",
                "sourceIp": "127.0.0.1",
                "protocol": "HTTP/1.1",
            },
        },
        "isBase64Encoded": False,
    }
    response = adapter(event, {})
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {
        "status": "ok",
        "service": "civiclens-api",
        "environment": stage,
    }


def test_handler_import_performs_no_network_calls() -> None:
    with patch.object(
        socket, "create_connection", side_effect=AssertionError("Network prohibited")
    ):
        module = importlib.import_module("app.lambda_handler")
        module = importlib.reload(module)
        assert callable(module.handler)
