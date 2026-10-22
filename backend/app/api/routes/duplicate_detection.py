import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.algorithms.duplicate_detection.models import Classification, ReviewStatus
from app.core.auth_dependencies import require_roles, verify_local_origin
from app.integrations.storage.base import StorageUnavailable
from app.models.complaint import Category
from app.models.user import Principal, Role
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.context_cursor import pack_cursor, unpack_cursor

router = APIRouter(prefix="/admin", tags=["Administrator duplicate review"])
Admin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]


class CandidateQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    classification: Classification | None = None
    reviewStatus: ReviewStatus | None = None
    category: Category | None = None
    complaintId: UUID | None = None
    minScore: float = Field(default=0, ge=0, le=1)
    maxScore: float = Field(default=1, ge=0, le=1)
    q: str = Field(default="", max_length=150)
    sort: Literal["score", "date"] = "score"
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def check_range(self):
        if self.minScore > self.maxScore:
            raise ValueError("Minimum score cannot exceed maximum score")
        return self


def service(request: Request, user: Principal, unsafe: bool = False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Verified active administrator access is required.")
    if unsafe and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
    return request.app.state.duplicate_detection_service


def execute(operation, *args):
    try:
        return operation(*args)
    except (RepositoryUnavailable, sqlite3.Error, OSError) as error:
        raise HTTPException(503, "Matching data unavailable. Retry later.") from error


def page(repository, query: CandidateQuery, complaint_id: str | None = None):
    context = query.model_dump(mode="json", exclude={"cursor"})
    context["complaintId"] = complaint_id or context.get("complaintId")
    key = unpack_cursor(query.cursor, context, (1,))
    if key and (not isinstance(key[0], int) or not 0 <= key[0] <= 1000000):
        raise HTTPException(400, "Invalid page cursor")
    offset = key[0] if key else 0
    filters = context | {"offset": offset}
    rows = execute(repository.catalog, filters)
    return {
        "items": rows[: query.limit],
        "nextCursor": pack_cursor(context, [offset + query.limit])
        if len(rows) > query.limit
        else None,
    }


@router.get("/duplicate-candidates")
def candidates(request: Request, user: Admin, query: Annotated[CandidateQuery, Query()]):
    return page(service(request, user).repository, query)


@router.get("/complaints/{complaint_id}/duplicate-candidates")
def complaint_candidates(
    complaint_id: UUID, request: Request, user: Admin, query: Annotated[CandidateQuery, Query()]
):
    repository = service(request, user).repository
    if not execute(repository.load, str(complaint_id)):
        raise HTTPException(404, "Complaint not found")
    return page(repository, query, str(complaint_id)) | {
        "processing": execute(repository.job, str(complaint_id))
    }


def require_candidate(repository, identity: str):
    result = execute(repository.candidate, identity)
    if result is None:
        raise HTTPException(404, "Candidate not found")
    return result


def comparison(complaint, candidate_id: str) -> dict:
    return {
        key: getattr(complaint, key)
        for key in (
            "complaintId",
            "title",
            "description",
            "category",
            "latitude",
            "longitude",
            "status",
            "createdAt",
            "incidentId",
        )
    } | {
        "images": [
            {
                "imageId": image.imageId,
                "url": f"/admin/duplicate-candidates/{candidate_id}/complaints/"
                f"{complaint.complaintId}/images/{image.imageId}",
            }
            for image in complaint.images[:2]
        ]
    }


@router.get("/duplicate-candidates/{candidate_id}")
def detail(candidate_id: UUID, request: Request, user: Admin):
    repository = service(request, user).repository
    result = require_candidate(repository, str(candidate_id))
    complaints = [
        execute(repository.load, result[key])
        for key in ("sourceComplaintId", "possibleDuplicateId")
    ]
    if any(complaint is None for complaint in complaints):
        raise HTTPException(404, "Comparison no longer available")
    comparisons = []
    incidents = request.app.state.incident_service
    for complaint in complaints:
        incident = incidents.repository.load(complaint.incidentId) if complaint.incidentId else None
        comparisons.append(
            comparison(complaint, str(candidate_id))
            | {"incident": incident.model_dump(mode="json") if incident else None}
        )
    return result | {
        "complaints": comparisons,
        "processing": [execute(repository.job, complaint.complaintId) for complaint in complaints],
    }


@router.post("/duplicate-candidates/{candidate_id}/dismiss")
def dismiss(candidate_id: UUID, request: Request, user: Admin):
    repository = service(request, user, True).repository
    require_candidate(repository, str(candidate_id))
    return execute(repository.review, str(candidate_id), ReviewStatus.DISMISSED, user.id)


@router.post("/duplicate-candidates/{candidate_id}/reviewed")
def reviewed(candidate_id: UUID, request: Request, user: Admin):
    repository = service(request, user, True).repository
    require_candidate(repository, str(candidate_id))
    return execute(
        repository.review, str(candidate_id), ReviewStatus.REVIEWED_POSSIBLE_DUPLICATE, user.id
    )


@router.post("/complaints/{complaint_id}/duplicate-check")
def recheck(complaint_id: UUID, request: Request, user: Admin):
    matching = service(request, user, True)
    if execute(matching.repository.load, str(complaint_id)) is None:
        raise HTTPException(404, "Complaint not found")
    # Existing persistent limiter, separate bucket from complaint creation.
    discovery = request.app.state.complaint_service.repository.discovery
    execute(discovery.public_rate, f"admin-matching:{user.id}")
    execute(matching.repository.enqueue, str(complaint_id))
    execute(matching.process_one, str(complaint_id))
    return {"processing": execute(matching.repository.job, str(complaint_id))}


@router.get("/duplicate-candidates/{candidate_id}/complaints/{complaint_id}/images/{image_id}")
def evidence(candidate_id: UUID, complaint_id: UUID, image_id: UUID, request: Request, user: Admin):
    matching = service(request, user)
    result = require_candidate(matching.repository, str(candidate_id))
    if str(complaint_id) not in (result["sourceComplaintId"], result["possibleDuplicateId"]):
        raise HTTPException(404, "Evidence not found")
    complaint = execute(matching.repository.load, str(complaint_id))
    image = (
        next((image for image in complaint.images if image.imageId == str(image_id)), None)
        if complaint
        else None
    )
    if image is None:
        raise HTTPException(404, "Evidence not found")
    try:
        content = matching.storage.get(image.storageKey)
    except StorageUnavailable as error:
        raise HTTPException(503, "Evidence temporarily unavailable") from error
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
