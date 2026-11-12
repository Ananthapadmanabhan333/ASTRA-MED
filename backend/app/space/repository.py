"""Database access for NASA open data. Writes are idempotent: re-ingesting the same records
never creates duplicates, and a newer DONKI ``versionId`` replaces the stored record."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DataSyncRunRow,
    EnvMeasurementRow,
    EnvMissionRow,
    OsdrStudyRow,
    SpaceNotificationRow,
    SpaceWeatherEventRow,
)

_EVENT_FIELDS = (
    "event_type", "category", "start_time", "peak_time", "end_time", "classification", "scale", "severity",
    "magnitude", "magnitude_unit", "location", "description", "instruments", "linked_ids", "notification_ids",
    "model_derived", "link", "version", "submitted_at", "raw",
)


async def upsert_events(
    session: AsyncSession, source_id: str, endpoint: str, retrieved_at: datetime, rows: list[dict[str, Any]]
) -> tuple[int, int, int]:
    """Insert new events, update ones whose version increased. Returns (new, updated, duplicates)."""
    if not rows:
        return 0, 0, 0
    ids = [r["external_id"] for r in rows]
    existing: dict[str, SpaceWeatherEventRow] = {}
    for chunk in range(0, len(ids), 500):
        stmt = select(SpaceWeatherEventRow).where(
            SpaceWeatherEventRow.source_id == source_id,
            SpaceWeatherEventRow.external_id.in_(ids[chunk:chunk + 500]),
        )
        existing.update({e.external_id: e for e in (await session.scalars(stmt)).all()})
    new = updated = duplicates = 0
    for r in rows:
        row = existing.get(r["external_id"])
        if row is None:
            session.add(SpaceWeatherEventRow(source_id=source_id, external_id=r["external_id"],
                                             retrieved_at=retrieved_at, endpoint=endpoint,
                                             **{k: r[k] for k in _EVENT_FIELDS}))
            new += 1
        elif r["version"] > row.version or (r["version"] == row.version and r["raw"] != row.raw):
            for k in _EVENT_FIELDS:
                setattr(row, k, r[k])
            row.retrieved_at, row.endpoint = retrieved_at, endpoint
            updated += 1
        else:
            duplicates += 1
    await session.flush()
    return new, updated, duplicates


async def upsert_notifications(
    session: AsyncSession, source_id: str, endpoint: str, retrieved_at: datetime, rows: list[dict[str, Any]]
) -> tuple[int, int, int]:
    if not rows:
        return 0, 0, 0
    ids = [r["message_id"] for r in rows]
    stmt = select(SpaceNotificationRow.message_id).where(
        SpaceNotificationRow.source_id == source_id, SpaceNotificationRow.message_id.in_(ids)
    )
    have = set((await session.scalars(stmt)).all())
    new = 0
    for r in rows:
        if r["message_id"] in have:
            continue
        session.add(SpaceNotificationRow(source_id=source_id, endpoint=endpoint, retrieved_at=retrieved_at, **r))
        new += 1
    await session.flush()
    return new, 0, len(rows) - new


async def upsert_missions(session: AsyncSession, rows: list[dict[str, Any]], retrieved_at: datetime) -> int:
    new = 0
    for r in rows:
        row = await session.get(EnvMissionRow, r["name"])
        if row is None:
            session.add(EnvMissionRow(retrieved_at=retrieved_at, milestones=[], quality={}, **r))
            new += 1
        else:
            row.title, row.description, row.link, row.retrieved_at = r["title"], r["description"], r["link"], retrieved_at
    await session.flush()
    return new


async def replace_measurements(
    session: AsyncSession, mission: str, quantities: Iterable[str], rows: list[dict[str, Any]]
) -> int:
    """Replace a mission's stored series for these quantities (idempotent re-ingestion)."""
    await session.execute(
        delete(EnvMeasurementRow).where(EnvMeasurementRow.mission == mission,
                                        EnvMeasurementRow.quantity.in_(list(quantities)))
    )
    if rows:
        await session.execute(EnvMeasurementRow.__table__.insert(), [{"mission": mission, **r} for r in rows])
    return len(rows)


async def upsert_studies(
    session: AsyncSession, endpoint: str, retrieved_at: datetime, rows: list[dict[str, Any]]
) -> tuple[int, int]:
    new = updated = 0
    for r in rows:
        row = await session.get(OsdrStudyRow, r["accession"])
        if row is None:
            session.add(OsdrStudyRow(endpoint=endpoint, retrieved_at=retrieved_at, **r))
            new += 1
        else:
            topics = sorted(set(row.topics or []) | set(r["topics"]))
            for k, v in r.items():
                if k != "topics":
                    setattr(row, k, v)
            row.topics, row.retrieved_at, row.endpoint = topics, retrieved_at, endpoint
            updated += 1
    await session.flush()
    return new, updated


async def record_sync(session: AsyncSession, **fields: Any) -> DataSyncRunRow:
    row = DataSyncRunRow(**fields)
    session.add(row)
    await session.flush()
    return row


# ----------------------------------------------------------------------------- queries ----
async def list_events(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    types: Iterable[str] | None = None,
    min_severity: int | None = None,
    limit: int = 2000,
) -> list[SpaceWeatherEventRow]:
    stmt = select(SpaceWeatherEventRow)
    if start is not None:
        stmt = stmt.where(or_(SpaceWeatherEventRow.start_time >= start, SpaceWeatherEventRow.end_time >= start))
    if end is not None:
        stmt = stmt.where(SpaceWeatherEventRow.start_time <= end)
    if types:
        stmt = stmt.where(SpaceWeatherEventRow.event_type.in_(list(types)))
    if min_severity is not None:
        stmt = stmt.where(SpaceWeatherEventRow.severity >= min_severity)
    stmt = stmt.order_by(SpaceWeatherEventRow.start_time.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def get_event(session: AsyncSession, event_id: int) -> SpaceWeatherEventRow | None:
    return await session.get(SpaceWeatherEventRow, event_id)


async def list_notifications(session: AsyncSession, start: datetime | None, end: datetime | None,
                             limit: int = 200) -> list[SpaceNotificationRow]:
    stmt = select(SpaceNotificationRow)
    if start is not None:
        stmt = stmt.where(SpaceNotificationRow.issue_time >= start)
    if end is not None:
        stmt = stmt.where(SpaceNotificationRow.issue_time <= end)
    stmt = stmt.order_by(SpaceNotificationRow.issue_time.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def event_stats(session: AsyncSession, source_id: str) -> dict[str, Any]:
    stmt = select(func.count(), func.min(SpaceWeatherEventRow.start_time), func.max(SpaceWeatherEventRow.start_time),
                  func.max(SpaceWeatherEventRow.retrieved_at)).where(SpaceWeatherEventRow.source_id == source_id)
    n, first, last, retrieved = (await session.execute(stmt)).one()
    by_type = dict((await session.execute(
        select(SpaceWeatherEventRow.event_type, func.count()).where(SpaceWeatherEventRow.source_id == source_id)
        .group_by(SpaceWeatherEventRow.event_type))).all())
    notes = await session.scalar(select(func.count()).select_from(SpaceNotificationRow))
    return {"records": int(n or 0), "first": first, "last": last, "last_retrieved": retrieved,
            "by_type": by_type, "notifications": int(notes or 0)}


async def list_missions(session: AsyncSession) -> list[EnvMissionRow]:
    stmt = select(EnvMissionRow).order_by(EnvMissionRow.start_time.is_(None), EnvMissionRow.start_time, EnvMissionRow.name)
    return list((await session.scalars(stmt)).all())


async def get_mission(session: AsyncSession, name: str) -> EnvMissionRow | None:
    return await session.get(EnvMissionRow, name)


async def measurements(
    session: AsyncSession, mission: str, quantities: Iterable[str] | None = None, platform: str | None = None
) -> list[EnvMeasurementRow]:
    stmt = select(EnvMeasurementRow).where(EnvMeasurementRow.mission == mission)
    if quantities:
        stmt = stmt.where(EnvMeasurementRow.quantity.in_(list(quantities)))
    if platform:
        stmt = stmt.where(EnvMeasurementRow.platform == platform)
    stmt = stmt.order_by(EnvMeasurementRow.quantity, EnvMeasurementRow.platform, EnvMeasurementRow.ts)
    return list((await session.scalars(stmt)).all())


async def measurement_stats(session: AsyncSession) -> dict[str, Any]:
    stmt = select(func.count(), func.min(EnvMeasurementRow.ts), func.max(EnvMeasurementRow.ts),
                  func.count(func.distinct(EnvMeasurementRow.mission)))
    n, first, last, missions = (await session.execute(stmt)).one()
    retrieved = await session.scalar(select(func.max(EnvMissionRow.telemetry_synced_at)))
    return {"records": int(n or 0), "first": first, "last": last, "missions_with_data": int(missions or 0),
            "last_retrieved": retrieved}


async def list_studies(
    session: AsyncSession, topic: str | None = None, q: str | None = None, organism: str | None = None,
    project_type: str | None = None, mission: str | None = None, limit: int = 100, offset: int = 0,
) -> tuple[list[OsdrStudyRow], int]:
    stmt = select(OsdrStudyRow)
    rows = list((await session.scalars(stmt.order_by(OsdrStudyRow.release_date.desc().nulls_last()))).all())
    def keep(r: OsdrStudyRow) -> bool:
        if topic and topic not in (r.topics or []):
            return False
        if mission and f"mission:{mission.upper()}" not in (r.topics or []):
            return False
        if organism and organism.lower() not in (r.organism or "").lower():
            return False
        if project_type and project_type.lower() not in (r.project_type or "").lower():
            return False
        if q:
            hay = " ".join(filter(None, (r.accession, r.title, r.description, r.organism, r.mission_name,
                                         r.flight_program, r.assay_type))).lower()
            if not all(word in hay for word in q.lower().split()):
                return False
        return True
    matched = [r for r in rows if keep(r)]  # catalogue is small (hundreds of rows)
    return matched[offset:offset + limit], len(matched)


async def study_stats(session: AsyncSession) -> dict[str, Any]:
    n, first, last, retrieved = (await session.execute(
        select(func.count(), func.min(OsdrStudyRow.release_date), func.max(OsdrStudyRow.release_date),
               func.max(OsdrStudyRow.retrieved_at)))).one()
    return {"records": int(n or 0), "first": first, "last": last, "last_retrieved": retrieved}


async def recent_syncs(session: AsyncSession, source_id: str, limit: int = 10) -> list[DataSyncRunRow]:
    stmt = (select(DataSyncRunRow).where(DataSyncRunRow.source_id == source_id)
            .order_by(DataSyncRunRow.started_at.desc()).limit(limit))
    return list((await session.scalars(stmt)).all())


async def last_successful_sync(session: AsyncSession, source_id: str, task_prefix: str = "") -> DataSyncRunRow | None:
    stmt = (select(DataSyncRunRow).where(DataSyncRunRow.source_id == source_id, DataSyncRunRow.status != "failed",
                                         DataSyncRunRow.task.startswith(task_prefix))
            .order_by(DataSyncRunRow.started_at.desc()).limit(1))
    return (await session.scalars(stmt)).first()


async def quality_totals(session: AsyncSession, source_id: str) -> dict[str, int]:
    stmt = select(func.coalesce(func.sum(DataSyncRunRow.records_received), 0),
                  func.coalesce(func.sum(DataSyncRunRow.invalid), 0),
                  func.coalesce(func.sum(DataSyncRunRow.duplicates), 0),
                  func.count()).where(DataSyncRunRow.source_id == source_id)
    received, invalid, duplicates, runs = (await session.execute(stmt)).one()
    failed = await session.scalar(select(func.count()).where(DataSyncRunRow.source_id == source_id,
                                                             DataSyncRunRow.status == "failed"))
    return {"received": int(received), "invalid": int(invalid), "duplicates": int(duplicates),
            "runs": int(runs), "failed_runs": int(failed)}


async def donki_coverage(session: AsyncSession, event_type: str) -> list[tuple[str, str]]:
    """Date ranges (ISO days) successfully queried for one DONKI type: days inside them with no
    stored event really had none reported; days outside were never checked."""
    stmt = select(DataSyncRunRow.detail).where(DataSyncRunRow.source_id == "donki", DataSyncRunRow.status != "failed",
                                               DataSyncRunRow.task.contains(f":{event_type} "))
    ranges = []
    for d in (await session.scalars(stmt)).all():
        if isinstance(d, dict) and d.get("start") and d.get("end"):
            ranges.append((d["start"], d["end"]))
    return sorted(set(ranges))
