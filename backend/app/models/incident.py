from dataclasses import dataclass, field
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.complaint import Category, Complaint


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    MERGED = "MERGED"
    SUPERSEDED = "SUPERSEDED"


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    incidentId: str
    canonicalTitle: str
    canonicalDescription: str
    category: Category
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    status: IncidentStatus = IncidentStatus.OPEN
    representativeComplaintId: str
    totalComplaintCount: int = Field(ge=0)
    uniqueReporterCount: int = Field(ge=0)
    firstReportedAt: str
    lastReportedAt: str
    createdAt: str
    updatedAt: str
    resolvedAt: str | None = None
    mergedIntoIncidentId: str | None = None
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_summary(self):
        if self.uniqueReporterCount > self.totalComplaintCount:
            raise ValueError("Reporter count exceeds report count")
        if (
            self.status in (IncidentStatus.MERGED, IncidentStatus.SUPERSEDED)
            and self.totalComplaintCount
        ):
            raise ValueError("Retired incidents cannot retain active members")
        if self.status == IncidentStatus.MERGED and not self.mergedIntoIncidentId:
            raise ValueError("Merged incident requires an alias target")
        if self.mergedIntoIncidentId == self.incidentId:
            raise ValueError("Self redirect is forbidden")
        return self


@dataclass(frozen=True)
class Actor:
    id: str
    type: str


@dataclass(frozen=True)
class Member:
    complaint: Complaint
    eligible_reporter: bool


@dataclass(frozen=True)
class MembershipChange:
    complaint_id: str
    previous_incident_id: str | None
    new_incident_id: str
    evidence: dict = field(default_factory=dict)


@dataclass
class IncidentPlan:
    operation_id: str
    fingerprint: str
    operation: str
    actor: Actor
    reason: str
    before: dict[str, Incident | None]
    after: dict[str, Incident]
    changes: list[MembershipChange]
    observed: list[Member]
    result_incident_id: str
    created_at: str


class IncidentError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"civiclens/incident-v1/{value}"))
