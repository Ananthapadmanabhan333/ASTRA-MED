"""Unified alert centre: one lifecycle (open -> acknowledged -> resolved) for alerts from every module.

* Rule alerts from the phase 2 monitor are **mirrored**: the monitor (and its ``alerts`` table)
  stays authoritative. Acknowledging or resolving such an alert here goes through the monitor,
  so both stores always agree; the consistency check repairs any drift.
* Sandbox rule alerts are delegated to the mission simulation sandbox the same way.
* AI, NASA space-weather and environment alerts live only here.

Every transition, automatic or by an operator, is appended to ``mission_alert_actions`` (who,
when, from and to status, note). The HTTP middleware also writes the operator action to the
security audit log.

Experimental AI predictions are never labelled critical and are capped at priority P3; their
classification travels with the alert so no screen can present one as a confirmed emergency.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.db.models import MissionAlertActionRow, MissionAlertRow
from app.detection.evaluator import AlertRecord
from app.detection.rules import THRESHOLD_RULES
from app.mission.events import new_id
from app.mission.jsonsafe import jsonable
from app.mission.taxonomy import (
    CATEGORY_LABELS,
    CLASSIFICATION_LABELS,
    CLASSIFICATION_NOTES,
    ORIGIN_LABELS,
    PRIORITY_LABELS,
    SEVERITY_RANK,
    SOURCE_LABELS,
    cap_ai_severity,
    priority_for,
)

logger = logging.getLogger("astra.mission.alerts")

RULE_SOURCE = "physiological_monitoring"
STATUS_FROM_RULE = {"active": "open", "acknowledged": "acknowledged", "resolved": "resolved"}
MAX_NOTE = 2000

# (source_ref, action, note) -> awaitable; raises ConflictError / NotFoundError like the owner would.
Delegate = Callable[[str, str, str | None], Awaitable[Any]]


@dataclass
class AlertSpec:
    source: str
    source_ref: str
    category: str
    classification: str
    severity: str
    title: str
    occurred_at: datetime
    summary: str | None = None
    astronaut_id: str | None = None
    context: str = "operations"
    simulation_id: str | None = None
    data_origin: str = "simulated"
    measurements: dict[str, Any] = field(default_factory=dict)
    explanation: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    confidence_level: str | None = None
    uncertainty: list[str] = field(default_factory=list)
    event_id: str | None = None


def rule_description(rec: AlertRecord) -> str:
    if rec.category == "rhythm":
        return "Beat-interval irregularity in the synthetic ECG sustained over consecutive samples."
    if rec.category == "baseline":
        return ("Personal-baseline deviation: |z| >= 4 against this crew member's expected value for the current "
                "activity, sustained for 20 samples.")
    rule = next((r for r in THRESHOLD_RULES if r.key == rec.rule_key), None)
    if rule is None:
        return "Prototype threshold rule."
    word = "above" if rule.direction == "high" else "below"
    return (f"{rule.title}: value {word} the activity-aware limit (caution {rule.caution:g}, critical "
            f"{rule.critical:g} {rule.unit} at rest) for 5 consecutive samples.")


def rule_spec(rec: AlertRecord, *, context: str = "operations", simulation_id: str | None = None,
              data_origin: str = "simulated", name: str | None = None) -> AlertSpec:
    who = f"{name or rec.astronaut_id}: " if rec.astronaut_id else ""
    tag = "[SIM] " if context == "simulation" else ""
    return AlertSpec(
        source=RULE_SOURCE, source_ref=rec.id, category="crew_physiology", classification="rule_detection",
        severity=rec.severity, title=f"{tag}{who}{rec.title}"[:200], summary=rec.message, occurred_at=rec.opened_at,
        astronaut_id=rec.astronaut_id, context=context, simulation_id=simulation_id, data_origin=data_origin,
        measurements={
            "metric": rec.metric, "unit": rec.unit, "direction": rec.direction, "trigger_value": rec.trigger_value,
            "threshold_value": rec.threshold_value, "peak_value": rec.peak_value, "activity_state": rec.activity_state,
            "rule_key": rec.rule_key, "rule_category": rec.category, "injected_scenario": rec.scenario,
            "data_category": "simulated",
        },
        explanation={"kind": "rule", "rule": rule_description(rec), "what_changed": rec.message,
                     "method": "Deterministic, activity-aware prototype rule (app/detection/rules.py)."},
        confidence=None, confidence_level="deterministic",
        uncertainty=["Values are simulated sensor readings with modelled noise.",
                     "Limits are prototype software settings, not clinical criteria."],
    )


def alert_view(row: MissionAlertRow) -> dict[str, Any]:
    return {
        "id": row.id, "source": row.source, "source_label": SOURCE_LABELS.get(row.source, row.source),
        "source_ref": row.source_ref, "event_id": row.event_id, "astronaut_id": row.astronaut_id,
        "context": row.context, "simulation_id": row.simulation_id, "data_origin": row.data_origin,
        "data_origin_label": ORIGIN_LABELS.get(row.data_origin, row.data_origin),
        "category": row.category, "category_label": CATEGORY_LABELS.get(row.category, row.category),
        "classification": row.classification,
        "classification_label": CLASSIFICATION_LABELS.get(row.classification, row.classification),
        "classification_note": CLASSIFICATION_NOTES.get(row.classification, ""),
        "experimental": row.classification == "experimental_ai",
        "severity": row.severity, "priority": row.priority, "priority_label": PRIORITY_LABELS[row.priority],
        "title": row.title, "summary": row.summary, "status": row.status,
        "created_at": row.created_at, "updated_at": row.updated_at, "received_at": row.received_at,
        "measurements": row.measurements or {}, "explanation": row.explanation or {},
        "confidence": row.confidence, "confidence_level": row.confidence_level, "uncertainty": row.uncertainty or [],
        "correlations": row.correlations or {}, "condition_cleared_at": row.condition_cleared_at,
        "acknowledged_at": row.acknowledged_at, "acknowledged_by": row.acknowledged_by, "ack_note": row.ack_note,
        "resolved_at": row.resolved_at, "resolved_by": row.resolved_by, "resolution_notes": row.resolution_notes,
        "occurrences": row.occurrences, "data_source": "simulated" if row.data_origin != "nasa" else "nasa",
    }


def action_view(row: MissionAlertActionRow) -> dict[str, Any]:
    return {"id": row.id, "alert_id": row.alert_id, "ts": row.ts, "action": row.action, "from_status": row.from_status,
            "to_status": row.to_status, "actor": row.actor, "actor_role": row.actor_role, "note": row.note,
            "detail": row.detail or {}}


class AlertCenter:
    def __init__(self, factory: async_sessionmaker[AsyncSession], hub) -> None:
        self.factory = factory
        self.hub = hub
        self._lock = asyncio.Lock()
        # Owners of alerts whose lifecycle lives elsewhere: (source, context) -> delegate.
        self.delegates: dict[tuple[str, str], Delegate] = {}
        # Operator attribution for transitions that come back through the monitor's change hook.
        self._pending_actor: dict[tuple[str, str], tuple[str, str | None, str | None]] = {}
        self.listeners: list[Callable[[str, dict[str, Any]], None]] = []

    # --------------------------------------------------------------- internals ----
    def _record(self, session: AsyncSession, row: MissionAlertRow, action: str, *, frm: str | None, to: str | None,
                actor: str = "system", role: str | None = None, note: str | None = None,
                detail: dict[str, Any] | None = None, ts: datetime | None = None) -> None:
        session.add(MissionAlertActionRow(alert_id=row.id, ts=ts or utcnow(), action=action, from_status=frm,
                                          to_status=to, actor=actor[:64], actor_role=role, note=note,
                                          detail=jsonable(detail or {})))

    async def _broadcast(self, kind: str, row: MissionAlertRow) -> None:
        view = alert_view(row)
        for listener in self.listeners:
            try:
                listener(kind, view)
            except Exception:
                logger.exception("alert listener failed")
        if self.hub is None or self.hub.count == 0:
            return
        from app.schemas.mission_control import MissionAlert, WsMissionAlert

        try:
            msg = WsMissionAlert(event=kind, alert=MissionAlert.model_validate(view))  # type: ignore[arg-type]
            await self.hub.broadcast(msg.model_dump_json())
        except Exception:
            logger.exception("could not broadcast mission alert %s", row.id)

    async def _find(self, session: AsyncSession, source: str, source_ref: str) -> MissionAlertRow | None:
        stmt = select(MissionAlertRow).where(MissionAlertRow.source == source, MissionAlertRow.source_ref == source_ref)
        return (await session.scalars(stmt)).first()

    # ------------------------------------------------------------ raise/update ----
    async def raise_alert(self, spec: AlertSpec) -> tuple[MissionAlertRow, bool]:
        """Open a new alert for (source, source_ref), or update the open one. Returns (row, created).

        A resolved alert is never reopened: a producer that sees the condition again uses a new
        source_ref, so each episode keeps its own lifecycle.
        """
        experimental = spec.classification == "experimental_ai"
        severity = cap_ai_severity(spec.severity) if experimental else spec.severity
        now = utcnow()
        kind = None
        async with self._lock, self.factory() as session:
            row = await self._find(session, spec.source, spec.source_ref)
            if row is None:
                level, score = priority_for(severity, spec.classification, astronaut_specific=bool(spec.astronaut_id))
                row = MissionAlertRow(
                    id=new_id("AL"), source=spec.source, source_ref=spec.source_ref, event_id=spec.event_id,
                    astronaut_id=spec.astronaut_id, context=spec.context, simulation_id=spec.simulation_id,
                    data_origin=spec.data_origin, category=spec.category, classification=spec.classification,
                    severity=severity, priority=level, title=spec.title[:200], summary=spec.summary, status="open",
                    created_at=as_utc(spec.occurred_at), updated_at=now, received_at=now,
                    measurements=jsonable(spec.measurements), explanation=jsonable(spec.explanation),
                    confidence=spec.confidence, confidence_level=spec.confidence_level,
                    uncertainty=jsonable(spec.uncertainty), correlations={},
                    occurrences=1,
                )
                session.add(row)
                await session.flush()
                self._record(session, row, "created", frm=None, to="open",
                             detail={"severity": severity, "priority": level, "priority_score": score})
                kind = "opened"
            elif row.status != "resolved":
                row.occurrences += 1
                row.updated_at = now
                row.measurements = {**(row.measurements or {}), **jsonable(spec.measurements)}
                if spec.explanation:
                    row.explanation = jsonable(spec.explanation)
                if spec.confidence is not None:
                    row.confidence, row.confidence_level = spec.confidence, spec.confidence_level
                if spec.uncertainty:
                    row.uncertainty = jsonable(spec.uncertainty)
                if row.condition_cleared_at is not None:
                    row.condition_cleared_at = None
                    self._record(session, row, "recurred", frm=row.status, to=row.status)
                    kind = kind or "updated"
                if SEVERITY_RANK[severity] > SEVERITY_RANK[row.severity]:
                    frm = row.status
                    row.severity = severity
                    row.priority, _ = priority_for(severity, row.classification,
                                                   astronaut_specific=bool(row.astronaut_id), escalated=True)
                    row.title = spec.title[:200]
                    row.summary = spec.summary or row.summary
                    row.status = "open"  # escalation re-activates an acknowledged alert
                    self._record(session, row, "escalated", frm=frm, to="open",
                                 detail={"severity": severity, "priority": row.priority})
                    kind = "escalated"
            await session.commit()
        if kind:
            await self._broadcast(kind, row)
        return row, kind == "opened"

    async def mark_cleared(self, source: str, source_ref: str, ts: datetime | None = None) -> MissionAlertRow | None:
        """The producer reports the condition is no longer present. The alert stays open for an operator."""
        async with self._lock, self.factory() as session:
            row = await self._find(session, source, source_ref)
            if row is None or row.status == "resolved" or row.condition_cleared_at is not None:
                return row
            row.condition_cleared_at = as_utc(ts or utcnow())
            row.updated_at = utcnow()
            self._record(session, row, "condition_cleared", frm=row.status, to=row.status)
            await session.commit()
        await self._broadcast("updated", row)
        return row

    async def set_links(self, alert_id: str, *, event_id: str | None = None,
                        correlations: dict[str, Any] | None = None) -> None:
        async with self._lock, self.factory() as session:
            row = await session.get(MissionAlertRow, alert_id)
            if row is None:
                return
            if event_id and not row.event_id:
                row.event_id = event_id
            if correlations is not None:
                row.correlations = jsonable(correlations)
            await session.commit()

    # ----------------------------------------------------------- rule mirroring ----
    async def mirror_rule_alert(self, kind: str, rec: AlertRecord, *, context: str = "operations",
                                simulation_id: str | None = None, data_origin: str = "simulated",
                                name: str | None = None) -> MissionAlertRow | None:
        """Apply one lifecycle change of a phase 2 (or sandbox) rule alert to its mirror."""
        spec = rule_spec(rec, context=context, simulation_id=simulation_id, data_origin=data_origin, name=name)
        if kind in ("opened", "escalated", "recurred"):
            row, _ = await self.raise_alert(spec)
            return await self._sync_status(rec, row.id)
        if kind == "cleared":
            async with self.factory() as session:
                exists = await self._find(session, RULE_SOURCE, rec.id)
            if exists is None:
                await self.raise_alert(spec)
            return await self.mark_cleared(RULE_SOURCE, rec.id, rec.condition_cleared_at)
        if kind in ("acknowledged", "resolved"):
            async with self.factory() as session:
                exists = await self._find(session, RULE_SOURCE, rec.id)
            if exists is None:
                await self.raise_alert(spec)
            async with self.factory() as session:
                row = await self._find(session, RULE_SOURCE, rec.id)
            return await self._sync_status(rec, row.id) if row else None
        return None

    async def _sync_status(self, rec: AlertRecord, alert_id: str) -> MissionAlertRow | None:
        """Bring the mirror's status and timestamps in line with the authoritative rule alert."""
        target = STATUS_FROM_RULE.get(rec.status, "open")
        kind = None
        async with self._lock, self.factory() as session:
            row = await session.get(MissionAlertRow, alert_id)
            if row is None:
                return None
            if row.status != target and not (row.status == "open" and target == "open"):
                frm = row.status
                actor, role, note = self._pending_actor.pop((rec.id, target), ("operator (rule alert API)", None, None))
                row.status = target
                row.updated_at = utcnow()
                if target in ("acknowledged", "resolved"):
                    row.acknowledged_at = rec.acknowledged_at or row.acknowledged_at or utcnow()
                    row.acknowledged_by = row.acknowledged_by or actor
                    if target == "acknowledged":
                        row.ack_note = note or rec.operator_note
                if target == "resolved":
                    row.resolved_at = rec.resolved_at or utcnow()
                    row.resolved_by = actor
                    row.resolution_notes = note or rec.operator_note
                self._record(session, row, "acknowledged" if target == "acknowledged" else
                             "resolved" if target == "resolved" else "reopened",
                             frm=frm, to=target, actor=actor, role=role, note=note or rec.operator_note)
                kind = target if target in ("acknowledged", "resolved") else "updated"
            if rec.condition_cleared_at and row.condition_cleared_at is None:
                row.condition_cleared_at = rec.condition_cleared_at
            await session.commit()
        if kind:
            await self._broadcast(kind, row)
        return row

    # ---------------------------------------------------------- operator actions ----
    async def act(self, alert_id: str, action: str, *, actor: str, role: str | None, note: str | None) -> MissionAlertRow:
        """Acknowledge or resolve. Resolution needs notes. Owned alerts go through their owner first."""
        note = (note or "").strip()[:MAX_NOTE] or None
        if action not in ("acknowledge", "resolve"):
            raise ConflictError(f"Unknown action {action}.")
        if action == "resolve" and not note:
            raise ConflictError("Resolution notes are required to resolve an alert.")
        async with self.factory() as session:
            row = await session.get(MissionAlertRow, alert_id)
        if row is None:
            raise NotFoundError(f"Alert {alert_id} not found.")
        if row.status == "resolved":
            raise ConflictError("This alert is already resolved.")
        if action == "acknowledge" and row.status == "acknowledged":
            raise ConflictError("This alert is already acknowledged.")
        target = "acknowledged" if action == "acknowledge" else "resolved"
        delegate = self.delegates.get((row.source, row.context))
        if delegate is not None:
            self._pending_actor[(row.source_ref, target)] = (actor, role, note)
            try:
                await delegate(row.source_ref, action, note)
            except NotFoundError:
                # The owner no longer knows the record (e.g. a sandbox run that was reset):
                # the alert centre still records the operator's decision.
                self._pending_actor.pop((row.source_ref, target), None)
            except Exception:
                self._pending_actor.pop((row.source_ref, target), None)
                raise
        now = utcnow()
        kind = None
        async with self._lock, self.factory() as session:
            row = await session.get(MissionAlertRow, alert_id)
            assert row is not None
            if row.status != target:
                self._pending_actor.pop((row.source_ref, target), None)
                frm = row.status
                row.status = target
                row.updated_at = now
                if target == "acknowledged":
                    row.acknowledged_at, row.acknowledged_by, row.ack_note = now, actor, note
                else:
                    if row.acknowledged_at is None:
                        row.acknowledged_at, row.acknowledged_by = now, actor
                    row.resolved_at, row.resolved_by, row.resolution_notes = now, actor, note
                self._record(session, row, target, frm=frm, to=target, actor=actor, role=role, note=note, ts=now)
                kind = target
            await session.commit()
        if kind:
            await self._broadcast(kind, row)
        return row

    async def act_on_rule_alert(self, rule_alert_id: str, action: str, *, actor: str, role: str | None,
                                note: str | None, monitor) -> Any:
        """Phase 2 ``/api/alerts/{id}/acknowledge|resolve``: same path, with operator attribution."""
        target = "acknowledged" if action == "acknowledge" else "resolved"
        self._pending_actor[(rule_alert_id, target)] = (actor, role, (note or "").strip() or None)
        try:
            result = await monitor.update_alert(rule_alert_id, action, note)
        except Exception:
            self._pending_actor.pop((rule_alert_id, target), None)
            raise
        record = monitor.evaluator.find(rule_alert_id)
        if record is None:
            from app.repositories import alerts as alerts_repo

            async with self.factory() as session:
                stored = await alerts_repo.get(session, rule_alert_id)
            record = alerts_repo.row_to_record(stored) if stored else None
        if record is not None:
            await self.mirror_rule_alert(target, record)
        return result

    # -------------------------------------------------------------------- read ----
    async def get(self, alert_id: str) -> tuple[MissionAlertRow, list[MissionAlertActionRow]]:
        async with self.factory() as session:
            row = await session.get(MissionAlertRow, alert_id)
            if row is None:
                raise NotFoundError(f"Alert {alert_id} not found.")
            actions = list((await session.scalars(
                select(MissionAlertActionRow).where(MissionAlertActionRow.alert_id == alert_id)
                .order_by(MissionAlertActionRow.ts, MissionAlertActionRow.id))).all())
        return row, actions

    async def find_by_ref(self, source: str, source_ref: str) -> MissionAlertRow | None:
        async with self.factory() as session:
            return await self._find(session, source, source_ref)

    async def list(
        self,
        *,
        statuses: list[str] | None = None,
        priorities: list[int] | None = None,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        classifications: list[str] | None = None,
        astronaut_id: str | None = None,
        context: str | None = None,
        simulation_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[MissionAlertRow]:
        stmt = select(MissionAlertRow)
        if statuses:
            stmt = stmt.where(MissionAlertRow.status.in_(statuses))
        if priorities:
            stmt = stmt.where(MissionAlertRow.priority.in_(priorities))
        if sources:
            stmt = stmt.where(MissionAlertRow.source.in_(sources))
        if categories:
            stmt = stmt.where(MissionAlertRow.category.in_(categories))
        if classifications:
            stmt = stmt.where(MissionAlertRow.classification.in_(classifications))
        if astronaut_id:
            stmt = stmt.where(MissionAlertRow.astronaut_id == astronaut_id)
        if context:
            stmt = stmt.where(MissionAlertRow.context == context)
        if simulation_id:
            stmt = stmt.where(MissionAlertRow.simulation_id == simulation_id)
        if since:
            # Open alerts always show, however old; closed ones only inside the window.
            stmt = stmt.where((MissionAlertRow.status != "resolved") | (MissionAlertRow.created_at >= as_utc(since)))
        order = case((MissionAlertRow.status == "open", 0), (MissionAlertRow.status == "acknowledged", 1), else_=2)
        stmt = stmt.order_by(order, MissionAlertRow.priority, MissionAlertRow.created_at.desc()).limit(limit)
        async with self.factory() as session:
            return list((await session.scalars(stmt)).all())

    async def summary(self, context: str | None = "operations", simulation_id: str | None = None) -> dict[str, Any]:
        now = utcnow()
        async with self.factory() as session:
            base = select(MissionAlertRow.priority, MissionAlertRow.status, MissionAlertRow.source,
                          MissionAlertRow.classification, MissionAlertRow.created_at, MissionAlertRow.acknowledged_at,
                          MissionAlertRow.resolved_at)
            if context:
                base = base.where(MissionAlertRow.context == context)
            if simulation_id:
                base = base.where(MissionAlertRow.simulation_id == simulation_id)
            open_rows = (await session.execute(base.where(MissionAlertRow.status != "resolved"))).all()
            recent = (await session.execute(base.where(MissionAlertRow.created_at >= now - timedelta(days=7)))).all()
            resolved_24h = await session.scalar(
                select(func.count()).select_from(MissionAlertRow).where(
                    MissionAlertRow.status == "resolved", MissionAlertRow.resolved_at >= now - timedelta(hours=24),
                    *( [MissionAlertRow.context == context] if context else []),
                    *( [MissionAlertRow.simulation_id == simulation_id] if simulation_id else [])))
        by_priority = {str(p): 0 for p in (1, 2, 3, 4)}
        by_source: dict[str, int] = {}
        experimental_open = 0
        for p, _status, src, cls, *_ in open_rows:
            by_priority[str(p)] += 1
            by_source[src] = by_source.get(src, 0) + 1
            experimental_open += cls == "experimental_ai"
        ack_minutes = [((a - c).total_seconds() / 60) for *_, c, a, _ in recent if a is not None and a >= c]
        oldest = min((r[4] for r in open_rows), default=None)
        return {
            "open": sum(1 for r in open_rows if r[1] == "open"),
            "acknowledged": sum(1 for r in open_rows if r[1] == "acknowledged"),
            "unresolved": len(open_rows),
            "resolved_24h": int(resolved_24h or 0),
            "by_priority": by_priority,
            "by_source": by_source,
            "experimental_open": experimental_open,
            "oldest_unresolved_at": oldest,
            "mean_minutes_to_acknowledge_7d": round(sum(ack_minutes) / len(ack_minutes), 1) if ack_minutes else None,
            "context": context,
        }
