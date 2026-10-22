import json
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.analytics.filters import AnalyticsFilters
from app.api.routes.complaints import Citizen
from app.api.routes.incidents import Admin, execute
from app.api.routes.work import Officer
from app.core.auth_dependencies import AuthenticatedUser, verify_local_origin
from app.integrations.storage.base import StorageUnavailable
from app.models.complaint import Category
from app.models.incident import stable_id
from app.schemas.civic_intelligence import (
    Decision,
    FairnessReview,
    Operation,
    RecurrenceDecision,
    RepairSubmission,
    VerificationResponse,
)
from app.services.evidence_service import Upload

router = APIRouter(tags=["Private civic intelligence"])
Filters = Annotated[AnalyticsFilters, Query()]
RepairState = Literal[
    "PENDING_VERIFICATION",
    "VERIFIED_RESOLVED",
    "REJECTED",
    "REWORK_REQUIRED",
    "REOPENED",
    "INFORMATION_REQUIRED",
]
RecurrenceState = Literal[
    "POTENTIAL_RECURRENCE", "CONFIRMED_RECURRENCE", "DISMISSED", "INSUFFICIENT_EVIDENCE"
]


def actor(user):
    return {"id": user.id, "role": user.role.value}


def service(request, user, unsafe=False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Active verified account required")
    if unsafe and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
        request.app.state.auth_service.rate_limit(
            f"civic-intelligence:{user.id}", limit=60, window=60
        )
    value = request.app.state.civic_intelligence_service
    if value is None:
        raise HTTPException(
            503,
            (
                "Civic intelligence cloud source adapters require controlled "
                "projection/bootstrap before use"
            ),
        )
    return value


async def upload_payload(request, schema):
    uploads = []
    try:
        if request.headers.get("content-type", "").split(";")[0] == "application/json":
            data = schema.model_validate(await request.json())
        else:
            async with request.form(max_files=2, max_fields=1, max_part_size=32768) as form:
                if set(form) - {"payload", "images"} or len(form.getlist("payload")) != 1:
                    raise HTTPException(422, "Supply one JSON payload and at most two images")
                data = schema.model_validate_json(form["payload"])
                for item in form.getlist("images"):
                    if not isinstance(item, UploadFile):
                        raise HTTPException(422, "Image file required")
                    content = await item.read(request.app.state.settings.max_upload_bytes + 1)
                    uploads.append(
                        Upload(content, item.filename or "image.jpg", item.content_type or "")
                    )
        return data.model_dump(mode="json"), uploads
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            422, "Invalid repair/verification payload; check required fields and bounds"
        ) from error


@router.post("/officer/incidents/{incident_id}/repair-attempts", status_code=201)
async def submit(incident_id: UUID, request: Request, user: Officer):
    value = service(request, user, True)
    data, uploads = await upload_payload(request, RepairSubmission)
    return await run_in_threadpool(
        execute, value.upload_action, "submit", str(incident_id), data, actor(user), uploads
    )


@router.get("/officer/incidents/{incident_id}/repair-attempts")
def officer_attempts(incident_id: UUID, request: Request, user: Officer):
    return execute(service(request, user).repository.attempts, str(incident_id), actor(user))


@router.get("/admin/incidents/{incident_id}/repair-attempts")
def admin_attempts(incident_id: UUID, request: Request, user: Admin):
    return execute(service(request, user).repository.attempts, str(incident_id), actor(user))


@router.get("/incidents/{incident_id}/repair-attempts/{attempt_id}/evidence/{image_id}")
def evidence(
    incident_id: UUID, attempt_id: UUID, image_id: UUID, request: Request, user: AuthenticatedUser
):
    value = service(request, user)
    key = execute(
        value.repository.evidence, str(incident_id), str(attempt_id), str(image_id), actor(user)
    )
    try:
        content = value.complaints.storage.get(key)
    except StorageUnavailable as error:
        raise HTTPException(503, "Private evidence temporarily unavailable") from error
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/citizen/verification-requests")
def requests(
    request: Request, user: Citizen, after: UUID | None = None, limit: int = Query(25, ge=1, le=50)
):
    return execute(
        service(request, user).repository.requests, actor(user), str(after) if after else "", limit
    )


@router.get("/citizen/verification-history")
def history(
    request: Request, user: Citizen, after: UUID | None = None, limit: int = Query(25, ge=1, le=50)
):
    return execute(
        service(request, user).repository.requests,
        actor(user),
        str(after) if after else "",
        limit,
        True,
    )


@router.get("/citizen/verification-requests/{request_id}")
def request_detail(request_id: UUID, request: Request, user: Citizen):
    return execute(service(request, user).repository.request_detail, str(request_id), actor(user))


@router.post("/citizen/verification-requests/{request_id}/respond")
async def respond(request_id: UUID, request: Request, user: Citizen):
    value = service(request, user, True)
    data, uploads = await upload_payload(request, VerificationResponse)
    return await run_in_threadpool(
        execute, value.upload_action, "respond", str(request_id), data, actor(user), uploads
    )


@router.get("/admin/repairs/pending")
def pending(
    request: Request,
    user: Admin,
    after: UUID | None = None,
    limit: int = Query(25, ge=1, le=50),
    state: RepairState | None = None,
):
    value = service(request, user)
    page = execute(value.repository.pending, str(after) if after else "", limit, state)
    return {
        "items": [execute(value.repository.detail, i, actor(user)) for i in page.pop("attemptIds")],
        **page,
    }


@router.get("/admin/repairs/{attempt_id}")
def repair_detail(attempt_id: UUID, request: Request, user: Admin):
    value = service(request, user)
    result = execute(value.repository.detail, str(attempt_id), actor(user))
    result["priority"] = execute(value.priorities.detail, result["incidentId"])
    return result


@router.post("/admin/repairs/{attempt_id}/{action}")
def repair_decision(
    attempt_id: UUID,
    action: Literal[
        "approve", "reject", "request-rework", "reopen", "request-information", "approve-evidence"
    ],
    data: Decision,
    request: Request,
    user: Admin,
):
    return execute(
        service(request, user, True).decision,
        str(attempt_id),
        action,
        data.model_dump(mode="json"),
        actor(user),
    )


@router.post("/admin/incidents/{incident_id}/check-recurrence")
def check_recurrence(incident_id: UUID, data: Operation, request: Request, user: Admin):
    return execute(
        service(request, user, True).check_recurrence,
        str(incident_id),
        data.model_dump(mode="json"),
        actor(user),
    )


@router.get("/admin/recurrences")
def recurrences(
    request: Request,
    user: Admin,
    after: UUID | None = None,
    limit: int = Query(25, ge=1, le=50),
    state: RecurrenceState | None = None,
    category: Category | None = None,
    start: date | None = None,
    end: date | None = None,
    incident: UUID | None = None,
):
    if start and end and (end < start or (end - start).days >= 366):
        raise HTTPException(422, "Select 1–366 days")
    if end and end >= date(2100, 12, 31):
        raise HTTPException(422, "End must precede 2100-12-31")
    return execute(
        service(request, user).repository.recurrences,
        str(after) if after else "",
        limit,
        state,
        category,
        start.isoformat() if start else None,
        (end + timedelta(days=1)).isoformat() if end else None,
        str(incident) if incident else None,
    )


@router.get("/admin/recurrences/{recurrence_id}")
def recurrence_detail(recurrence_id: UUID, request: Request, user: Admin):
    return execute(service(request, user).repository.recurrence_detail, str(recurrence_id))


@router.post("/admin/recurrences/{recurrence_id}/{action}")
def recurrence_decision(
    recurrence_id: UUID,
    action: Literal["confirm", "dismiss", "request-review"],
    data: RecurrenceDecision,
    request: Request,
    user: Admin,
):
    return execute(
        service(request, user, True).repository.review_recurrence,
        str(recurrence_id),
        action,
        data.model_dump(mode="json"),
        actor(user),
    )


@router.get("/admin/analytics/fairness")
@router.get("/admin/analytics/fairness/areas")
def fairness(request: Request, user: Admin, filters: Filters):
    return execute(service(request, user).fairness, filters)


@router.get("/admin/analytics/fairness/compare")
def area_comparison(
    request: Request,
    user: Admin,
    first: str = Query(max_length=100),
    second: str = Query(max_length=100),
):
    try:
        filters = AnalyticsFilters.model_validate(
            {k: v for k, v in request.query_params.items() if k not in ("first", "second")}
        )
    except ValidationError as error:
        raise HTTPException(422, "Invalid comparison filters") from error
    result = execute(service(request, user).fairness, filters)
    result["areas"] = [a for a in result["areas"] if a["areaId"] in (first, second)]
    if len(result["areas"]) != 2:
        raise HTTPException(422, "Choose two different occupied areas within the selected cohort")
    return result


@router.get("/admin/analytics/fairness/reviews")
def reviews(
    request: Request, user: Admin, after: UUID | None = None, limit: int = Query(25, ge=1, le=50)
):
    return execute(
        service(request, user).repository.fairness_reviews, str(after) if after else "", limit
    )


@router.post("/admin/analytics/fairness/reviews", status_code=201)
def create_review(data: FairnessReview, request: Request, user: Admin):
    identity = stable_id(f"fairness/{user.id}/{data.operationId}")
    return execute(
        service(request, user, True).repository.save_fairness_review,
        identity,
        data.model_dump(mode="json"),
        actor(user),
    )


@router.patch("/admin/analytics/fairness/reviews/{review_id}")
def edit_review(review_id: UUID, data: FairnessReview, request: Request, user: Admin):
    return execute(
        service(request, user, True).repository.save_fairness_review,
        str(review_id),
        data.model_dump(mode="json"),
        actor(user),
    )
