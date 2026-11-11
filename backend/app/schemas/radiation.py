from __future__ import annotations

from datetime import date

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource


class DailyDose(ApiModel):
    day: date
    mission_day: int
    dose_msv: float
    solar_particle_event: bool


class CrewRadiation(ApiModel):
    astronaut_id: str
    name: str
    prior_career_dose_msv: float
    mission_dose_msv: float
    career_dose_msv: float
    career_limit_pct: float
    dose_rate_msv_day: float
    daily: list[DailyDose]


class RadiationOverview(ApiModel):
    reference_career_limit_msv: float
    reference_note: str
    gcr_reference_rate_msv_day: float
    crew: list[CrewRadiation]
    data_source: DataSource = DATA_SOURCE_FIELD
