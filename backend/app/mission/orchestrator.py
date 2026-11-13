"""Mission event orchestration: producers -> one queue -> normalise, prioritise, de-duplicate, store, broadcast.

Producers
---------
* **Physiological monitoring** (phase 2): the monitor's change hook enqueues every alert lifecycle
  change and every scenario start/end. Rule alerts are mirrored into the alert centre.
* **AI anomaly detection and forecasting** (phase 3): a periodic sweep reads each crew member's
  risk assessment (anomaly ensemble, forecast crossings, deviations) and the live baseline
  deviations. Findings become *experimental* events and alerts (never critical, at most P3).
* **NASA space weather** (phase 4): a periodic scan turns newly stored DONKI events into events;
  radiation-relevant ones younger than ``mission_space_alert_hours`` also raise alerts.
* **Environmental monitoring**: the simulated habitat atmosphere and dose rate, checked every few
  seconds; a deviation opens an alert and its return to nominal clears it.
* **Emergency simulations and incident reports** (phase 5): change hooks on both services.

Collectors run independently and record their health (last run, last error), so one failing
source (NASA unreachable, models untrained) never stops the others. Alerts with a crew member are
correlated with what else was happening: injected test scenarios, the habitat, the dose rate,
nearby real NASA events (temporal proximity only) and related mission events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.timeutil import as_utc, utcnow
from app.db.models import SpaceWeatherEventRow
from app.detection.evaluator import AlertRecord
from app.mission.alerts import RULE_SOURCE, AlertCenter, AlertSpec
from app.mission.events import EventInput, MissionEventService, event_view
from app.services.mission import _habitat_dose_multiplier
from app.simulator.habitat import habitat_at
from app.simulator.scenarios import ActiveScenario, Scenario

logger = logging.getLogger("astra.mission.orchestrator")

ENV_ADVISORY_SIGMA = 4.0
ENV_CAUTION_SIGMA = 8.0
ENV_NOMINAL_SIGMA = 2.5
DOSE_ALERT_MULTIPLIER = 5.0
ANOMALY_MIN_MINUTES = 10
CORRELATION_WINDOW_H = 48
SPACE_FIRST_SCAN_DAYS = 7

DONKI_CATEGORY = {"SEP": "radiation", "RBE": "radiation"}
SCENARIO_CATEGORY = {Scenario.SOLAR_PARTICLE_EVENT: "radiation", Scenario.HABITAT_ATMOSPHERE: "environment"}


@dataclass
class Collector:
    name: str
    label: str
    interval_s: float | None = None
    runs: int = 0
    failures: int = 0
    last_run_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None
    last_duration_ms: float | None = None
    state: str = "idle"  # idle | ok | degraded | unavailable | disabled
    detail: dict[str, Any] = field(default_factory=dict)

    def view(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in ("name", "label", "interval_s", "runs", "failures", "last_run_at",
                                              "last_ok_at", "last_error", "last_duration_ms", "state", "detail")}


class MissionOrchestrator:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession], monitor, ai, space,
                 events: MissionEventService, alerts: AlertCenter) -> None:
        self.settings = settings
        self.factory = factory
        self.monitor = monitor
        self.ai = ai
        self.space = space
        self.events = events
        self.alerts = alerts
        self.queue: asyncio.Queue[tuple[str, Any, datetime]] = asyncio.Queue(maxsize=10_000)
        self.processed = 0
        self.dropped = 0
        self.errors = 0
        self.last_error: str | None = None
        self._tasks: list[asyncio.Task] = []
        self.collectors = {
            "monitor": Collector("monitor", "Physiological monitoring hook"),
            "ai": Collector("ai", "AI sweep (anomaly, forecast, risk)", settings.mission_ai_sweep_seconds),
            "space": Collector("space", "NASA space-weather scan", settings.mission_space_scan_seconds),
            "environment": Collector("environment", "Habitat environment and dose rate", settings.mission_env_check_seconds),
            "emergency": Collector("emergency", "Emergency simulator hook"),
            "reports": Collector("reports", "Incident report hook"),
        }
        # AI sweep cache per crew member: what the crew monitoring view shows between sweeps.
        self.ai_snapshot: dict[str, dict[str, Any]] = {}
        self._ai_episodes: dict[tuple[str, str], str] = {}  # (astronaut, kind) -> episode ref
        self._risk_category: dict[str, str] = {}
        self._env_episode: str | None = None
        self._env_peak: str | None = None
        self._dose_episode: str | None = None
        self._last_swx_id: int | None = None

    # ------------------------------------------------------------- lifecycle ----
    def attach(self, emergency=None, reports=None) -> None:
        self.monitor.listeners.append(self._on_monitor)
        if emergency is not None:
            emergency.listeners.append(self._on_emergency)
        if reports is not None:
            reports.listeners.append(self._on_report)

    def start(self) -> None:
        self._tasks.append(asyncio.create_task(self._consume(), name="astra-mission-consumer"))
        if self.settings.mission_orchestrator_enabled:
            self._tasks.append(asyncio.create_task(self._every("ai", self.ai_sweep), name="astra-mission-ai"))
            if self.space is not None:
                self._tasks.append(asyncio.create_task(self._every("space", self.space_scan), name="astra-mission-space"))
            else:
                self.collectors["space"].state = "disabled"
            self._tasks.append(asyncio.create_task(self._every("environment", self.environment_check),
                                                   name="astra-mission-env"))
        else:
            for key in ("ai", "space", "environment"):
                self.collectors[key].state = "disabled"

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()

    async def drain(self, timeout: float = 10.0) -> None:
        """Wait until every queued change has been processed (tests, shutdown)."""
        if not any(t.get_name() == "astra-mission-consumer" and not t.done() for t in self._tasks):
            while not self.queue.empty():
                await self._process(*self.queue.get_nowait())
                self.queue.task_done()
            return
        await asyncio.wait_for(self.queue.join(), timeout)

    def status(self) -> dict[str, Any]:
        return {
            "running": any(not t.done() for t in self._tasks),
            "queue_depth": self.queue.qsize(), "processed": self.processed, "dropped": self.dropped,
            "errors": self.errors, "last_error": self.last_error,
            "events": dict(self.events.counters),
            "collectors": [c.view() for c in self.collectors.values()],
        }

    # ----------------------------------------------------------------- hooks ----
    def _enqueue(self, topic: str, payload: Any) -> None:
        try:
            self.queue.put_nowait((topic, payload, utcnow()))
        except asyncio.QueueFull:
            self.dropped += 1
            logger.error("mission event queue full; dropped a %s change", topic)

    def _on_monitor(self, topic: str, payload: Any) -> None:
        self._enqueue(topic, payload)

    def _on_emergency(self, kind: str, run, extra: dict[str, Any]) -> None:
        self._enqueue("emergency", (kind, {"id": run.id, "label": run.label, "scenario": run.scenario,
                                           "astronaut_id": run.astronaut_id, "severity": run.severity,
                                           "started_at": run.started_at, "ends_at": run.ends_at,
                                           "cancelled_at": run.cancelled_at, "created_by": run.created_by}, extra))

    def _on_report(self, kind: str, row) -> None:
        content = row.content or {}
        self._enqueue("report", (kind, {"id": row.id, "title": row.title, "astronaut_id": row.astronaut_id,
                                        "occurred_at": row.occurred_at, "created_by": row.created_by,
                                        "review_status": row.review_status,
                                        "severity": (content.get("observation") or {}).get("severity"),
                                        "simulation_id": (content.get("source") or {}).get("simulation_id")}))

    # ------------------------------------------------------------- consumer ----
    async def _consume(self) -> None:
        while True:
            topic, payload, at = await self.queue.get()
            try:
                await self._process(topic, payload, at)
            finally:
                self.queue.task_done()

    async def _process(self, topic: str, payload: Any, at: datetime) -> None:
        collector = self.collectors["emergency" if topic == "emergency" else "reports" if topic == "report" else "monitor"]
        started = time.perf_counter()
        collector.runs += 1
        collector.last_run_at = utcnow()
        try:
            if topic == "alert":
                await self.handle_rule_alert(*payload)
            elif topic == "scenario":
                await self.handle_scenario(*payload)
            elif topic == "emergency":
                await self.handle_emergency(*payload)
            elif topic == "report":
                await self.handle_report(*payload)
            collector.last_ok_at, collector.state, collector.last_error = utcnow(), "ok", None
        except Exception as exc:
            self.errors += 1
            collector.failures += 1
            collector.state = "degraded"
            collector.last_error = self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            logger.exception("could not process %s change", topic)
        finally:
            self.processed += 1
            collector.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)

    def _name(self, aid: str | None) -> str:
        if not aid:
            return "Crew"
        profile = self.monitor.engine.profiles.get(aid)
        return profile.name if profile else aid

    # ---------------------------------------------------------- rule alerts ----
    async def handle_rule_alert(self, kind: str, rec: AlertRecord) -> None:
        name = self._name(rec.astronaut_id)
        row = await self.alerts.mirror_rule_alert(kind, rec, name=name)
        severity = rec.severity if kind in ("opened", "escalated", "recurred") else "info"
        verb = {"opened": "opened", "escalated": f"escalated to {rec.severity}", "cleared": "condition cleared",
                "recurred": "condition recurred", "acknowledged": "acknowledged", "resolved": "resolved"}[kind]
        ts = {"opened": rec.opened_at, "cleared": rec.condition_cleared_at, "acknowledged": rec.acknowledged_at,
              "resolved": rec.resolved_at}.get(kind) or rec.updated_at
        ev, created = await self.events.publish(EventInput(
            source=RULE_SOURCE, kind=f"alert_{kind}", category="crew_physiology", severity=severity,
            title=f"{name}: {rec.title} ({verb})", summary=rec.message, occurred_at=ts,
            astronaut_id=rec.astronaut_id, ref_type="rule_alert", ref_id=rec.id,
            payload={"alert_center_id": row.id if row else None, "metric": rec.metric, "unit": rec.unit,
                     "trigger_value": rec.trigger_value, "peak_value": rec.peak_value,
                     "threshold_value": rec.threshold_value, "rule_severity": rec.severity,
                     "activity_state": rec.activity_state, "injected_scenario": rec.scenario},
        ))
        if row is not None and kind == "opened":
            correlations = await self.correlate(rec.astronaut_id, rec.opened_at)
            await self.alerts.set_links(row.id, event_id=ev.id, correlations=correlations)

    # ------------------------------------------------------------- scenarios ----
    async def handle_scenario(self, kind: str, s: ActiveScenario) -> None:
        spec = s.spec
        category = SCENARIO_CATEGORY.get(s.scenario, "simulation")
        target = self._name(s.astronaut_id) if s.astronaut_id else "whole crew"
        who = "Operator test scenario" if s.triggered_by == "operator" else "Simulator episode"
        severity = "info"
        if kind == "started" and category in ("radiation", "environment"):
            severity = "caution" if category == "radiation" else "advisory"
        ts = s.started_at if kind == "started" else (s.cancelled_at or s.ends_at)
        await self.events.publish(EventInput(
            source="emergency_simulation" if s.triggered_by == "operator" else RULE_SOURCE,
            kind=f"scenario_{kind}", category=category, severity=severity,
            title=f"{who} {kind}: {spec.label} ({target})",
            summary=spec.description, occurred_at=ts, astronaut_id=s.astronaut_id,
            classification="simulation_scenario", ref_type="scenario", ref_id=s.id,
            payload={"scenario": s.scenario.value, "intensity": s.intensity, "triggered_by": s.triggered_by,
                     "starts_at": s.started_at.isoformat(), "ends_at": s.ends_at.isoformat()},
        ))
        if s.scenario == Scenario.SOLAR_PARTICLE_EVENT:
            ref = f"spe:{s.id}"
            if kind == "started":
                await self.alerts.raise_alert(AlertSpec(
                    source="environment_monitoring", source_ref=ref, category="radiation",
                    classification="simulated_environment", severity="caution",
                    title=f"Simulated solar particle event: habitat dose rate up to x{spec.dose_rate_multiplier:g}",
                    summary="The simulator raised the habitat dose rate for the whole crew. Simulated values only.",
                    occurred_at=s.started_at, measurements={"dose_rate_multiplier": spec.dose_rate_multiplier,
                                                            "intensity": s.intensity, "data_category": "simulated"},
                    explanation={"kind": "rule", "rule": "Any simulated solar particle event opens a radiation alert.",
                                 "method": "Simulator scenario catalogue (app/simulator/scenarios.py)."},
                    confidence_level="deterministic",
                    uncertainty=["Dose rates come from the simulator's radiation model, not a dosimeter."]))
            else:
                await self.alerts.mark_cleared("environment_monitoring", ref, ts)

    # ------------------------------------------------------------- emergency ----
    async def handle_emergency(self, kind: str, run: dict[str, Any], extra: dict[str, Any]) -> None:
        target = self._name(run["astronaut_id"]) if run["astronaut_id"] else "whole crew"
        title = {"started": f"Emergency simulation started: {run['label']} ({target}, {run['severity']})",
                 "cancelled": f"Emergency simulation cancelled: {run['label']} ({target})",
                 "analyzed": f"Emergency simulation analysed: {run['label']} ({target})"}[kind]
        summary = None
        if kind == "analyzed" and extra.get("escalations"):
            summary = "Escalation levels: " + ", ".join(f"{self._name(a)} {lvl}" for a, lvl in extra["escalations"].items())
        await self.events.publish(EventInput(
            source="emergency_simulation", kind=f"emergency_{kind}", category="simulation",
            severity="advisory" if kind == "started" else "info", title=title, summary=summary,
            occurred_at=run["started_at"] if kind == "started" else utcnow(), astronaut_id=run["astronaut_id"],
            classification="simulation_scenario", ref_type="emergency_run",
            ref_id=run["id"] if kind != "analyzed" else f"{run['id']}:{utcnow().isoformat()}",
            payload={"run_id": run["id"], "scenario": run["scenario"], "severity": run["severity"],
                     "created_by": run["created_by"], **extra},
        ))

    # --------------------------------------------------------------- reports ----
    async def handle_report(self, kind: str, rep: dict[str, Any]) -> None:
        sandbox = bool(rep.get("simulation_id"))
        await self.events.publish(EventInput(
            source="incident_reports", kind=f"report_{kind}", category="medical_incident",
            severity=(rep.get("severity") or "advisory") if kind == "created" else "info",
            title=(f"Incident report created: {rep['title']}" if kind == "created"
                   else f"Incident report {rep['review_status'].replace('_', ' ')}: {rep['title']}"),
            occurred_at=rep["occurred_at"] if kind == "created" else utcnow(), astronaut_id=rep["astronaut_id"],
            context="simulation" if sandbox else "operations", simulation_id=rep.get("simulation_id"),
            data_origin="sandbox" if sandbox else "simulated",
            ref_type="incident_report", ref_id=rep["id"] if kind == "created" else f"{rep['id']}:{rep['review_status']}",
            payload={"report_id": rep["id"], "review_status": rep["review_status"], "created_by": rep["created_by"]},
        ))

    # ------------------------------------------------------------ correlation ----
    async def correlate(self, astronaut_id: str | None, ts: datetime, *, context: str = "operations",
                        simulation_id: str | None = None, scenarios: list[ActiveScenario] | None = None,
                        habitat: dict[str, Any] | None = None, nasa_ts: datetime | None = None) -> dict[str, Any]:
        """What else was happening around an alert. Only injected scenarios are known causes."""
        ts = as_utc(ts)
        if scenarios is None:
            scenarios = [s for s in self.monitor.engine.scenarios.values()
                         if (astronaut_id is None or s.affects(astronaut_id)) and s.started_at <= ts <= s.effective_end]
        if habitat is None:
            habitat = habitat_at(ts, [s for s in self.monitor.engine.scenarios.values() if s.is_active(ts)])
        params = habitat.get("parameters", {})
        worst = max(params.values(), key=lambda p: abs(p["deviation_sigma"]), default=None)
        out: dict[str, Any] = {
            "at": ts,
            "injected_scenarios": [{"id": s.id, "scenario": s.scenario.value, "label": s.spec.label,
                                    "triggered_by": s.triggered_by, "intensity": s.intensity,
                                    "started_at": s.started_at, "ends_at": s.ends_at} for s in scenarios],
            "habitat": None if worst is None else {
                "parameter": worst["label"], "value": worst["value"], "unit": worst["unit"],
                "deviation_sigma": worst["deviation_sigma"], "category": "simulated"},
            "dose_rate_multiplier": round(_habitat_dose_multiplier(self.monitor, ts), 2) if context == "operations" else None,
            "space_weather": None,
            "related_events": [],
            "notes": [],
        }
        if scenarios:
            out["notes"].append("An injected test scenario was active: it is the known cause of the simulated values.")
        if self.space is not None:
            try:
                from app.space.timeline import nearby_events

                async with self.factory() as session:
                    near = await nearby_events(session, as_utc(nasa_ts or ts), CORRELATION_WINDOW_H)
                out["space_weather"] = {"window_hours": CORRELATION_WINDOW_H, "events": near["events"][:6],
                                        "note": near["note"], "category": "indicator"}
            except Exception as exc:
                out["notes"].append(f"NASA space-weather context unavailable: {type(exc).__name__}")
        related = await self.events.list(astronaut_id=astronaut_id, context=context, simulation_id=simulation_id,
                                         start=ts - timedelta(minutes=30), end=ts + timedelta(minutes=5), limit=12)
        out["related_events"] = [{k: v for k, v in event_view(r).items()
                                  if k in ("id", "title", "category", "severity", "occurred_at", "source")}
                                 for r in related]
        out["method"] = ("Temporal co-occurrence within the window. Injected scenarios are ground truth for simulated "
                         "data; NASA events are real but closeness in time is not evidence of a causal link.")
        return out

    # ------------------------------------------------------------- collectors ----
    async def _every(self, name: str, fn) -> None:
        c = self.collectors[name]
        interval = c.interval_s or 60.0
        await asyncio.sleep(min(5.0, interval))  # let start-up work (model load, first sync) begin first
        while True:
            started = time.perf_counter()
            c.runs += 1
            c.last_run_at = utcnow()
            try:
                result = await fn()
                c.last_ok_at = utcnow()
                c.state = (result or {}).get("state", "ok")
                c.detail = (result or {}).get("detail", {})
                c.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # graceful degradation: record, back off, keep the other collectors going
                c.failures += 1
                c.state = "degraded"
                c.last_error = f"{type(exc).__name__}: {exc}"[:300]
                logger.warning("collector %s failed: %s", name, c.last_error)
            c.last_duration_ms = round((time.perf_counter() - started) * 1000, 1)
            backoff = min(4.0, 1.0 + c.failures * 0.5) if c.state == "degraded" else 1.0
            await asyncio.sleep(interval * backoff)

    # ---- AI sweep
    async def ai_sweep(self) -> dict[str, Any]:
        bundle = await self.ai.bundle()
        detail: dict[str, Any] = {"model_version": bundle.version if bundle else None, "crew": {}}
        for aid in self.monitor.engine.profiles:
            snap: dict[str, Any] = {"generated_at": utcnow(), "risk": None, "deviations": None, "error": None}
            try:
                snap["deviations"] = await self.ai.current_deviations(aid, self.monitor.latest_reading(aid))
            except ApiError as exc:
                snap["error"] = exc.message
            if bundle is not None:
                try:
                    risk = await self.ai.risk(aid)
                    snap["risk"] = {k: risk[k] for k in ("risk_score", "category", "category_label", "health_score",
                                                          "model_version", "generated_at")} | {
                        "warnings": risk["warnings"][:4], "anomaly": risk["anomaly"],
                        "confidence": risk["explanation"]["confidence"],
                        "what_changed": risk["explanation"]["what_changed"],
                        "contributors": risk["explanation"]["contributors"][:4]}
                    await self._ai_findings(aid, risk)
                except ApiError as exc:
                    snap["error"] = exc.message
            self.ai_snapshot[aid] = snap
            detail["crew"][aid] = snap["risk"]["category"] if snap["risk"] else snap["error"]
        if bundle is None:
            return {"state": "unavailable", "detail": {**detail, "reason": "No trained model version is loaded."}}
        return {"state": "ok", "detail": detail}

    async def _ai_findings(self, aid: str, risk: dict[str, Any], *, context: str = "operations",
                           simulation_id: str | None = None, now: datetime | None = None,
                           episodes: dict | None = None, categories: dict | None = None) -> None:
        """Turn one risk assessment into experimental events and alerts (shared with the sandbox)."""
        now = now or utcnow()
        name = ("[SIM] " if context == "simulation" else "") + self._name(aid)
        origin = "sandbox" if context == "simulation" else "simulated"
        conf = risk["explanation"]["confidence"]
        uncertainty = [*conf.get("basis", []), *risk.get("limitations", [])]
        episode_store = self._ai_episodes if episodes is None else episodes
        cat_store = self._risk_category if categories is None else categories

        def episode(kind: str, active: bool) -> str | None:
            key = (aid, kind)
            if not active:
                return episode_store.pop(key, None)
            if key not in episode_store:
                episode_store[key] = f"{kind}:{aid}:{now.strftime('%Y%m%dT%H%M%S')}" + (f":{simulation_id}" if simulation_id else "")
            return episode_store[key]

        # Anomaly ensemble: a flagged pattern that persisted.
        anomaly = risk.get("anomaly") or {}
        flagged = bool(anomaly.get("available")) and (anomaly.get("flagged_minutes") or 0) >= ANOMALY_MIN_MINUTES
        ref = episode("anomaly", flagged)
        if flagged and ref:
            kind_text = (anomaly.get("kind") or "multivariate pattern").replace("_", " ")
            title = f"{name}: AI anomaly pattern ({kind_text}) - experimental"
            ev, _ = await self.events.publish(EventInput(
                source="anomaly_detection", kind="anomaly_detected", category="ai_prediction", severity="advisory",
                title=title, summary=(f"{anomaly.get('votes')} of {anomaly.get('n_detectors')} detectors flag the recent "
                                      f"windows ({anomaly.get('score')}x threshold) for {anomaly.get('flagged_minutes')} min."),
                occurred_at=now - timedelta(minutes=anomaly.get("flagged_minutes") or 0), astronaut_id=aid,
                context=context, simulation_id=simulation_id, data_origin=origin, classification="experimental_ai",
                experimental=True, confidence=conf.get("score"), ref_type="ai_episode", ref_id=ref,
                payload={"anomaly": anomaly, "model_version": risk.get("model_version")},
            ))
            row, created = await self.alerts.raise_alert(AlertSpec(
                source="anomaly_detection", source_ref=ref, category="ai_prediction",
                classification="experimental_ai", severity="caution" if (anomaly.get("score") or 0) >= 2 else "advisory",
                title=title, summary=ev.summary, occurred_at=ev.occurred_at, astronaut_id=aid, context=context,
                simulation_id=simulation_id, data_origin=origin, event_id=ev.id,
                measurements={"ensemble_score": anomaly.get("score"), "votes": anomaly.get("votes"),
                              "detectors": anomaly.get("n_detectors"), "flagged_minutes": anomaly.get("flagged_minutes"),
                              "contributors": risk["explanation"]["contributors"][:4], "data_category": "derived"},
                explanation={"kind": "anomaly", "what_changed": risk["explanation"]["what_changed"],
                             "method": "Calibrated ensemble of anomaly detectors on 5-minute windows (phase 3).",
                             "warnings": [w for w in risk["warnings"] if w["source"] == "anomaly"][:2],
                             "model_version": risk.get("model_version")},
                confidence=conf.get("score"), confidence_level=conf.get("level"), uncertainty=uncertainty,
            ))
            if created and context == "operations":
                await self.alerts.set_links(row.id, correlations=await self.correlate(aid, now))
        elif ref:  # episode ended
            await self.alerts.mark_cleared("anomaly_detection", ref, now)

        # Forecast crossings: a caution limit likely reached within the forecast horizon.
        trend = [w for w in risk.get("warnings", []) if w["source"] == "trend" and "reaches" in w["title"]]
        ref = episode("forecast", bool(trend))
        if trend and ref:
            w = trend[0]
            title = f"{name}: {w['title']} - experimental forecast"
            ev, _ = await self.events.publish(EventInput(
                source="predictive_forecast", kind="forecast_crossing", category="ai_prediction", severity="advisory",
                title=title, summary=w["detail"], occurred_at=now, astronaut_id=aid, context=context,
                simulation_id=simulation_id, data_origin=origin, classification="experimental_ai", experimental=True,
                confidence=conf.get("score"), ref_type="ai_episode", ref_id=ref, payload={"warning": w},
            ))
            await self.alerts.raise_alert(AlertSpec(
                source="predictive_forecast", source_ref=ref, category="ai_prediction", classification="experimental_ai",
                severity="advisory", title=title, summary=w["detail"], occurred_at=now, astronaut_id=aid,
                context=context, simulation_id=simulation_id, data_origin=origin, event_id=ev.id,
                measurements={"signals": w.get("signals"), "points": w.get("points"), "data_category": "derived"},
                explanation={"kind": "forecast", "what_changed": w["detail"],
                             "method": "Phase 3 forecaster with split-conformal 90% intervals.",
                             "model_version": risk.get("model_version")},
                confidence=conf.get("score"), confidence_level=conf.get("level"),
                uncertainty=["Forecast intervals are calibrated on simulated test data.", *uncertainty],
            ))
        elif ref:
            await self.alerts.mark_cleared("predictive_forecast", ref, now)

        # Risk category transitions; a high concern also raises an (experimental) alert.
        category = risk["category"]
        before = cat_store.get(aid)
        cat_store[aid] = category
        if before is not None and before != category:
            await self.events.publish(EventInput(
                source="predictive_forecast", kind="risk_category_changed", category="ai_prediction",
                severity="advisory" if category in ("moderate_concern", "high_concern") else "info",
                title=f"{name}: AI risk {before.replace('_', ' ')} -> {category.replace('_', ' ')} (experimental)",
                summary=risk["explanation"]["what_changed"], occurred_at=now, astronaut_id=aid, context=context,
                simulation_id=simulation_id, data_origin=origin, classification="experimental_ai", experimental=True,
                confidence=conf.get("score"), dedupe_key=f"{before}->{category}",
                payload={"risk_score": risk["risk_score"], "from": before, "to": category},
            ))
        ref = episode("risk", category == "high_concern")
        if category == "high_concern" and ref:
            await self.alerts.raise_alert(AlertSpec(
                source="predictive_forecast", source_ref=ref, category="ai_prediction", classification="experimental_ai",
                severity="caution", title=f"{name}: AI risk assessment high concern ({risk['risk_score']:.0f}/100) - experimental",
                summary=risk["explanation"]["what_changed"], occurred_at=now, astronaut_id=aid, context=context,
                simulation_id=simulation_id, data_origin=origin,
                measurements={"risk_score": risk["risk_score"], "health_score": risk["health_score"],
                              "warnings": [{k: w[k] for k in ("title", "detail", "source", "points")} for w in risk["warnings"][:5]],
                              "data_category": "derived"},
                explanation={"kind": "risk", "what_changed": risk["explanation"]["what_changed"],
                             "method": risk["explanation"]["method"], "contributors": risk["explanation"]["contributors"][:5],
                             "model_version": risk.get("model_version")},
                confidence=conf.get("score"), confidence_level=conf.get("level"), uncertainty=uncertainty,
            ))
        elif ref:
            await self.alerts.mark_cleared("predictive_forecast", ref, now)

    # ---- NASA space weather
    async def space_scan(self) -> dict[str, Any]:
        from app.space import donki
        from app.space.intel import VANTAGE_NOTE, alert_for

        now = utcnow()
        stmt = select(SpaceWeatherEventRow).order_by(SpaceWeatherEventRow.id).limit(1000)
        if self._last_swx_id is None:
            stmt = stmt.where(SpaceWeatherEventRow.start_time >= now - timedelta(days=SPACE_FIRST_SCAN_DAYS))
        else:
            stmt = stmt.where(SpaceWeatherEventRow.id > self._last_swx_id)
        async with self.factory() as session:
            rows = list((await session.scalars(stmt)).all())
            if self._last_swx_id is None:
                newest = await session.scalar(select(SpaceWeatherEventRow.id).order_by(SpaceWeatherEventRow.id.desc()).limit(1))
                self._last_swx_id = newest or 0
        new_events = alerts = 0
        for e in rows:
            if e.event_type == "WSA":
                continue
            self._last_swx_id = max(self._last_swx_id or 0, e.id)
            a = alert_for(e)
            label = donki.EVENT_TYPES.get(e.event_type, e.event_type)
            when = e.peak_time or e.start_time
            category = DONKI_CATEGORY.get(e.event_type, "solar_activity")
            ev, created = await self.events.publish(EventInput(
                source="space_weather", kind=f"donki_{e.event_type.lower()}", category=category,
                severity=a["severity"] if a else "info",
                title=f"{label}{' ' + e.scale if e.scale else ''}{': ' + e.classification if e.classification else ''}"[:200],
                summary=(e.description or "")[:500] or None, occurred_at=when, data_origin="nasa",
                classification="environmental_indicator", ref_type="donki", ref_id=str(e.id),
                payload={"event_type": e.event_type, "scale": e.scale, "severity_level": e.severity,
                         "magnitude": e.magnitude, "magnitude_unit": e.magnitude_unit, "link": e.link,
                         "model_derived": e.model_derived, "rule": a["rule"] if a else None, "external_id": e.external_id},
            ))
            new_events += created
            if a and now - when <= timedelta(hours=self.settings.mission_space_alert_hours):
                _, opened = await self.alerts.raise_alert(AlertSpec(
                    source="space_weather", source_ref=f"donki:{e.id}", category=category,
                    classification="environmental_indicator", severity=a["severity"], title=ev.title, summary=a["note"],
                    occurred_at=when, data_origin="nasa", event_id=ev.id,
                    measurements={"event_type": e.event_type, "classification": e.classification, "scale": e.scale,
                                  "magnitude": e.magnitude, "magnitude_unit": e.magnitude_unit,
                                  "data_category": "indicator", "link": e.link},
                    explanation={"kind": "rule", "rule": a["rule"], "what_changed": ev.title,
                                 "method": "Prototype rules for radiation-relevant DONKI events (app/space/intel.py)."},
                    confidence_level="source-reported",
                    uncertainty=[VANTAGE_NOTE, "DONKI entries can be revised; the newest stored version is shown."],
                ))
                alerts += opened
        return {"state": "ok", "detail": {"scanned": len(rows), "new_events": new_events, "new_alerts": alerts,
                                          "last_event_id": self._last_swx_id}}

    # ---- habitat environment and dose rate
    async def environment_check(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utcnow()
        active = self.monitor.active_scenarios(now)
        habitat = habitat_at(now, active)
        params = habitat["parameters"]
        key, worst = max(params.items(), key=lambda kv: abs(kv[1]["deviation_sigma"]))
        sigma = abs(worst["deviation_sigma"])
        if sigma >= ENV_ADVISORY_SIGMA:
            severity = "caution" if sigma >= ENV_CAUTION_SIGMA else "advisory"
            if self._env_episode is None:
                self._env_episode = f"habitat:{habitat.get('anomaly_scenario_id') or now.strftime('%Y%m%dT%H%M%S')}"
                self._env_peak = None
            title = f"Simulated habitat {worst['label']} {worst['value']} {worst['unit']} ({worst['deviation_sigma']:+.1f} sigma)"
            if self._env_peak != severity:
                self._env_peak = severity
                ev, _ = await self.events.publish(EventInput(
                    source="environment_monitoring", kind="environment_anomaly", category="environment",
                    severity=severity, title=title, summary=habitat["note"], occurred_at=now,
                    classification="simulated_environment", ref_type="habitat_episode",
                    ref_id=f"{self._env_episode}:{severity}",
                    payload={"parameters": params, "anomaly_scenario_id": habitat.get("anomaly_scenario_id")},
                ))
                await self.alerts.raise_alert(AlertSpec(
                    source="environment_monitoring", source_ref=self._env_episode, category="environment",
                    classification="simulated_environment", severity=severity, title=title, summary=habitat["note"],
                    occurred_at=now, event_id=ev.id,
                    measurements={k: {"value": p["value"], "unit": p["unit"], "nominal": p["nominal"],
                                      "deviation_sigma": p["deviation_sigma"]} for k, p in params.items()}
                    | {"data_category": "simulated"},
                    explanation={"kind": "rule", "rule": f"Advisory at {ENV_ADVISORY_SIGMA:g} sigma, caution at "
                                                         f"{ENV_CAUTION_SIGMA:g} sigma from the simulator's nominal level.",
                                 "method": "Simulated habitat model (app/simulator/habitat.py)."},
                    confidence_level="deterministic",
                    uncertainty=["Nominal levels and variation are simulator settings, not safety limits."]))
        elif sigma < ENV_NOMINAL_SIGMA and self._env_episode is not None:
            await self.events.publish(EventInput(
                source="environment_monitoring", kind="environment_nominal", category="environment", severity="info",
                title="Simulated habitat atmosphere back near nominal", occurred_at=now,
                classification="simulated_environment", ref_type="habitat_episode", ref_id=f"{self._env_episode}:nominal",
            ))
            await self.alerts.mark_cleared("environment_monitoring", self._env_episode, now)
            self._env_episode = self._env_peak = None

        multiplier = _habitat_dose_multiplier(self.monitor, now)
        if multiplier >= DOSE_ALERT_MULTIPLIER and self._dose_episode is None:
            self._dose_episode = f"dose:{now.strftime('%Y%m%dT%H%M%S')}"
            await self.events.publish(EventInput(
                source="environment_monitoring", kind="dose_rate_elevated", category="radiation", severity="caution",
                title=f"Simulated habitat dose rate x{multiplier:.0f} above the galactic background", occurred_at=now,
                classification="simulated_environment", ref_type="dose_episode", ref_id=self._dose_episode,
                payload={"multiplier": round(multiplier, 2)},
            ))
        elif multiplier < 1.5 and self._dose_episode is not None:
            await self.events.publish(EventInput(
                source="environment_monitoring", kind="dose_rate_nominal", category="radiation", severity="info",
                title="Simulated habitat dose rate back to background", occurred_at=now,
                classification="simulated_environment", ref_type="dose_episode", ref_id=f"{self._dose_episode}:end",
            ))
            self._dose_episode = None
        return {"state": "ok", "detail": {"max_deviation_sigma": round(sigma, 2), "parameter": key,
                                          "dose_rate_multiplier": round(multiplier, 2),
                                          "environment_alert_open": self._env_episode is not None}}
