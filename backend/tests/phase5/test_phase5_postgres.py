"""Phase 5 on PostgreSQL (opt-in, like tests/test_postgres.py): VARCHAR limits, JSON columns and
the security tables are enforced there but not on SQLite.

    ASTRA_TEST_POSTGRES_URL=postgresql+asyncpg://...@localhost:54369/astra_med_test
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import AuditLogRow, AuthSessionRow, Base, IncidentReportRow, TwinDailyRow
from app.db.session import create_engine
from app.main import create_app

PG_URL = os.getenv("ASTRA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="set ASTRA_TEST_POSTGRES_URL to run PostgreSQL integration tests")


async def _drop_all() -> None:
    engine = create_engine(PG_URL)  # type: ignore[arg-type]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_app():
    await _drop_all()
    settings = Settings(
        database_url=PG_URL, auth_enabled=True, simulator_enabled=False, random_events_per_hour=0,
        backfill_days=1, backfill_interval_minutes=10, space_sync_enabled=False, twin_background=False,
        mission_start_date=(datetime.now(UTC) - timedelta(days=5)).date(), log_level="WARNING",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app
    await _drop_all()


async def test_phase5_flow_on_postgres(pg_app):
    pw = "Pg-" + secrets.token_urlsafe(18)
    await pg_app.state.auth.create_user("pg.operator", "PG Operator", "mission_operator", pw)
    async with AsyncClient(transport=ASGITransport(app=pg_app), base_url="http://pg") as c:
        r = await c.post("/api/auth/login", json={"username": "pg.operator", "password": pw})
        assert r.status_code == 200
        c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        assert (await c.get("/api/twin/AST-01")).status_code == 200
        assert (await c.get("/api/multisystem/AST-01")).status_code == 200
        run = await c.post("/api/emergency/runs", json={"scenario": "sleep_disruption", "astronaut_id": "AST-01",
                                                        "severity": "severe", "duration_seconds": 60})
        assert run.status_code == 201
        assert (await c.post(f"/api/emergency/runs/{run.json()['id']}/analyze")).status_code == 200
        long_title = "T" * 200  # the maximum the schema accepts must fit the column
        rep = await c.post("/api/reports", json={"astronaut_id": "AST-01", "title": long_title})
        assert rep.status_code == 201 and rep.json()["integrity"] == "intact"
        assert (await c.get(f"/api/reports/{rep.json()['id']}/pdf")).status_code == 200
        ask = await c.post("/api/assistant/ask", json={"question": "How is Maya doing right now?"})
        assert ask.status_code == 200 and ask.json()["statements"]
        assert (await c.get("/api/overview", params={"period": "7d"})).status_code == 200
    async with pg_app.state.session_factory() as s:
        assert (await s.scalars(select(TwinDailyRow).where(TwinDailyRow.astronaut_id == "AST-01"))).all()
        report = (await s.scalars(select(IncidentReportRow))).one()
        assert report.title == long_title
        assert len((await s.scalars(select(AuthSessionRow))).all()) == 1
        actions = {a.action for a in (await s.scalars(select(AuditLogRow))).all()}
    assert {"login", "assistant_query", "report_exported"} <= actions
