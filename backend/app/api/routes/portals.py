from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth_dependencies import require_portal
from app.models.user import Principal

router = APIRouter(prefix="/portal", tags=["Role portals"])


@router.get("/citizen")
def citizen_portal(
    user: Annotated[Principal, Depends(require_portal("citizen"))],
) -> dict[str, str]:
    return {
        "portal": "citizen",
        "message": "Citizen portal access granted.",
        "role": user.role.value,
    }


@router.get("/officer")
def officer_portal(
    user: Annotated[Principal, Depends(require_portal("officer"))],
) -> dict[str, str]:
    return {
        "portal": "officer",
        "message": "Officer portal access granted.",
        "role": user.role.value,
    }


@router.get("/admin")
def admin_portal(user: Annotated[Principal, Depends(require_portal("admin"))]) -> dict[str, str]:
    return {
        "portal": "admin",
        "message": "Administrator portal access granted.",
        "role": user.role.value,
    }
