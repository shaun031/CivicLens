from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.permissions import PORTAL_ROLES
from app.integrations.auth.base import IdentityProvider
from app.models.user import Principal, Role

SESSION_COOKIE = "civiclens_session"


def credential_from_request(request: Request) -> str | None:
    if request.app.state.settings.auth_provider == "local":
        return request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token if scheme.casefold() == "bearer" and token else None


def get_current_user(request: Request) -> Principal:
    provider: IdentityProvider = request.app.state.identity_provider
    return provider.authenticate(credential_from_request(request))


AuthenticatedUser = Annotated[Principal, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[..., Principal]:
    def check_role(user: AuthenticatedUser) -> Principal:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission to access this resource.")
        return user

    return check_role


def require_portal(portal: str) -> Callable[..., Principal]:
    return require_roles(*PORTAL_ROLES[portal])


def verify_local_origin(request: Request) -> None:
    # All unsafe local-auth requests, including login/register, must supply an exact trusted Origin.
    if request.headers.get("origin") not in request.app.state.settings.cors_origins:
        raise HTTPException(403, "Request origin is not permitted.")
    if request.url.scheme == "http" and request.url.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise HTTPException(403, "Local HTTP authentication requires a loopback host.")
