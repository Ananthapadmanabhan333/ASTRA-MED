"""Mission-level views: status strip and crew radiation overview."""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import astronauts as astronauts_repo
from app.repositories import sleep_radiation as sr_repo
from app.schemas.mission import CrewStatusCounts, MissionStatus
from app.schemas.radiation import CrewRadiation, DailyDose, RadiationOverview
from app.services.health import crew_status
from app.services.monitoring import MonitoringService
from app.simulator.radiation import (
    CAREER_LIMIT_MSV,
    GCR_DOSE_RATE_MSV_PER_DAY,
    dose_rate_msv_per_second,
)

AU_LIGHT_SECONDS = 499.005
TRANSIT_DAYS = 240


def earth_distance_au(mission_day: float) -> float:
    """Smooth stand-in for an Earth–Mars transfer: departure near 0 AU, ~1.5 AU on arrival."""
    x = min(mission_day, TRANSIT_DAYS) / TRANSIT_DAYS
    return round(0.02 + 1.45 * (1 - math.cos(math.pi * x)) / 2, 3)


def _habitat_dose_multiplier(monitor: MonitoringService, now: datetime) -> float:
    multiplier = 1.0
    for s in monitor.active_scenarios(now):
        level = s.envelope(now)
        multiplier = max(multiplier, 1 + (s.spec.dose_rate_multiplier - 1) * level)
    return multiplier


def mission_status(monitor: MonitoringService, now: datetime) -> MissionStatus:
    settings = monitor.settings
    start = datetime.combine(settings.mission_start_date, time(0), tzinfo=UTC)
    elapsed = max(0.0, (now - start).total_seconds())
    mission_day = elapsed / 86400

    alerts = monitor.open_alerts_for()
    statuses = Counter(
        crew_status([a for a in alerts if a.astronaut_id == aid]) for aid in monitor.engine.profiles
    )
    multiplier = _habitat_dose_multiplier(monitor, now)
    distance = earth_distance_au(mission_day)
    return MissionStatus(
        mission_name=settings.mission_name,
        phase=settings.mission_phase,
        mission_start=settings.mission_start_date,
        mission_day=int(mission_day),
        mission_elapsed_seconds=round(elapsed, 1),
        server_time=now,
        earth_distance_au=distance,
        one_way_light_delay_s=round(distance * AU_LIGHT_SECONDS, 1),
        crew_count=len(monitor.engine.profiles),
        crew_status=CrewStatusCounts(**{k: statuses.get(k, 0) for k in ("nominal", "advisory", "caution", "critical")}),
        open_alerts=len(alerts),
        critical_alerts=sum(1 for a in alerts if a.severity == "critical"),
        active_scenarios=len(monitor.active_scenarios(now)),
        habitat_dose_rate_msv_day=round(GCR_DOSE_RATE_MSV_PER_DAY * multiplier, 3),
        simulator_running=monitor.running,
    )


async def radiation_overview(
    monitor: MonitoringService, session: AsyncSession, now: datetime, days: int
) -> RadiationOverview:
    multiplier = _habitat_dose_multiplier(monitor, now)
    since = now.date() - timedelta(days=days - 1)
    crew = []
    for row in await astronauts_repo.list_astronauts(session):
        mission = await sr_repo.mission_total(session, row.id)
        career = row.prior_career_dose_msv + mission
        profile = monitor.engine.profiles[row.id]
        crew.append(
            CrewRadiation(
                astronaut_id=row.id,
                name=row.name,
                prior_career_dose_msv=row.prior_career_dose_msv,
                mission_dose_msv=round(mission, 2),
                career_dose_msv=round(career, 2),
                career_limit_pct=round(100 * career / CAREER_LIMIT_MSV, 1),
                dose_rate_msv_day=round(dose_rate_msv_per_second(profile, multiplier) * 86400, 3),
                daily=[
                    DailyDose(
                        day=d.day,
                        mission_day=d.mission_day,
                        dose_msv=round(d.dose_msv, 3),
                        solar_particle_event=d.solar_particle_event,
                    )
                    for d in await sr_repo.daily_doses(session, row.id, since)
                ],
            )
        )
    return RadiationOverview(
        reference_career_limit_msv=CAREER_LIMIT_MSV,
        reference_note=(
            "Reference only: NASA-STD-3001 Vol. 1 Rev. B (2022) sets a 600 mSv career effective-dose "
            "limit. Doses shown here are simulated."
        ),
        gcr_reference_rate_msv_day=GCR_DOSE_RATE_MSV_PER_DAY,
        crew=crew,
    )
