"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic.json_schema import models_json_schema
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.ai.service import AIService
from app.api import (
    ai_routes,
    assistant_routes,
    auth_routes,
    emergency_routes,
    medical_routes,
    overview_routes,
    report_routes,
    routes,
    space_routes,
    twin_routes,
    ws,
)
from app.assistant.service import AssistantService
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import create_engine, create_schema, create_session_factory
from app.emergency.service import EmergencyService
from app.medical.multisystem import MultisystemEngine
from app.reports.service import ReportService
from app.schemas.ws import WS_SCHEMA_MODELS
from app.security.audit import (
    SENSITIVE_READ_PREFIXES,
    SKIP_PREFIXES,
    UNSAFE_METHODS,
    AuditLog,
    client_ip,
    outcome_for,
    resource_from_path,
)
from app.security.deps import require
from app.security.service import AuthService
from app.services.monitoring import MonitoringService
from app.space.service import SpaceDataService
from app.twin.service import TwinService

logger = logging.getLogger("astra.app")

DESCRIPTION = """
Astronaut health monitoring engine for the ASTRA-MED prototype (NASA Space Apps Challenge 2026).

**All physiological data served by this API is simulated.** Crew members are fictional. Nothing
here is clinically validated; thresholds and insights are software test scenarios, not diagnoses.

Space-environment endpoints under `/api/space` serve **real NASA open data** (DONKI space weather,
OSDR Environmental Data App ISS measurements, OSDR study metadata), each labelled with its category,
source, retrieval time and licence. Environmental indicators are never converted into crew doses.

Live data streams over the WebSocket at `/ws/health-monitoring`. Its message schemas are
included below as `WsHello`, `WsVitals`, `WsAlert`, `WsSimulation` and `WsPong`.

**Authentication.** Every endpoint except `/api/system/health` and `/api/auth/login|token` needs a
signed-in user. Browsers sign in with `POST /api/auth/login` (HttpOnly session cookie; send the
returned CSRF token as `X-CSRF-Token` on writes). Scripts use `POST /api/auth/token` and send
`Authorization: Bearer <token>`. Access is role-based; see `GET /api/auth/roles`.
"""

# Pages served by FastAPI itself that load scripts and styles (everything else is JSON or files).
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


async def wait_for_database(engine: AsyncEngine, attempts: int = 15, delay_s: float = 2.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - depends on infrastructure
            if attempt == attempts:
                raise
            logger.warning("database not ready (%s); retry %d/%d", exc.__class__.__name__, attempt, attempts)
            await asyncio.sleep(delay_s)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if not settings.auth_enabled:
        if settings.is_production:
            raise RuntimeError("ASTRA_AUTH_ENABLED=false is not allowed when ASTRA_ENVIRONMENT=production.")
        logger.warning("AUTHENTICATION IS DISABLED: every caller has every permission. Development only.")
    if "*" in settings.cors_origin_list:
        raise RuntimeError("ASTRA_CORS_ORIGINS must list explicit origins (credentials are allowed).")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db_engine = create_engine(settings.database_url)
        await wait_for_database(db_engine)
        await create_schema(db_engine)
        factory = create_session_factory(db_engine)
        app.state.auth = AuthService(settings, factory)
        app.state.audit = AuditLog(factory, settings.audit_read_dedupe_seconds)
        monitor = MonitoringService(settings, factory)
        await monitor.bootstrap()
        if settings.simulator_enabled:
            monitor.start()
        app.state.db_engine = db_engine
        app.state.session_factory = factory
        app.state.monitor = monitor
        app.state.ai = AIService(settings, factory, monitor)
        if settings.ai_enabled:
            preload = asyncio.create_task(app.state.ai.bundle(), name="astra-ai-preload")
        app.state.space = SpaceDataService(settings, factory) if settings.space_enabled else None
        if app.state.space is not None and settings.space_sync_enabled:
            app.state.space.start()
        app.state.twin = TwinService(settings, factory, monitor)
        app.state.multisystem = MultisystemEngine(monitor, app.state.ai, app.state.twin)
        app.state.emergency = EmergencyService(factory, monitor, app.state.ai, app.state.twin, app.state.multisystem)
        app.state.multisystem.overlays = app.state.emergency.overlay_for
        app.state.reports = ReportService(factory, monitor, app.state.ai, app.state.multisystem)
        app.state.assistant = AssistantService(settings, factory, monitor, app.state.ai, app.state.twin,
                                               app.state.multisystem)
        if settings.twin_background:
            app.state.twin.start()
        logger.info("ASTRA-MED API ready (%s, db=%s)", settings.environment, db_engine.dialect.name)
        try:
            yield
        finally:
            if settings.ai_enabled and not preload.done():
                preload.cancel()
            await app.state.twin.stop()
            if app.state.space is not None:
                await app.state.space.stop()
            await monitor.stop()
            await db_engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex[:12])[:32]
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Answer here, inside the CORS middleware, so browsers see the error envelope instead of
            # an opaque network failure (Starlette's outermost error handler adds no CORS headers).
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse(status_code=500, content={"error": {
                "code": "internal_error", "message": "The server hit an unexpected error.", "details": None}})
        elapsed_ms = (time.perf_counter() - started) * 1000
        await _audit_request(request, response.status_code, request_id)
        _security_headers(request, response, settings)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.1f ms) rid=%s",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response

    # Added after the middleware above, so CORS wraps it and error responses still carry CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "Authorization"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    register_exception_handlers(app)
    app.include_router(routes.public_router)
    app.include_router(auth_routes.router)
    app.include_router(auth_routes.admin_router)
    app.include_router(routes.router, dependencies=[require("health:read")])
    app.include_router(ai_routes.router, dependencies=[require("health:read")])
    app.include_router(space_routes.router, dependencies=[require("space:read")])
    app.include_router(twin_routes.router, dependencies=[require("health:read")])
    app.include_router(medical_routes.router, dependencies=[require("health:read")])
    app.include_router(emergency_routes.router, dependencies=[require("health:read")])
    app.include_router(report_routes.router, dependencies=[require("reports:read")])
    app.include_router(assistant_routes.router, dependencies=[require("health:read")])
    app.include_router(overview_routes.router, dependencies=[require("health:read")])
    app.include_router(ws.router)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title, version=app.version, description=app.description, routes=app.routes
        )
        _, defs = models_json_schema(
            [(m, "serialization") for m in WS_SCHEMA_MODELS],
            ref_template="#/components/schemas/{model}",
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in defs.get("$defs", {}).items():
            components.setdefault(name, definition)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


async def _audit_request(request: Request, status: int, request_id: str) -> None:
    """Record writes and (deduplicated) views of health records. Denials are logged where raised."""
    principal = getattr(request.state, "principal", None)
    path = request.url.path
    if principal is None or not path.startswith("/api/") or path.startswith(SKIP_PREFIXES):
        return
    if status in (401, 403):
        return  # require()/current_principal already wrote a more specific entry
    route = request.scope.get("route")
    template = getattr(route, "path", path)
    resource_type, resource_id = resource_from_path(template, request.scope.get("path_params") or {})
    audit: AuditLog = request.app.state.audit
    if request.method in UNSAFE_METHODS:
        action = f"{request.method} {template}"
    elif status < 400 and template.startswith(SENSITIVE_READ_PREFIXES):
        if not audit.first_read(principal.user_id, template, resource_id or ""):
            return
        action = f"view {template}"
    else:
        return
    await audit.record(
        action, principal=principal, outcome=outcome_for(status), status_code=status,
        resource_type=resource_type, resource_id=resource_id, ip=client_ip(request), request_id=request_id,
    )


def _security_headers(request: Request, response, settings: Settings) -> None:
    headers = response.headers
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Frame-Options"] = "DENY"
    headers["Cross-Origin-Resource-Policy"] = "same-site"
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    path = request.url.path
    if path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"  # health records must not linger in caches
    content_type = headers.get("content-type", "")
    if not path.startswith(DOC_PATHS) and not content_type.startswith("application/pdf"):
        headers["Content-Security-Policy"] = API_CSP
    if settings.auth_cookie_secure:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


app = create_app()
