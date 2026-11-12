"""Monitoring service: drives the simulator, evaluates alerts, persists and broadcasts.

    engine.step() ─► alert evaluator ─► PostgreSQL (every N ticks) ─► WebSocket hub

The tick loop is resilient: one failing tick is logged and the next one runs on schedule.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import utcnow
from app.detection.baseline import BaselineDetector
from app.detection.evaluator import AlertChange, AlertEvaluator, AlertRecord
from app.repositories import alerts as alerts_repo
from app.repositories import events as events_repo
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.schemas.alerts import Alert
from app.schemas.simulation import SimulationEvent, SimulationEventCreate
from app.schemas.ws import WsAlert, WsHello, WsSimulation, WsVitals
from app.services import mappers
from app.services.hub import ConnectionHub
from app.services.seeding import mission_day_for, seed_database
from app.simulator.engine import SimulationEngine, TickResult, VitalReading
from app.simulator.physiology import target_vitals
from app.simulator.profiles import CREW
from app.simulator.scenarios import SCENARIOS, ActiveScenario, Scenario
from app.simulator.schedule import activity_at

logger = logging.getLogger("astra.monitor")


class MonitoringService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        hub: ConnectionHub | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.hub = hub or ConnectionHub()
        self.engine = SimulationEngine(
            CREW,
            seed=settings.simulator_seed,
            ecg_sample_rate_hz=settings.ecg_sample_rate_hz,
            random_events_per_hour=settings.random_events_per_hour,
            default_tick_seconds=settings.tick_seconds,
        )
        profiles = self.engine.profiles
        self.evaluator = AlertEvaluator(
            BaselineDetector(lambda aid, ts, st, met: target_vitals(profiles[aid], ts, st, met))
        )
        self.latest: dict[str, VitalReading] = {}
        self._pending: list[VitalReading] = []
        self._dose: dict[str, float] = defaultdict(float)
        self._ticks = 0
        self._task: asyncio.Task | None = None
        self.started_at: datetime | None = None

    # ---------------------------------------------------------------- lifecycle ----
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def bootstrap(self, now: datetime | None = None) -> None:
        now = now or utcnow()
        await seed_database(self.session_factory, self.engine, self.settings, now)
        async with self.session_factory() as session:
            rows = await alerts_repo.open_alerts(session)
        self.evaluator.restore(alerts_repo.row_to_record(r) for r in rows)
        logger.info("restored %d open alerts", len(rows))
        self.started_at = now

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._run(), name="astra-monitor")
            logger.info("simulator started at %.2fs/tick", self.settings.tick_seconds)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._flush(force=True)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        interval = self.settings.tick_seconds
        next_at = loop.time()
        while True:
            try:
                await self.tick(utcnow())
            except asyncio.CancelledError:
                raise
            except Exception:  # keep monitoring alive through transient failures
                logger.exception("tick failed")
            next_at += interval
            delay = next_at - loop.time()
            if delay < -interval:  # fell behind (e.g. laptop sleep); resynchronise
                next_at = loop.time()
                delay = 0
            await asyncio.sleep(max(0.0, delay))

    # --------------------------------------------------------------------- ticks ----
    async def tick(self, now: datetime) -> TickResult:
        result = self.engine.step(now)
        changes: list[AlertChange] = []
        for reading in result.readings:
            self.latest[reading.astronaut_id] = reading
            changes.extend(self.evaluator.process(reading))
        for aid, dose in result.dose_msv.items():
            self._dose[aid] += dose
        self._pending.extend(result.readings)
        self._ticks += 1

        await self._persist(result, force=self._ticks % self.settings.persist_every_ticks == 0)
        await self._broadcast(result, changes, now)
        return result

    async def _persist(self, result: TickResult, *, force: bool) -> None:
        dirty = self.evaluator.pop_dirty()
        scenarios = [*result.started, *result.ended]
        if not (force or dirty or scenarios):
            return
        async with self.session_factory() as session:
            if force:
                await self._write_buffers(session, result.ts)
            if dirty:
                await alerts_repo.upsert(session, dirty)
            if scenarios:
                await events_repo.upsert(session, scenarios)
            await session.commit()

    async def _write_buffers(self, session: AsyncSession, now: datetime) -> None:
        pending, self._pending = self._pending, []
        await vitals_repo.insert_readings(session, pending)
        doses, self._dose = dict(self._dose), defaultdict(float)
        mday = mission_day_for(self.settings, now.date())
        for aid, dose in doses.items():
            await sr_repo.add_dose(session, aid, now.date(), mday, dose)

    async def _flush(self, force: bool = False) -> None:
        if not (self._pending or self._dose):
            return
        try:
            async with self.session_factory() as session:
                await self._write_buffers(session, utcnow())
                await session.commit()
        except Exception:
            logger.exception("final flush failed")

    async def _broadcast(self, result: TickResult, changes: list[AlertChange], now: datetime) -> None:
        if self.hub.count == 0:
            return
        msg = WsVitals(
            ts=result.ts,
            readings=[mappers.reading_schema(r) for r in result.readings],
            ecg=[mappers.ecg_schema(c) for c in result.ecg],
        )
        await self.hub.broadcast(msg.model_dump_json())
        for s in result.started:
            await self._send_simulation("started", s, now)
        for s in result.ended:
            await self._send_simulation("ended", s, now)
        for change in changes:
            await self._send_alert(change.kind, change.alert)

    async def _send_alert(self, kind: str, alert: AlertRecord) -> None:
        msg = WsAlert(event=kind, alert=mappers.alert_schema(alert))  # type: ignore[arg-type]
        await self.hub.broadcast(msg.model_dump_json())

    async def _send_simulation(self, kind: str, s: ActiveScenario, now: datetime) -> None:
        msg = WsSimulation(event=kind, scenario=mappers.scenario_schema(s, now))  # type: ignore[arg-type]
        await self.hub.broadcast(msg.model_dump_json())

    # ----------------------------------------------------------------- snapshots ----
    def hello(self) -> WsHello:
        now = utcnow()
        return WsHello(
            server_time=now,
            tick_seconds=self.settings.tick_seconds,
            ecg_sample_rate_hz=self.settings.ecg_sample_rate_hz,
            astronaut_ids=list(self.engine.profiles),
            latest=[mappers.reading_schema(r) for r in self.latest.values()],
            open_alerts=[mappers.alert_schema(a) for a in self.evaluator.open_alerts()],
            active_scenarios=[
                mappers.scenario_schema(s, now) for s in self.engine.active_scenarios(now)
            ],
        )

    def latest_reading(self, astronaut_id: str) -> VitalReading | None:
        return self.latest.get(astronaut_id)

    def current_activity(self, astronaut_id: str, now: datetime) -> tuple[str, float]:
        return activity_at(self.engine.profiles[astronaut_id], now, self.engine.seed)

    def open_alerts_for(self, astronaut_id: str | None = None) -> list[AlertRecord]:
        return [
            a for a in self.evaluator.open_alerts() if astronaut_id in (None, a.astronaut_id)
        ]

    def active_scenarios(self, now: datetime, astronaut_id: str | None = None) -> list[ActiveScenario]:
        return [
            s
            for s in self.engine.active_scenarios(now)
            if astronaut_id is None or s.affects(astronaut_id)
        ]

    # ---------------------------------------------------------- operator actions ----
    def _require_control(self) -> None:
        if not self.settings.simulation_control_enabled:
            raise ForbiddenError("Simulation control is disabled on this deployment.")

    async def start_scenario(self, req: SimulationEventCreate) -> SimulationEvent:
        self._require_control()
        scenario = Scenario(req.scenario)
        spec = SCENARIOS[scenario]
        if not spec.crew_wide:
            if req.astronaut_id is None:
                raise ConflictError("This scenario needs an astronaut_id.")
            if req.astronaut_id not in self.engine.profiles:
                raise NotFoundError(f"Astronaut {req.astronaut_id} not found.")
        now = utcnow()
        target = None if spec.crew_wide else req.astronaut_id
        # One running scenario per target (each astronaut, plus one crew-wide slot).
        clash = [
            s for s in self.engine.active_scenarios(now)
            if s.cancelled_at is None and s.astronaut_id == target
        ]
        if clash:
            raise ConflictError(
                "A test scenario is already running for this target.",
                details={"scenario_id": clash[0].id},
            )
        active = self.engine.start_scenario(
            scenario,
            req.astronaut_id,
            now,
            intensity=req.intensity,
            duration_s=req.duration_seconds,
            triggered_by="operator",
        )
        async with self.session_factory() as session:
            await events_repo.upsert(session, [active])
            await session.commit()
        await self._send_simulation("started", active, now)
        logger.info("operator started %s for %s", scenario.value, target or "crew")
        return mappers.scenario_schema(active, now)

    async def start_scenario_group(
        self,
        components: list[tuple[Scenario, float]],
        astronaut_id: str | None,
        duration_s: int,
        now: datetime | None = None,
    ) -> list[ActiveScenario]:
        """Start several scenarios on one target at once (emergency simulator composites).

        The same one-run-per-target rule applies: nothing may already be running on the target.
        """
        self._require_control()
        now = now or utcnow()
        crew_wide = all(SCENARIOS[s].crew_wide for s, _ in components)
        target = None if crew_wide else astronaut_id
        if target is not None and target not in self.engine.profiles:
            raise NotFoundError(f"Astronaut {target} not found.")
        clash = [s for s in self.engine.active_scenarios(now) if s.cancelled_at is None and s.astronaut_id == target]
        if clash:
            raise ConflictError("A test scenario is already running for this target.",
                                details={"scenario_id": clash[0].id})
        started = [
            self.engine.start_scenario(scenario, target, now, intensity=intensity, duration_s=duration_s,
                                       triggered_by="operator")
            for scenario, intensity in components
        ]
        async with self.session_factory() as session:
            await events_repo.upsert(session, started)
            await session.commit()
        for active in started:
            await self._send_simulation("started", active, now)
        logger.info("operator started %s for %s", "+".join(s.scenario.value for s in started), target or "crew")
        return started

    async def cancel_scenario(self, scenario_id: str) -> SimulationEvent:
        self._require_control()
        now = utcnow()
        active = self.engine.cancel_scenario(scenario_id, now)
        if active is None:
            raise NotFoundError(f"No running scenario with id {scenario_id}.")
        async with self.session_factory() as session:
            await events_repo.upsert(session, [active])
            await session.commit()
        await self._send_simulation("cancelled", active, now)
        return mappers.scenario_schema(active, now)

    async def update_alert(self, alert_id: str, action: str, note: str | None) -> Alert:
        now = utcnow()
        async with self.session_factory() as session:
            row = await alerts_repo.get(session, alert_id)
            if row is None:
                raise NotFoundError(f"Alert {alert_id} not found.")
            record = self.evaluator.find(alert_id) or alerts_repo.row_to_record(row)
            if record.status == "resolved":
                raise ConflictError("This alert is already resolved.")
            if action == "acknowledge":
                if record.status == "acknowledged":
                    raise ConflictError("This alert is already acknowledged.")
                record.status = "acknowledged"
                record.acknowledged_at = now
            else:
                record.status = "resolved"
                record.resolved_at = now
                record.acknowledged_at = record.acknowledged_at or now
            if note:
                record.operator_note = note
            record.updated_at = now
            await alerts_repo.upsert(session, [record])
            await session.commit()
        if action == "resolve":
            self.evaluator.release(alert_id)
        await self._send_alert("acknowledged" if action == "acknowledge" else "resolved", record)
        return mappers.alert_schema(record)
