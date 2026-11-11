from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VitalSampleRow
from app.simulator.engine import VitalReading

_COLUMNS = (
    "heart_rate",
    "spo2",
    "systolic",
    "diastolic",
    "temperature_c",
    "respiratory_rate",
    "activity_state",
    "activity_met",
    "rhythm",
    "hrv_rmssd_ms",
    "scenario",
)


def _as_dict(r: VitalReading) -> dict:
    d = {c: getattr(r, c) for c in _COLUMNS}
    d.update(astronaut_id=r.astronaut_id, ts=r.ts, data_source="simulated")
    return d


async def insert_readings(
    session: AsyncSession, readings: Sequence[VitalReading], batch: int = 2000
) -> int:
    for i in range(0, len(readings), batch):
        chunk = [_as_dict(r) for r in readings[i : i + batch]]
        if chunk:
            await session.execute(insert(VitalSampleRow), chunk)
    return len(readings)


async def last_sample_ts(session: AsyncSession, astronaut_id: str) -> datetime | None:
    return await session.scalar(
        select(func.max(VitalSampleRow.ts)).where(VitalSampleRow.astronaut_id == astronaut_id)
    )


async def latest(session: AsyncSession, astronaut_id: str) -> VitalSampleRow | None:
    return await session.scalar(
        select(VitalSampleRow)
        .where(VitalSampleRow.astronaut_id == astronaut_id)
        .order_by(VitalSampleRow.ts.desc())
        .limit(1)
    )


async def fetch_range(
    session: AsyncSession,
    astronaut_id: str,
    start: datetime,
    end: datetime,
    columns: Sequence[str] = ("heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate", "activity_met"),
) -> list[tuple]:
    cols = [VitalSampleRow.ts, *(getattr(VitalSampleRow, c) for c in columns)]
    stmt = (
        select(*cols)
        .where(
            VitalSampleRow.astronaut_id == astronaut_id,
            VitalSampleRow.ts >= start,
            VitalSampleRow.ts <= end,
        )
        .order_by(VitalSampleRow.ts)
    )
    return [tuple(row) for row in (await session.execute(stmt)).all()]


async def mean_metric(
    session: AsyncSession,
    astronaut_id: str,
    metric: str,
    start: datetime,
    end: datetime,
    activity_states: Sequence[str],
) -> float | None:
    col = getattr(VitalSampleRow, metric)
    value = await session.scalar(
        select(func.avg(col)).where(
            VitalSampleRow.astronaut_id == astronaut_id,
            VitalSampleRow.ts >= start,
            VitalSampleRow.ts < end,
            VitalSampleRow.activity_state.in_(list(activity_states)),
            VitalSampleRow.scenario.is_(None),
        )
    )
    return float(value) if value is not None else None


async def prune_before(session: AsyncSession, cutoff: datetime) -> None:
    await session.execute(delete(VitalSampleRow).where(VitalSampleRow.ts < cutoff))
