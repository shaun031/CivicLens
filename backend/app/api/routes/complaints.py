from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.auth_dependencies import AuthenticatedUser, verify_local_origin
from app.models.complaint import Complaint, ComplaintInput, ComplaintPage, ComplaintSummary
from app.models.discovery import SearchFilters, SearchQuery
from app.models.user import Principal, Role
from app.repositories.complaint_repository import RepositoryUnavailable
from app.services.complaint_service import ComplaintService
from app.services.evidence_service import Upload

router = APIRouter(prefix="/complaints", tags=["Complaints"])


def citizen_only(user: AuthenticatedUser) -> Principal:
    if user.role != Role.CITIZEN or not user.is_verified or not user.is_active:
        raise HTTPException(
            403,
            "Verified citizen access is required. Officer/admin workflows are not available.",
        )
    return user


Citizen = Annotated[Principal, Depends(citizen_only)]


def service(request: Request) -> ComplaintService:
    return request.app.state.complaint_service


@router.post(
    "",
    status_code=201,
    response_model=Complaint,
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            }
        ],
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "title",
                            "description",
                            "category",
                            "reportedSeverity",
                            "latitude",
                            "longitude",
                        ],
                        "properties": {
                            "title": {"type": "string", "minLength": 10, "maxLength": 150},
                            "description": {"type": "string", "minLength": 20, "maxLength": 2000},
                            "category": {
                                "type": "string",
                                "enum": [
                                    "POTHOLE",
                                    "DAMAGED_ROAD",
                                    "BROKEN_STREETLIGHT",
                                    "GARBAGE",
                                    "DRAINAGE",
                                    "PUBLIC_PROPERTY_DAMAGE",
                                    "OTHER",
                                ],
                            },
                            "reportedSeverity": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH"],
                            },
                            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                            "landmark": {"type": "string", "maxLength": 200},
                            "addressLabel": {"type": "string", "maxLength": 200},
                            "images": {
                                "type": "array",
                                "maxItems": 2,
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                    }
                }
            },
        },
    },
)
async def create_complaint(request: Request, user: Citizen) -> Complaint:
    if request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
    try:
        key = str(UUID(request.headers.get("Idempotency-Key", "")))
    except ValueError as error:
        raise HTTPException(422, "A UUID Idempotency-Key header is required.") from error
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "Use multipart/form-data for complaint submission.")
    async with request.form(max_files=2, max_fields=8, max_part_size=8192) as form:
        values, uploads = {}, []
        fields = set(ComplaintInput.model_fields)
        for name, value in form.multi_items():
            if name == "images" and isinstance(value, UploadFile):
                disposition = unquote(value.headers.get("content-disposition", ""))
                if any(char in disposition for char in ("\\", "/", ":")):
                    raise HTTPException(422, "Unsafe image filename.")
                content = await value.read(request.app.state.settings.max_upload_bytes + 1)
                uploads.append(Upload(content, value.filename or "image", value.content_type or ""))
            elif name not in fields or isinstance(value, UploadFile) or name in values:
                raise HTTPException(422, "Unexpected or repeated complaint field.")
            else:
                values[name] = value
        if len(uploads) > 2:
            raise HTTPException(422, "A complaint accepts at most two images.")
        try:
            data = ComplaintInput.model_validate(values)
        except ValidationError as error:
            raise HTTPException(
                422,
                [
                    {"loc": ["body", *item["loc"]], "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ],
            ) from error
        if len(data.description) > request.app.state.settings.complaint_description_max:
            raise HTTPException(422, "Description exceeds the configured length limit.")
        return await run_in_threadpool(
            service(request).create, user.id, data, uploads, key, request.state.request_id
        )


@router.get("", response_model=ComplaintPage)
def list_complaints(
    request: Request,
    user: Citizen,
    query: Annotated[SearchQuery, Query()],
) -> ComplaintPage:
    if set(request.query_params) - {*SearchFilters.model_fields, "limit", "cursor"}:
        raise HTTPException(422, "Unsupported complaint search parameter.")
    try:
        filters = SearchFilters.model_validate(query.model_dump(exclude={"limit", "cursor"}))
        return service(request).repository.list(user.id, query.limit, query.cursor, filters)
    except RepositoryUnavailable as error:
        raise HTTPException(503, "Complaint database is unavailable.") from error


@router.get("/summary", response_model=ComplaintSummary)
def complaint_summary(
    request: Request, user: Citizen, days: Annotated[int, Query(ge=7, le=90)] = 30
) -> ComplaintSummary:
    try:
        return service(request).repository.summary(user.id, days)
    except RepositoryUnavailable as error:
        raise HTTPException(503, "Complaint database is unavailable.") from error


@router.get("/{complaint_id}", response_model=Complaint)
def complaint_details(complaint_id: UUID, request: Request, user: Citizen) -> Complaint:
    return service(request).get(str(complaint_id), user.id)


@router.get("/{complaint_id}/images/{image_id}", response_class=Response)
def complaint_image(
    complaint_id: UUID, image_id: UUID, request: Request, user: Citizen
) -> Response:
    return Response(
        content=service(request).image(str(complaint_id), str(image_id), user.id),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="evidence.jpg"',
            "X-Content-Type-Options": "nosniff",
        },
    )
