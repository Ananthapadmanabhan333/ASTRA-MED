from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertRow
from app.detection.evaluator import AlertRecord

_FIELDS = (
    "id", "astronaut_id", "rule_key", "category", "metric", "direction", "severity", "status",
    "title", "message", "unit", "trigger_value", "threshold_value", "peak_value",
    "activity_state", "scenario", "opened_at", "updated_at", "condition_cleared_at",
    "acknowledged_at", "resolved_at", "operator_note",
)


def record_to_row(rec: AlertRecord) -> AlertRow:
    return AlertRow(**{f: getattr(rec, f) for f in _FIELDS}, data_source="simulated")


def row_to_record(row: AlertRow) -> AlertRecord:
    return AlertRecord(**{f: getattr(row, f) for f in _FIELDS})


async def upsert(session: AsyncSession, records: Iterable[AlertRecord]) -> None:
    for rec in records:
        await session.merge(record_to_row(rec))


async def get(session: AsyncSession, alert_id: str) -> AlertRow | None:
    return await session.get(AlertRow, alert_id)


async def list_alerts(
    session: AsyncSession,
    *,
    statuses: Iterable[str] | None = None,
    severities: Iterable[str] | None = None,
    astronaut_id: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
) -> list[AlertRow]:
    stmt = select(AlertRow)
    if statuses:
        stmt = stmt.where(AlertRow.status.in_(list(statuses)))
    if severities:
        stmt = stmt.where(AlertRow.severity.in_(list(severities)))
    if astronaut_id:
        stmt = stmt.where(AlertRow.astronaut_id == astronaut_id)
    if since:
        stmt = stmt.where(AlertRow.opened_at >= since)
    stmt = stmt.order_by(AlertRow.opened_at.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def open_alerts(session: AsyncSession) -> list[AlertRow]:
    return await list_alerts(session, statuses=("active", "acknowledged"), limit=1000)


async def count_since(
    session: AsyncSession, astronaut_id: str, since: datetime
) -> list[tuple[str, int]]:
    stmt = (
        select(AlertRow.metric, func.count())
        .where(AlertRow.astronaut_id == astronaut_id, AlertRow.opened_at >= since)
        .group_by(AlertRow.metric)
    )
    return [(m, int(c)) for m, c in (await session.execute(stmt)).all()]
