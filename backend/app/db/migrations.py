"""Alembic helpers used at start-up when ASTRA_DB_SCHEMA_MODE=migrate.

The schema is owned by the migration scripts in ``backend/migrations``. The API never upgrades the
database itself (a deploy runs ``alembic upgrade head`` first, once), it only checks that the
database is at the newest revision and refuses to start otherwise, so code and schema cannot drift.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

BACKEND = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def head_revisions() -> set[str]:
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())


async def current_revisions(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        try:
            rows = (await conn.execute(text("SELECT version_num FROM alembic_version"))).all()
        except Exception:  # the table does not exist: never migrated
            return set()
    return {r[0] for r in rows}


class SchemaNotMigratedError(RuntimeError):
    pass


async def assert_migrated(engine: AsyncEngine) -> None:
    heads, current = head_revisions(), await current_revisions(engine)
    if current != heads:
        raise SchemaNotMigratedError(
            f"Database schema is at {sorted(current) or 'no revision'}, the code expects {sorted(heads)}. "
            "Run `alembic upgrade head` in backend/ (or set ASTRA_DB_SCHEMA_MODE=create for development)."
        )
