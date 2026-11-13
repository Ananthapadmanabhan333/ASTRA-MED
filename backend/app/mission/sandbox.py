"""Mission simulation sandbox: a complete, isolated demonstration mission.

Isolation
---------
A sandbox run owns a separate :class:`SimulationEngine` (selected crew, its own random stream, no
random events), a separate :class:`AlertEvaluator` and its own **simulation clock**. Its samples go
only to ``mission_sim_samples``; its events and alerts carry ``context="simulation"``,
``data_origin="sandbox"`` and the run id. It never writes ``vital_samples``, ``alerts`` or
``simulation_events``, so the live crew stream, the digital twin and the AI baselines are untouched.
A failure inside a run marks that run ``failed``; it cannot stop live monitoring.

Clock and speed
---------------
Every wall-clock tick the clock advances ``speed`` x tick seconds in engine steps of at most 10
simulated seconds (so the rule detector sees one sample per step). Pause freezes the clock;
the speed can change while running. A run ends when the clock reaches its planned length.

Pipeline
--------
generator (or external telemetry via the ingestion API) -> rule detection -> unified alerts and
events -> periodic AI analysis of the stream (phase 3 anomaly ensemble, forecast, risk) ->
correlation (injected scenarios, sandbox habitat, real NASA events near the wall-clock time) ->
incident report on request. Playback reads the stored run back at any resolution.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError, ConflictError, NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.db.models import MissionAlertRow, MissionEventRow, MissionSimSampleRow, MissionSimulationRow
from app.detection.baseline import BaselineDetector
from app.detection.evaluator import AlertEvaluator, AlertRecord
from app.mission.alerts import RULE_SOURCE, AlertCenter, AlertSpec, alert_view
from app.mission.events import EventInput, MissionEventService, event_view
from app.mission.presets import INJECTIONS, PRESETS
from app.simulator.engine import SimulationEngine, VitalReading
from app.simulator.habitat import habitat_at
from app.simulator.physiology import target_vitals
from app.simulator.profiles import CREW, CREW_BY_ID
from app.simulator.scenarios import ActiveScenario, Scenario
from app.simulator.schedule import activity_at

logger = logging.getLogger("astra.mission.sandbox")

STEP_CAP_S = 10.0
AI_FIRST_AFTER = timedelta(minutes=15)  # the ensemble needs a few 5-minute windows of stream data
SIGNAL_COLUMNS = ("heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate")
SAMPLE_COLUMNS = (*SIGNAL_COLUMNS, "activity_state", "activity_met", "rhythm", "hrv_rmssd_ms", "scenario")
ACTIVE = ("running", "paused")
SANDBOX_LABEL = "SIMULATION SANDBOX - fictional crew, software test mission; not live crew telemetry"


def _sample(r: VitalReading, source: str) -> dict[str, Any]:
    return {"astronaut_id": r.astronaut_id, "ts": r.ts, **{c: getattr(r, c) for c in SAMPLE_COLUMNS}, "source": source}


def _dose_multiplier(scenarios: list[ActiveScenario], t: datetime) -> float:
    m = 1.0
    for s in scenarios:
        m = max(m, 1 + (s.spec.dose_rate_multiplier - 1) * s.envelope(t))
    return m


@dataclass
class EnvWatch:
    """Habitat/dose-rate episode state for one context (shared logic with the operations collector)."""

    episode: str | None = None
    peak: str | None = None
    dose_episode: str | None = None


@dataclass
class SandboxRun:
    id: str
    name: str
    preset: str | None
    crew: list[str]
    speed: float
    seed: int
    sim_start: datetime
    sim_now: datetime
    sim_end: datetime
    created_by: str
    engine: SimulationEngine
    evaluator: AlertEvaluator
    status: str = "running"
    step_s: float = 1.0
    carry_s: float = 0.0
    script: list[dict[str, Any]] = field(default_factory=list)
    injections: list[dict[str, Any]] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)
    latest: dict[str, VitalReading] = field(default_factory=dict)
    dose_msv: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    stats: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    analyses: dict[str, Any] = field(default_factory=dict)
    ai_every: timedelta = timedelta(minutes=15)
    last_ai_at: datetime | None = None
    ai_status: str = "waiting"
    ai_task: asyncio.Task | None = None
    ai_episodes: dict = field(default_factory=dict)
    ai_categories: dict = field(default_factory=dict)
    env: EnvWatch = field(default_factory=EnvWatch)
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    error: str | None = None
    wall_started_at: datetime | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def scenario_by_id(self, sid: str) -> ActiveScenario | None:
        return self.engine.scenarios.get(sid)


class MissionSimulator:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession], hub, ai,
                 events: MissionEventService, alerts: AlertCenter, orchestrator, reports) -> None:
        self.settings = settings
        self.factory = factory
        self.hub = hub
        self.ai = ai
        self.events = events
        self.alerts = alerts
        self.orchestrator = orchestrator
        self.reports = reports
        self.run: SandboxRun | None = None
        alerts.delegates[(RULE_SOURCE, "simulation")] = self.update_alert

    # ================================================================ catalogue ====
    @staticmethod
    def presets() -> list[dict[str, Any]]:
        return [p.view() for p in PRESETS.values()]

    @staticmethod
    def injection_types() -> list[dict[str, Any]]:
        return [{"key": t.key, "kind": t.kind, "label": t.label, "description": t.description,
                 "crew_wide": t.crew_wide, "default_duration_s": t.default_duration_s,
                 "event_only": t.scenario is None} for t in INJECTIONS.values()]

    # ================================================================ lifecycle ====
    def _require_enabled(self) -> None:
        if not (self.settings.mission_sim_enabled and self.settings.simulation_control_enabled):
            from app.core.errors import ForbiddenError

            raise ForbiddenError("Mission simulation is disabled on this deployment.")

    def _active(self, run_id: str | None = None) -> SandboxRun:
        run = self.run
        if run is None or run.status not in ACTIVE or (run_id and run.id != run_id):
            raise ConflictError("No mission simulation is running." if run_id is None else
                                f"Simulation {run_id} is not the active run.")
        return run

    async def start(self, *, name: str | None, preset: str | None, crew: list[str] | None, speed: float | None,
                    duration_minutes: int | None, seed: int | None, ai_every_minutes: int | None,
                    created_by: str, autostart: bool = True) -> SandboxRun:
        self._require_enabled()
        if self.run is not None and self.run.status in ACTIVE:
            raise ConflictError("A mission simulation is already active. Pause, stop or reset it first.",
                                details={"simulation_id": self.run.id})
        p = PRESETS.get(preset) if preset else None
        if preset and p is None:
            raise NotFoundError(f"Unknown scenario preset {preset}.")
        crew = list(dict.fromkeys(crew or [c.id for c in CREW][: (p.crew_size if p else len(CREW))]))
        unknown = [c for c in crew if c not in CREW_BY_ID]
        if unknown or not crew:
            raise NotFoundError(f"Unknown crew member(s): {', '.join(unknown) or 'none selected'}.")
        speed = float(speed or (p.speed if p else 30))
        if not 0.5 <= speed <= self.settings.mission_sim_max_speed:
            raise ConflictError(f"Speed must be between 0.5 and {self.settings.mission_sim_max_speed:g}.")
        minutes = int(duration_minutes or (p.duration_minutes if p else 120))
        minutes = max(5, min(minutes, self.settings.mission_sim_max_minutes))
        seed = int(seed if seed is not None else uuid.uuid4().int % 1_000_000)
        now = utcnow().replace(microsecond=0)
        rid = uuid.uuid4().hex[:16]
        engine = SimulationEngine([CREW_BY_ID[c] for c in crew], seed=self.settings.simulator_seed,
                                  ecg_sample_rate_hz=self.settings.ecg_sample_rate_hz, random_events_per_hour=0,
                                  default_tick_seconds=1.0)
        import numpy as np

        engine.rng = np.random.default_rng(seed)  # schedules match the crew plan; noise is the run's own
        profiles = engine.profiles
        evaluator = AlertEvaluator(BaselineDetector(lambda aid, ts, st, met: target_vitals(profiles[aid], ts, st, met)))
        run = SandboxRun(
            id=rid, name=(name or (p.label if p else "Custom mission simulation"))[:120], preset=preset, crew=crew,
            speed=speed, seed=seed, sim_start=now, sim_now=now, sim_end=now + timedelta(minutes=minutes),
            created_by=created_by, engine=engine, evaluator=evaluator, wall_started_at=now,
            ai_every=timedelta(minutes=max(5, int(ai_every_minutes or 15))),
            config={"duration_minutes": minutes, "ai_every_minutes": max(5, int(ai_every_minutes or 15)),
                    "tick_seconds": self.settings.mission_sim_tick_seconds, "step_cap_s": STEP_CAP_S},
        )
        run.step_s = self._step_for(speed)
        engine.default_tick_seconds = run.step_s
        if p:
            for step in p.script:
                target = None if step.astronaut is None else crew[step.astronaut % len(crew)]
                run.script.append({"at": now + timedelta(minutes=step.at_minute), "injection": step.injection,
                                   "astronaut_id": target, "intensity": step.intensity,
                                   "duration_s": step.duration_s, "by": "script"})
        run.config["script"] = [{**s, "at": s["at"].isoformat()} for s in run.script]
        async with self.factory() as session:
            session.add(MissionSimulationRow(
                id=rid, name=run.name, preset=preset, crew=crew, status="running", speed=speed, seed=seed,
                sim_start=now, sim_time=now, sim_end=run.sim_end, wall_started_at=now, wall_updated_at=now,
                created_by=created_by, config=run.config, injections=[], analyses={}, stats={}))
            await session.commit()
        self.run = run
        # Prime the engine at t0 so the first broadcast already has readings.
        result = engine.step(now)
        for r in result.readings:
            run.latest[r.astronaut_id] = r
            run.pending.append(_sample(r, "generator"))
        await self._publish(run, "simulation_started", "info",
                            f"Mission simulation started: {run.name} ({len(crew)} crew, {speed:g}x)",
                            summary=f"Preset: {p.label if p else 'custom'}. Planned length {minutes} simulated minutes.",
                            occurred=now, ref=f"{rid}:start", payload={"crew": crew, "speed": speed, "preset": preset})
        await self._persist(run)
        if autostart:
            run.task = asyncio.create_task(self._loop(run), name=f"astra-sandbox-{rid}")
        await self._broadcast_state(run)
        logger.info("mission simulation %s started by %s (%s, %s crew, %gx)", rid, created_by, preset, len(crew), speed)
        return run

    def _step_for(self, speed: float) -> float:
        return min(STEP_CAP_S, max(1.0, speed * self.settings.mission_sim_tick_seconds))

    async def _loop(self, run: SandboxRun) -> None:
        loop = asyncio.get_running_loop()
        tick = self.settings.mission_sim_tick_seconds
        last = loop.time()
        while run.status in ACTIVE:
            await asyncio.sleep(tick)
            now = loop.time()
            dt, last = min(now - last, 5 * tick), now
            if run.status != "running":
                continue
            try:
                await self.advance(run, dt * run.speed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # isolate: the run fails, live monitoring carries on
                logger.exception("mission simulation %s failed", run.id)
                await self._finish(run, "failed", error=f"{type(exc).__name__}: {exc}"[:500])
                return

    async def pause(self, run_id: str | None = None, by: str = "operator") -> SandboxRun:
        run = self._active(run_id)
        if run.status == "paused":
            raise ConflictError("The simulation is already paused.")
        async with run.lock:
            run.status = "paused"
            await self._persist(run)
        await self._publish(run, "simulation_paused", "info", f"Mission simulation paused at {self._tplus(run)}",
                            occurred=run.sim_now, ref=f"{run.id}:pause:{run.sim_now.isoformat()}", payload={"by": by})
        await self._broadcast_state(run)
        return run

    async def resume(self, run_id: str | None = None, by: str = "operator") -> SandboxRun:
        run = self._active(run_id)
        if run.status != "paused":
            raise ConflictError("The simulation is not paused.")
        async with run.lock:
            run.status = "running"
            await self._persist(run)
        if run.task is None or run.task.done():
            run.task = asyncio.create_task(self._loop(run), name=f"astra-sandbox-{run.id}")
        await self._publish(run, "simulation_resumed", "info", f"Mission simulation resumed at {self._tplus(run)}",
                            occurred=run.sim_now, ref=f"{run.id}:resume:{run.sim_now.isoformat()}", payload={"by": by})
        await self._broadcast_state(run)
        return run

    async def set_speed(self, speed: float, run_id: str | None = None) -> SandboxRun:
        run = self._active(run_id)
        if not 0.5 <= speed <= self.settings.mission_sim_max_speed:
            raise ConflictError(f"Speed must be between 0.5 and {self.settings.mission_sim_max_speed:g}.")
        async with run.lock:
            run.speed = float(speed)
            run.step_s = self._step_for(speed)
            await self._persist(run)
        await self._broadcast_state(run)
        return run

    async def stop(self, run_id: str | None = None, by: str = "operator") -> SandboxRun:
        """End the run now (status completed). Its alerts stay open for review and reports."""
        run = self._active(run_id)
        await self._finish(run, "completed", by=by)
        return run

    async def reset(self, run_id: str | None = None, by: str = "operator") -> dict[str, Any]:
        """Abandon the run: stop it, close its open sandbox alerts and return to idle. Data stay for playback."""
        run = self.run
        if run is None or (run_id and run.id != run_id):
            raise ConflictError("There is no simulation to reset.")
        if run.status in ACTIVE:
            await self._finish(run, "reset", by=by)
        closed = 0
        for row in await self.alerts.list(context="simulation", simulation_id=run.id, statuses=["open", "acknowledged"],
                                          limit=500):
            try:
                await self.alerts.act(row.id, "resolve", actor=f"system (reset by {by})", role=None,
                                      note="Sandbox run reset; sandbox alert closed automatically.")
                closed += 1
            except ApiError:
                pass
        self.run = None
        await self._broadcast_idle()
        return {"simulation_id": run.id, "status": "reset", "alerts_closed": closed}

    async def _finish(self, run: SandboxRun, status: str, *, by: str = "system", error: str | None = None) -> None:
        if run.status not in ACTIVE:
            return
        run.status = status
        run.error = error
        current = asyncio.current_task()
        for task in (run.task, run.ai_task):
            if task is not None and task is not current and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        await self._persist(run, ended=True)
        sev = "caution" if status == "failed" else "info"
        await self._publish(run, f"simulation_{status}", sev,
                            f"Mission simulation {status}: {run.name} at {self._tplus(run)}",
                            summary=error, occurred=run.sim_now, ref=f"{run.id}:{status}", payload={"by": by})
        await self._broadcast_state(run)
        logger.info("mission simulation %s %s (%s)", run.id, status, by)

    # ================================================================== advance ====
    async def advance(self, run: SandboxRun, sim_seconds: float) -> None:
        """Advance the simulation clock (called by the loop; tests call it directly)."""
        async with run.lock:
            if run.status != "running":  # paused: the clock is frozen
                return
            remaining = sim_seconds + run.carry_s
            ended: list[ActiveScenario] = []
            while remaining >= run.step_s - 1e-9 and run.sim_now < run.sim_end:
                t = min(run.sim_now + timedelta(seconds=run.step_s), run.sim_end)
                await self._fire_due(run, t)
                result = run.engine.step(t)
                changes = []
                for r in result.readings:
                    run.latest[r.astronaut_id] = r
                    run.pending.append(_sample(r, "generator"))
                    changes.extend(run.evaluator.process(r))
                for aid, d in result.dose_msv.items():
                    run.dose_msv[aid] += d
                ended.extend(result.ended)
                run.sim_now = t
                remaining -= run.step_s
                for ch in changes:
                    await self._on_rule_change(run, ch.kind, replace(ch.alert))
                await self._environment(run, t)
            run.carry_s = max(0.0, remaining) if run.sim_now < run.sim_end else 0.0
            for s in ended:
                await self._on_scenario_end(run, s)
            await self._persist(run)
            done = run.sim_now >= run.sim_end
        if done:
            await self._finish(run, "completed")
        else:
            await self._broadcast_state(run)
            self._maybe_ai(run)

    # =============================================================== injections ====
    async def inject(self, *, injection: str, astronaut_id: str | None, intensity: float, duration_s: int | None,
                     at_minute: float | None, by: str, run_id: str | None = None) -> dict[str, Any]:
        run = self._active(run_id)
        spec = INJECTIONS.get(injection)
        if spec is None:
            raise NotFoundError(f"Unknown injection {injection}.")
        if not spec.crew_wide:
            if not astronaut_id:
                raise ConflictError("This injection needs an astronaut_id.")
            if astronaut_id not in run.crew:
                raise NotFoundError(f"{astronaut_id} is not part of this simulated mission.")
        if not 0.3 <= intensity <= 1.5:
            raise ConflictError("Intensity must be between 0.3 and 1.5.")
        step = {"at": run.sim_now if at_minute is None else max(run.sim_now, run.sim_start + timedelta(minutes=at_minute)),
                "injection": injection, "astronaut_id": None if spec.crew_wide else astronaut_id,
                "intensity": intensity, "duration_s": duration_s, "by": by}
        async with run.lock:
            if step["at"] <= run.sim_now:
                fired = await self._fire(run, step, run.sim_now)
                await self._persist(run)
            else:
                run.script.append(step)
                run.script.sort(key=lambda s: s["at"])
                fired = {**step, "status": "scheduled", "at": step["at"]}
        await self._broadcast_state(run)
        return fired

    async def _fire_due(self, run: SandboxRun, t: datetime) -> None:
        due = [s for s in run.script if s["at"] <= t]
        if not due:
            return
        run.script = [s for s in run.script if s["at"] > t]
        for step in due:
            await self._fire(run, step, max(step["at"], run.sim_now))

    async def _fire(self, run: SandboxRun, step: dict[str, Any], t: datetime) -> dict[str, Any]:
        spec = INJECTIONS[step["injection"]]
        record: dict[str, Any] = {
            "id": uuid.uuid4().hex[:10], "injection": spec.key, "label": spec.label, "kind": spec.kind,
            "astronaut_id": step["astronaut_id"], "intensity": step["intensity"], "by": step["by"],
            "sim_time": t, "wall_time": utcnow(), "scenario_id": None, "ends_at": None, "status": "fired",
        }
        if spec.scenario:
            duration = int(step["duration_s"] or spec.default_duration_s)
            s = run.engine.start_scenario(Scenario(spec.scenario), step["astronaut_id"], t,
                                          intensity=step["intensity"], duration_s=duration, triggered_by="operator")
            record["scenario_id"], record["ends_at"] = s.id, s.ends_at
        run.injections.append(record)
        run.stats["injections"] += 1
        who = CREW_BY_ID[step["astronaut_id"]].name if step["astronaut_id"] else "whole crew"
        category = {"health": "simulation", "environment": "environment",
                    "space_weather": "radiation" if spec.key == "solar_particle_event" else "solar_activity"}[spec.kind]
        await self._publish(run, f"injection_{spec.kind}", spec.severity,
                            f"Injected: {spec.label} ({who}, intensity {step['intensity']:g})",
                            summary=spec.description, occurred=t, astronaut_id=step["astronaut_id"], category=category,
                            classification="simulation_scenario", ref=f"{run.id}:inj:{record['id']}",
                            payload={**{k: v for k, v in record.items() if k not in ("sim_time", "wall_time", "ends_at")},
                                     "ends_at": record["ends_at"].isoformat() if record["ends_at"] else None})
        if spec.key == "solar_particle_event":
            await self.alerts.raise_alert(AlertSpec(
                source="environment_monitoring", source_ref=f"spe:{run.id}:{record['scenario_id']}", category="radiation",
                classification="simulated_environment", severity="caution",
                title="[SIM] Simulated solar particle event: sandbox dose rate up to x40",
                summary="Scripted sandbox event. Dose rates come from the simulator's radiation model.", occurred_at=t,
                context="simulation", simulation_id=run.id, data_origin="sandbox",
                measurements={"dose_rate_multiplier": 40.0, "intensity": step["intensity"], "data_category": "simulated"},
                explanation={"kind": "rule", "rule": "Any simulated solar particle event opens a radiation alert.",
                             "method": "Sandbox scenario injection."},
                confidence_level="deterministic", uncertainty=["Simulated dose rate, not a dosimeter reading."]))
        return {**record, "status": "fired"}

    async def _on_scenario_end(self, run: SandboxRun, s: ActiveScenario) -> None:
        for rec in run.injections:
            if rec.get("scenario_id") == s.id:
                rec["status"] = "ended"
        who = CREW_BY_ID[s.astronaut_id].name if s.astronaut_id else "whole crew"
        await self._publish(run, "injection_ended", "info", f"Injection ended: {s.spec.label} ({who})",
                            occurred=s.cancelled_at or s.ends_at, astronaut_id=s.astronaut_id,
                            classification="simulation_scenario", ref=f"{run.id}:end:{s.id}")
        if s.scenario == Scenario.SOLAR_PARTICLE_EVENT:
            await self.alerts.mark_cleared("environment_monitoring", f"spe:{run.id}:{s.id}", s.ends_at)

    # ============================================================= telemetry in ====
    async def ingest(self, run_id: str, readings: list[dict[str, Any]], source: str = "external") -> dict[str, Any]:
        """Measurements sent to the backend for a sandbox run go through the same detection path."""
        run = self._active(run_id)
        tolerance = timedelta(seconds=self.settings.mission_clock_skew_tolerance_s)
        accepted, issues, alerts_before = 0, [], run.stats["alerts"]
        async with run.lock:
            for i, item in enumerate(readings):
                aid = item["astronaut_id"]
                if aid not in run.crew:
                    issues.append({"index": i, "issue": f"{aid} is not part of this simulated mission"})
                    continue
                ts = as_utc(item["ts"])
                if ts < run.sim_start:
                    issues.append({"index": i, "issue": "timestamp before the simulation started"})
                    continue
                skew = (ts - run.sim_now).total_seconds()
                if ts > run.sim_now + tolerance:
                    issues.append({"index": i, "issue": f"timestamp {skew:.0f}s ahead of the simulation clock; "
                                                        "clamped to the simulation clock", "clamped": True})
                    ts = run.sim_now
                profile = CREW_BY_ID[aid]
                state, met = activity_at(profile, ts, self.settings.simulator_seed)
                base = run.latest.get(aid)
                values = {c: item.get(c) if item.get(c) is not None else (getattr(base, c) if base else None)
                          for c in SIGNAL_COLUMNS}
                if any(v is None for v in values.values()):
                    issues.append({"index": i, "issue": "missing signals and no earlier reading to carry forward"})
                    continue
                r = VitalReading(astronaut_id=aid, ts=ts, **{k: float(v) for k, v in values.items()},
                                 activity_state=item.get("activity_state") or state,
                                 activity_met=float(item.get("activity_met") or met),
                                 rhythm=item.get("rhythm") or "regular", hrv_rmssd_ms=None, scenario="external")
                run.latest[aid] = r
                run.pending.append(_sample(r, source))
                accepted += 1
                for ch in run.evaluator.process(r):
                    await self._on_rule_change(run, ch.kind, replace(ch.alert))
            run.stats["external_samples"] += accepted
            await self._persist(run)
        if accepted:
            await self._publish(run, "telemetry_ingested", "info",
                                f"{accepted} external measurement{'s' if accepted != 1 else ''} ingested",
                                occurred=run.sim_now, ref=None, dedupe="telemetry",
                                payload={"accepted": accepted, "rejected": len(readings) - accepted, "source": source})
        await self._broadcast_state(run)
        return {"simulation_id": run.id, "received": len(readings), "accepted": accepted,
                "rejected": sum(1 for x in issues if not x.get("clamped")), "issues": issues,
                "alerts_opened": run.stats["alerts"] - alerts_before, "sim_time": run.sim_now}

    # ================================================================== alerts ====
    def _name(self, aid: str | None) -> str:
        return CREW_BY_ID[aid].name if aid in CREW_BY_ID else "Crew"

    async def _on_rule_change(self, run: SandboxRun, kind: str, rec: AlertRecord) -> None:
        name = self._name(rec.astronaut_id)
        row = await self.alerts.mirror_rule_alert(kind, rec, context="simulation", simulation_id=run.id,
                                                  data_origin="sandbox", name=name)
        if kind == "opened":
            run.stats["alerts"] += 1
        severity = rec.severity if kind in ("opened", "escalated", "recurred") else "info"
        ev = await self._publish(run, f"alert_{kind}", severity, f"[SIM] {name}: {rec.title} ({kind})",
                                 summary=rec.message, occurred=rec.updated_at if kind != "opened" else rec.opened_at,
                                 astronaut_id=rec.astronaut_id, category="crew_physiology", source=RULE_SOURCE,
                                 classification="rule_detection", ref=f"{run.id}:{rec.id}:{kind}",
                                 payload={"alert_center_id": row.id if row else None, "metric": rec.metric,
                                          "trigger_value": rec.trigger_value, "peak_value": rec.peak_value,
                                          "unit": rec.unit, "injected_scenario": rec.scenario})
        if row is not None and kind == "opened":
            t = rec.opened_at
            scenarios = [s for s in run.engine.scenarios.values() if s.affects(rec.astronaut_id) and s.is_active(t)]
            correlations = await self.orchestrator.correlate(
                rec.astronaut_id, t, context="simulation", simulation_id=run.id, scenarios=scenarios,
                habitat=habitat_at(t, run.engine.active_scenarios(t)), nasa_ts=utcnow())
            correlations["notes"].append("Sandbox clock: NASA events are matched to the wall-clock time of the run.")
            await self.alerts.set_links(row.id, event_id=ev.id if ev else None, correlations=correlations)

    async def update_alert(self, alert_ref: str, action: str, note: str | None) -> None:
        """Delegate for the alert centre: apply an operator decision to the sandbox evaluator."""
        run = self.run
        rec = run.evaluator.find(alert_ref) if run is not None else None
        if rec is None:
            raise NotFoundError("This sandbox alert belongs to a run that is no longer loaded.")
        if rec.status == "resolved":
            raise ConflictError("This alert is already resolved.")
        if action == "acknowledge":
            if rec.status == "acknowledged":
                raise ConflictError("This alert is already acknowledged.")
            rec.status, rec.acknowledged_at = "acknowledged", run.sim_now
        else:
            rec.status, rec.resolved_at = "resolved", run.sim_now
            rec.acknowledged_at = rec.acknowledged_at or run.sim_now
            run.evaluator.release(alert_ref)
        rec.operator_note = note or rec.operator_note

    # ============================================================= environment ====
    async def _environment(self, run: SandboxRun, t: datetime) -> None:
        from app.mission.orchestrator import ENV_ADVISORY_SIGMA, ENV_CAUTION_SIGMA, ENV_NOMINAL_SIGMA

        active = run.engine.active_scenarios(t)
        habitat = habitat_at(t, active)
        params = habitat["parameters"]
        _, worst = max(params.items(), key=lambda kv: abs(kv[1]["deviation_sigma"]))
        sigma = abs(worst["deviation_sigma"])
        w = run.env
        if sigma >= ENV_ADVISORY_SIGMA:
            severity = "caution" if sigma >= ENV_CAUTION_SIGMA else "advisory"
            if w.episode is None:
                w.episode = f"habitat:{run.id}:{habitat.get('anomaly_scenario_id') or t.strftime('%H%M%S')}"
                w.peak = None
            if w.peak != severity:
                w.peak = severity
                title = f"[SIM] Habitat {worst['label']} {worst['value']} {worst['unit']} ({worst['deviation_sigma']:+.1f} sigma)"
                ev = await self._publish(run, "environment_anomaly", severity, title, summary=habitat["note"],
                                         occurred=t, category="environment", source="environment_monitoring",
                                         classification="simulated_environment", ref=f"{w.episode}:{severity}",
                                         payload={"parameters": params})
                await self.alerts.raise_alert(AlertSpec(
                    source="environment_monitoring", source_ref=w.episode, category="environment",
                    classification="simulated_environment", severity=severity, title=title, summary=habitat["note"],
                    occurred_at=t, context="simulation", simulation_id=run.id, data_origin="sandbox",
                    event_id=ev.id if ev else None,
                    measurements={k: {"value": p["value"], "unit": p["unit"], "nominal": p["nominal"],
                                      "deviation_sigma": p["deviation_sigma"]} for k, p in params.items()},
                    explanation={"kind": "rule", "rule": f"Advisory at {ENV_ADVISORY_SIGMA:g} sigma, caution at "
                                                         f"{ENV_CAUTION_SIGMA:g} sigma from the simulator's nominal level.",
                                 "method": "Simulated habitat model in the sandbox."},
                    confidence_level="deterministic", uncertainty=["Nominal levels are simulator settings, not limits."]))
        elif sigma < ENV_NOMINAL_SIGMA and w.episode is not None:
            await self._publish(run, "environment_nominal", "info", "[SIM] Habitat atmosphere back near nominal",
                                occurred=t, category="environment", source="environment_monitoring",
                                classification="simulated_environment", ref=f"{w.episode}:nominal")
            await self.alerts.mark_cleared("environment_monitoring", w.episode, t)
            w.episode = w.peak = None

    # ====================================================================== AI ====
    def _maybe_ai(self, run: SandboxRun) -> None:
        if run.status != "running" or (run.ai_task is not None and not run.ai_task.done()):
            return
        if run.sim_now - run.sim_start < AI_FIRST_AFTER:
            return
        if run.last_ai_at is not None and run.sim_now - run.last_ai_at < run.ai_every:
            return
        run.last_ai_at = run.sim_now
        run.ai_task = asyncio.create_task(self.analyze(run), name=f"astra-sandbox-ai-{run.id}")

    async def analyze(self, run: SandboxRun | None = None, run_id: str | None = None) -> dict[str, Any]:
        """Phase 3 AI over each crew member's sandbox stream (anomaly ensemble, forecast, risk)."""
        run = run or self._active(run_id)
        now = run.sim_now
        run.ai_status = "running"
        out: dict[str, Any] = {}
        try:
            async with run.lock:
                await self._persist(run)
            for aid in run.crew:
                df = await self._samples_frame(run.id, aid, run.sim_start, now)
                open_alerts = [{"id": a.id, "severity": a.severity, "title": a.title, "metric": a.metric,
                                "condition_cleared": a.condition_cleared_at is not None}
                               for a in run.evaluator.open_alerts() if a.astronaut_id == aid]
                try:
                    res = await self.ai.analyse_stream(aid, df, now, open_alerts)
                except ApiError as exc:
                    out[aid] = {"available": False, "reason": exc.message, "sim_time": now}
                    continue
                risk, det, fc = res["risk"], res["detection"], res["forecast"]
                out[aid] = {
                    "available": True, "sim_time": now, "model_version": res["model_version"],
                    "risk": {k: risk[k] for k in ("risk_score", "category", "category_label", "health_score")}
                    | {"warnings": [{k: w[k] for k in ("title", "detail", "source", "points")} for w in risk["warnings"][:5]],
                       "confidence": risk["explanation"]["confidence"], "what_changed": risk["explanation"]["what_changed"],
                       "anomaly": risk["anomaly"], "contributors": risk["explanation"]["contributors"][:6]},
                    "detections": [{k: d[k] for k in ("start", "end", "peak_score", "kind", "signals", "votes",
                                                      "duration_minutes")} for d in det["detections"]],
                    "flagged_windows": sum(1 for p in det["timeline"] if p["flagged"]),
                    "windows": len(det["timeline"]),
                    "forecast": None if fc is None else [
                        {"signal": s["signal"], "label": s["label"], "unit": s["unit"],
                         "horizons": [{k: h[k] for k in ("horizon_h", "value", "lower", "upper", "caution_limit",
                                                         "crossing")} for h in s["horizons"]]}
                        for s in fc["series"]],
                    "forecast_error": res["forecast_error"],
                    "limitations": risk.get("limitations", []),
                }
                for d in det["detections"]:
                    await self._publish(run, "anomaly_detected", "advisory",
                                        f"[SIM] {self._name(aid)}: AI anomaly window ({(d['kind'] or 'pattern').replace('_', ' ')}) - experimental",
                                        summary=f"Peak {d['peak_score']:.2f}x threshold, {d['votes']} detector votes, "
                                                f"{d['duration_minutes']:.0f} min ({', '.join(d['signals'][:3])}).",
                                        occurred=d["start"], astronaut_id=aid, category="ai_prediction",
                                        source="anomaly_detection", classification="experimental_ai", experimental=True,
                                        confidence=risk["explanation"]["confidence"].get("score"),
                                        ref=f"{run.id}:det:{aid}:{pd.Timestamp(d['start']).isoformat()}",
                                        payload={"detection": {k: (v.isoformat() if isinstance(v, datetime) else v)
                                                               for k, v in d.items() if k != "explanation"}})
                await self.orchestrator._ai_findings(aid, risk, context="simulation", simulation_id=run.id, now=now,
                                                     episodes=run.ai_episodes, categories=run.ai_categories)
            run.analyses = {**run.analyses, **out, "_last": {"sim_time": now.isoformat(), "wall_time": utcnow().isoformat()}}
            run.stats["ai_runs"] += 1
            run.ai_status = "ok" if any(v.get("available") for k, v in out.items() if not k.startswith("_")) else "unavailable"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            run.ai_status = f"error: {type(exc).__name__}"
            logger.exception("sandbox AI analysis failed for %s", run.id)
        async with run.lock:
            await self._persist(run)
        await self._broadcast_state(run)
        return out

    async def _samples_frame(self, run_id: str, aid: str, start: datetime, end: datetime) -> pd.DataFrame:
        cols = ("ts", *SIGNAL_COLUMNS, "activity_state", "activity_met")
        async with self.factory() as session:
            rows = (await session.execute(
                select(*(getattr(MissionSimSampleRow, c) for c in cols))
                .where(MissionSimSampleRow.simulation_id == run_id, MissionSimSampleRow.astronaut_id == aid,
                       MissionSimSampleRow.ts >= start, MissionSimSampleRow.ts <= end)
                .order_by(MissionSimSampleRow.ts))).all()
        from app.ai.windows import samples_to_frame

        return samples_to_frame([dict(zip(cols, r)) for r in rows])

    # ============================================================ persistence ====
    async def _persist(self, run: SandboxRun, ended: bool = False) -> None:
        pending, run.pending = run.pending, []
        now = utcnow()
        async with self.factory() as session:
            if pending:
                await session.execute(insert(MissionSimSampleRow), [{"simulation_id": run.id, **p} for p in pending])
                run.stats["samples"] += len(pending)
            row = await session.get(MissionSimulationRow, run.id)
            if row is not None:
                row.status, row.speed, row.sim_time, row.wall_updated_at = run.status, run.speed, run.sim_now, now
                row.stats = dict(run.stats) | {"dose_msv": {k: round(v, 5) for k, v in run.dose_msv.items()}}
                row.injections = [_jsonable(i) for i in run.injections]
                row.analyses = _jsonable(run.analyses)
                row.error = run.error
                if ended:
                    row.wall_ended_at = now
            await session.commit()

    async def _publish(self, run: SandboxRun, kind: str, severity: str, title: str, *, occurred: datetime,
                       ref: str | None, summary: str | None = None, astronaut_id: str | None = None,
                       category: str = "simulation", source: str = "mission_simulation",
                       classification: str = "simulation_scenario", experimental: bool = False,
                       confidence: float | None = None, dedupe: str | None = None,
                       payload: dict[str, Any] | None = None) -> MissionEventRow | None:
        try:
            row, created = await self.events.publish(EventInput(
                source=source, kind=kind, category=category, severity=severity, title=title, summary=summary,
                occurred_at=occurred, astronaut_id=astronaut_id, context="simulation", simulation_id=run.id,
                data_origin="sandbox", classification=classification, experimental=experimental,
                confidence=confidence, ref_type="sandbox" if ref else None, ref_id=ref, dedupe_key=dedupe,
                payload={**(payload or {}), "sim_offset_s": round((as_utc(occurred) - run.sim_start).total_seconds(), 1)},
            ))
            run.stats["events"] += int(created)
            return row
        except Exception:
            logger.exception("sandbox event publish failed")
            return None

    # ================================================================== views ====
    def _tplus(self, run: SandboxRun, t: datetime | None = None) -> str:
        s = int(((t or run.sim_now) - run.sim_start).total_seconds())
        return f"T+{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def state(self, run: SandboxRun | None = None) -> dict[str, Any]:
        run = run or self.run
        if run is None:
            return {"active": False, "status": "idle", "context": "simulation", "data_source": "simulated",
                    "label": SANDBOX_LABEL}
        t = run.sim_now
        habitat = habitat_at(t, run.engine.active_scenarios(t))
        total = (run.sim_end - run.sim_start).total_seconds()
        nxt = run.script[0] if run.script else None
        return {
            "active": run.status in ACTIVE, "id": run.id, "name": run.name, "preset": run.preset,
            "status": run.status, "speed": run.speed, "step_seconds": run.step_s, "crew": run.crew,
            "sim_start": run.sim_start, "sim_time": t, "sim_end": run.sim_end, "t_plus": self._tplus(run),
            "progress": round(min(1.0, (t - run.sim_start).total_seconds() / total), 4) if total else 1.0,
            "wall_started_at": run.wall_started_at, "created_by": run.created_by,
            "latest": [{"astronaut_id": r.astronaut_id, "name": self._name(r.astronaut_id), "ts": r.ts,
                        **{c: getattr(r, c) for c in SIGNAL_COLUMNS}, "activity_state": r.activity_state,
                        "rhythm": r.rhythm, "scenario": r.scenario,
                        "status": _status([a for a in run.evaluator.open_alerts() if a.astronaut_id == r.astronaut_id]),
                        "dose_msv": round(run.dose_msv.get(r.astronaut_id, 0.0), 5)}
                       for r in (run.latest[a] for a in run.crew if a in run.latest)],
            "active_injections": [_jsonable({k: v for k, v in i.items() if k != "wall_time"})
                                  for i in run.injections if i.get("status") == "fired"
                                  and (i.get("ends_at") is None or i["ends_at"] > t)][-8:],
            "next_injection": None if nxt is None else _jsonable({**nxt, "t_plus": self._tplus(run, nxt["at"])}),
            "habitat": {k: {"label": p["label"], "value": p["value"], "unit": p["unit"],
                            "deviation_sigma": p["deviation_sigma"]} for k, p in habitat["parameters"].items()},
            "dose_rate_multiplier": round(_dose_multiplier(run.engine.active_scenarios(t), t), 2),
            "open_alerts": len(run.evaluator.open_alerts()),
            "stats": dict(run.stats), "ai_status": run.ai_status,
            "last_ai_at": run.last_ai_at, "error": run.error,
            "context": "simulation", "data_source": "simulated", "label": SANDBOX_LABEL,
        }

    async def _broadcast_state(self, run: SandboxRun | None) -> None:
        if self.hub is None or self.hub.count == 0:
            return
        from app.schemas.mission_control import SimState, WsSimState

        try:
            msg = WsSimState(state=SimState.model_validate(self.state(run)))
            await self.hub.broadcast(msg.model_dump_json())
        except Exception:
            logger.exception("could not broadcast simulation state")

    async def _broadcast_idle(self) -> None:
        await self._broadcast_state(None)

    async def list_runs(self, limit: int = 30) -> list[MissionSimulationRow]:
        async with self.factory() as session:
            return list((await session.scalars(select(MissionSimulationRow)
                                               .order_by(MissionSimulationRow.wall_started_at.desc()).limit(limit))).all())

    async def get_row(self, run_id: str) -> MissionSimulationRow:
        async with self.factory() as session:
            row = await session.get(MissionSimulationRow, run_id)
        if row is None:
            raise NotFoundError(f"Simulation {run_id} not found.")
        return row

    async def playback(self, run_id: str, max_points: int = 240) -> dict[str, Any]:
        """The stored run, bucketed for replay: per-crew series, injections, events and alerts."""
        row = await self.get_row(run_id)
        start, end = row.sim_start, row.sim_time
        span = max(1.0, (end - start).total_seconds())
        resolution = max(1.0, math.ceil(span / max_points))
        cols = ("astronaut_id", "ts", *SIGNAL_COLUMNS, "scenario")
        async with self.factory() as session:
            rows = (await session.execute(
                select(*(getattr(MissionSimSampleRow, c) for c in cols))
                .where(MissionSimSampleRow.simulation_id == run_id).order_by(MissionSimSampleRow.ts))).all()
            events = list((await session.scalars(
                select(MissionEventRow).where(MissionEventRow.simulation_id == run_id)
                .order_by(MissionEventRow.occurred_at))).all())
            alerts = list((await session.scalars(
                select(MissionAlertRow).where(MissionAlertRow.simulation_id == run_id)
                .order_by(MissionAlertRow.created_at))).all())
        df = pd.DataFrame(rows, columns=list(cols))
        series = []
        for aid in row.crew:
            part = df[df["astronaut_id"] == aid] if len(df) else df
            points = []
            if len(part):
                part = part.assign(bucket=((pd.to_datetime(part["ts"], utc=True) - pd.Timestamp(start)).dt.total_seconds()
                                           // resolution).astype(int))
                grouped = part.groupby("bucket")
                means = grouped[list(SIGNAL_COLUMNS)].mean()
                scen = grouped["scenario"].agg(lambda s: next((x for x in s if x), None))
                counts = grouped.size()
                for b, vals in means.iterrows():
                    sc = scen.loc[b]
                    points.append({"ts": start + timedelta(seconds=(int(b) + 0.5) * resolution),
                                   **{c: round(float(vals[c]), 2) for c in SIGNAL_COLUMNS},
                                   "scenario": sc if isinstance(sc, str) else None, "samples": int(counts.loc[b])})
            series.append({"astronaut_id": aid, "name": self._name(aid), "points": points})
        return {
            "simulation": run_view(row), "resolution_seconds": resolution, "start": start, "end": end,
            "series": series, "injections": row.injections or [],
            "events": [event_view(e) for e in events], "alerts": [alert_view(a) for a in alerts],
            "label": SANDBOX_LABEL,
        }

    async def frame(self, run_id: str, at: datetime) -> dict[str, Any]:
        """Exact state of a stored run at one simulated instant (for scrubbing the playback)."""
        row = await self.get_row(run_id)
        at = min(max(as_utc(at), row.sim_start), row.sim_time)
        cols = ("ts", *SIGNAL_COLUMNS, "activity_state", "rhythm", "scenario", "source")
        crew = []
        async with self.factory() as session:
            for aid in row.crew:
                r = (await session.execute(
                    select(*(getattr(MissionSimSampleRow, c) for c in cols))
                    .where(MissionSimSampleRow.simulation_id == run_id, MissionSimSampleRow.astronaut_id == aid,
                           MissionSimSampleRow.ts <= at).order_by(MissionSimSampleRow.ts.desc()).limit(1))).first()
                crew.append({"astronaut_id": aid, "name": self._name(aid),
                             "reading": None if r is None else dict(zip(cols, r))})
            alerts = list((await session.scalars(
                select(MissionAlertRow).where(MissionAlertRow.simulation_id == run_id,
                                              MissionAlertRow.created_at <= at))).all())
        active = [i for i in (row.injections or []) if _parse(i.get("sim_time")) and _parse(i["sim_time"]) <= at
                  and (i.get("ends_at") is None or _parse(i["ends_at"]) > at)]
        return {"simulation_id": run_id, "at": at, "t_plus": _tplus_from(row.sim_start, at), "crew": crew,
                "active_injections": active, "alerts": [alert_view(a) for a in alerts], "label": SANDBOX_LABEL}

    # ================================================================= reports ====
    async def create_report(self, run_id: str, *, alert_id: str | None, astronaut_id: str | None, principal) -> Any:
        """Freeze a sandbox incident into an incident report (same ten sections, sandbox-labelled)."""
        row = await self.get_row(run_id)
        alert = None
        if alert_id:
            alert, _ = await self.alerts.get(alert_id)
            if alert.simulation_id != run_id:
                raise ConflictError("That alert does not belong to this simulation.")
            astronaut_id = alert.astronaut_id or astronaut_id
        if not astronaut_id or astronaut_id not in row.crew:
            raise ConflictError("A sandbox report needs an alert with a crew member, or one of the run's crew.")
        occurred = alert.created_at if alert else row.sim_time
        start, end = occurred - timedelta(minutes=30), occurred + timedelta(minutes=15)
        df = await self._samples_frame(run_id, astronaut_id, start, end)
        from app.twin import summary as S

        measurements = {"window": {"start": start, "end": end}, "summary": S.summarize_metrics(df.assign(scenario=None))
                        if len(df) else {}, "samples": len(df), "data_category": "simulated (sandbox)"}
        analysis = (row.analyses or {}).get(astronaut_id)
        events = await self.events.list(simulation_id=run_id, astronaut_id=astronaut_id, start=start, end=end, limit=40)
        view = alert_view(alert) if alert else None
        profile = CREW_BY_ID[astronaut_id]
        corr = (view or {}).get("correlations") or {}
        injections = [i for i in (row.injections or []) if i.get("astronaut_id") in (None, astronaut_id)]
        active_then = [i["label"] for i in injections if _parse(i.get("sim_time")) and _parse(i["sim_time"]) <= occurred
                       and (i.get("ends_at") is None or _parse(i["ends_at"]) > occurred)]
        habitat = habitat_at(occurred, [])
        for i in injections:  # rebuild the sandbox habitat at the event time from the injected scenarios
            if i.get("injection") == "habitat_atmosphere" and i.get("scenario_id") and _parse(i.get("sim_time")):
                s_ = ActiveScenario(id=i["scenario_id"], scenario=Scenario.HABITAT_ATMOSPHERE, astronaut_id=None,
                                    intensity=float(i.get("intensity") or 1.0), started_at=_parse(i["sim_time"]),
                                    ends_at=_parse(i.get("ends_at")) or _parse(i["sim_time"]), triggered_by="operator")
                habitat = habitat_at(occurred, [s_])
        risk = (analysis or {}).get("risk") or {}
        anomaly = risk.get("anomaly") or {}
        stage_label = f"Simulation sandbox, {_tplus_from(row.sim_start, occurred)}"
        content = {
            "schema_version": 1,
            "label": SANDBOX_LABEL,
            "mission": {"name": f"{self.settings.mission_name} mission simulation: {row.name}", "phase": "Simulation sandbox",
                        "mission_start": row.sim_start, "mission_day": _tplus_from(row.sim_start, occurred),
                        "stage": "sandbox run", "simulation_id": run_id, "simulation_name": row.name,
                        "preset": row.preset, "speed": row.speed},
            "astronaut": {"id": profile.id, "name": profile.name, "role": profile.role, "age": profile.age,
                          "sex": profile.sex, "fictional": True},
            "timestamp": {"occurred_at": occurred, "report_created_at": utcnow(), "timezone": "UTC (simulation clock)",
                          "t_plus": _tplus_from(row.sim_start, occurred)},
            "summary": (view or {}).get("summary") or f"Sandbox incident during {row.name}.",
            "source": {"alert_id": None, "run_id": None, "simulation_id": run_id,
                       "sandbox_alert_id": alert_id, "sandbox_alert_source": (view or {}).get("source"),
                       "classification": (view or {}).get("classification")},
            "observation": None if view is None else {
                "title": view["title"], "summary": view["summary"], "severity": view["severity"],
                "priority": view["priority_label"], "status": view["status"], "classification": view["classification_label"],
                "classification_note": view["classification_note"],
                "simulated_test_scenario": ", ".join(active_then) or None},
            "measurements": {**measurements, "alert": (view or {}).get("measurements")},
            "baseline_comparison": {"available": bool(risk.get("contributors")),
                                    "contributors": risk.get("contributors") or [],
                                    "method": "Personal-baseline comparison from the AI analysis of the sandbox stream "
                                              "(phase 3 baselines).", "data_category": "derived"},
            "environment": {"activity_state": ((view or {}).get("measurements") or {}).get("activity_state"),
                            "mission_stage": stage_label, "simulated_test_scenario": ", ".join(active_then) or None,
                            "habitat": {"parameters": habitat["parameters"], "category": "simulated"},
                            "space_weather": corr.get("space_weather"), "injections": injections,
                            "correlations": corr},
            "anomaly_results": {
                "ai_output": None if not analysis else {
                    **analysis, "available": bool(analysis.get("available")), "kind": anomaly.get("kind"),
                    "anomaly_peak": {"ensemble_score": anomaly.get("score"), "votes": anomaly.get("votes")}},
                "multisystem": {"summary": "The six-system assessment covers the live crew stream; this sandbox report "
                                           "uses the AI analysis of the simulated stream instead.",
                                "systems": [], "patterns": []},
                "events": [event_view(e) for e in events]},
            "model_explanation": {"rule": ((view or {}).get("explanation") or {}).get("rule"),
                                  "what_changed": ((view or {}).get("explanation") or {}).get("what_changed")
                                  or risk.get("what_changed"),
                                  "model_version": (analysis or {}).get("model_version"),
                                  "confidence": risk.get("confidence"),
                                  "uncertainty": (view or {}).get("uncertainty", [])},
            "data_quality": {"packet": {"samples": len(df), "notes": []}, "multisystem": None, "limitations": [
                "Generated in the mission simulation sandbox; it is not part of the live crew record.",
                "All crew data in ASTRA-MED is simulated; crew members are fictional.",
                "AI outputs are experimental, trained and evaluated on simulated data only.",
                "This report supports, and does not replace, review by qualified medical personnel."]},
            "review_workflow": None,
            "disclaimer": "Simulation sandbox report. Decision support only; not a diagnosis and not clinically validated.",
        }
        base_title = (view or {}).get("title") or f"Sandbox incident - {profile.name}"
        title = base_title if base_title.startswith("[SIM]") else f"[SIM] {base_title}"
        report = await self.reports.store_snapshot(principal, title=title, astronaut_id=astronaut_id,
                                                   occurred_at=occurred, content=content)
        return report


def _status(alerts: list[AlertRecord]) -> str:
    rank = {"advisory": 1, "caution": 2, "critical": 3}
    worst = max((a.severity for a in alerts if a.condition_cleared_at is None), key=lambda s: rank[s], default=None)
    return worst or "nominal"


def _parse(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return as_utc(v)
    try:
        return as_utc(datetime.fromisoformat(str(v)))
    except ValueError:
        return None


def _tplus_from(start: datetime, t: datetime) -> str:
    s = max(0, int((as_utc(t) - as_utc(start)).total_seconds()))
    return f"T+{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return as_utc(obj).isoformat()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def run_view(row: MissionSimulationRow) -> dict[str, Any]:
    total = (row.sim_end - row.sim_start).total_seconds()
    return {
        "id": row.id, "name": row.name, "preset": row.preset, "crew": row.crew, "status": row.status,
        "speed": row.speed, "seed": row.seed, "sim_start": row.sim_start, "sim_time": row.sim_time,
        "sim_end": row.sim_end, "t_plus": _tplus_from(row.sim_start, row.sim_time),
        "progress": round(min(1.0, (row.sim_time - row.sim_start).total_seconds() / total), 4) if total else 1.0,
        "wall_started_at": row.wall_started_at, "wall_updated_at": row.wall_updated_at,
        "wall_ended_at": row.wall_ended_at, "created_by": row.created_by, "config": row.config or {},
        "injections": row.injections or [], "analyses": row.analyses or {}, "stats": row.stats or {},
        "error": row.error, "context": "simulation", "data_source": "simulated", "label": SANDBOX_LABEL,
    }
