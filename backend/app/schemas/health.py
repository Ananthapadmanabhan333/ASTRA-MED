from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.schemas.common import (
    DATA_SOURCE_FIELD,
    ActivityState,
    ApiModel,
    CrewStatus,
    DataSource,
    Metric,
    Rhythm,
    TimeRange,
)


class VitalReading(ApiModel):
    astronaut_id: str
    ts: datetime
    heart_rate: float = Field(description="Beats per minute")
    spo2: float = Field(description="Peripheral oxygen saturation, %")
    systolic: float = Field(description="mmHg")
    diastolic: float = Field(description="mmHg")
    temperature_c: float = Field(description="Core body temperature, °C")
    respiratory_rate: float = Field(description="Breaths per minute")
    activity_state: ActivityState
    activity_met: float = Field(description="Metabolic equivalent of current activity")
    rhythm: Rhythm = Field(description="Rhythm classified from synthetic ECG beat intervals")
    hrv_rmssd_ms: float | None = Field(
        default=None, description="RMSSD over recent beats; null for backfilled history"
    )
    scenario: str | None = Field(
        default=None, description="Injected test scenario affecting this reading, if any"
    )
    data_source: DataSource = DATA_SOURCE_FIELD


class SleepSession(ApiModel):
    astronaut_id: str
    night: date
    scheduled_start: datetime
    scheduled_end: datetime
    start: datetime
    end: datetime
    duration_hours: float
    efficiency_pct: float
    onset_offset_minutes: float = Field(description="Actual minus scheduled sleep start")
    data_source: DataSource = DATA_SOURCE_FIELD


class SleepSummary(ApiModel):
    target_hours: float
    last_night_hours: float | None
    last_night_efficiency_pct: float | None
    average_7d_hours: float | None
    sleep_debt_7d_hours: float | None = Field(description="Sum of target minus actual over 7 nights")


class ActivitySummary(ApiModel):
    current_state: ActivityState | None
    current_met: float | None
    exercise_minutes_today: float
    exercise_target_minutes: int


class RadiationBrief(ApiModel):
    mission_dose_msv: float
    career_dose_msv: float
    career_limit_pct: float


class HealthSnapshot(ApiModel):
    astronaut_id: str
    generated_at: datetime
    status: CrewStatus
    latest: VitalReading | None
    sleep: SleepSummary
    activity: ActivitySummary
    radiation: RadiationBrief
    open_alerts: list[Alert]
    active_scenarios: list[SimulationEvent]
    data_source: DataSource = DATA_SOURCE_FIELD


class HistoryPoint(ApiModel):
    ts: datetime
    heart_rate: float
    spo2: float
    systolic: float
    diastolic: float
    temperature_c: float
    respiratory_rate: float
    activity_met: float
    samples: int = Field(description="Raw samples averaged into this point")


class HistorySeries(ApiModel):
    astronaut_id: str
    range: TimeRange
    start: datetime
    end: datetime
    resolution_seconds: int
    points: list[HistoryPoint]
    data_source: DataSource = DATA_SOURCE_FIELD


class SeriesPoint(ApiModel):
    ts: datetime
    value: float


class CrewSeries(ApiModel):
    astronaut_id: str
    name: str
    points: list[SeriesPoint]


class ComparisonSeries(ApiModel):
    metric: Metric
    range: TimeRange
    start: datetime
    end: datetime
    resolution_seconds: int
    series: list[CrewSeries]
    data_source: DataSource = DATA_SOURCE_FIELD


from app.schemas.alerts import Alert  # noqa: E402
from app.schemas.simulation import SimulationEvent  # noqa: E402

HealthSnapshot.model_rebuild()
