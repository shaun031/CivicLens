import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.api.routes.complaints import Citizen
from app.core.auth_dependencies import require_roles, verify_local_origin
from app.models.discovery import (
    Bounds,
    Category,
    CitizenNearby,
    Nearby,
    NearbyIssuePage,
    Publication,
    PublicationRequest,
    PublicationReview,
    PublicIssue,
    PublicIssuePage,
    Status,
)
from app.models.user import Principal, Role
from app.repositories.complaint_repository import RepositoryUnavailable

router = APIRouter(tags=["Publication and public discovery"])
Admin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]


def repository(request: Request):
    return request.app.state.complaint_service.repository.discovery


def execute(operation, *args):
    try:
        return operation(*args)
    except (RepositoryUnavailable, sqlite3.Error) as error:
        raise HTTPException(
            503, "Discovery data is temporarily unavailable. Please retry."
        ) from error


def origin(request: Request):
    if request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)


def public_repository(request: Request):
    result = repository(request)
    # Ignore untrusted forwarded headers; deploy-time proxy handling must be explicitly reviewed.
    execute(result.public_rate, request.client.host if request.client else "unknown")
    return result


@router.patch("/complaints/{complaint_id}/publication-request", response_model=Publication)
def publication_request(
    complaint_id: UUID, data: PublicationRequest, request: Request, user: Citizen
):
    origin(request)
    return execute(
        repository(request).request_publication, str(complaint_id), user.id, data.requested
    )


@router.patch("/admin/complaints/{complaint_id}/publication", response_model=Publication)
def publication_review(complaint_id: UUID, data: PublicationReview, request: Request, user: Admin):
    origin(request)
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Verified active administrator access is required.")
    return execute(repository(request).review_publication, str(complaint_id), user.id, data)


class BoundsQuery(Bounds):
    category: Category | None = None
    status: Status | None = None
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


class NearbyQuery(Nearby):
    category: Category | None = None
    status: Status | None = None
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


def page_limits(query):
    if query.limit < 1 or query.limit > 100 or (query.cursor and len(query.cursor) > 2048):
        raise HTTPException(422, "Page limit must be 1–100 and cursor at most 2048 characters.")


@router.get("/public/issues", response_model=PublicIssuePage, response_model_exclude_none=True)
def public_bounds(request: Request, query: Annotated[BoundsQuery, Query()]):
    page_limits(query)
    bounds = Bounds.model_validate(query.model_dump(include=set(Bounds.model_fields)))
    return execute(
        public_repository(request).public_page,
        bounds,
        query.category,
        query.status,
        query.limit,
        query.cursor,
    )


@router.get(
    "/public/issues/nearby", response_model=PublicIssuePage, response_model_exclude_none=True
)
def public_nearby(request: Request, query: Annotated[NearbyQuery, Query()]):
    page_limits(query)
    if query.radiusMeters > request.app.state.settings.nearby_max_radius_meters:
        raise HTTPException(422, "Radius exceeds the configured maximum.")
    nearby = Nearby.model_validate(query.model_dump(include=set(Nearby.model_fields)))
    return execute(
        public_repository(request).nearby_page,
        nearby,
        query.category,
        query.status,
        query.limit,
        query.cursor,
    )


@router.get(
    "/public/issues/{public_id}", response_model=PublicIssue, response_model_exclude_none=True
)
def public_detail(public_id: UUID, request: Request):
    issue = execute(public_repository(request).public_details, str(public_id))
    if not issue:
        raise HTTPException(404, "Public issue not found.")
    return issue


@router.get("/citizen/issues/nearby", response_model=NearbyIssuePage)
def citizen_nearby(request: Request, user: Citizen, query: Annotated[CitizenNearby, Query()]):
    """Identity is server-authenticated. Never accept a caller-supplied owner ID."""
    if query.radiusKm * 1000 > request.app.state.settings.nearby_max_radius_meters:
        raise HTTPException(422, "Radius exceeds the configured maximum.")
    return execute(
        repository(request).citizen_nearby,
        user.id,
        query.meters(),
        query.category,
        query.status,
        query.limit,
        query.cursor,
    )


@router.get("/citizen/issues/latest-location")
def latest_location(request: Request, user: Citizen):
    return {"location": execute(repository(request).latest_location, user.id)}
