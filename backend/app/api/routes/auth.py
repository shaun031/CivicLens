from fastapi import APIRouter, Depends, Request, Response

from app.core.auth_dependencies import SESSION_COOKIE, AuthenticatedUser, verify_local_origin
from app.models.user import Principal
from app.schemas.auth import ForgotPasswordInput, LoginInput, RegisterInput, ResetPasswordInput
from app.services.auth_service import AuthService

router = APIRouter(tags=["Authentication"])
local_router = APIRouter(
    prefix="/auth", tags=["Local authentication"], dependencies=[Depends(verify_local_origin)]
)


@router.get("/auth/me", response_model=Principal)
def current_user(user: AuthenticatedUser) -> Principal:
    return user


@local_router.post("/register", status_code=201, response_model=Principal)
def register(data: RegisterInput, request: Request) -> Principal:
    service: AuthService = request.app.state.auth_service
    service.rate_limit(f"register:{request.client.host}", limit=8)
    # Never accept role from a public request; extra fields are rejected by the schema.
    return service.register(data)


@local_router.post("/login", response_model=Principal)
def login(data: LoginInput, request: Request, response: Response) -> Principal:
    service: AuthService = request.app.state.auth_service
    user, token = service.login(
        str(data.email),
        data.password.get_secret_value(),
        request.client.host,
        request.cookies.get(SESSION_COOKIE),
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=service.settings.cookie_secure or request.url.scheme == "https",
        samesite="lax",
        max_age=service.settings.session_ttl_seconds,
        path="/api",
    )
    return user


@local_router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    request.app.state.auth_service.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(
        SESSION_COOKIE,
        path="/api",
        httponly=True,
        secure=request.app.state.settings.cookie_secure or request.url.scheme == "https",
        samesite="lax",
    )


@local_router.post("/forgot-password", status_code=202)
def forgot_password(data: ForgotPasswordInput, request: Request) -> dict[str, str]:
    service: AuthService = request.app.state.auth_service
    service.rate_limit(f"forgot:{request.client.host}")
    service.request_reset(str(data.email))
    return {
        "message": "If the account is eligible, a reset link is in the private local outbox. "
        "No email was sent."
    }


@local_router.post("/reset-password")
def reset_password(data: ResetPasswordInput, request: Request) -> dict[str, str]:
    service: AuthService = request.app.state.auth_service
    service.rate_limit(f"reset:{request.client.host}")
    service.reset_password(data.token.get_secret_value(), data.password.get_secret_value())
    return {"message": "Password reset. Sign in with your new password."}
