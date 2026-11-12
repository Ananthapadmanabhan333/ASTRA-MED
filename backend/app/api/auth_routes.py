"""Sign-in, session and account administration endpoints (phase 5)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.core.errors import ConflictError, UnauthorizedError
from app.core.timeutil import utcnow
from app.db.models import UserRow
from app.schemas.auth import (
    AccessMatrix,
    AdminUser,
    AuditEntry,
    LoginRequest,
    PasswordChange,
    PermissionInfo,
    RoleInfo,
    SessionInfo,
    TokenResponse,
    UserCreate,
    UserInfo,
    UserUpdate,
)
from app.schemas.common import ERROR_RESPONSES, ErrorResponse
from app.security.audit import client_ip
from app.security.deps import CurrentUser, get_audit, get_auth, require, role_label
from app.security.rbac import (
    PERMISSIONS,
    ROLE_DESCRIPTIONS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    Principal,
    permissions_for,
)
from app.security.service import LoginResult, session_expiry

AUTH_ERRORS = {
    401: {"model": ErrorResponse, "description": "Invalid credentials or locked account"},
    429: {"model": ErrorResponse, "description": "Too many attempts"},
}

router = APIRouter(prefix="/api/auth", tags=["auth"], responses=ERROR_RESPONSES)
admin_router = APIRouter(prefix="/api/admin", tags=["admin"], responses=ERROR_RESPONSES)


def user_info(user: UserRow) -> UserInfo:
    return UserInfo(
        id=user.id, username=user.username, display_name=user.display_name, role=user.role,
        role_label=role_label(user.role), active=user.active, last_login_at=user.last_login_at,
    )


def admin_user(user: UserRow) -> AdminUser:
    return AdminUser(
        **user_info(user).model_dump(), created_at=user.created_at,
        locked_until=user.locked_until if user.locked_until and user.locked_until > utcnow() else None,
        failed_logins=user.failed_logins,
    )


def principal_info(p: Principal) -> UserInfo:
    return UserInfo(id=p.user_id, username=p.username, display_name=p.display_name, role=p.role,
                    role_label=role_label(p.role))


async def _login(request: Request, body: LoginRequest, kind: str) -> LoginResult:
    audit = get_audit(request)
    try:
        result = await get_auth(request).login(
            body.username, body.password, client_ip(request), request.headers.get("user-agent")
        )
    except UnauthorizedError as exc:
        reason = (exc.details or {}).get("reason", "invalid_credentials")
        await audit.record(
            "login_failed", username=body.username.strip().lower()[:64], outcome="denied", status_code=401,
            ip=client_ip(request), request_id=getattr(request.state, "request_id", None),
            detail={"reason": reason, "kind": kind},
        )
        exc.details = None  # never tell the client which part was wrong
        raise
    principal = Principal(result.user.id, result.user.username, result.user.display_name, result.user.role)
    await audit.record(
        "login", principal=principal, resource_type="session", resource_id=result.session.id,
        ip=client_ip(request), request_id=getattr(request.state, "request_id", None), detail={"kind": kind},
    )
    return result


@router.post("/login", response_model=SessionInfo, responses=AUTH_ERRORS)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
    """Browser sign-in. Sets an HttpOnly, SameSite=Strict session cookie and returns the CSRF token."""
    settings = request.app.state.settings
    if not settings.auth_enabled:
        raise ConflictError("Authentication is disabled on this deployment.")
    result = await _login(request, body, "cookie")
    response.set_cookie(
        settings.auth_cookie_name, result.token,
        max_age=int(timedelta(hours=settings.auth_session_hours).total_seconds()),
        httponly=True, secure=settings.auth_cookie_secure, samesite="strict", path="/",
    )
    return SessionInfo(
        user=user_info(result.user),
        permissions=sorted(permissions_for(result.user.role)),
        method="session",
        csrf_token=result.session.csrf_token,
        expires_at=session_expiry(result.session, settings.auth_idle_minutes),
        auth_enabled=True,
    )


@router.post("/token", response_model=TokenResponse, responses=AUTH_ERRORS)
async def issue_token(body: LoginRequest, request: Request) -> TokenResponse:
    """Bearer token for scripts and other non-browser clients (no cookie, no CSRF token needed)."""
    if not request.app.state.settings.auth_enabled:
        raise ConflictError("Authentication is disabled on this deployment.")
    result = await _login(request, body, "bearer")
    return TokenResponse(access_token=result.token, expires_at=result.session.expires_at,
                         user=user_info(result.user))


@router.get("/me", response_model=SessionInfo, responses={401: {"model": ErrorResponse}})
async def me(principal: CurrentUser, request: Request) -> SessionInfo:
    """The signed-in user, their permissions and (for cookie sessions) the CSRF token."""
    settings = request.app.state.settings
    expires = None
    if principal.session_id:
        row = await get_auth(request).session_info(principal.session_id)
        expires = session_expiry(row, settings.auth_idle_minutes) if row else None
    return SessionInfo(
        user=principal_info(principal), permissions=sorted(principal.permissions),
        method=principal.method,  # type: ignore[arg-type]
        csrf_token=principal.csrf_token if principal.method == "session" else None,
        expires_at=expires, auth_enabled=settings.auth_enabled,
    )


@router.post("/logout", status_code=204)
async def logout(principal: CurrentUser, request: Request, response: Response) -> Response:
    if principal.session_id:
        await get_auth(request).logout(principal.session_id)
        await get_audit(request).record(
            "logout", principal=principal, resource_type="session", resource_id=principal.session_id,
            ip=client_ip(request), request_id=getattr(request.state, "request_id", None),
        )
    settings = request.app.state.settings
    response.delete_cookie(settings.auth_cookie_name, path="/", httponly=True,
                           secure=settings.auth_cookie_secure, samesite="strict")
    response.status_code = 204
    return response


@router.post("/password", status_code=204, responses={401: {"model": ErrorResponse}})
async def change_password(body: PasswordChange, principal: CurrentUser, request: Request) -> Response:
    """Change your own password. Signs out your other sessions."""
    if principal.method == "disabled":
        raise ConflictError("Authentication is disabled on this deployment.")
    await get_auth(request).change_password(principal.user_id, body.current_password, body.new_password,
                                            keep_session=principal.session_id)
    await get_audit(request).record("password_changed", principal=principal, resource_type="user",
                                    resource_id=principal.user_id, ip=client_ip(request))
    return Response(status_code=204)


@router.get("/roles", response_model=AccessMatrix)
async def roles(_: CurrentUser) -> AccessMatrix:
    """The role → permission matrix enforced by the API."""
    return AccessMatrix(
        roles=[RoleInfo(key=r.value, label=ROLE_LABELS[r], description=ROLE_DESCRIPTIONS[r],  # type: ignore[arg-type]
                        permissions=sorted(ROLE_PERMISSIONS[r])) for r in ROLE_PERMISSIONS],
        permissions=[PermissionInfo(key=k, description=v) for k, v in PERMISSIONS.items()],
    )


# -------------------------------------------------------------------------- admin ----
@admin_router.get("/users", response_model=list[AdminUser], dependencies=[require("users:manage")])
async def list_users(request: Request) -> list[AdminUser]:
    return [admin_user(u) for u in await get_auth(request).list_users()]


@admin_router.post("/users", response_model=AdminUser, status_code=201)
async def create_user(body: UserCreate, request: Request,
                      principal: Annotated[Principal, require("users:manage")]) -> AdminUser:
    user = await get_auth(request).create_user(body.username, body.display_name, body.role, body.password)
    await get_audit(request).record("user_created", principal=principal, resource_type="user",
                                    resource_id=user.id, ip=client_ip(request),
                                    detail={"username": user.username, "role": user.role})
    return admin_user(user)


@admin_router.patch("/users/{user_id}", response_model=AdminUser)
async def update_user(user_id: str, body: UserUpdate, request: Request,
                      principal: Annotated[Principal, require("users:manage")]) -> AdminUser:
    if user_id == principal.user_id and (body.active is False or (body.role and body.role != principal.role)):
        raise ConflictError("You cannot deactivate yourself or change your own role.")
    user = await get_auth(request).update_user(
        user_id, role=body.role, active=body.active, display_name=body.display_name, unlock=body.unlock
    )
    await get_audit(request).record("user_updated", principal=principal, resource_type="user",
                                    resource_id=user_id, ip=client_ip(request),
                                    detail=body.model_dump(exclude_none=True))
    return admin_user(user)


@admin_router.get("/audit", response_model=list[AuditEntry], dependencies=[require("audit:read")])
async def audit_log(
    request: Request,
    username: str | None = None,
    action: str | None = None,
    outcome: Annotated[str | None, Query(pattern="^(success|denied|failure)$")] = None,
    resource_type: str | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 72,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AuditEntry]:
    """Newest first. Entries hold identifiers only, never measurement values."""
    rows = await get_audit(request).list(
        username=username, action=action, outcome=outcome, resource_type=resource_type,
        since=utcnow() - timedelta(hours=hours), limit=limit,
    )
    return [AuditEntry.model_validate(r) for r in rows]
