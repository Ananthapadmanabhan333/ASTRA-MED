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
from pydantic.json_schema import models_json_schema
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api import routes, ws
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import create_engine, create_schema, create_session_factory
from app.schemas.ws import WS_SCHEMA_MODELS
from app.services.monitoring import MonitoringService

logger = logging.getLogger("astra.app")

DESCRIPTION = """
Astronaut health monitoring engine for the ASTRA-MED prototype (NASA Space Apps Challenge 2026).

**All physiological data served by this API is simulated.** Crew members are fictional. Nothing
here is clinically validated; thresholds and insights are software test scenarios, not diagnoses.

Live data streams over the WebSocket at `/ws/health-monitoring`. Its message schemas are
included below as `WsHello`, `WsVitals`, `WsAlert`, `WsSimulation` and `WsPong`.
"""


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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db_engine = create_engine(settings.database_url)
        await wait_for_database(db_engine)
        await create_schema(db_engine)
        factory = create_session_factory(db_engine)
        monitor = MonitoringService(settings, factory)
        await monitor.bootstrap()
        if settings.simulator_enabled:
            monitor.start()
        app.state.db_engine = db_engine
        app.state.session_factory = factory
        app.state.monitor = monitor
        logger.info("ASTRA-MED API ready (%s, db=%s)", settings.environment, db_engine.dialect.name)
        try:
            yield
        finally:
            await monitor.stop()
            await db_engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "%s %s -> %d (%.1f ms) rid=%s",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response

    register_exception_handlers(app)
    app.include_router(routes.router)
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


app = create_app()
