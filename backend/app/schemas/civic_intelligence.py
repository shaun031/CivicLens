import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.work import Strict


class Operation(Strict):
    operationId: UUID


class RepairSubmission(Operation):
    expectedIncidentVersion: int = Field(ge=1)
    expectedAssignmentVersion: int = Field(ge=1)
    description: str = Field(min_length=20, max_length=2000)
    notes: str = Field(default="", max_length=2000)
    repairedAt: datetime

    @field_validator("repairedAt")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Repair timestamp must include a timezone")
        return value


class VerificationResponse(Operation):
    expectedVersion: int = Field(ge=1)
    result: Literal["CONFIRMED_FIXED", "STILL_BROKEN", "UNSURE"]
    feedback: str = Field(default="", max_length=2000)


class Decision(Operation):
    expectedVersion: int = Field(ge=1)
    expectedIncidentVersion: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    confirmed: Literal[True]
    approvedEvidenceIds: list[UUID] = Field(default_factory=list, max_length=2)


class RecurrenceDecision(Operation):
    expectedVersion: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)
    confirmed: Literal[True]
    physicalIdentityConfirmed: bool = False


class FairnessReview(Operation):
    expectedVersion: int = Field(default=0, ge=0)
    areaId: str = Field(min_length=1, max_length=100)
    context: dict[str, str] = Field(default_factory=dict, max_length=20)
    state: Literal["UNDER_ADMIN_REVIEW", "REVIEWED"]
    notes: str = Field(min_length=10, max_length=2000)

    @field_validator("areaId")
    @classmethod
    def grid_identity(cls, value):
        try:
            kind, size, latitude, longitude = value.split(":")
            grid, lat, lon = float(size), int(latitude), int(longitude)
            if (
                kind != "grid"
                or not math.isfinite(grid)
                or not 0.001 <= grid <= 0.1
                or not (lat * grid < 90 and (lat + 1) * grid > -90)
                or not (lon * grid < 180 and (lon + 1) * grid > -180)
            ):
                raise ValueError
        except (ValueError, OverflowError) as error:
            raise ValueError("A valid non-wrapping grid area identity is required") from error
        return value

    @field_validator("context")
    @classmethod
    def bounded_context(cls, value):
        if any(len(k) > 64 or len(v) > 256 for k, v in value.items()):
            raise ValueError("Review filter keys/values exceed safe bounds")
        from app.analytics.filters import AnalyticsFilters

        AnalyticsFilters.model_validate(value)
        return value
