from __future__ import annotations

import os
from datetime import UTC, datetime

# Phase 1-4 tests exercise the API without signing in. Security tests (tests/security) switch
# authentication back on explicitly with Settings(auth_enabled=True).
os.environ.setdefault("ASTRA_AUTH_ENABLED", "false")
# Background jobs that tests drive explicitly when they need them.
os.environ.setdefault("ASTRA_TWIN_BACKGROUND", "false")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW

# A fixed mid-morning UTC instant: every crew member is awake and not exercising.
T0 = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def trained_artifacts(tmp_path_factory):
    """A small model version trained once per test session (shared by the AI and phase 6 tests)."""
    from app.ai.experiments.config import ExperimentConfig
    from app.ai.experiments.runner import run

    root = tmp_path_factory.mktemp("ai-artifacts")
    results = run(ExperimentConfig().quick(), root)
    assert results["version"]
    return root


@pytest.fixture
def engine() -> SimulationEngine:
    return SimulationEngine(CREW, seed=7, random_events_per_hour=0)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        simulator_enabled=False,  # tests drive ticks explicitly
        random_events_per_hour=0,
        backfill_days=1,
        backfill_interval_minutes=10,
        log_level="WARNING",
    )


@pytest_asyncio.fixture
async def api(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.monitor
