"""Periodic data retention.

Raw 1 Hz vital samples grow by roughly 69,000 rows a day for a four-person crew, so rows older than
``ASTRA_HISTORY_RETENTION_DAYS`` are removed. Expired sign-in sessions are removed a day after they
expire. The audit log and the mission event history are deliberately kept: they are the record of
who did what, and shortening them is a policy decision, not housekeeping.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.models import AuthSessionRow, VitalSampleRow


async def prune_once(settings: Settings, factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    now = utcnow()
    async with factory() as session:
        vitals = await session.execute(
            delete(VitalSampleRow).where(VitalSampleRow.ts < now - timedelta(days=settings.history_retention_days))
        )
        sessions = await session.execute(delete(AuthSessionRow).where(AuthSessionRow.expires_at < now - timedelta(days=1)))
        await session.commit()
    return {"vital_samples": vitals.rowcount or 0, "expired_sessions": sessions.rowcount or 0}
