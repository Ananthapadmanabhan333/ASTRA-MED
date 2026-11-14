"""Mission event store: one normalised, prioritised, de-duplicated history of everything that happens.

Producers hand in an :class:`EventInput`. :meth:`MissionEventService.publish` then

1. **synchronises timestamps**: every time becomes timezone-aware UTC. ``occurred_at`` is the
   source's own time (the simulation clock for sandbox runs) and ``received_at`` the wall-clock
   time the pipeline took the event in. An operations event stamped more than the configured
   tolerance in the future is clamped to ``received_at`` and the skew is recorded;
2. **prioritises** it on the shared scale in :mod:`app.mission.taxonomy`;
3. **de-duplicates** it by fingerprint. Events that describe a source record (``ref_type`` +
   ``ref_id``, e.g. an alert or a DONKI event) are merged whenever they recur; other events are
   merged when they repeat within the de-duplication window. A merge increments ``occurrences``
   and raises the severity if the repeat is worse;
4. **persists** it in ``mission_events`` (the event history) and
5. **broadcasts** it to live dashboards as a ``mission_event`` WebSocket message.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import as_utc, utcnow
from app.db.models import MissionEventRow
from app.mission.jsonsafe import jsonable
from app.mission.taxonomy import (
    CATEGORY_LABELS,
    CLASSIFICATION_NOTES,
    ORIGIN_LABELS,
    PRIORITY_LABELS,
    SEVERITY_RANK,
    SOURCE_LABELS,
    priority_for,
)

logger = logging.getLogger("astra.mission.events")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class EventInput:
    source: str
    kind: str
    category: str
    severity: str
    title: str
    occurred_at: datetime
    summary: str | None = None
    astronaut_id: str | None = None
    context: str = "operations"
    simulation_id: str | None = None
    data_origin: str = "simulated"
    classification: str = "rule_detection"
    experimental: bool = False
    confidence: float | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    dedupe_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def fingerprint(inp: EventInput) -> tuple[str, bool]:
    """(fingerprint, ref_based). Ref-based fingerprints identify one source record and never expire."""
    if inp.ref_type and inp.ref_id:
        basis = f"{inp.source}|{inp.kind}|{inp.ref_type}|{inp.ref_id}|{inp.context}|{inp.simulation_id or ''}"
        ref_based = True
    else:
        basis = (f"{inp.source}|{inp.kind}|{inp.astronaut_id or ''}|{inp.context}|{inp.simulation_id or ''}|"
                 f"{inp.dedupe_key or inp.title}")
        ref_based = False
    return hashlib.sha1(basis.encode("utf-8")).hexdigest(), ref_based


def event_view(row: MissionEventRow) -> dict[str, Any]:
    payload = row.payload or {}
    return {
        "id": row.id, "source": row.source, "source_label": SOURCE_LABELS.get(row.source, row.source),
        "kind": row.kind, "category": row.category, "category_label": CATEGORY_LABELS.get(row.category, row.category),
        "severity": row.severity, "priority": row.priority, "priority_label": PRIORITY_LABELS[row.priority],
        "priority_score": row.priority_score, "title": row.title, "summary": row.summary,
        "astronaut_id": row.astronaut_id, "context": row.context, "simulation_id": row.simulation_id,
        "data_origin": row.data_origin, "data_origin_label": ORIGIN_LABELS.get(row.data_origin, row.data_origin),
        "classification": payload.get("classification"),
        "classification_note": CLASSIFICATION_NOTES.get(payload.get("classification") or "", None),
        "experimental": row.experimental, "confidence": row.confidence, "ref_type": row.ref_type, "ref_id": row.ref_id,
        "occurred_at": row.occurred_at, "received_at": row.received_at, "last_seen_at": row.last_seen_at,
        "latency_s": round((row.received_at - row.occurred_at).total_seconds(), 3),
        "clock_skew_s": row.clock_skew_s, "occurrences": row.occurrences, "payload": payload,
    }


# Event sources that need a permission beyond health:read. Incident reports (titles, IDs, review
# status) are only for roles with reports:read, so their events are hidden from everyone else in
# the event APIs, the overview and the live stream.
SOURCE_PERMISSIONS: dict[str, str] = {"incident_reports": "reports:read"}


def hidden_sources(principal) -> frozenset[str]:
    """Event sources this principal may not see."""
    return frozenset(src for src, perm in SOURCE_PERMISSIONS.items() if not principal.can(perm))


class MissionEventService:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession], hub) -> None:
        self.settings = settings
        self.factory = factory
        self.hub = hub
        self.counters: Counter[str] = Counter()
        self._lock = asyncio.Lock()  # one writer: fingerprint look-up and insert must not interleave

    # ------------------------------------------------------------------ publish ----
    def _normalise(self, inp: EventInput, received: datetime) -> tuple[datetime, float | None]:
        occurred = as_utc(inp.occurred_at)
        ahead = (occurred - received).total_seconds()
        # Sandbox events carry the simulation clock, which may run ahead of the wall clock by design.
        if inp.context == "operations" and ahead > self.settings.mission_clock_skew_tolerance_s:
            self.counters["clock_skew_clamped"] += 1
            return received, round(ahead, 3)
        return occurred, None

    async def publish(self, inp: EventInput) -> tuple[MissionEventRow, bool]:
        """Store (or merge) one event. Returns (row, created)."""
        received = utcnow()
        occurred, skew = self._normalise(inp, received)
        fp, ref_based = fingerprint(inp)
        payload = jsonable({**inp.payload, "classification": inp.classification})
        async with self._lock, self.factory() as session:
            stmt = select(MissionEventRow).where(MissionEventRow.fingerprint == fp)
            if not ref_based:
                window = timedelta(minutes=self.settings.mission_event_dedupe_minutes)
                stmt = stmt.where(MissionEventRow.last_seen_at >= received - window)
            existing = (await session.scalars(stmt.order_by(MissionEventRow.last_seen_at.desc()).limit(1))).first()
            if existing is not None:
                existing.occurrences += 1
                existing.last_seen_at = received
                escalated = SEVERITY_RANK.get(inp.severity, 0) > SEVERITY_RANK.get(existing.severity, 0)
                if escalated:
                    existing.severity = inp.severity
                    existing.priority, existing.priority_score = priority_for(
                        inp.severity, inp.classification, astronaut_specific=bool(inp.astronaut_id), escalated=True)
                    existing.title = inp.title[:200]
                    existing.summary = inp.summary
                    existing.payload = {**(existing.payload or {}), **payload, "escalated_at": received.isoformat()}
                await session.commit()
                self.counters["merged"] += 1
                if escalated:
                    await self._broadcast("updated", existing)
                return existing, False

            level, score = priority_for(inp.severity, inp.classification, astronaut_specific=bool(inp.astronaut_id))
            row = MissionEventRow(
                id=new_id("EV"), fingerprint=fp, source=inp.source, kind=inp.kind, category=inp.category,
                severity=inp.severity, priority=level, priority_score=score, title=inp.title[:200],
                summary=inp.summary, astronaut_id=inp.astronaut_id, context=inp.context,
                simulation_id=inp.simulation_id, data_origin=inp.data_origin, experimental=inp.experimental,
                confidence=inp.confidence, ref_type=inp.ref_type, ref_id=inp.ref_id, occurred_at=occurred,
                received_at=received, last_seen_at=received, clock_skew_s=skew, occurrences=1, payload=payload,
            )
            session.add(row)
            await session.commit()
        self.counters["created"] += 1
        await self._broadcast("created", row)
        return row, True

    async def _broadcast(self, kind: str, row: MissionEventRow) -> None:
        if self.hub is None or self.hub.count == 0:
            return
        from app.schemas.mission_control import MissionEvent, WsMissionEvent

        try:
            msg = WsMissionEvent(event=kind, item=MissionEvent.model_validate(event_view(row)))  # type: ignore[arg-type]
            await self.hub.broadcast(msg.model_dump_json(), requires=SOURCE_PERMISSIONS.get(row.source))
        except Exception:  # a broadcast failure must never lose the stored event
            logger.exception("could not broadcast mission event %s", row.id)

    # -------------------------------------------------------------------- read ----
    async def list(
        self,
        *,
        categories: list[str] | None = None,
        sources: list[str] | None = None,
        severities: list[str] | None = None,
        priorities: list[int] | None = None,
        astronaut_id: str | None = None,
        context: str | None = None,
        simulation_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        q: str | None = None,
        include_crew_wide: bool = True,
        exclude_sources: frozenset[str] | set[str] = frozenset(),
        limit: int = 200,
    ) -> list[MissionEventRow]:
        stmt = select(MissionEventRow)
        if exclude_sources:
            stmt = stmt.where(MissionEventRow.source.not_in(sorted(exclude_sources)))
        if categories:
            stmt = stmt.where(MissionEventRow.category.in_(categories))
        if sources:
            stmt = stmt.where(MissionEventRow.source.in_(sources))
        if severities:
            stmt = stmt.where(MissionEventRow.severity.in_(severities))
        if priorities:
            stmt = stmt.where(MissionEventRow.priority.in_(priorities))
        if astronaut_id:
            if include_crew_wide:
                stmt = stmt.where(or_(MissionEventRow.astronaut_id == astronaut_id, MissionEventRow.astronaut_id.is_(None)))
            else:
                stmt = stmt.where(MissionEventRow.astronaut_id == astronaut_id)
        if context:
            stmt = stmt.where(MissionEventRow.context == context)
        if simulation_id:
            stmt = stmt.where(MissionEventRow.simulation_id == simulation_id)
        if start:
            stmt = stmt.where(MissionEventRow.occurred_at >= as_utc(start))
        if end:
            stmt = stmt.where(MissionEventRow.occurred_at <= as_utc(end))
        if q:
            like = f"%{q.strip()[:80]}%"
            stmt = stmt.where(or_(MissionEventRow.title.ilike(like), MissionEventRow.summary.ilike(like)))
        stmt = stmt.order_by(MissionEventRow.occurred_at.desc()).limit(limit)
        async with self.factory() as session:
            return list((await session.scalars(stmt)).all())

    async def get(self, event_id: str) -> MissionEventRow | None:
        async with self.factory() as session:
            return await session.get(MissionEventRow, event_id)

    async def counts(self, start: datetime, end: datetime, context: str | None = "operations",
                     astronaut_id: str | None = None,
                     exclude_sources: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
        """Distribution of events by category, source, priority and data origin in a time range."""
        out: dict[str, Any] = {}
        async with self.factory() as session:
            for key, col in (("by_category", MissionEventRow.category), ("by_source", MissionEventRow.source),
                             ("by_priority", MissionEventRow.priority), ("by_origin", MissionEventRow.data_origin),
                             ("by_severity", MissionEventRow.severity)):
                stmt = select(col, func.count()).where(MissionEventRow.occurred_at >= start,
                                                       MissionEventRow.occurred_at <= end)
                if context:
                    stmt = stmt.where(MissionEventRow.context == context)
                if exclude_sources:
                    stmt = stmt.where(MissionEventRow.source.not_in(sorted(exclude_sources)))
                if astronaut_id:
                    stmt = stmt.where(or_(MissionEventRow.astronaut_id == astronaut_id,
                                          MissionEventRow.astronaut_id.is_(None)))
                rows = (await session.execute(stmt.group_by(col))).all()
                out[key] = {str(k): int(v) for k, v in rows}
        out["total"] = sum(out["by_category"].values())
        return out
