from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Integer, cast, delete, func, insert, select
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


async def bucket_means(
    session: AsyncSession,
    astronaut_id: str,
    start: datetime,
    end: datetime,
    resolution_s: int,
    columns: Sequence[str],
) -> list[tuple[datetime, list[float], int]]:
    """Average stored samples into fixed buckets inside the database: (bucket_centre, means, count).

    Same buckets as ``services.history.bucket_rows`` (index = floor((ts - start) / resolution)), but
    only one row per bucket leaves the database, so a 7-day range moves a few hundred rows instead of
    ~120,000 per crew member and no Python loop runs on the event loop.
    """
    base = start.timestamp()
    if session.bind.dialect.name == "postgresql":
        epoch = func.extract("epoch", VitalSampleRow.ts)
        idx = func.floor((epoch - base) / resolution_s)
    else:  # SQLite stores naive UTC text; julianday() gives fractional days since noon, 4713 BC
        epoch = (func.julianday(VitalSampleRow.ts) - 2440587.5) * 86400.0
        idx = cast((epoch - base) / resolution_s, Integer)  # non-negative, so truncation equals floor
    bucket = idx.label("bucket")
    stmt = (
        select(bucket, *(func.avg(getattr(VitalSampleRow, c)) for c in columns), func.count())
        .where(VitalSampleRow.astronaut_id == astronaut_id, VitalSampleRow.ts >= start, VitalSampleRow.ts <= end)
        .group_by(bucket)
        .order_by(bucket)
    )
    out = []
    for row in (await session.execute(stmt)).all():
        k = int(row[0])
        ts = start + timedelta(seconds=k * resolution_s + resolution_s / 2)
        out.append((ts, [float(v) for v in row[1:-1]], int(row[-1])))
    return out


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
