import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.routes.complaints import Citizen
from app.core.auth_dependencies import require_roles, verify_local_origin
from app.integrations.storage.base import StorageUnavailable
from app.models.complaint import Category
from app.models.incident import Actor, IncidentError, IncidentStatus
from app.models.user import Principal, Role
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.context_cursor import pack_cursor, unpack_cursor
from app.utils.geography import haversine

router = APIRouter(tags=["Incident membership and correction"])
Admin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]


def service(request: Request, user: Principal, unsafe: bool = False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Active verified administrator access is required")
    if unsafe and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
    return request.app.state.incident_service


def execute(operation, *args):
    try:
        return operation(*args)
    except IncidentError as error:
        raise HTTPException(error.status, error.message) from error
    except (RepositoryUnavailable, sqlite3.Error, OSError) as error:
        raise HTTPException(
            503, "Incident data unavailable. Retry with the same operation ID."
        ) from error


class IncidentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="", max_length=150)
    category: Category | None = None
    status: IncidentStatus | None = IncidentStatus.OPEN
    sort: Literal["newest", "oldest"] = "newest"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=2048)


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    operationId: UUID
    sourceIncidentId: UUID
    expectedSourceVersion: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=500)
    confirmed: bool

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("Correction reasons must not contain control characters")
        return value


class LinkCorrection(Correction):
    targetIncidentId: UUID
    expectedTargetVersion: int = Field(ge=1)
    physicalIssueConfirmed: bool
    complaintId: UUID | None = None
    matchingCandidateId: UUID | None = None


class SplitCorrection(Correction):
    complaintIds: list[UUID] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.complaintIds)) != len(self.complaintIds):
            raise ValueError("Select each complaint only once")
        return self


def paginate_context(cursor, context):
    key = unpack_cursor(cursor, context, (2,))
    if key and (not isinstance(key[0], str) or not isinstance(key[1], str)):
        raise HTTPException(400, "Invalid incident page cursor")
    return key


@router.get("/admin/incidents/summary")
def summary(request: Request, user: Admin):
    return execute(service(request, user).repository.summary)


@router.get("/admin/incidents")
def incidents(request: Request, user: Admin, query: Annotated[IncidentQuery, Query()]):
    context = query.model_dump(mode="json", exclude={"cursor"})
    key = paginate_context(query.cursor, context)
    items, next_key = execute(service(request, user).repository.catalog, context, query.limit, key)
    return {"items": items, "nextCursor": pack_cursor(context, next_key) if next_key else None}


@router.get("/admin/incidents/{incident_id}")
def incident_detail(incident_id: UUID, request: Request, user: Admin):
    incidents = service(request, user)
    incident, chain = execute(incidents.resolve, str(incident_id))
    return incident.model_dump(mode="json") | {
        "requestedIncidentId": str(incident_id),
        "aliasChain": chain,
        "reviewNeeded": execute(incidents.repository.review_needed, incident.incidentId),
    }


def member_dto(member, incident_id):
    complaint = member.complaint
    return {
        key: getattr(complaint, key)
        for key in (
            "complaintId",
            "incidentId",
            "title",
            "description",
            "category",
            "status",
            "latitude",
            "longitude",
            "createdAt",
            "reportedSeverity",
        )
    } | {
        "eligibleReporter": member.eligible_reporter,
        "images": [
            {
                "imageId": image.imageId,
                "url": f"/admin/incidents/{incident_id}/complaints/"
                f"{complaint.complaintId}/images/{image.imageId}",
            }
            for image in complaint.images[:2]
        ],
    }


@router.get("/admin/incidents/{incident_id}/complaints")
def members(
    incident_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=20, ge=1, le=30),
    cursor: str | None = Query(default=None, max_length=2048),
):
    incidents = service(request, user)
    incident, _ = execute(incidents.resolve, str(incident_id))
    context = {"incidentId": incident.incidentId, "version": incident.version, "limit": limit}
    key = paginate_context(cursor, context)
    rows = execute(incidents.members, incident.incidentId)
    if key:
        rows = [m for m in rows if [m.complaint.createdAt, m.complaint.complaintId] > key]
    items = [
        member_dto(row, incident.incidentId)
        | {
            "distanceMeters": haversine(
                incident.latitude,
                incident.longitude,
                row.complaint.latitude,
                row.complaint.longitude,
            )
        }
        for row in rows[:limit]
    ]
    next_key = [items[-1]["createdAt"], items[-1]["complaintId"]] if len(rows) > limit else None
    return {
        "items": items,
        "nextCursor": pack_cursor(context, next_key) if next_key else None,
        "incidentVersion": incident.version,
    }


@router.get("/admin/incidents/{incident_id}/history")
def history(
    incident_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=2048),
):
    incidents = service(request, user)
    execute(incidents.require, str(incident_id))  # Alias history stays on the original incident.
    context = {"incidentId": str(incident_id), "limit": limit, "kind": "incident-history"}
    key = paginate_context(cursor, context)
    items, next_key = execute(incidents.repository.history, str(incident_id), limit, key)
    return {"items": items, "nextCursor": pack_cursor(context, next_key) if next_key else None}


@router.get("/admin/incidents/{incident_id}/recommendations")
def recommendations(
    incident_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=30, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=2048),
):
    incidents = service(request, user)
    incident, _ = execute(incidents.resolve, str(incident_id))
    context = {
        "incidentId": incident.incidentId,
        "version": incident.version,
        "kind": "clustering-recommendations",
        "limit": limit,
    }
    key = unpack_cursor(cursor, context, (1,))
    if key and (type(key[0]) is not int or not 0 <= key[0] <= 500):
        raise HTTPException(400, "Invalid recommendations cursor")
    offset, items, processing = key[0] if key else 0, [], []
    for member in execute(incidents.members, incident.incidentId):
        job = execute(incidents.repository.job, member.complaint.complaintId)
        processing.append(
            {
                "complaintId": member.complaint.complaintId,
                "state": job["state"] if job else "PENDING",
            }
        )
        for row in ((job or {}).get("report") or {}).get("recommendations", []):
            items.append(
                {
                    key: row[key]
                    for key in (
                        "targetIncidentId",
                        "targetVersion",
                        "candidateId",
                        "eligibleForAutoLink",
                        "explanation",
                    )
                }
                | {"sourceComplaintId": member.complaint.complaintId}
            )
    items.sort(key=lambda row: (row["sourceComplaintId"], row["targetIncidentId"]))
    next_key = [offset + limit] if len(items) > offset + limit else None
    return {
        "items": items[offset : offset + limit],
        "processing": processing,
        "mode": incidents.config.mode,
        "nextCursor": pack_cursor(context, next_key) if next_key else None,
    }


def apply_change(request, user, kind, data, incident_id=None):
    incidents = service(request, user, True)
    if incident_id and str(data.sourceIncidentId) != str(incident_id):
        raise HTTPException(409, "Source incident no longer matches the selected operation")
    return execute(incidents.mutate, kind, data.model_dump(mode="json"), Actor(user.id, "ADMIN"))


@router.post("/admin/incidents/merge")
def merge(data: LinkCorrection, request: Request, user: Admin):
    return apply_change(request, user, "MERGE", data)


@router.post("/admin/incidents/{incident_id}/link-complaint")
def link(incident_id: UUID, data: LinkCorrection, request: Request, user: Admin):
    if str(data.targetIncidentId) != str(incident_id) or data.complaintId is None:
        raise HTTPException(422, "A current target incident and complaint ID are required")
    return apply_change(request, user, "MANUAL_LINK", data)


@router.post("/admin/incidents/{incident_id}/split")
def split(incident_id: UUID, data: SplitCorrection, request: Request, user: Admin):
    return apply_change(request, user, "SPLIT", data, incident_id)


@router.post("/admin/incidents/{incident_id}/unlink-complaint")
def unlink(incident_id: UUID, data: SplitCorrection, request: Request, user: Admin):
    if len(data.complaintIds) != 1:
        raise HTTPException(422, "Unlink selects exactly one current complaint")
    return apply_change(request, user, "UNLINK", data, incident_id)


@router.post("/admin/incidents/{incident_id}/recheck")
def recheck(incident_id: UUID, data: Correction, request: Request, user: Admin):
    return apply_change(request, user, "RECHECK", data, incident_id)


@router.get("/admin/incidents/{incident_id}/complaints/{complaint_id}/images/{image_id}")
def image(incident_id: UUID, complaint_id: UUID, image_id: UUID, request: Request, user: Admin):
    incidents = service(request, user)
    incident, _ = execute(incidents.resolve, str(incident_id))
    member = execute(incidents.require_member, str(complaint_id))
    if member.complaint.incidentId != incident.incidentId:
        raise HTTPException(404, "Evidence not found")
    found = next(
        (image for image in member.complaint.images if image.imageId == str(image_id)), None
    )
    if not found:
        raise HTTPException(404, "Evidence not found")
    try:
        content = incidents.matching.storage.get(found.storageKey)
    except StorageUnavailable as error:
        raise HTTPException(503, "Evidence temporarily unavailable") from error
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/complaints/{complaint_id}/incident")
def owner_summary(complaint_id: UUID, request: Request, user: Citizen):
    # Ownership is checked BEFORE reading incident state, aliases or any membership metadata.
    complaints = request.app.state.complaint_service.repository
    complaint = execute(complaints.get, str(complaint_id), user.id)
    if complaint is None:
        raise HTTPException(404, "Complaint not found")
    if not complaint.incidentId:
        return {"incidentId": None, "processing": "PENDING"}
    incidents = request.app.state.incident_service
    incident, _ = execute(incidents.resolve, complaint.incidentId)
    return {
        "incidentId": incident.incidentId,
        "category": complaint.category,
        "status": incident.status,
        "processing": "COMPLETE",
    }
