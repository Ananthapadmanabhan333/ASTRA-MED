"""Create, review and export incident reports.

A report freezes the decision-support packet (or, without an alert, the measurements around a
time) into ``content`` with a SHA-256 digest, so later reads can show whether the stored snapshot
is intact. Review status moves through draft -> pending_review -> under_review -> reviewed ->
closed; every change is kept in ``review_history`` (and in the audit log).
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.db.models import EmergencyRunRow, IncidentReportRow
from app.medical import DECISION_SUPPORT_DISCLAIMER
from app.medical.decision import packet
from app.repositories import alerts as alerts_repo
from app.repositories import vitals as vitals_repo
from app.security.rbac import Principal
from app.services.mission import mission_status
from app.services.monitoring import MonitoringService
from app.twin import summary as S
from app.twin.stages import stage_for

STATUSES = ("draft", "pending_review", "under_review", "reviewed", "closed")
STATUS_LABELS = {"draft": "Draft", "pending_review": "Pending review", "under_review": "Under review",
                 "reviewed": "Reviewed", "closed": "Closed"}
# Which status changes need which permission. Medical sign-off is reserved for reports:review.
TRANSITIONS: dict[tuple[str, str], str] = {
    ("draft", "pending_review"): "reports:write",
    ("pending_review", "draft"): "reports:write",
    ("pending_review", "under_review"): "reports:review",
    ("under_review", "reviewed"): "reports:review",
    ("under_review", "pending_review"): "reports:review",
    ("reviewed", "closed"): "reports:review",
    ("reviewed", "under_review"): "reports:review",
    ("closed", "under_review"): "reports:review",
}
STANDARD_LIMITATIONS = [
    "All crew data in ASTRA-MED is simulated; crew members are fictional.",
    "Alert limits and statistical bands are prototype software settings, not clinical criteria.",
    "AI models were trained and evaluated on simulated data only and are not clinically validated.",
    "NASA space-weather data is real but is context only; it is never converted into a crew dose.",
    "This report supports, and does not replace, review by qualified medical personnel.",
]


def canonical(content: dict[str, Any]) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def digest(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return as_utc(obj).isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump(mode="json"))
    return obj


class ReportService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], monitor: MonitoringService, ai, multisystem) -> None:
        self.factory = factory
        self.monitor = monitor
        self.ai = ai
        self.multisystem = multisystem

    async def _measurements_around(self, session: AsyncSession, aid: str, ts: datetime) -> dict[str, Any]:
        cols = ("heart_rate", "spo2", "respiratory_rate", "temperature_c", "systolic", "diastolic", "activity_state", "scenario")
        rows = await vitals_repo.fetch_range(session, aid, ts - timedelta(minutes=30), ts + timedelta(minutes=15), cols)
        df = S.frame(rows, ("ts", *cols))
        return {"window": {"start": ts - timedelta(minutes=30), "end": ts + timedelta(minutes=15)},
                "summary": S.summarize_metrics(df), "samples": len(df), "data_category": "simulated"}

    async def create(self, principal: Principal, *, alert_id: str | None, run_id: str | None,
                     astronaut_id: str | None, occurred_at: datetime | None, title: str | None,
                     summary: str | None) -> IncidentReportRow:
        now = utcnow()
        async with self.factory() as session:
            record = None
            run = None
            if alert_id:
                record = self.monitor.evaluator.find(alert_id)
                if record is None:
                    row = await alerts_repo.get(session, alert_id)
                    if row is None:
                        raise NotFoundError(f"Alert {alert_id} not found.")
                    record = alerts_repo.row_to_record(row)
                astronaut_id = record.astronaut_id
                occurred_at = record.opened_at
            if run_id:
                run = await session.get(EmergencyRunRow, run_id)
                if run is None:
                    raise NotFoundError(f"Emergency run {run_id} not found.")
                astronaut_id = astronaut_id or run.astronaut_id
                occurred_at = occurred_at or run.started_at
            if not astronaut_id or astronaut_id not in self.monitor.engine.profiles:
                raise ConflictError("A report needs an alert, a single-crew-member run, or an astronaut_id.")
            occurred_at = as_utc(occurred_at or now)
            profile = self.monitor.engine.profiles[astronaut_id]
            status = mission_status(self.monitor, now)
            mission_day = (occurred_at.date() - self.monitor.settings.mission_start_date).days

            pk = await packet(session, self.monitor, self.ai, self.multisystem, record, now) if record else None
            ms = await self.multisystem.assess(session, astronaut_id, now, use_cache=False)
            measurements = pk["measurements"] if pk else await self._measurements_around(session, astronaut_id, occurred_at)

            content = _jsonable({
                "schema_version": 1,
                "label": "SIMULATED DATA - fictional crew member, software test environment",
                "mission": {"name": status.mission_name, "phase": status.phase, "mission_start": status.mission_start,
                            "mission_day": mission_day, "stage": stage_for(mission_day).label},
                "astronaut": {"id": profile.id, "name": profile.name, "role": profile.role, "age": profile.age,
                              "sex": profile.sex, "fictional": True},
                "timestamp": {"occurred_at": occurred_at, "report_created_at": now, "timezone": "UTC"},
                "summary": summary or (pk["observation"]["summary"] if pk else None),
                "source": {"alert_id": alert_id, "run_id": run_id,
                           "run": None if run is None else {"label": run.label, "severity": run.severity,
                                                            "started_at": run.started_at, "ends_at": run.ends_at,
                                                            "analyses": (run.analyses or [])[-1:]}},
                "observation": pk["observation"] if pk else None,
                "measurements": measurements,
                "baseline_comparison": pk["baseline_comparison"] if pk else {
                    "available": True, "features": [f for s in ms["systems"] for f in s["features"]],
                    "method": "Multisystem engine inputs at report time", "data_category": "derived"},
                "environment": pk["environmental_context"] if pk else {"habitat": ms.get("habitat")},
                "anomaly_results": {
                    "ai_output": pk["ai_output"] if pk else None,
                    "multisystem": {"summary": ms["summary"],
                                    "systems": [{"key": s["key"], "label": s["label"], "status": s["status"],
                                                 "explanation": s["explanation"]} for s in ms["systems"]],
                                    "patterns": ms["patterns"], "ai": ms.get("ai")},
                },
                "model_explanation": {
                    "rule": (pk or {}).get("ai_output", {}).get("rule"),
                    "kind": (pk or {}).get("ai_output", {}).get("kind"),
                    "what_changed": (pk or {}).get("ai_output", {}).get("what_changed"),
                    "model_version": (pk or {}).get("ai_output", {}).get("model_version") or (ms.get("ai") or {}).get("model_version"),
                    "confidence": (pk or {}).get("confidence_uncertainty", {}).get("confidence"),
                    "uncertainty": (pk or {}).get("confidence_uncertainty", {}).get("sources", []),
                },
                "data_quality": {"packet": pk["data_quality"] if pk else None,
                                 "multisystem": ms["data_quality"], "limitations": STANDARD_LIMITATIONS},
                "review_workflow": pk["review_workflow"] if pk else None,
                "disclaimer": DECISION_SUPPORT_DISCLAIMER,
            })
            report = IncidentReportRow(
                id=uuid.uuid4().hex[:16],
                title=(title or (pk["observation"]["title"] if pk else (run.label if run else "Health event")))[:200],
                astronaut_id=astronaut_id, alert_id=alert_id, run_id=run_id, occurred_at=occurred_at,
                created_at=now, updated_at=now, created_by=principal.username, review_status="draft",
                review_history=[{"ts": now.isoformat(), "by": principal.username, "role": principal.role,
                                 "from": None, "to": "draft", "note": "Report created"}],
                content=content, content_sha256=digest(content),
            )
            session.add(report)
            await session.commit()
            return report

    async def list(self, astronaut_id: str | None, status: str | None, limit: int) -> list[IncidentReportRow]:
        stmt = select(IncidentReportRow).order_by(IncidentReportRow.created_at.desc()).limit(limit)
        if astronaut_id:
            stmt = stmt.where(IncidentReportRow.astronaut_id == astronaut_id)
        if status:
            stmt = stmt.where(IncidentReportRow.review_status == status)
        async with self.factory() as session:
            return list((await session.scalars(stmt)).all())

    async def get(self, report_id: str) -> IncidentReportRow:
        async with self.factory() as session:
            row = await session.get(IncidentReportRow, report_id)
        if row is None:
            raise NotFoundError(f"Report {report_id} not found.")
        return row

    async def review(self, report_id: str, principal: Principal, to: str, note: str | None) -> IncidentReportRow:
        async with self.factory() as session:
            row = await session.get(IncidentReportRow, report_id)
            if row is None:
                raise NotFoundError(f"Report {report_id} not found.")
            frm = row.review_status
            needed = TRANSITIONS.get((frm, to))
            if needed is None:
                allowed = [t for (f, t) in TRANSITIONS if f == frm]
                raise ConflictError(f"Cannot move a report from {STATUS_LABELS[frm]} to {STATUS_LABELS.get(to, to)}.",
                                    details={"allowed": allowed})
            if not principal.can(needed):
                raise ForbiddenError(f"Moving to {STATUS_LABELS[to]} needs the {needed} permission.",
                                     details={"reason": "permission", "required": [needed]})
            if to == "reviewed" and not (note and note.strip()):
                raise ConflictError("A reviewer note is required to mark a report as reviewed.")
            now = datetime.now(UTC)
            row.review_status = to
            row.updated_at = now
            row.review_history = [*row.review_history, {"ts": now.isoformat(), "by": principal.username,
                                                        "role": principal.role, "from": frm, "to": to,
                                                        "note": (note or "").strip()[:2000] or None}]
            await session.commit()
            return row


def report_view(row: IncidentReportRow, include_content: bool = True) -> dict[str, Any]:
    intact = digest(row.content) == row.content_sha256
    out = {
        "id": row.id, "title": row.title, "astronaut_id": row.astronaut_id,
        "astronaut_name": (row.content.get("astronaut") or {}).get("name"), "alert_id": row.alert_id,
        "run_id": row.run_id, "occurred_at": row.occurred_at, "created_at": row.created_at,
        "updated_at": row.updated_at, "created_by": row.created_by, "review_status": row.review_status,
        "review_status_label": STATUS_LABELS[row.review_status], "review_history": row.review_history,
        "content_sha256": row.content_sha256, "integrity": "intact" if intact else "modified",
        "severity": ((row.content.get("observation") or {}).get("severity")), "data_source": "simulated",
    }
    if include_content:
        out["content"] = row.content
    return out
