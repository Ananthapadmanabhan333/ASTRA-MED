"""Crew status and per-astronaut health snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import AstronautRow
from app.detection.evaluator import AlertRecord
from app.detection.rules import SEVERITY_RANK
from app.repositories import astronauts as astronauts_repo
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.schemas.astronaut import AstronautSummary
from app.schemas.health import (
    ActivitySummary,
    HealthSnapshot,
    RadiationBrief,
    SleepSummary,
    VitalReading,
)
from app.services import mappers
from app.services.monitoring import MonitoringService
from app.simulator.radiation import CAREER_LIMIT_MSV
from app.simulator.schedule import exercise_minutes_on


def crew_status(alerts: list[AlertRecord]) -> str:
    """Worst severity among open alerts whose condition is still present."""
    live = [a for a in alerts if a.is_open and a.condition_cleared_at is None]
    if not live:
        return "nominal"
    return max((a.severity for a in live), key=lambda s: SEVERITY_RANK[s])


async def require_astronaut(session: AsyncSession, astronaut_id: str) -> AstronautRow:
    row = await astronauts_repo.get_astronaut(session, astronaut_id)
    if row is None:
        raise NotFoundError(f"Astronaut {astronaut_id} not found.")
    return row


async def latest_reading(
    monitor: MonitoringService, session: AsyncSession, astronaut_id: str
) -> VitalReading | None:
    live = monitor.latest_reading(astronaut_id)
    if live is not None:
        return mappers.reading_schema(live)
    row = await vitals_repo.latest(session, astronaut_id)
    return mappers.reading_schema(row) if row else None


async def summaries(monitor: MonitoringService, session: AsyncSession, now: datetime) -> list[AstronautSummary]:
    out = []
    for row in await astronauts_repo.list_astronauts(session):
        alerts = monitor.open_alerts_for(row.id)
        scenarios = [s for s in monitor.active_scenarios(now, row.id) if s.astronaut_id]
        base = AstronautSummary.model_validate(
            {
                **{c.name: getattr(row, c.name) for c in AstronautRow.__table__.columns},
                "status": crew_status(alerts),
                "latest": await latest_reading(monitor, session, row.id),
                "open_alerts": len(alerts),
                "active_scenario": scenarios[0].scenario.value if scenarios else None,
            }
        )
        out.append(base)
    return out


async def sleep_summary(session: AsyncSession, row: AstronautRow, now: datetime) -> SleepSummary:
    nights = await sr_repo.list_sleep(session, row.id, now.date() - timedelta(days=8), limit=7)
    if not nights:
        return SleepSummary(
            target_hours=row.sleep_target_hours,
            last_night_hours=None,
            last_night_efficiency_pct=None,
            average_7d_hours=None,
            sleep_debt_7d_hours=None,
        )
    avg = sum(n.duration_hours for n in nights) / len(nights)
    debt = sum(max(0.0, row.sleep_target_hours - n.duration_hours) for n in nights)
    return SleepSummary(
        target_hours=row.sleep_target_hours,
        last_night_hours=round(nights[0].duration_hours, 2),
        last_night_efficiency_pct=nights[0].efficiency_pct,
        average_7d_hours=round(avg, 2),
        sleep_debt_7d_hours=round(debt, 2),
    )


async def radiation_brief(session: AsyncSession, row: AstronautRow) -> RadiationBrief:
    mission = await sr_repo.mission_total(session, row.id)
    career = row.prior_career_dose_msv + mission
    return RadiationBrief(
        mission_dose_msv=round(mission, 2),
        career_dose_msv=round(career, 2),
        career_limit_pct=round(100 * career / CAREER_LIMIT_MSV, 1),
    )


async def snapshot(
    monitor: MonitoringService, session: AsyncSession, astronaut_id: str, now: datetime
) -> HealthSnapshot:
    row = await require_astronaut(session, astronaut_id)
    profile = monitor.engine.profiles[astronaut_id]
    alerts = monitor.open_alerts_for(astronaut_id)
    latest = await latest_reading(monitor, session, astronaut_id)
    state, met = monitor.current_activity(astronaut_id, now)
    return HealthSnapshot(
        astronaut_id=astronaut_id,
        generated_at=now,
        status=crew_status(alerts),  # type: ignore[arg-type]
        latest=latest,
        sleep=await sleep_summary(session, row, now),
        activity=ActivitySummary(
            current_state=latest.activity_state if latest else state,  # type: ignore[arg-type]
            current_met=latest.activity_met if latest else round(met, 2),
            exercise_minutes_today=round(
                exercise_minutes_on(profile, now.date(), now, monitor.engine.seed), 1
            ),
            exercise_target_minutes=row.exercise_target_minutes,
        ),
        radiation=await radiation_brief(session, row),
        open_alerts=[mappers.alert_schema(a) for a in alerts],
        active_scenarios=[
            mappers.scenario_schema(s, now) for s in monitor.active_scenarios(now, astronaut_id)
        ],
    )
