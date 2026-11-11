from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RadiationDoseRow, SleepSessionRow
from app.simulator.schedule import NightPlan


# ------------------------------------------------------------------------- sleep ----
async def existing_nights(session: AsyncSession, astronaut_id: str) -> set[date]:
    rows = await session.scalars(
        select(SleepSessionRow.night).where(SleepSessionRow.astronaut_id == astronaut_id)
    )
    return set(rows.all())


def plan_to_row(astronaut_id: str, plan: NightPlan) -> SleepSessionRow:
    return SleepSessionRow(
        astronaut_id=astronaut_id,
        night=plan.night,
        scheduled_start=plan.scheduled_start,
        scheduled_end=plan.scheduled_end,
        start=plan.start,
        end=plan.end,
        duration_hours=round(plan.duration_hours, 2),
        efficiency_pct=plan.efficiency_pct,
    )


async def add_nights(session: AsyncSession, astronaut_id: str, plans: Iterable[NightPlan]) -> None:
    session.add_all([plan_to_row(astronaut_id, p) for p in plans])


async def list_sleep(
    session: AsyncSession, astronaut_id: str, since: date, limit: int = 60
) -> list[SleepSessionRow]:
    stmt = (
        select(SleepSessionRow)
        .where(SleepSessionRow.astronaut_id == astronaut_id, SleepSessionRow.night >= since)
        .order_by(SleepSessionRow.night.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


# --------------------------------------------------------------------- radiation ----
async def existing_dose_days(session: AsyncSession, astronaut_id: str) -> set[date]:
    rows = await session.scalars(
        select(RadiationDoseRow.day).where(RadiationDoseRow.astronaut_id == astronaut_id)
    )
    return set(rows.all())


async def add_dose(
    session: AsyncSession,
    astronaut_id: str,
    day: date,
    mission_day: int,
    dose_msv: float,
    solar_particle_event: bool = False,
) -> None:
    row = await session.scalar(
        select(RadiationDoseRow).where(
            RadiationDoseRow.astronaut_id == astronaut_id, RadiationDoseRow.day == day
        )
    )
    if row is None:
        session.add(
            RadiationDoseRow(
                astronaut_id=astronaut_id,
                day=day,
                mission_day=mission_day,
                dose_msv=dose_msv,
                solar_particle_event=solar_particle_event,
            )
        )
    else:
        row.dose_msv += dose_msv
        row.solar_particle_event = row.solar_particle_event or solar_particle_event


async def mission_total(session: AsyncSession, astronaut_id: str) -> float:
    value = await session.scalar(
        select(func.sum(RadiationDoseRow.dose_msv)).where(RadiationDoseRow.astronaut_id == astronaut_id)
    )
    return float(value or 0.0)


async def daily_doses(
    session: AsyncSession, astronaut_id: str, since: date
) -> list[RadiationDoseRow]:
    stmt = (
        select(RadiationDoseRow)
        .where(RadiationDoseRow.astronaut_id == astronaut_id, RadiationDoseRow.day >= since)
        .order_by(RadiationDoseRow.day)
    )
    return list((await session.scalars(stmt)).all())
