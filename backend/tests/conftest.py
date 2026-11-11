from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW

# A fixed mid-morning UTC instant: every crew member is awake and not exercising.
T0 = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)


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
