"""Bring a database created before migrations existed under Alembic control.

Databases from phases 1-6 were created by ``create_all`` and have no ``alembic_version`` table.
This script compares such a database with the models. If they match, ``--stamp`` records the
newest revision (the schema is already complete). If the only differences are tables added by later
revisions, it records the baseline so ``alembic upgrade head`` adds them. Anything else is printed
and nothing changes.

    python scripts/db_adopt.py                 # compare only (reads ASTRA_DATABASE_URL)
    python scripts/db_adopt.py --stamp         # compare, then stamp the baseline if identical
    python scripts/db_adopt.py --url postgresql+asyncpg://...   # another database
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.migrations import alembic_config  # noqa: E402
from app.db.models import Base  # noqa: E402

BASELINE = "0001"
# Tables created by revisions after the baseline (a phase 1-6 database simply lacks them).
LATER_TABLES = {"crew_self_reports"}


def _only_later_tables(changes: list) -> bool:
    for c in changes:
        op = c[0] if isinstance(c, tuple) else None
        if op == "add_table" and c[1].name in LATER_TABLES:
            continue
        if op == "add_index" and c[1].table.name in LATER_TABLES:
            continue
        return False
    return True


async def diff(url: str) -> tuple[list, str | None]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            def run(sync_conn):
                ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
                return compare_metadata(ctx, Base.metadata), ctx.get_current_revision()

            return await conn.run_sync(run)
    finally:
        await engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="")
    ap.add_argument("--stamp", action="store_true")
    args = ap.parse_args()
    url = Settings(database_url=args.url).database_url if args.url else Settings().database_url

    changes, current = asyncio.run(diff(url))
    if current:
        print(f"Database is already under Alembic control (revision {current}). Use: alembic upgrade head")
        return 0
    if changes and not _only_later_tables(changes):
        print(f"The database differs from the models in {len(changes)} place(s); not stamping:")
        for c in changes:
            print("  ", c)
        return 1
    target = BASELINE if changes else "head"
    print("The database matches the baseline schema; later tables are missing." if changes
          else "The database matches the models exactly.")
    if args.stamp:
        cfg = alembic_config()
        cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
        command.stamp(cfg, target)
        print(f"Stamped revision {target}. Next: alembic upgrade head")
    else:
        print(f"Re-run with --stamp to record revision {target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
