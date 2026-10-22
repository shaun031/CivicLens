from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Check API health")
def health_check(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Return API availability and the validated runtime environment."""
    return HealthResponse(
        status="ok",
        service="civiclens-api",
        environment=settings.app_env,
    )
