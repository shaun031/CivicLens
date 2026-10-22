import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVENTS = {
    "ComplaintSubmitted": ("COMPLAINT", "triage"),
    "IncidentMembershipChanged": ("INCIDENT", "priority"),
    "IncidentPriorityChanged": ("INCIDENT", "notify"),
    "IncidentDepartmentAssigned": ("INCIDENT", "notify"),
    "IncidentOfficerAssigned": ("INCIDENT", "notify"),
    "IncidentOfficerReassigned": ("INCIDENT", "notify"),
    "IncidentWorkStarted": ("INCIDENT", "notify"),
    "IncidentProgressUpdated": ("INCIDENT", "notify"),
    "IncidentStatusChanged": ("INCIDENT", "notify"),
    "IncidentOverdue": ("INCIDENT", "notify"),
    "DuplicateReviewRequired": ("COMPLAINT", "notify"),
    "RoutingReviewRequired": ("COMPLAINT", "notify"),
    "WorkflowFailed": ("COMPLAINT", "notify"),
    **{
        kind: ("INCIDENT", "notify")
        for kind in (
            "RepairSubmitted",
            "RepairVerificationRequested",
            "RepairVerificationResponded",
            "RepairVerificationDisputed",
            "RepairApproved",
            "RepairRejected",
            "RepairReworkRequested",
            "RepairInformationRequested",
            "IncidentVerifiedResolved",
            "IncidentReopened",
            "PotentialRecurrenceDetected",
            "RecurrenceConfirmed",
            "RecurrenceDismissed",
        )
    },
    "FairnessReviewFlagged": ("AREA_REVIEW", "notify"),
}


def utcnow():
    return datetime.now(UTC)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    eventId: UUID
    eventType: str
    eventVersion: Literal[1]
    occurredAt: datetime
    aggregateType: Literal["COMPLAINT", "INCIDENT", "AREA_REVIEW"]
    aggregateId: UUID
    correlationId: UUID
    causationId: UUID | None = None
    source: Literal["civiclens.domain"] = "civiclens.domain"
    payload: dict[str, UUID] = Field(default_factory=dict)

    @field_validator("eventVersion", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported event version")
        return value

    @field_validator("occurredAt")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("UTC timestamp required")
        return value

    @field_validator("occurredAt", mode="before")
    @classmethod
    def timestamp_input(cls, value):
        if not isinstance(value, (str, datetime)) or isinstance(value, str) and "T" not in value:
            raise ValueError("Explicit ISO8601 UTC timestamp required")
        return value

    @model_validator(mode="after")
    def contract(self):
        if self.eventType not in EVENTS or EVENTS[self.eventType][0] != self.aggregateType:
            raise ValueError("Unsupported domain event")
        if set(self.payload) - {
            "officerId",
            "previousOfficerId",
            "escalationId",
            "attemptId",
            "recurrenceId",
            "reviewId",
        }:
            raise ValueError("Only documented ID references are permitted")
        if len(self.model_dump_json().encode()) > 2048:
            raise ValueError("Event too large")
        return self

    @classmethod
    def parse(cls, value):
        if isinstance(value, str):
            if len(value.encode()) > 2048:
                raise ValueError("Event too large")
            value = json.loads(value)
        return cls.model_validate(value)


def new_event(kind, identity, *, correlation=None, cause=None, payload=None, now=None):
    return Event(
        eventId=uuid4(),
        eventType=kind,
        eventVersion=1,
        occurredAt=now or utcnow(),
        aggregateType=EVENTS[kind][0],
        aggregateId=identity,
        correlationId=correlation or identity,
        causationId=cause,
        payload=payload or {},
    )


def consumer(event):
    return EVENTS[event.eventType][1]


def check_causation(event, lookup):
    parent, seen = str(event.causationId) if event.causationId else None, {str(event.eventId)}
    for _ in range(8):
        if not parent:
            return
        if parent in seen:
            raise ValueError("Event causation cycle")
        seen.add(parent)
        parent = lookup(parent)
    if parent:
        raise ValueError("Event causation exceeds bounded8 links")
