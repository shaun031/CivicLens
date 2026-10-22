from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Public health endpoint response."""

    status: Literal["ok"]
    service: str
    environment: str
