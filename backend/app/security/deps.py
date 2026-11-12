"""FastAPI dependencies: who is calling, and may they do this?"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from app.core.errors import ForbiddenError, UnauthorizedError
from app.security.audit import AuditLog, client_ip
from app.security.rbac import AUTH_DISABLED, ROLE_LABELS, Principal, Role
from app.security.service import AuthService

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DENIAL_DEDUPE_S = 60


def get_auth(conn: HTTPConnection) -> AuthService:
    return conn.app.state.auth


def get_audit(conn: HTTPConnection) -> AuditLog:
    return conn.app.state.audit


def credentials(conn: HTTPConnection) -> tuple[str | None, str]:
    """(token, method): an ``Authorization: Bearer`` header wins over the session cookie."""
    header = conn.headers.get("authorization", "")
    if header[:7].lower() == "bearer " and header[7:].strip():
        return header[7:].strip(), "bearer"
    cookie = conn.cookies.get(conn.app.state.settings.auth_cookie_name)
    if cookie:
        return cookie, "session"
    return None, ""


async def authenticate(conn: HTTPConnection) -> Principal | None:
    if not conn.app.state.settings.auth_enabled:
        return AUTH_DISABLED
    token, method = credentials(conn)
    if not token:
        return None
    return await get_auth(conn).resolve(token, method)


async def current_principal(request: Request) -> Principal:
    principal = await authenticate(request)
    if principal is None:
        has_token = credentials(request)[0] is not None
        raise UnauthorizedError(
            "Your session has ended. Sign in again." if has_token else "Sign in to continue.",
            details={"reason": "session_expired" if has_token else "not_signed_in"},
        )
    # Cookie-authenticated writes must echo the session's CSRF token (double-submit defence on
    # top of SameSite=Strict). Bearer requests are not sent automatically by browsers.
    if principal.method == "session" and request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not principal.csrf_token or not hmac.compare_digest(sent, principal.csrf_token):
            request.state.principal = principal
            await get_audit(request).record(
                "csrf_rejected", principal=principal, outcome="denied", status_code=403,
                resource_type="request", resource_id=request.url.path, ip=client_ip(request),
                request_id=getattr(request.state, "request_id", None),
            )
            raise ForbiddenError("Missing or invalid CSRF token. Reload the page and try again.",
                                 details={"reason": "csrf"})
    request.state.principal = principal
    return principal


CurrentUser = Annotated[Principal, Depends(current_principal)]


def role_label(role: str) -> str:
    try:
        return ROLE_LABELS[Role(role)]
    except ValueError:
        return role


def require(*permissions: str) -> Any:
    """Dependency that admits the caller only if their role grants every listed permission."""

    async def checker(request: Request, principal: CurrentUser) -> Principal:
        missing = [p for p in permissions if not principal.can(p)]
        if missing:
            audit = get_audit(request)
            # Polling clients repeat the same denied request; one entry per route per minute is enough.
            route = f"{request.method} {request.url.path}"
            if audit.first_read(principal.user_id, f"deny:{route}", "", window_s=DENIAL_DEDUPE_S):
                await audit.record(
                    "access_denied", principal=principal, outcome="denied", status_code=403,
                    resource_type="route", resource_id=route,
                    ip=client_ip(request), request_id=getattr(request.state, "request_id", None),
                    detail={"missing": missing},
                )
            raise ForbiddenError(
                f"Your role ({role_label(principal.role)}) does not allow this.",
                details={"reason": "permission", "required": missing, "role": principal.role},
            )
        return principal

    return Depends(checker)
