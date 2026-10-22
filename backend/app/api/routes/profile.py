from fastapi import APIRouter, Request

from app.core.auth_dependencies import (
    AuthenticatedUser,
    credential_from_request,
    verify_local_origin,
)
from app.models.user import Principal
from app.schemas.auth import ProfileUpdate

router = APIRouter(tags=["Profile"])


@router.patch("/profile", response_model=Principal)
def update_profile(data: ProfileUpdate, request: Request, user: AuthenticatedUser) -> Principal:
    if request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
    return request.app.state.identity_provider.update_profile(
        user, data.display_name, credential_from_request(request)
    )
