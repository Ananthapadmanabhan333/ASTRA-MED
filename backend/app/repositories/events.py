from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SimulationEventRow
from app.simulator.scenarios import ActiveScenario


def scenario_to_row(s: ActiveScenario) -> SimulationEventRow:
    return SimulationEventRow(
        id=s.id,
        scenario=s.scenario.value,
        astronaut_id=s.astronaut_id,
        intensity=s.intensity,
        started_at=s.started_at,
        ends_at=s.ends_at,
        cancelled_at=s.cancelled_at,
        triggered_by=s.triggered_by,
    )


async def upsert(session: AsyncSession, scenarios: Iterable[ActiveScenario]) -> None:
    for s in scenarios:
        await session.merge(scenario_to_row(s))


async def existing_ids(session: AsyncSession, ids: Iterable[str]) -> set[str]:
    ids = list(ids)
    if not ids:
        return set()
    rows = await session.scalars(select(SimulationEventRow.id).where(SimulationEventRow.id.in_(ids)))
    return set(rows.all())


async def list_events(
    session: AsyncSession,
    *,
    astronaut_id: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[SimulationEventRow]:
    stmt = select(SimulationEventRow)
    if astronaut_id:
        stmt = stmt.where(
            or_(
                SimulationEventRow.astronaut_id == astronaut_id,
                SimulationEventRow.astronaut_id.is_(None),
            )
        )
    if since:
        stmt = stmt.where(SimulationEventRow.started_at >= since)
    stmt = stmt.order_by(SimulationEventRow.started_at.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())
