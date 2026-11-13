"""Runs, analysis snapshots and timelines for the emergency scenario simulator."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ApiError, ConflictError, NotFoundError
from app.core.timeutil import utcnow
from app.db.models import AlertRow, EmergencyRunRow, SimulationEventRow
from app.emergency import SIMULATION_LABEL
from app.emergency.catalogue import CATALOGUE, SEVERITY_INTENSITY
from app.medical.decision import SIGNIFICANT, escalation_for, load_workflow
from app.repositories import vitals as vitals_repo
from app.schemas.ai import AnomalyDetectionRequest
from app.services.monitoring import MonitoringService
from app.simulator.habitat import habitat_at
from app.simulator.radiation import GCR_DOSE_RATE_MSV_PER_DAY
from app.simulator.scenarios import ActiveScenario
from app.twin.service import TwinService

logger = logging.getLogger("astra.emergency")

TIMELINE_SIGNALS = ("heart_rate", "spo2", "respiratory_rate", "temperature_c", "systolic", "diastolic")
LEAD_IN = timedelta(minutes=5)
MAX_ANALYSES = 10


def run_status(run: EmergencyRunRow, now: datetime) -> str:
    if run.cancelled_at is not None:
        return "cancelled"
    return "running" if now < run.ends_at else "completed"


class EmergencyService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], monitor: MonitoringService, ai, twin: TwinService,
                 multisystem) -> None:
        self.factory = factory
        self.monitor = monitor
        self.ai = ai
        self.twin = twin
        self.multisystem = multisystem
        self._overlays: dict[str, tuple[datetime, dict[str, Any]]] = {}  # astronaut -> (ends_at, overlay)
        # Phase 6 change hooks: called with (kind, run, extra) after a run starts, is cancelled or analysed.
        self.listeners: list = []

    def _emit(self, kind: str, run: EmergencyRunRow, extra: dict[str, Any] | None = None) -> None:
        for listener in self.listeners:
            try:
                listener(kind, run, extra or {})
            except Exception:
                logger.exception("emergency listener failed")

    # -------------------------------------------------------------- overlays ----
    def overlay_for(self, aid: str) -> dict[str, Any] | None:
        """Sleep what-if overlay of a running sleep-disruption run, if any (used by multisystem)."""
        hit = self._overlays.get(aid)
        if hit is None:
            return None
        ends, overlay = hit
        if utcnow() >= ends:
            self._overlays.pop(aid, None)
            return None
        return overlay

    async def _sleep_overlay(self, aid: str, nights: int, intensity: float) -> dict[str, Any]:
        days = [d for d in await self.twin.days(aid, utcnow().date() - timedelta(days=nights + 2)) if d.sleep and d.complete]
        chosen = days[-nights:]
        out = {}
        for d in chosen:
            s = d.sleep
            out[d.day.isoformat()] = {
                **s,
                "duration_hours": round(max(3.0, s["duration_hours"] * (1 - 0.3 * intensity)), 2),
                "efficiency_pct": round(max(60.0, s["efficiency_pct"] - 12 * intensity), 1),
                "original_duration_hours": s["duration_hours"], "original_efficiency_pct": s["efficiency_pct"],
                "basis": "what-if overlay",
            }
        return {"type": "sleep", "nights": out, "category": "simulated",
                "note": "What-if overlay for this run only: stored sleep records are unchanged."}

    # ------------------------------------------------------------------ runs ----
    async def start(self, key: str, astronaut_id: str | None, severity: str, duration_s: int | None,
                    nights: int, created_by: str) -> EmergencyRunRow:
        spec = CATALOGUE.get(key)
        if spec is None:
            raise NotFoundError(f"Unknown emergency scenario {key}.")
        if not spec.crew_wide and not astronaut_id:
            raise ConflictError("This scenario needs an astronaut_id.")
        intensity = SEVERITY_INTENSITY[severity]
        duration = duration_s or spec.default_duration_s
        now = utcnow()
        components = [(scenario, round(min(1.5, max(0.3, intensity * factor)), 3)) for scenario, factor in spec.components]
        overlay: dict[str, Any] = {}
        if spec.overlay == "sleep" and astronaut_id:
            await self.twin.ensure(astronaut_id)
            overlay = await self._sleep_overlay(astronaut_id, nights, intensity)
        started = await self.monitor.start_scenario_group(components, None if spec.crew_wide else astronaut_id,
                                                          duration, now)
        if spec.overlay == "habitat":
            overlay = {"type": "habitat", "parameters": started[0].spec.habitat_effects, "intensity": started[0].intensity,
                       "category": "simulated"}
        run = EmergencyRunRow(
            id=uuid.uuid4().hex[:16], scenario=key, label=spec.label,
            astronaut_id=None if spec.crew_wide else astronaut_id, severity=severity, intensity=intensity,
            duration_s=duration, started_at=now, ends_at=now + timedelta(seconds=duration), created_by=created_by,
            components=[{"event_id": s.id, "scenario": s.scenario.value, "label": s.spec.label, "intensity": s.intensity,
                         "astronaut_id": s.astronaut_id} for s in started],
            overlay=overlay, analyses=[],
        )
        async with self.factory() as session:
            session.add(run)
            await session.commit()
        if overlay.get("type") == "sleep" and astronaut_id:
            self._overlays[astronaut_id] = (run.ends_at, overlay)
        logger.info("emergency run %s (%s, %s) started by %s", run.id, key, severity, created_by)
        self._emit("started", run)
        return run

    async def get(self, run_id: str) -> EmergencyRunRow:
        async with self.factory() as session:
            run = await session.get(EmergencyRunRow, run_id)
        if run is None:
            raise NotFoundError(f"Emergency run {run_id} not found.")
        return run

    async def list(self, hours: int, limit: int = 50) -> list[EmergencyRunRow]:
        async with self.factory() as session:
            return list((await session.scalars(
                select(EmergencyRunRow).where(EmergencyRunRow.started_at >= utcnow() - timedelta(hours=hours))
                .order_by(EmergencyRunRow.started_at.desc()).limit(limit))).all())

    async def cancel(self, run_id: str) -> EmergencyRunRow:
        now = utcnow()
        async with self.factory() as session:
            run = await session.get(EmergencyRunRow, run_id)
            if run is None:
                raise NotFoundError(f"Emergency run {run_id} not found.")
            if run_status(run, now) != "running":
                raise ConflictError("This run is not running.")
            for c in run.components:
                try:
                    await self.monitor.cancel_scenario(c["event_id"])
                except NotFoundError:
                    pass
            run.cancelled_at = now
            await session.commit()
        if run.astronaut_id:
            self._overlays.pop(run.astronaut_id, None)
        self._emit("cancelled", run)
        return run

    def targets(self, run: EmergencyRunRow) -> list[str]:
        return [run.astronaut_id] if run.astronaut_id else list(self.monitor.engine.profiles)

    def _scenarios(self, run: EmergencyRunRow) -> list[ActiveScenario]:
        found = [self.monitor.engine.scenarios.get(c["event_id"]) for c in run.components]
        return [s for s in found if s is not None]

    # -------------------------------------------------------------- analysis ----
    async def analyze(self, run_id: str, requested_by: str) -> dict[str, Any]:
        """Run the Phase 3 models, the multisystem engine and alert escalation over the run window."""
        run = await self.get(run_id)
        now = utcnow()
        window_start = run.started_at - LEAD_IN
        workflow = load_workflow()
        per_astronaut = []
        async with self.factory() as session:
            alerts = list((await session.scalars(select(AlertRow).where(
                AlertRow.opened_at >= run.started_at, AlertRow.opened_at <= max(now, run.ends_at),
                AlertRow.astronaut_id.in_(self.targets(run))).order_by(AlertRow.opened_at))).all())
            for aid in self.targets(run):
                entry: dict[str, Any] = {"astronaut_id": aid, "name": self.monitor.engine.profiles[aid].name}
                try:
                    det = await self.ai.detect(AnomalyDetectionRequest(astronaut_id=aid, start=window_start, end=now,
                                                                       include_explanations=False))
                    flagged = [t for t in det["timeline"] if t["flagged"]]
                    peak = max(det["timeline"], key=lambda t: t["ensemble_score"], default=None)
                    entry["anomaly"] = {
                        "available": True, "model_version": det["model_version"], "windows": len(det["timeline"]),
                        "flagged_windows": len(flagged), "detections": [
                            {k: d[k] for k in ("start", "end", "peak_score", "kind", "signals", "votes")}
                            for d in det["detections"]],
                        "peak": None if peak is None else {"ts": peak["ts"], "ensemble_score": peak["ensemble_score"],
                                                           "votes": peak["votes"], "top_signals": peak["top_signals"]},
                        "data_quality": det["data_quality"],
                    }
                except ApiError as exc:
                    entry["anomaly"] = {"available": False, "reason": exc.message}
                try:
                    risk = await self.ai.risk(aid)
                    entry["risk"] = {k: risk[k] for k in ("risk_score", "category", "category_label")} | {
                        "warnings": [{k: w[k] for k in ("title", "detail", "source")} for w in risk["warnings"][:5]]}
                except ApiError as exc:
                    entry["risk"] = {"available": False, "reason": exc.message}
                ms = await self.multisystem.assess(session, aid, now, use_cache=False)
                entry["systems"] = {s["key"]: s["status"] for s in ms["systems"]}
                entry["patterns"] = [{"key": p["key"], "label": p["label"], "evidence": p["evidence"]} for p in ms["patterns"]]
                entry["summary"] = ms["summary"]
                mine = [a for a in alerts if a.astronaut_id == aid]
                entry["alerts"] = [{"id": a.id, "title": a.title, "severity": a.severity, "opened_at": a.opened_at,
                                    "status": a.status,
                                    "escalation": escalation_for(a.severity, ms, workflow)["level"]} for a in mine]
                worst = max((a.severity for a in mine if a.severity in SIGNIFICANT),
                            key=lambda s: SIGNIFICANT.index(s), default=None)
                entry["escalation"] = escalation_for(worst or "advisory", ms, workflow)
                per_astronaut.append(entry)
            snapshot = {
                "id": uuid.uuid4().hex[:10], "ts": now, "requested_by": requested_by, "run_status": run_status(run, now),
                "window": {"start": window_start, "end": now}, "crew": per_astronaut, "label": SIMULATION_LABEL,
                "note": "Model outputs on simulated data. Escalation levels are review-process settings, not diagnoses.",
            }
            stored = await session.get(EmergencyRunRow, run_id)
            stored.analyses = [*(stored.analyses or []), _jsonable(snapshot)][-MAX_ANALYSES:]
            await session.commit()
        self._emit("analyzed", run, {"escalations": {c["astronaut_id"]: c["escalation"].get("level") for c in per_astronaut},
                                    "requested_by": requested_by})
        return snapshot

    # -------------------------------------------------------------- timeline ----
    async def timeline(self, run_id: str, astronaut_id: str | None = None) -> dict[str, Any]:
        run = await self.get(run_id)
        now = utcnow()
        aid = astronaut_id or run.astronaut_id or next(iter(self.monitor.engine.profiles))
        if aid not in self.targets(run):
            raise ConflictError("That crew member is not affected by this run.")
        start, end = run.started_at - LEAD_IN, min(now, (run.cancelled_at or run.ends_at) + LEAD_IN)
        async with self.factory() as session:
            rows = await vitals_repo.fetch_range(session, aid, start, end, columns=(*TIMELINE_SIGNALS, "scenario"))
            alerts = list((await session.scalars(select(AlertRow).where(
                AlertRow.astronaut_id == aid, AlertRow.opened_at >= start, AlertRow.opened_at <= end))).all())
            sims = list((await session.scalars(select(SimulationEventRow).where(
                SimulationEventRow.id.in_([c["event_id"] for c in run.components])))).all())
        step = max(1, len(rows) // 600)
        vitals = [{"ts": r[0], **{s: r[i + 1] for i, s in enumerate(TIMELINE_SIGNALS)}, "scenario": r[-1]}
                  for r in rows[::step]]
        events: list[dict[str, Any]] = [{"ts": run.started_at, "kind": "run_started", "label": f"{run.label} started ({run.severity})"}]
        for s in sims:
            events.append({"ts": s.started_at, "kind": "scenario_started", "label": f"Simulator scenario: {s.scenario}"})
        for a in alerts:
            events.append({"ts": a.opened_at, "kind": "alert_opened", "label": a.title, "severity": a.severity, "alert_id": a.id})
            if a.acknowledged_at:
                events.append({"ts": a.acknowledged_at, "kind": "alert_acknowledged", "label": a.title, "alert_id": a.id})
            if a.resolved_at:
                events.append({"ts": a.resolved_at, "kind": "alert_resolved", "label": a.title, "alert_id": a.id})
        for an in run.analyses or []:
            events.append({"ts": an["ts"], "kind": "analysis", "label": f"AI analysis by {an['requested_by']}",
                           "analysis_id": an["id"]})
        if run.cancelled_at:
            events.append({"ts": run.cancelled_at, "kind": "run_cancelled", "label": "Run cancelled"})
        elif run.ends_at <= now:
            events.append({"ts": run.ends_at, "kind": "run_completed", "label": "Run completed"})
        events.sort(key=lambda e: str(e["ts"]))

        environment = []
        scenarios = self._scenarios(run)
        if run.overlay.get("type") == "habitat" or run.scenario == "radiation_event":
            t = start
            while t <= end:
                point: dict[str, Any] = {"ts": t}
                if run.overlay.get("type") == "habitat":
                    h = habitat_at(t, scenarios)["parameters"]
                    point |= {k: v["value"] for k, v in h.items()}
                if run.scenario == "radiation_event":
                    mult = max([1.0] + [1 + (s.spec.dose_rate_multiplier - 1) * s.envelope(t) for s in scenarios])
                    point["dose_rate_msv_day"] = round(GCR_DOSE_RATE_MSV_PER_DAY * mult, 3)
                environment.append(point)
                t += timedelta(seconds=15)
        return {
            "run_id": run.id, "astronaut_id": aid, "start": start, "end": end, "status": run_status(run, now),
            "vitals": vitals, "events": events, "environment": environment, "overlay": run.overlay or None,
            "label": SIMULATION_LABEL, "data_source": "simulated",
        }


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def run_view(run: EmergencyRunRow, now: datetime) -> dict[str, Any]:
    return {
        "id": run.id, "scenario": run.scenario, "label": run.label, "astronaut_id": run.astronaut_id,
        "severity": run.severity, "intensity": run.intensity, "duration_s": run.duration_s,
        "started_at": run.started_at, "ends_at": run.ends_at, "cancelled_at": run.cancelled_at,
        "status": run_status(run, now), "created_by": run.created_by, "components": run.components,
        "overlay": run.overlay or None, "analyses": run.analyses or [], "label_simulated": SIMULATION_LABEL,
        "data_source": "simulated",
    }


def catalogue_view() -> list[dict[str, Any]]:
    out = []
    for e in CATALOGUE.values():
        out.append({
            "key": e.key, "label": e.label, "description": e.description, "crew_wide": e.crew_wide,
            "default_duration_s": e.default_duration_s, "overlay": e.overlay, "observe": list(e.observe),
            "components": [{"scenario": s.value, "factor": f} for s, f in e.components],
            "severities": [{"key": k, "intensity": v} for k, v in SEVERITY_INTENSITY.items()],
        })
    return out
