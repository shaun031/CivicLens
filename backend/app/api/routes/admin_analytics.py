import sqlite3
from typing import Annotated, Literal

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.analytics.filters import AnalyticsFilters
from app.analytics.models import AnalyticsResponse, ReportPreviewResponse
from app.analytics.reporting import REPORTS, csv_report, report
from app.api.routes.incidents import Admin
from app.core.auth_dependencies import verify_local_origin
from app.models.incident import IncidentError

router = APIRouter(prefix="/admin/analytics", tags=["Private municipal analytics"])
Filters = Annotated[AnalyticsFilters, Query()]
View = Literal[
    "overview",
    "complaint-trends",
    "incidents",
    "priorities",
    "departments",
    "officers",
    "sla",
    "backlog",
    "hotspots",
    "response-times",
]


def service(request, user, export=False):
    if not user.is_active or not user.is_verified:
        raise HTTPException(403, "Active verified administrator required")
    if export and request.app.state.settings.auth_provider == "local":
        verify_local_origin(request)
        request.app.state.auth_service.rate_limit(
            f"analytics-export:{user.id}", limit=10, window=60
        )
    return request.app.state.analytics_service


def execute(operation, *args):
    try:
        return operation(*args)
    except IncidentError as error:
        raise HTTPException(error.status, error.message) from error
    except (sqlite3.Error, OSError, ClientError, BotoCoreError) as error:
        raise HTTPException(
            503, "Analytics unavailable; retry after source/projection reconciliation"
        ) from error


@router.get("/reports")
def reports(request: Request, user: Admin):
    analytics = service(request, user)
    source = execute(analytics.repository.snapshot)
    return {
        "reports": [{"type": key, "view": value} for key, value in REPORTS.items()],
        "maximumRows": 2000,
        "maximumBytes": 1048576,
        "detailsPageSize": 50,
        "reportingTimezone": analytics.settings.analytics_timezone,
        "scope": analytics.settings.analytics_scope,
        "serviceAreas": analytics.settings.analytics_service_areas,
        "departments": source["departments"],
    }


@router.get("/reports/{kind}", response_model=ReportPreviewResponse)
def preview(kind: str, request: Request, user: Admin, filters: Filters):
    return execute(report, service(request, user), kind, filters)


@router.post("/reports/{kind}/csv")
def export(kind: str, request: Request, user: Admin, filters: Filters):
    analytics = service(request, user, True)
    value = execute(report, analytics, kind, filters)
    body = execute(csv_report, value)
    execute(
        analytics.repository.audit_export,
        user.id,
        kind,
        value["filters"],
        len(value["rows"]),
        value["generatedAt"],
    )
    filename = f"civiclens-{kind}-{value['generatedAt'][:10]}.csv"
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{view}", response_model=AnalyticsResponse)
def analytics_view(view: View, request: Request, user: Admin, filters: Filters):
    return execute(service(request, user).view, view, filters)
