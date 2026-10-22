from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    CITIZEN = "CITIZEN"
    OFFICER = "OFFICER"
    ADMIN = "ADMIN"


class Principal(BaseModel):
    """Safe identity resolved only from a server session or verified Cognito token."""

    model_config = ConfigDict(frozen=True)
    id: str
    email: str
    display_name: str
    role: Role
    provider: Literal["local", "cognito"]
    is_authenticated: bool = True
    is_active: bool = True
    is_verified: bool = True
