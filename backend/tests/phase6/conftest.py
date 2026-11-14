"""Phase 6 fixtures: a controllable clock, an app with the orchestrator consumer only (collectors are
driven explicitly), and helpers to tick the live monitor and to drain the event queue."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from tests.security.conftest import secure, secure_settings  # noqa: F401  (shared fixtures)

CLOCK_MODULES = (
    "app.ai.service", "app.api.auth_routes", "app.api.emergency_routes", "app.api.medical_routes", "app.api.routes",
    "app.api.space_routes", "app.api.twin_routes", "app.api.ws", "app.assistant.service", "app.emergency.service",
    "app.medical.multisystem", "app.reports.service", "app.security.audit", "app.security.service",
    "app.services.monitoring", "app.space.service", "app.twin.service",
    # phase 6
    "app.mission.events", "app.mission.alerts", "app.mission.orchestrator", "app.mission.sandbox",
    "app.mission.views", "app.mission.system", "app.mission.analytics", "app.api.mission_routes",
)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    # The most recent 11:00 UTC: every crew member is awake and not exercising (as tests/conftest.T0).
    # Starting at the real time made results depend on the crew schedule at the hour the suite ran.
    now = datetime.now(UTC).replace(microsecond=0)
    start = now.replace(hour=11, minute=0, second=0)
    c = Clock(start if start <= now else start - timedelta(days=1))
    for name in CLOCK_MODULES:
        monkeypatch.setattr(importlib.import_module(name), "utcnow", c)
    return c


def p6_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p6.db').as_posix()}",
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=1,
        backfill_interval_minutes=5,
        space_sync_enabled=False,
        twin_background=False,
        ai_cache_seconds=0,
        mission_orchestrator_enabled=False,  # tests call the collectors directly
        mission_sim_tick_seconds=10.0,  # the wall-clock loop stays out of the way; tests advance runs
        mission_start_date=(datetime.now(UTC) - timedelta(days=20)).date(),
        log_level="WARNING",
    )
    base.update(overrides)
    return Settings(**base)


@dataclass
class P6:
    app: object
    client: AsyncClient
    clock: Clock

    @property
    def state(self):
        return self.app.state

    @property
    def monitor(self):
        return self.app.state.monitor

    async def tick(self, seconds: int) -> None:
        for _ in range(seconds):
            await self.monitor.tick(self.clock.advance(1))

    async def drain(self) -> None:
        await self.app.state.orchestrator.drain()


@pytest_asyncio.fixture
async def p6(tmp_path, clock):
    app = create_app(p6_settings(tmp_path))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=120) as client:
            yield P6(app, client, clock)
