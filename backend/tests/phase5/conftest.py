"""Phase 5 fixtures: a controllable clock, a short mission and helpers to drive the simulator."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app

# Modules that read the wall clock through ``utcnow``. The clock fixture patches them together so
# simulated ticks, analyses, timelines and reports all agree on "now".
CLOCK_MODULES = (
    "app.ai.service", "app.api.auth_routes", "app.api.emergency_routes", "app.api.medical_routes", "app.api.routes",
    "app.api.space_routes", "app.api.twin_routes", "app.api.ws", "app.assistant.service", "app.emergency.service",
    "app.medical.multisystem", "app.reports.service", "app.security.audit", "app.security.service",
    "app.services.monitoring", "app.space.service", "app.twin.service",
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


@pytest.fixture
def p5_settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p5.db').as_posix()}",
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=2,
        backfill_interval_minutes=5,
        space_sync_enabled=False,
        twin_background=False,
        ai_cache_seconds=0,
        mission_start_date=(datetime.now(UTC) - timedelta(days=20)).date(),
        log_level="WARNING",
    )


@dataclass
class P5:
    app: object
    client: AsyncClient
    clock: Clock

    @property
    def monitor(self):
        return self.app.state.monitor

    async def tick(self, seconds: int) -> None:
        for _ in range(seconds):
            await self.monitor.tick(self.clock.advance(1))


@pytest_asyncio.fixture
async def p5(p5_settings, clock):
    app = create_app(p5_settings)
    async with app.router.lifespan_context(app):
        await app.state.twin.refresh(full=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield P5(app, client, clock)
