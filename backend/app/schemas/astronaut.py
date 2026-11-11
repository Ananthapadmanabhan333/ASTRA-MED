from __future__ import annotations

from pydantic import Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, CrewStatus, DataSource
from app.schemas.health import VitalReading


class BaselineVitals(ApiModel):
    heart_rate: float
    spo2: float
    systolic: float
    diastolic: float
    temperature_c: float
    respiratory_rate: float
    hrv_sdnn_ms: float


class Astronaut(ApiModel):
    id: str
    name: str = Field(description="Fictional crew member")
    role: str
    specialty: str
    age: int
    sex: str
    height_cm: int
    mass_kg: float
    blood_type: str
    prior_career_dose_msv: float
    sleep_start_hour: float = Field(description="Scheduled sleep start, hours UTC (mission time)")
    sleep_target_hours: float
    exercise_target_minutes: int
    baseline: BaselineVitals
    data_source: DataSource = DATA_SOURCE_FIELD


class AstronautSummary(Astronaut):
    status: CrewStatus
    latest: VitalReading | None
    open_alerts: int
    active_scenario: str | None
