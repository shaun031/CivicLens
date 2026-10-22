from typing import Annotated, Literal
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ConfigDict, Field, model_validator

from app.api.routes.incidents import Admin
from app.api.routes.incidents import execute as domain_execute
from app.core.auth_dependencies import AuthenticatedUser, verify_local_origin
from app.models.complaint import Category
from app.schemas.work import Action
from app.utils.context_cursor import pack_cursor, unpack_cursor

router = APIRouter(tags=["Notifications, workflows and demonstration SLA"])


def execute(operation, *args):
    try:
        return domain_execute(operation, *args)
    except (ClientError, BotoCoreError) as error:
        raise HTTPException(
            503, "Workflow storage is temporarily unavailable; retry the same request"
        ) from error


Limit = Annotated[int, Query(ge=1, le=50)]
Cursor = Annotated[str | None, Query(max_length=2048)]
Status = Literal[
    "PENDING",
    "RUNNING",
    "WAITING_RETRY",
    "COMPLETED",
    "COMPLETED_WITH_REVIEW_REQUIRED",
    "FAILED",
    "CANCELLED",
]
NotificationType = Literal[
    "COMPLAINT_RECEIVED",
    "INCIDENT_STATUS_CHANGED",
    "COMPLAINT_UNDER_REVIEW",
    "INCIDENT_ASSIGNED",
    "OFFICER_ASSIGNED",
    "WORK_STARTED",
    "WORK_PROGRESS_UPDATED",
    "INCIDENT_OVERDUE",
    "URGENT_HAZARD_REVIEW",
    "ADMIN_ACTION_REQUIRED",
    "REPAIR_VERIFICATION_UPDATE",
    "OFFICER_REPAIR_UPDATE",
]


def service(request, user, unsafe=False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Active verified account required")
    if unsafe and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
        request.app.state.auth_service.rate_limit(
            f"workflow-control:{user.id}", limit=60, window=60
        )
    return request.app.state.workflow_service.repository


def page(result, context):
    after = result.pop("after", None)
    return result | {"nextCursor": pack_cursor(context, after) if after else None}


@router.get("/notifications")
def notifications(
    request: Request,
    user: AuthenticatedUser,
    limit: Limit = 20,
    cursor: Cursor = None,
    type: NotificationType | None = None,
    read: bool | None = None,
):
    context = {
        "route": "notifications",
        "user": user.id,
        "type": type,
        "read": read,
        "limit": limit,
    }
    result = execute(
        service(request, user).notifications,
        user.id,
        limit,
        unpack_cursor(cursor, context, (2,)),
        type,
        read,
    )
    return page(result, context)


@router.get("/notifications/unread-count")
def unread(request: Request, user: AuthenticatedUser):
    return execute(service(request, user).unread, user.id)


@router.patch("/notifications/{notification_id}/read")
def read_notification(notification_id: UUID, request: Request, user: AuthenticatedUser):
    return execute(service(request, user, True).read, user.id, str(notification_id))


@router.post("/notifications/mark-all-read")
def read_all(request: Request, user: AuthenticatedUser):
    return execute(service(request, user, True).read, user.id)


@router.get("/admin/workflows/summary")
def summary(request: Request, user: Admin):
    return execute(service(request, user).summary)


@router.get("/admin/workflows/dead-letters")
def dead_letters(request: Request, user: Admin, limit: Limit = 20, cursor: Cursor = None):
    context = {"route": "dead-letters", "user": user.id, "limit": limit}
    return page(
        execute(
            service(request, user).listing, "dead", limit, unpack_cursor(cursor, context, (2,))
        ),
        context,
    )


@router.post("/admin/workflows/dead-letters/{message_id}/redrive")
def redrive(message_id: UUID, data: Action, request: Request, user: Admin):
    return execute(
        service(request, user, True).replay, str(message_id), data.model_dump(mode="json"), user.id
    )


@router.post("/admin/workflows/dead-letters/{message_id}/acknowledge")
def acknowledge_dead(message_id: UUID, data: Action, request: Request, user: Admin):
    return execute(
        service(request, user, True).replay,
        str(message_id),
        data.model_dump(mode="json"),
        user.id,
        False,
        True,
    )


@router.get("/admin/workflows")
def workflows(
    request: Request,
    user: Admin,
    limit: Limit = 20,
    cursor: Cursor = None,
    status: Status | None = None,
    workflowType: Literal["IncidentTriageWorkflow"] | None = None,
):
    context = {
        "route": "workflows",
        "user": user.id,
        "status": status,
        "type": workflowType,
        "limit": limit,
    }
    return page(
        execute(
            service(request, user).listing,
            "workflow",
            limit,
            unpack_cursor(cursor, context, (2,)),
            status,
        ),
        context,
    )


@router.get("/admin/workflows/{workflow_id}")
def workflow_detail(workflow_id: UUID, request: Request, user: Admin):
    return execute(service(request, user).detail, str(workflow_id))


@router.post("/admin/workflows/{workflow_id}/retry")
def retry_workflow(workflow_id: UUID, data: Action, request: Request, user: Admin):
    return execute(
        service(request, user, True).replay,
        str(workflow_id),
        data.model_dump(mode="json"),
        user.id,
        True,
    )


class Policy(Action):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expectedVersion: int = Field(ge=0)
    priorityBand: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    category: Category | None = None
    departmentId: UUID | None = None
    urgent: bool = False
    responseHours: float = Field(gt=0, le=8760)
    resolutionHours: float = Field(gt=0, le=17520)

    @model_validator(mode="after")
    def valid_target(self):
        if self.resolutionHours < self.responseHours:
            raise ValueError("Resolution target must not precede response target")
        return self


@router.get("/admin/sla/policies")
def policies(request: Request, user: Admin):
    service(request, user)
    return execute(request.app.state.sla_service.policies)


@router.put("/admin/sla/policies/{policy_id}")
def save_policy(policy_id: str, data: Policy, request: Request, user: Admin):
    if policy_id in ("LOW", "MEDIUM", "HIGH", "CRITICAL") and (
        data.priorityBand != policy_id or data.category or data.departmentId or data.urgent
    ):
        raise HTTPException(
            422,
            "Default band policies retain universal coverage; create a separate specialized policy",
        )
    if len(policy_id) > 40 or not policy_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(422, "Policy ID must be a bounded alphanumeric identifier")
    service(request, user, True)
    return execute(
        request.app.state.sla_service.save, policy_id, data.model_dump(mode="json"), user.id
    )


@router.get("/admin/sla/escalations")
def escalations(request: Request, user: Admin, limit: Limit = 20, cursor: Cursor = None):
    service(request, user)
    context = {"route": "escalations", "user": user.id, "limit": limit}
    return page(
        execute(
            request.app.state.sla_service.escalations, limit, unpack_cursor(cursor, context, (2,))
        ),
        context,
    )


@router.post("/admin/sla/escalations/{escalation_id}/acknowledge")
def acknowledge_escalation(escalation_id: UUID, data: Action, request: Request, user: Admin):
    service(request, user, True)
    if not data.confirmed:
        raise HTTPException(422, "Confirmation required")
    return execute(request.app.state.sla_service.acknowledge, str(escalation_id), user.id)
