import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes.admin_analytics import router as analytics_router
from app.api.routes.auth import local_router
from app.api.routes.auth import router as auth_router
from app.api.routes.civic_intelligence import router as intelligence_router
from app.api.routes.complaints import router as complaints_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.duplicate_detection import router as duplicate_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.portals import router as portal_router
from app.api.routes.priority import router as priority_router
from app.api.routes.profile import router as profile_router
from app.api.routes.work import router as work_router
from app.api.routes.workflows import router as workflows_router
from app.core.body_limit import ComplaintBodyLimit
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.integrations.auth.cognito import CognitoIdentityProvider
from app.integrations.auth.local import LocalIdentityProvider
from app.services.auth_service import AuthService
from app.services.complaint_factory import build_complaint_service
from app.services.duplicate_detection_service import build_duplicate_service
from app.services.incident_service import build_incident_service
from app.services.priority_service import build_priority_service
from app.services.work_service import build_work_service
from app.services.workflow_service import build_workflow_service

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application for local hosting and AWS Lambda."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if resolved_settings.auth_provider == "local":
            application.state.auth_service.store.initialize()
        stopped = asyncio.Event()
        task = None
        if resolved_settings.app_env == "local" and resolved_settings.matching_worker_enabled:
            task = asyncio.create_task(
                application.state.duplicate_detection_service.worker(stopped)
            )
        try:
            yield
        finally:
            stopped.set()
            if task is not None:
                await task

    application = FastAPI(
        title=f"{resolved_settings.app_name} API",
        description="Public infrastructure complaint management API foundation.",
        version="0.1.0",
        debug=False,  # Never expose traceback pages containing private evidence paths.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.include_router(api_router)
    application.state.settings = resolved_settings
    if resolved_settings.auth_provider == "local":
        service = AuthService(resolved_settings)
        application.state.auth_service = service
        application.state.identity_provider = LocalIdentityProvider(service)
        application.include_router(local_router, prefix="/api")
    else:
        application.state.identity_provider = CognitoIdentityProvider(resolved_settings)
    application.state.complaint_service = build_complaint_service(
        resolved_settings,
        application.state.auth_service.store
        if resolved_settings.auth_provider == "local"
        else None,
    )
    application.add_middleware(
        ComplaintBodyLimit,
        max_bytes=resolved_settings.max_complaint_request_bytes,
        api_max_bytes=resolved_settings.max_api_request_bytes,
    )
    application.state.duplicate_detection_service = build_duplicate_service(
        resolved_settings, application.state.complaint_service
    )
    application.state.incident_service = build_incident_service(
        resolved_settings,
        application.state.complaint_service,
        application.state.duplicate_detection_service,
    )
    application.state.duplicate_detection_service.incidents = application.state.incident_service
    application.state.priority_service = build_priority_service(
        resolved_settings, application.state.incident_service
    )
    application.state.duplicate_detection_service.priorities = application.state.priority_service
    application.state.work_service = build_work_service(
        resolved_settings, application.state.incident_service, application.state.priority_service
    )
    application.state.duplicate_detection_service.work = application.state.work_service
    application.state.workflow_service = build_workflow_service(
        resolved_settings,
        application.state.duplicate_detection_service,
        application.state.incident_service,
        application.state.priority_service,
        application.state.work_service,
    )
    application.state.duplicate_detection_service.workflows = application.state.workflow_service
    from app.services.analytics_service import AnalyticsService

    if resolved_settings.complaint_provider == "sqlite":
        from app.repositories.analytics_repository import SQLiteAnalytics

        analytics_repository = SQLiteAnalytics(
            application.state.auth_service.store, resolved_settings
        )
    else:
        from app.integrations.database.dynamodb_analytics import DynamoAnalytics

        analytics_repository = DynamoAnalytics(resolved_settings)
    application.state.analytics_service = AnalyticsService(
        analytics_repository, resolved_settings, application.state.priority_service.config
    )
    application.state.workflow_service.analytics = analytics_repository
    application.state.civic_intelligence_service = None
    if resolved_settings.complaint_provider == "sqlite":
        from app.repositories.civic_intelligence_repository import SQLiteCivicIntelligence
        from app.services.civic_intelligence_service import CivicIntelligenceService

        intelligence = CivicIntelligenceService(
            SQLiteCivicIntelligence(
                application.state.auth_service.store, application.state.work_service.repository
            ),
            application.state.complaint_service,
            application.state.analytics_service,
            resolved_settings,
            application.state.priority_service,
        )
        application.state.civic_intelligence_service = intelligence
        application.state.analytics_service.intelligence = intelligence
        application.state.workflow_service.intelligence = intelligence
    if resolved_settings.complaint_provider == "sqlite":
        from app.services.sla_service import SQLiteSLA

        application.state.sla_service = SQLiteSLA(
            application.state.workflow_service.repository, application.state.priority_service
        )
    else:
        from app.integrations.database.dynamodb_events import DynamoSLA

        application.state.sla_service = DynamoSLA(application.state.workflow_service)
    application.include_router(complaints_router, prefix="/api")
    application.include_router(discovery_router, prefix="/api")
    application.include_router(duplicate_router, prefix="/api")
    application.include_router(priority_router, prefix="/api")
    application.include_router(work_router, prefix="/api")
    application.include_router(workflows_router, prefix="/api")
    application.include_router(intelligence_router, prefix="/api")
    application.include_router(analytics_router, prefix="/api")
    application.include_router(incidents_router, prefix="/api")
    application.include_router(auth_router, prefix="/api")
    application.include_router(profile_router, prefix="/api")
    application.include_router(portal_router, prefix="/api")
    # Keep factory-injected configuration consistent in both middleware and routes.
    application.dependency_overrides[get_settings] = lambda: resolved_settings

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI normally echoes invalid inputs; strip them to avoid returning passwords/tokens.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ]
            },
        )

    @application.middleware("http")
    async def auth_cache_control(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        started = time.monotonic()
        if (
            resolved_settings.complaint_provider == "dynamodb"
            and not resolved_settings.workflow_table_name
            and request.method in ("POST", "PATCH", "PUT", "DELETE")
            and request.url.path.startswith(("/api/complaints", "/api/admin", "/api/officer"))
        ):
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": "Workflow persistence is not configured; "
                    "business changes were not accepted."
                },
                headers={"Cache-Control": "no-store"},
            )
        else:
            try:
                response = await call_next(request)
            except Exception as error:
                # Handle before ServerErrorMiddleware/Uvicorn can log sensitive exception payloads.
                response = await handle_unexpected_error(request, error)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if resolved_settings.app_env == "production" and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api/complaints"):
            logger.info(
                "request_id=%s operation=complaint_%s status=%d duration_ms=%d",
                request.state.request_id,
                request.method.lower(),
                response.status_code,
                int((time.monotonic() - started) * 1000),
            )
        return response

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            "request_id=%s operation=unexpected_error error_category=%s",
            getattr(request.state, "request_id", "unassigned"),
            type(error).__name__,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # Wrap limits/configuration failures too, so an allowed cross-origin client can read 413/503.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=resolved_settings.auth_provider == "local",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return application


app = create_app()
