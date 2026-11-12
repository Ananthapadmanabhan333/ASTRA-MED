"""Space ingestion on PostgreSQL (opt-in, like tests/test_postgres.py).

PostgreSQL enforces VARCHAR lengths where SQLite does not; this caught a real overflow on a long
WSA-ENLIL classification during the first live sync.
"""

from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import Base, SpaceWeatherEventRow
from app.db.session import create_engine, create_schema, create_session_factory
from app.space.service import SpaceDataService

from .conftest import fixture

PG_URL = os.getenv("ASTRA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="set ASTRA_TEST_POSTGRES_URL to run PostgreSQL integration tests")


@pytest_asyncio.fixture
async def pg():
    engine = create_engine(PG_URL)  # type: ignore[arg-type]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_schema(engine)
    await create_schema(engine)  # the upgrade statements must be idempotent
    yield engine, create_session_factory(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_long_nasa_strings_and_full_ingestion_on_postgres(pg, fake_nasa, no_sleep):
    engine, factory = pg
    wsa = fixture("donki_WSA.json")
    wsa[0] = dict(wsa[0], impactList=[{"location": name, "arrivalTime": "2026-10-20T00:00Z", "isGlancingBlow": True}
                                      for name in ("Mars", "Psyche", "Solar Orbiter", "STEREO A", "Juno", "Lucy",
                                                   "Parker Solar Probe", "BepiColombo")])
    fake_nasa.overrides["/DONKI/WS/get/WSAEnlilSimulations"] = lambda req: httpx.Response(200, json=wsa)
    settings = Settings(database_url=PG_URL, space_request_spacing_s=0, donki_backfill_days=20, log_level="WARNING")
    svc = SpaceDataService(settings, factory, transport=httpx.MockTransport(fake_nasa), sleep=no_sleep)
    summary = await svc.sync_donki_recent()
    assert not any(v.get("errors") for v in summary.values()), summary
    await svc.sync_eda(["RR-1"])
    await svc.sync_osdr(["rodent"])
    async with factory() as session:
        n = await session.scalar(select(func.count()).select_from(SpaceWeatherEventRow))
        long_cls = await session.scalar(select(func.max(func.length(SpaceWeatherEventRow.classification))))
    assert n > 0 and long_cls > 64
    rows = await svc.sources_status()
    assert {r["info"].id: r["stats"]["records"] > 0 for r in rows} == {"donki": True, "eda": True, "osdr": True}
    await svc.stop()
