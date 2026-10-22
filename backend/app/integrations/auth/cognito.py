from typing import Any

import httpx
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from app.core.config import Settings
from app.models.user import Principal, Role


class CognitoTokenVerifier:
    """RS256-only access-token validation; JWKS is fetched lazily, only in AWS mode."""

    def __init__(self, settings: Settings, jwks_client: PyJWKClient | None = None) -> None:
        self.settings = settings
        self.keys = jwks_client or PyJWKClient(
            f"{settings.cognito_issuer}/.well-known/jwks.json",
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def verify(self, token: str) -> dict[str, Any]:
        try:
            if len(token) > 16384 or jwt.get_unverified_header(token).get("alg") != "RS256":
                raise jwt.InvalidTokenError("Invalid token algorithm")
            signing_key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.cognito_issuer,
                leeway=15,
                options={
                    "require": ["exp", "iat", "sub", "token_use", "client_id"],
                    "verify_aud": False,
                },
            )
            if (
                claims.get("token_use") != "access"
                or claims.get("client_id") != self.settings.cognito_client_id
            ):
                raise jwt.InvalidTokenError("Wrong token use or app client")
            if (
                not isinstance(claims.get("scope"), str)
                or self.settings.cognito_api_scope not in claims["scope"].split()
            ):
                raise jwt.InvalidTokenError("Required API scope missing")
            if not isinstance(claims.get("sub"), str) or not claims["sub"]:
                raise jwt.InvalidTokenError("Missing subject")
            return claims
        except PyJWKClientConnectionError as error:
            raise HTTPException(503, "Identity verification is temporarily unavailable.") from error
        except (jwt.PyJWTError, ValueError, TypeError) as error:
            raise HTTPException(
                401, "Invalid access token.", headers={"WWW-Authenticate": "Bearer"}
            ) from error


class CognitoIdentityProvider:
    def __init__(self, settings: Settings, verifier: CognitoTokenVerifier | None = None) -> None:
        self.settings = settings
        self.verifier = verifier or CognitoTokenVerifier(settings)

    def authenticate(self, credential: str | None) -> Principal:
        if not credential:
            raise HTTPException(
                401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"}
            )
        claims = self.verifier.verify(credential)
        groups = claims.get("cognito:groups", [])
        if not isinstance(groups, list) or not all(isinstance(group, str) for group in groups):
            raise HTTPException(403, "Account provisioning is incomplete.")
        role = next(
            (role for role in (Role.ADMIN, Role.OFFICER, Role.CITIZEN) if role.value in groups),
            None,
        )
        if role is None:
            raise HTTPException(403, "Account provisioning is incomplete.")
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(
                    f"{self.settings.cognito_domain}/oauth2/userInfo",
                    headers={"Authorization": f"Bearer {credential}"},
                )
                if response.status_code in (401, 403):
                    raise HTTPException(401, "Account session is no longer valid.")
                response.raise_for_status()
                profile = response.json()
            if not isinstance(profile, dict):
                raise HTTPException(503, "Account profile is temporarily unavailable.")
            if profile.get("sub") != claims["sub"] or profile.get("email_verified") not in (
                True,
                "true",
            ):
                raise HTTPException(401, "Verified account profile required.")
            if not isinstance(profile.get("email"), str) or not profile["email"]:
                raise HTTPException(401, "Verified account profile required.")
            return Principal(
                id=claims["sub"],
                email=profile["email"],
                display_name=profile["name"]
                if isinstance(profile.get("name"), str) and profile["name"]
                else profile["email"],
                role=role,
                provider="cognito",
            )
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise HTTPException(503, "Account profile is temporarily unavailable.") from error

    def update_profile(self, user: Principal, name: str, credential: str | None) -> Principal:
        # Uses the user's verified access token, not IAM credentials or arbitrary user IDs.
        try:
            endpoint = self.settings.cognito_issuer.rsplit("/", 1)[0]
            with httpx.Client(timeout=5) as client:
                response = client.post(
                    endpoint,
                    headers={
                        "Content-Type": "application/x-amz-json-1.1",
                        "X-Amz-Target": "AWSCognitoIdentityProviderService.UpdateUserAttributes",
                    },
                    json={
                        "AccessToken": credential,
                        "UserAttributes": [{"Name": "name", "Value": name}],
                    },
                )
                response.raise_for_status()
            return user.model_copy(update={"display_name": name})
        except httpx.HTTPError as error:
            raise HTTPException(503, "Profile update is temporarily unavailable.") from error
