import math
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.algorithms.priority_scoring.aging import utc
from app.api.routes.incidents import Admin, execute
from app.api.routes.incidents import service as authorize_incidents
from app.models.complaint import Category
from app.models.incident import Actor
from app.utils.context_cursor import pack_cursor, unpack_cursor

router = APIRouter(tags=["Explainable incident priorities"])
Band = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class PriorityQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    q: str = Field(default="", max_length=150)
    band: Band | None = None
    category: Category | None = None
    status: Literal["OPEN", "RESOLVED"] = "OPEN"
    urgent: bool | None = None
    assessmentStatus: Literal["PROVISIONAL", "VERIFIED", "NEEDS_REVIEW"] | None = None
    overrideStatus: Literal["NONE", "ACTIVE", "EXPIRED", "REMOVED", "REVIEW_REQUIRED"] | None = None
    minSeverity: float | None = Field(default=None, ge=0, le=10)
    maxSeverity: float | None = Field(default=None, ge=0, le=10)
    minImpact: float | None = Field(default=None, ge=0, le=10)
    maxImpact: float | None = Field(default=None, ge=0, le=10)
    minDays: float | None = Field(default=None, ge=0, le=100000)
    maxDays: float | None = Field(default=None, ge=0, le=100000)
    sort: Literal["priority", "oldest"] = "priority"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def ranges(self):
        for low, high in (
            (self.minSeverity, self.maxSeverity),
            (self.minImpact, self.maxImpact),
            (self.minDays, self.maxDays),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError("Minimum filter must not exceed maximum")
        return self


class PriorityAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    operationId: UUID
    expectedIncidentVersion: int = Field(ge=1)
    expectedPriorityRevision: int = Field(ge=0)
    reason: str = Field(min_length=10, max_length=1000)
    confirmed: bool

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Reason cannot contain control characters")
        return value


class EvidenceAction(PriorityAction):
    evidenceReferences: list[UUID] = Field(default_factory=list, max_length=10)


class AssessmentAction(EvidenceAction):
    score: float | None = Field(default=None, ge=0, le=10)
    status: Literal["UNASSESSED", "PROVISIONAL", "VERIFIED"]

    @model_validator(mode="after")
    def valid_assessment(self):
        if self.status == "UNASSESSED" and self.score is not None:
            raise ValueError("Unassessed inputs must have an unknown/null score")
        if self.status != "UNASSESSED" and self.score is None:
            raise ValueError("An assessment score is required")
        if self.status == "PROVISIONAL" and self.score > 6:
            raise ValueError("Provisional administrative scores are capped at six")
        if self.status == "VERIFIED" and not self.evidenceReferences:
            raise ValueError("Verified assessment requires current evidence references")
        return self


class HazardAction(EvidenceAction):
    flag: bool


class OverrideAction(PriorityAction):
    score: float = Field(ge=0, le=100)
    expiresAt: str | None = Field(default=None, max_length=40)

    @field_validator("expiresAt")
    @classmethod
    def aware_expiry(cls, value):
        return utc(value).isoformat().replace("+00:00", "Z") if value is not None else None


def priority_service(request, user, unsafe=False):
    authorize_incidents(request, user, unsafe)
    return request.app.state.priority_service


@router.get("/admin/incidents/priorities/summary")
def summary(request: Request, user: Admin):
    service = priority_service(request, user)
    return execute(service.repository.summary, service.clock().timestamp(), service.config.version)


@router.get("/admin/incidents/priorities")
def ranked(request: Request, user: Admin, query: Annotated[PriorityQuery, Query()]):
    service = priority_service(request, user)
    context = query.model_dump(mode="json", exclude={"cursor"}) | {"config": service.config.version}
    key = unpack_cursor(query.cursor, context, (5, 6))
    revision, after = (None, None) if not key else (key[0], key[2:])
    valid_until = key[1] if key else None
    now = service.clock().timestamp()
    oldest = query.sort == "oldest"
    if key and (
        type(revision) is not int
        or len(after) != (3 if oldest else 4)
        or not isinstance(after[-1], str)
        or (
            oldest
            and (
                type(after[0]) not in (int, float)
                or after[0] not in (-1, 0)
                or not isinstance(after[1], str)
            )
        )
        or type(valid_until) not in (int, float)
        or not math.isfinite(valid_until)
        or valid_until > now + 60.1
        or (
            not oldest
            and any(type(v) not in (int, float) or not math.isfinite(v) for v in after[:-1])
        )
    ):
        raise HTTPException(400, "Invalid priority queue cursor")
    items, next_key, current, expiry = execute(
        service.repository.queue,
        context,
        query.limit,
        after,
        revision,
        now,
        service.config.version,
        valid_until,
    )
    return {
        "items": items,
        "queueRevision": current,
        "nextCursor": pack_cursor(context, [current, expiry, *next_key]) if next_key else None,
        "consistency": "Queue changes invalidate cursors; restart the first page on 409",
    }


@router.get("/admin/incidents/{incident_id}/priority")
def detail(incident_id: UUID, request: Request, user: Admin):
    return execute(priority_service(request, user).detail, str(incident_id))


@router.get("/admin/incidents/{incident_id}/priority/history")
def history(
    incident_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=4096),
):
    service = priority_service(request, user)
    execute(service.incidents.require, str(incident_id))
    context = {"id": str(incident_id), "limit": limit, "kind": "priority-history"}
    key = unpack_cursor(cursor, context, (2,))
    if key and not all(isinstance(value, str) for value in key):
        raise HTTPException(400, "Invalid priority history cursor")
    items, after = execute(service.repository.history, str(incident_id), limit, key)
    return {"items": items, "nextCursor": pack_cursor(context, after) if after else None}


def apply(incident_id, request, user, kind, action):
    service = priority_service(request, user, True)
    if request.app.state.settings.auth_provider == "local":
        request.app.state.auth_service.rate_limit(
            f"priority-controls:{user.id}", limit=30, window=60
        )
    else:
        # Existing durable Dynamo rate keys, isolated from citizen submission buckets.
        execute(service.incidents.repository.complaints.rate_limit, f"priority-controls:{user.id}")
    return execute(
        service.change,
        str(incident_id),
        kind,
        action.model_dump(mode="json"),
        Actor(user.id, "ADMIN"),
    )


@router.post("/admin/incidents/{incident_id}/priority/recalculate")
def recalculate(incident_id: UUID, data: PriorityAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "RECALCULATE", data)


@router.patch("/admin/incidents/{incident_id}/severity")
def severity(incident_id: UUID, data: AssessmentAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "SEVERITY", data)


@router.patch("/admin/incidents/{incident_id}/public-impact")
def impact(incident_id: UUID, data: AssessmentAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "PUBLIC_IMPACT", data)


@router.patch("/admin/incidents/{incident_id}/hazard-review")
def hazard(incident_id: UUID, data: HazardAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "HAZARD", data)


@router.post("/admin/incidents/{incident_id}/priority/override")
def override(incident_id: UUID, data: OverrideAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "OVERRIDE", data)


@router.delete("/admin/incidents/{incident_id}/priority/override")
def remove_override(incident_id: UUID, data: PriorityAction, request: Request, user: Admin):
    return apply(incident_id, request, user, "REMOVE_OVERRIDE", data)
