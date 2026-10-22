import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.routes.incidents import Admin, execute
from app.core.auth_dependencies import require_roles, verify_local_origin
from app.models.incident import Actor
from app.models.user import Principal, Role
from app.schemas.work import (
    Action,
    AssignmentAction,
    DepartmentAction,
    MembershipAction,
    ProgressAction,
    RuleAction,
    VersionAction,
    WorkQuery,
)
from app.utils.context_cursor import pack_cursor, unpack_cursor

router = APIRouter(tags=["Municipal departments and work allocation"])
Officer = Annotated[Principal, Depends(require_roles(Role.OFFICER))]


def service(request, user, unsafe=False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Active verified municipal account required")
    if unsafe and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
        request.app.state.auth_service.rate_limit(f"municipal-work:{user.id}", limit=60, window=60)
    return request.app.state.work_service


def actor(user):
    return Actor(user.id, user.role.value)


@router.get("/admin/departments/summary")
def summary(request: Request, user: Admin):
    return execute(service(request, user).repository.summary)


@router.post("/admin/departments/seed")
def seed(data: Action, request: Request, user: Admin):
    return execute(
        service(request, user, True).repository.seed, data.model_dump(mode="json"), actor(user)
    )


@router.get("/admin/departments")
def departments(request: Request, user: Admin):
    return execute(service(request, user).repository.departments)


@router.post("/admin/departments", status_code=201)
def create_department(data: DepartmentAction, request: Request, user: Admin):
    # Derive the prospective UUID from the request, so retry does not create a second entity.
    from app.models.incident import stable_id

    identity = stable_id(f"department/{user.id}/{data.operationId}")
    return execute(
        service(request, user, True).repository.save_department,
        identity,
        data.model_dump(mode="json"),
        actor(user),
    )


@router.get("/admin/routing-rules")
def rules(request: Request, user: Admin):
    repository = service(request, user).repository
    return execute(repository.list_rules)


@router.post("/admin/routing-rules")
def save_rule(data: RuleAction, request: Request, user: Admin):
    return execute(
        service(request, user, True).repository.save_rule, data.model_dump(mode="json"), actor(user)
    )


@router.get("/admin/officers")
def officer_directory(
    request: Request,
    user: Admin,
    after: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=50),
):
    return execute(
        service(request, user).repository.officer_directory, str(after) if after else "", limit
    )


@router.get("/admin/departments/{department_id}")
def department_detail(department_id: UUID, request: Request, user: Admin):
    return execute(service(request, user).repository.department_detail, str(department_id))


@router.patch("/admin/departments/{department_id}")
def edit_department(department_id: UUID, data: DepartmentAction, request: Request, user: Admin):
    return execute(
        service(request, user, True).repository.save_department,
        str(department_id),
        data.model_dump(mode="json"),
        actor(user),
    )


@router.get("/admin/departments/{department_id}/officers")
def members(department_id: UUID, request: Request, user: Admin):
    return {
        "items": execute(service(request, user).repository.department_detail, str(department_id))[
            "officers"
        ]
    }


@router.post("/admin/departments/{department_id}/officers")
def membership(department_id: UUID, data: MembershipAction, request: Request, user: Admin):
    return execute(
        service(request, user, True).repository.save_membership,
        str(department_id),
        data.model_dump(mode="json"),
        actor(user),
    )


@router.delete("/admin/departments/{department_id}/officers/{officer_id}")
def remove_membership(
    department_id: UUID, officer_id: UUID, data: VersionAction, request: Request, user: Admin
):
    repository = service(request, user, True).repository
    return execute(
        repository.remove_membership,
        str(department_id),
        str(officer_id),
        data.model_dump(mode="json"),
        actor(user),
    )


def page(request, user, query, officer=None, department=None, unassigned=False):
    repository = service(request, user).repository
    context = query.model_dump(mode="json", exclude={"cursor"}) | {
        "principal": user.id,
        "own": officer,
        "department": department,
        "unassigned": unassigned,
    }
    if officer and (query.officerId is not None or query.departmentId is not None):
        raise HTTPException(422, "Officer queues use only the authenticated officer identity")
    if department:
        execute(repository.department_exists, department)
        context["departmentId"] = department
    key = unpack_cursor(query.cursor, context, (7,))
    if key and (
        type(key[0]) is not int
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in key[1:-1])
        or not isinstance(key[-1], str)
    ):
        raise HTTPException(400, "Invalid work queue cursor")
    result = execute(
        repository.queue,
        context,
        key[2:] if key else None,
        key[0] if key else None,
        key[1] if key else None,
        officer,
        unassigned,
    )
    after = result.pop("after")
    result["nextCursor"] = (
        pack_cursor(context, [result["queueRevision"], result["validUntil"], *after])
        if after
        else None
    )
    return result


@router.get("/admin/assignments")
def assignments(request: Request, user: Admin, query: Annotated[WorkQuery, Query()]):
    return page(request, user, query)


@router.get("/admin/assignments/unassigned")
def unassigned(request: Request, user: Admin, query: Annotated[WorkQuery, Query()]):
    return page(request, user, query, unassigned=True)


@router.get("/admin/departments/{department_id}/incidents")
def department_queue(
    department_id: UUID, request: Request, user: Admin, query: Annotated[WorkQuery, Query()]
):
    return page(request, user, query, department=str(department_id))


@router.get("/admin/incidents/{incident_id}/assignment")
def assignment_detail(incident_id: UUID, request: Request, user: Admin):
    return execute(service(request, user).detail, str(incident_id))


@router.post("/admin/incidents/{incident_id}/recommend-officer")
def recommend_officer(incident_id: UUID, request: Request, user: Admin):
    return execute(service(request, user, True).recommend, str(incident_id))


def mutate(identity, kind, data, request, user):
    return execute(
        service(request, user, True).repository.assign,
        str(identity),
        kind,
        data.model_dump(mode="json"),
        actor(user),
    )


@router.post("/admin/incidents/{incident_id}/assign-department")
def assign_department(incident_id: UUID, data: AssignmentAction, request: Request, user: Admin):
    return mutate(incident_id, "DEPARTMENT" if data.departmentId else "ROUTE", data, request, user)


@router.post("/admin/incidents/{incident_id}/assign-officer")
def assign_officer(incident_id: UUID, data: AssignmentAction, request: Request, user: Admin):
    return mutate(incident_id, "OFFICER", data, request, user)


@router.post("/admin/incidents/{incident_id}/reassign")
def reassign(incident_id: UUID, data: AssignmentAction, request: Request, user: Admin):
    return mutate(incident_id, "REASSIGN", data, request, user)


@router.post("/admin/incidents/{incident_id}/unassign-officer")
def unassign_officer(incident_id: UUID, data: AssignmentAction, request: Request, user: Admin):
    return mutate(incident_id, "UNASSIGN", data, request, user)


def history_page(repository, entity, limit, cursor, officer=None):
    context = {"entity": entity, "limit": limit, "officer": officer, "kind": "work-history"}
    key = unpack_cursor(cursor, context, (2,))
    if key and not all(isinstance(v, str) for v in key):
        raise HTTPException(400, "Invalid history cursor")
    result = execute(repository.history, entity, limit, key, officer)
    after = result.pop("after")
    result["nextCursor"] = pack_cursor(context, after) if after else None
    return result


@router.get("/admin/incidents/{incident_id}/assignment-history")
def assignment_history(
    incident_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=4096),
):
    work = service(request, user)
    execute(work.incidents.require, str(incident_id))
    return history_page(work.repository, str(incident_id), limit, cursor)


@router.get("/admin/departments/{department_id}/history")
def department_history(
    department_id: UUID,
    request: Request,
    user: Admin,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=4096),
):
    work = service(request, user)
    execute(work.repository.department_exists, str(department_id))
    return history_page(work.repository, str(department_id), limit, cursor)


@router.get("/officer/incidents")
def officer_queue(request: Request, user: Officer, query: Annotated[WorkQuery, Query()]):
    return page(request, user, query, officer=user.id)


@router.get("/officer/incidents/{incident_id}")
def officer_detail(incident_id: UUID, request: Request, user: Officer):
    return execute(service(request, user).detail, str(incident_id), user.id)


@router.get("/officer/incidents/{incident_id}/history")
def officer_history(
    incident_id: UUID,
    request: Request,
    user: Officer,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=4096),
):
    return history_page(service(request, user).repository, str(incident_id), limit, cursor, user.id)


@router.post("/officer/incidents/{incident_id}/start")
def start_work(incident_id: UUID, data: ProgressAction, request: Request, user: Officer):
    return execute(
        service(request, user, True).repository.progress,
        str(incident_id),
        "START",
        data.model_dump(mode="json"),
        actor(user),
    )


@router.post("/officer/incidents/{incident_id}/progress")
def progress(incident_id: UUID, data: ProgressAction, request: Request, user: Officer):
    return execute(
        service(request, user, True).repository.progress,
        str(incident_id),
        "PROGRESS",
        data.model_dump(mode="json"),
        actor(user),
    )


@router.get("/officer/incidents/{incident_id}/complaints/{complaint_id}/images/{image_id}")
def evidence(
    incident_id: UUID, complaint_id: UUID, image_id: UUID, request: Request, user: Officer
):
    data = execute(
        service(request, user).evidence, str(incident_id), str(complaint_id), str(image_id), user.id
    )
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
