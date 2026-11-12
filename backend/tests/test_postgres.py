"""PostgreSQL integration tests (opt-in).

The default suite runs on SQLite. Point these at a disposable PostgreSQL database to verify the
production storage path; every table is dropped before and after the run:

    ASTRA_TEST_POSTGRES_URL=postgresql+asyncpg://astra:<password>@localhost:5432/astra_med_test
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.models import Base, VitalSampleRow
from app.db.session import create_engine
from app.main import create_app
from app.repositories import vitals as vitals_repo

PG_URL = os.getenv("ASTRA_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set ASTRA_TEST_POSTGRES_URL to run PostgreSQL integration tests"
)


async def _drop_all() -> None:
    engine = create_engine(PG_URL)  # type: ignore[arg-type]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_settings():
    await _drop_all()
    yield Settings(
        database_url=PG_URL,
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=1,
        backfill_interval_minutes=10,
        log_level="WARNING",
    )
    await _drop_all()


async def test_storage_alerts_and_restart_on_postgres(pg_settings):
    app = create_app(pg_settings)
    async with app.router.lifespan_context(app):
        assert app.state.db_engine.dialect.name == "postgresql"
        monitor = app.state.monitor
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pg") as client:
            health = (await client.get("/api/system/health")).json()
            assert health["database"] == "ok"

            history = (await client.get("/api/health/AST-01/history", params={"range": "24h"})).json()
            assert len(history["points"]) > 50, "backfill should be stored and readable"

            started = await client.post(
                "/api/simulation/events",
                json={"scenario": "desaturation", "astronaut_id": "AST-03", "duration_seconds": 300},
            )
            assert started.status_code == 201

            t0 = utcnow()
            for i in range(80):
                await monitor.tick(t0 + timedelta(seconds=i + 1))

            alerts = (
                await client.get("/api/alerts", params={"status": "active", "astronaut_id": "AST-03"})
            ).json()
            spo2 = next(a for a in alerts if a["metric"] == "spo2")
            assert spo2["severity"] == "critical"

        async with app.state.session_factory() as session:
            live_rows = await session.scalar(
                select(func.count()).select_from(VitalSampleRow).where(VitalSampleRow.ts > t0)
            )
            latest = await vitals_repo.latest(session, "AST-03")
        assert live_rows >= 4 * 15, "live ticks should be flushed every 5 s"
        assert latest is not None and latest.ts.tzinfo is not None, "TIMESTAMPTZ must round-trip as aware UTC"

    # Restart against the same database: open alerts are restored, history is not duplicated.
    app2 = create_app(pg_settings)
    async with app2.router.lifespan_context(app2):
        assert app2.state.monitor.evaluator.find(spo2["id"]) is not None
        async with app2.state.session_factory() as session:
            total_after_restart = await session.scalar(select(func.count()).select_from(VitalSampleRow))
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://pg") as client:
            resolved = await client.post(f"/api/alerts/{spo2['id']}/resolve", json={"note": "Postgres test"})
            assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert total_after_restart < 4 * 144 + live_rows + 8, "restart must not re-backfill history"
