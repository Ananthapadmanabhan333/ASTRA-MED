from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url, connect_args={"timeout": 30}, hide_parameters=True)

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    # hide_parameters: a logged database error never prints bound values (password hashes, token
    # digests, vital signs).
    return create_async_engine(database_url, pool_size=10, max_overflow=10, pool_pre_ping=True,
                               hide_parameters=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# Column changes made after a table was first created. ``create_all`` never alters existing tables,
# so these idempotent statements bring an older PostgreSQL database up to date (SQLite does not
# enforce VARCHAR lengths, so it needs none). Alembic should replace this once migrations exist.
_POSTGRES_UPGRADES = (
    "ALTER TABLE space_weather_events ALTER COLUMN classification TYPE TEXT",
    "ALTER TABLE space_weather_events ALTER COLUMN magnitude_unit TYPE VARCHAR(64)",
    "ALTER TABLE data_sync_runs ALTER COLUMN task TYPE VARCHAR(160)",
)


async def create_schema(engine: AsyncEngine) -> None:
    """Development schema bootstrap (ASTRA_DB_SCHEMA_MODE=create). Production uses Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            for statement in _POSTGRES_UPGRADES:
                await conn.execute(text(statement))


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
