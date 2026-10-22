import json
import time
from unittest.mock import patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.core.config import Settings
from app.integrations.auth.cognito import CognitoIdentityProvider, CognitoTokenVerifier
from app.main import create_app
from app.models.user import Role
from app.services.auth_service import AuthService


@pytest.fixture
def cloud_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="aws",
        debug=False,
        auth_provider="cognito",
        cors_origins=[],
        cognito_issuer="https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Test",
        cognito_client_id="testclient",
        cognito_domain="https://civic-test.auth.ap-south-1.amazoncognito.com",
        complaints_table_name="test-complaints",
        evidence_bucket_name="test-evidence",
    )


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def claims(cloud_settings):
    return {
        "iss": cloud_settings.cognito_issuer,
        "sub": "verified-subject",
        "client_id": "testclient",
        "token_use": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "scope": "openid email profile civiclens/access",
        "cognito:groups": ["CITIZEN"],
    }


@pytest.fixture
def key_client(monkeypatch, private_key):
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())) | {
        "kid": "local-key",
        "use": "sig",
        "alg": "RS256",
    }
    client = PyJWKClient("https://unused.example/jwks", lifespan=300, cache_keys=False)

    def fetch():
        data = {"keys": [public]}
        client.jwk_set_cache.put(data)
        return data

    monkeypatch.setattr(client, "fetch_data", fetch)
    return client


def encode(claims, private_key, kid="local-key"):
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def test_valid_access_token_without_audience_and_jwks_cache(
    cloud_settings, private_key, claims, key_client
):
    verifier = CognitoTokenVerifier(cloud_settings, key_client)
    with patch.object(key_client, "fetch_data", wraps=key_client.fetch_data) as fetch:
        assert verifier.verify(encode(claims, private_key))["sub"] == "verified-subject"
        verifier.verify(encode(claims, private_key))
        assert fetch.call_count == 1


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.example"},
        {"client_id": "anotherclient"},
        {"token_use": "id"},
        {"exp": 1},
        {"iat": int(time.time()) + 300},
        {"nbf": int(time.time()) + 300},
        {"scope": "openid email"},
        {"sub": ""},
    ],
)
def test_invalid_access_claims_rejected(cloud_settings, private_key, claims, key_client, change):
    with pytest.raises(HTTPException) as error:
        CognitoTokenVerifier(cloud_settings, key_client).verify(
            encode(claims | change, private_key)
        )
    assert error.value.status_code == 401


def test_signature_and_unsigned_algorithm_attacks_rejected(
    cloud_settings, private_key, claims, key_client
):
    verifier = CognitoTokenVerifier(cloud_settings, key_client)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tokens = [
        encode(claims | {"cognito:groups": ["ADMIN"]}, other),
        jwt.encode(claims, "untrusted-test-key-at-least-32-characters", algorithm="HS256"),
        jwt.encode(claims, key=None, algorithm="none"),
    ]
    for token in tokens:
        with pytest.raises(HTTPException) as error:
            verifier.verify(token)
        assert error.value.status_code == 401


def test_key_rotation_refreshes_unknown_kid(
    cloud_settings, private_key, claims, key_client, monkeypatch
):
    verifier = CognitoTokenVerifier(cloud_settings, key_client)
    verifier.verify(encode(claims, private_key))
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rotated.public_key())) | {
        "kid": "rotated"
    }
    monkeypatch.setattr(key_client, "fetch_data", lambda: {"keys": [public]})
    assert verifier.verify(encode(claims, rotated, "rotated"))["sub"] == "verified-subject"


def test_groups_only_from_verified_claims_and_userinfo_subject_bound(
    cloud_settings, private_key, claims, key_client
):
    provider = CognitoIdentityProvider(
        cloud_settings, CognitoTokenVerifier(cloud_settings, key_client)
    )

    def remote(request):
        return httpx.Response(
            200,
            json={
                "sub": "verified-subject",
                "email": "citizen@example.com",
                "email_verified": True,
                "name": "Cognito Citizen",
            },
        )

    real_client = httpx.Client
    with patch(
        "app.integrations.auth.cognito.httpx.Client",
        side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(remote), **kwargs),
    ):
        principal = provider.authenticate(encode(claims, private_key))
    assert principal.role == Role.CITIZEN and principal.provider == "cognito"
    assert principal.id == claims["sub"]
    for groups in ([], ["unrecognized"], "ADMIN"):
        with pytest.raises(HTTPException) as error:
            provider.authenticate(encode(claims | {"cognito:groups": groups}, private_key))
        assert error.value.status_code == 403


@pytest.mark.anyio
async def test_aws_routes_disable_local_password_auth_and_ignore_session_cookie(cloud_settings):
    app = create_app(cloud_settings)
    assert not hasattr(app.state, "auth_service")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://local.test"
    ) as client:
        for path in ("register", "login", "logout", "forgot-password", "reset-password"):
            assert (await client.post(f"/api/auth/{path}", json={})).status_code == 404
        client.cookies.set("civiclens_session", "fake-local-session")
        assert (await client.get("/api/auth/me", headers={"X-Role": "ADMIN"})).status_code == 401
        assert (await client.get("/api/health")).json()["environment"] == "aws"
    with pytest.raises(ValueError):
        AuthService(cloud_settings)
    with pytest.raises(ValueError, match="Local authentication is forbidden"):
        Settings(_env_file=None, app_env="aws", auth_provider="local", debug=False)


def test_missing_aws_configuration_cannot_fall_back():
    with pytest.raises(ValueError, match="Cognito issuer"):
        Settings(_env_file=None, app_env="aws", debug=False)


def test_jwks_outage_fails_closed(cloud_settings, private_key, claims, key_client):
    with (
        patch.object(
            key_client,
            "get_signing_key_from_jwt",
            side_effect=PyJWKClientConnectionError("offline"),
        ),
        pytest.raises(HTTPException) as error,
    ):
        CognitoTokenVerifier(cloud_settings, key_client).verify(encode(claims, private_key))
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "profile,status,expected",
    [
        ({"sub": "wrong", "email_verified": True}, 200, 401),
        ({"sub": "verified-subject", "email_verified": False}, 200, 401),
        ({}, 401, 401),
        ({}, 503, 503),
    ],
)
def test_userinfo_must_be_available_and_match_verified_subject(
    cloud_settings, private_key, claims, key_client, profile, status, expected
):
    real_client = httpx.Client
    with (
        patch(
            "app.integrations.auth.cognito.httpx.Client",
            side_effect=lambda **kwargs: real_client(
                transport=httpx.MockTransport(lambda request: httpx.Response(status, json=profile)),
                **kwargs,
            ),
        ),
        pytest.raises(HTTPException) as error,
    ):
        CognitoIdentityProvider(
            cloud_settings, CognitoTokenVerifier(cloud_settings, key_client)
        ).authenticate(encode(claims, private_key))
    assert error.value.status_code == expected
