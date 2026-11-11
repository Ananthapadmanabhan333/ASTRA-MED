from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AstronautRow
from app.simulator.profiles import AstronautProfile


def profile_to_row(p: AstronautProfile) -> AstronautRow:
    return AstronautRow(
        id=p.id,
        name=p.name,
        role=p.role,
        specialty=p.specialty,
        age=p.age,
        sex=p.sex,
        height_cm=p.height_cm,
        mass_kg=p.mass_kg,
        blood_type=p.blood_type,
        prior_career_dose_msv=p.prior_career_dose_msv,
        sleep_start_hour=p.sleep_start_hour,
        sleep_target_hours=p.sleep_target_hours,
        exercise_target_minutes=p.exercise_minutes,
        baseline=asdict(p.baseline),
    )


async def upsert_profiles(session: AsyncSession, profiles: Iterable[AstronautProfile]) -> None:
    for p in profiles:
        await session.merge(profile_to_row(p))


async def list_astronauts(session: AsyncSession) -> list[AstronautRow]:
    return list((await session.scalars(select(AstronautRow).order_by(AstronautRow.id))).all())


async def get_astronaut(session: AsyncSession, astronaut_id: str) -> AstronautRow | None:
    return await session.get(AstronautRow, astronaut_id)
