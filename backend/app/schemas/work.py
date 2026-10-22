from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.complaint import Category


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Rectangle(Strict):
    name: str = Field(min_length=1, max_length=100)
    south: float = Field(ge=-90, le=90)
    north: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    east: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def ordered(self):
        if self.south >= self.north or self.west >= self.east:
            raise ValueError("Rectangle must have positive area and not wrap the antimeridian")
        return self


class Action(Strict):
    operationId: UUID
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Reason cannot contain control characters")
        return value


class DepartmentAction(Action):
    expectedVersion: int = Field(ge=0)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,49}$")
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=1000)
    active: bool = True
    areas: list[Rectangle] = Field(default_factory=list, max_length=10)


class RuleAction(Action):
    expectedVersion: int = Field(ge=0)
    category: Category
    departmentId: UUID
    precedence: int = Field(default=100, ge=0, le=1000)
    active: bool = True


class MembershipAction(Action):
    expectedVersion: int = Field(ge=0)
    officerId: UUID
    active: bool = True
    availability: Literal["AVAILABLE", "BUSY", "UNAVAILABLE", "ON_LEAVE"] = "AVAILABLE"
    capacity: float | None = Field(default=None, gt=0, le=10000)
    areas: list[Rectangle] = Field(default_factory=list, max_length=10)


class VersionAction(Action):
    expectedVersion: int = Field(ge=0)


class AssignmentAction(Action):
    expectedIncidentVersion: int = Field(ge=1)
    expectedAssignmentVersion: int = Field(ge=0)
    departmentId: UUID | None = None
    officerId: UUID | None = None
    mode: Literal["MANUAL_APPROVAL", "CONSERVATIVE_AUTO_ASSIGN"] = "MANUAL_APPROVAL"
    review: bool = False
    capacityOverride: bool = False


class ProgressAction(Action):
    expectedIncidentVersion: int = Field(ge=1)
    expectedAssignmentVersion: int = Field(ge=0)
    note: str = Field(min_length=10, max_length=2000)
    percentage: int = Field(default=0, ge=0, le=100)
    requestReview: bool = False


class WorkQuery(Strict):
    departmentId: UUID | None = None
    officerId: UUID | None = None
    status: (
        Literal[
            "UNASSIGNED", "DEPARTMENT_ASSIGNED", "OFFICER_ASSIGNED", "IN_PROGRESS", "NEEDS_REVIEW"
        ]
        | None
    ) = None
    band: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    category: Category | None = None
    urgent: bool | None = None
    assignedAfter: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=4096)

    @field_validator("assignedAfter")
    @classmethod
    def valid_date(cls, value):
        from app.algorithms.priority_scoring.aging import utc

        return utc(value).isoformat() if value is not None else None
