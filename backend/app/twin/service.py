"""Maintains each crew member's digital twin: one summary row per mission day.

Days inside the vitals retention window are summarised from stored samples (basis ``stored``).
Older days, whose samples were pruned, are recomputed with the same deterministic simulator and
seed (basis ``regenerated``) and labelled as such. Today's row is refreshed every few minutes, so
the twin follows new measurements; the live reading itself comes from the monitoring service.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.models import (
    AlertRow,
    EmergencyRunRow,
    RadiationDoseRow,
    SimulationEventRow,
    SleepSessionRow,
    TwinDailyRow,
)
from app.repositories import vitals as vitals_repo
from app.services.monitoring import MonitoringService
from app.simulator.schedule import night_plan
from app.twin import summary as S
from app.twin.stages import stage_for

logger = logging.getLogger("astra.twin")

REFRESH_S = 300.0
REGEN_INTERVAL = timedelta(minutes=5)
STORED_MIN_HOUR_FRACTION = 0.8  # share of the day's hours that must have stored samples
SAMPLE_COLUMNS = (*S.METRICS, "activity_state", "activity_met", "rhythm", "scenario")


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0), tzinfo=UTC)
    return start, start + timedelta(days=1)


class TwinService:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession], monitor: MonitoringService) -> None:
        self.settings = settings
        self.factory = factory
        self.monitor = monitor
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.updated_at: dict[str, datetime] = {}
        self.ready = asyncio.Event()

    # ------------------------------------------------------------------ lifecycle ----
    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="astra-twin")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        try:
            await self.refresh(full=True)
        except Exception:
            logger.exception("initial twin build failed")
        self.ready.set()
        while True:
            await asyncio.sleep(REFRESH_S)
            try:
                await self.refresh(full=False)
            except Exception:
                logger.exception("twin refresh failed")

    def mission_day(self, d: date) -> int:
        return (d - self.settings.mission_start_date).days

    # -------------------------------------------------------------------- refresh ----
    async def refresh(self, full: bool = False, astronaut_id: str | None = None, now: datetime | None = None) -> int:
        """Recompute missing/incomplete days (full) or just yesterday and today. Returns rows written."""
        now = now or utcnow()
        today = now.date()
        first = self.settings.mission_start_date
        ids = [astronaut_id] if astronaut_id else list(self.monitor.engine.profiles)
        written = 0
        async with self._lock, self.factory() as session:
            for aid in ids:
                existing = {
                    r.day: r for r in (await session.scalars(
                        select(TwinDailyRow).where(TwinDailyRow.astronaut_id == aid)
                    )).all()
                }
                days = (
                    [first + timedelta(days=i) for i in range((today - first).days + 1)]
                    if full else [d for d in (today - timedelta(days=1), today) if d >= first]
                )
                for d in days:
                    row = existing.get(d)
                    if row is not None and row.complete and full:
                        continue
                    values = await self.compute_day(session, aid, d, now)
                    if row is None:
                        session.add(TwinDailyRow(astronaut_id=aid, day=d, **values))
                    else:
                        for k, v in values.items():
                            setattr(row, k, v)
                    written += 1
                await session.commit()
                self.updated_at[aid] = now
        return written

    async def compute_day(self, session: AsyncSession, aid: str, d: date, now: datetime) -> dict[str, Any]:
        engine = self.monitor.engine
        profile = engine.profiles[aid]
        start, end = day_bounds(d)
        until = min(end, now)
        complete = end <= now
        rows = await vitals_repo.fetch_range(session, aid, start, until - timedelta(microseconds=1), columns=SAMPLE_COLUMNS)
        df = S.frame(rows, ("ts", *SAMPLE_COLUMNS))
        expected_hours = max(1, int((until - start).total_seconds() // 3600))
        hours = int(df["ts"].dt.floor("h").nunique()) if not df.empty else 0
        basis = "stored"
        scenarios: list[dict[str, Any]] = []
        if complete and hours < STORED_MIN_HOUR_FRACTION * expected_hours:
            basis = "regenerated"
            historical = [s for s in engine.historical_scenarios(start - timedelta(days=1), end + timedelta(days=1))
                          if s.affects(aid) and s.started_at < end and s.ends_at > start]
            readings = list(engine.history(profile, start, end, REGEN_INTERVAL, historical))
            df = S.frame([{c: getattr(r, c) for c in ("ts", *SAMPLE_COLUMNS)} for r in readings], ("ts", *SAMPLE_COLUMNS))
            scenarios = [{"scenario": s.scenario.value, "label": s.spec.label, "started_at": s.started_at.isoformat(),
                          "triggered_by": s.triggered_by, "source": "regenerated"} for s in historical]
        interval = S.sample_interval_s(df)
        events = await self._events(session, aid, start, end, include_alerts=basis == "stored")
        if basis == "stored":
            scenarios = events.pop("scenarios")
        else:
            events.pop("scenarios")
        events["scenarios"] = scenarios
        return {
            "mission_day": self.mission_day(d),
            "stage": stage_for(self.mission_day(d)).key,
            "basis": basis,
            "complete": complete,
            "metrics": S.summarize_metrics(df),
            "activity": S.summarize_activity(df, interval),
            "sleep": await self._sleep(session, aid, d, now),
            "radiation": await self._radiation(session, aid, d),
            "events": events,
            "coverage": S.coverage(df, interval, (until - start).total_seconds()) | {"expected_hours": expected_hours},
            "computed_at": now,
        }

    async def _sleep(self, session: AsyncSession, aid: str, night: date, now: datetime) -> dict[str, Any] | None:
        row = await session.scalar(select(SleepSessionRow).where(
            SleepSessionRow.astronaut_id == aid, SleepSessionRow.night == night))
        if row is not None:
            return {"duration_hours": round(row.duration_hours, 2), "efficiency_pct": round(row.efficiency_pct, 1),
                    "start": row.start.isoformat(), "end": row.end.isoformat(), "basis": "stored"}
        plan = night_plan(self.monitor.engine.profiles[aid], night, self.monitor.engine.seed)
        if plan.end > now:
            return None
        return {"duration_hours": round(plan.duration_hours, 2), "efficiency_pct": round(plan.efficiency_pct, 1),
                "start": plan.start.isoformat(), "end": plan.end.isoformat(), "basis": "regenerated"}

    @staticmethod
    async def _radiation(session: AsyncSession, aid: str, d: date) -> dict[str, Any] | None:
        row = await session.scalar(select(RadiationDoseRow).where(
            RadiationDoseRow.astronaut_id == aid, RadiationDoseRow.day == d))
        if row is None:
            return None
        return {"dose_msv": round(row.dose_msv, 4), "solar_particle_event": row.solar_particle_event,
                "category": "simulated"}

    @staticmethod
    async def _events(session: AsyncSession, aid: str, start: datetime, end: datetime, include_alerts: bool) -> dict[str, Any]:
        alerts = list((await session.scalars(select(AlertRow).where(
            AlertRow.astronaut_id == aid, AlertRow.opened_at >= start, AlertRow.opened_at < end
        ).order_by(AlertRow.opened_at))).all()) if include_alerts else []
        sims = list((await session.scalars(select(SimulationEventRow).where(
            and_(SimulationEventRow.started_at >= start, SimulationEventRow.started_at < end),
            (SimulationEventRow.astronaut_id == aid) | SimulationEventRow.astronaut_id.is_(None),
        ))).all())
        runs = list((await session.scalars(select(EmergencyRunRow).where(
            EmergencyRunRow.started_at >= start, EmergencyRunRow.started_at < end,
            (EmergencyRunRow.astronaut_id == aid) | EmergencyRunRow.astronaut_id.is_(None),
        ))).all())
        return {
            "alerts_available": include_alerts,
            "alert_counts": dict(Counter(a.severity for a in alerts)),
            "alerts": [{"id": a.id, "title": a.title, "severity": a.severity, "metric": a.metric,
                        "opened_at": a.opened_at.isoformat(), "scenario": a.scenario} for a in alerts[:20]],
            "scenarios": [{"scenario": s.scenario, "started_at": s.started_at.isoformat(),
                           "triggered_by": s.triggered_by, "source": "stored"} for s in sims],
            "emergency_runs": [{"id": r.id, "label": r.label, "severity": r.severity,
                                "started_at": r.started_at.isoformat()} for r in runs],
        }

    # ---------------------------------------------------------------------- reads ----
    async def days(self, aid: str, first: date | None = None, last: date | None = None) -> list[TwinDailyRow]:
        stmt = select(TwinDailyRow).where(TwinDailyRow.astronaut_id == aid)
        if first:
            stmt = stmt.where(TwinDailyRow.day >= first)
        if last:
            stmt = stmt.where(TwinDailyRow.day <= last)
        async with self.factory() as session:
            return list((await session.scalars(stmt.order_by(TwinDailyRow.day))).all())

    async def ensure(self, aid: str) -> None:
        """Build the twin on demand if the background task has not reached this crew member yet."""
        async with self.factory() as session:
            have = await session.scalar(select(TwinDailyRow.id).where(TwinDailyRow.astronaut_id == aid).limit(1))
        if have is None:
            await self.refresh(full=True, astronaut_id=aid)


def daily_series(rows: list[TwinDailyRow], metric: str, statistic: str) -> pd.DataFrame:
    data = []
    for r in rows:
        value = None
        if metric == "sleep_duration_hours":
            value = (r.sleep or {}).get("duration_hours")
        elif metric == "sleep_efficiency_pct":
            value = (r.sleep or {}).get("efficiency_pct")
        elif metric == "dose_msv":
            value = (r.radiation or {}).get("dose_msv")
        elif metric == "exercise_minutes":
            value = (r.activity or {}).get("exercise_minutes")
        else:
            value = (r.metrics.get(metric) or {}).get(statistic)
        data.append({"day": r.day, "mission_day": r.mission_day, "stage": r.stage, "basis": r.basis,
                     "complete": r.complete, "value": value})
    return pd.DataFrame(data)
