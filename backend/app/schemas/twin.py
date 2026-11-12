from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.astronaut import Astronaut
from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, CrewStatus, DataSource
from app.schemas.health import VitalReading

Basis = Literal["stored", "regenerated"]


class CategoryInfo(ApiModel):
    key: str
    description: str


class StageRef(ApiModel):
    key: str
    label: str


class StageInfo(StageRef):
    first_day: int
    last_day: int | None


class TwinMission(ApiModel):
    day: int
    stage: StageRef
    stages: list[StageInfo]


class TwinCurrent(ApiModel):
    reading: VitalReading | None
    status: CrewStatus
    open_alerts: int
    active_scenarios: list[str]
    category: str


class ValueRef(ApiModel):
    value: float | None
    category: str
    note: str | None = None
    n_days: int | None = None
    n: int | None = None
    basis: list[str] | None = None


class Change(ApiModel):
    abs: float | None
    pct: float | None


class RestingComparison(ApiModel):
    metric: str
    label: str
    unit: str
    configured: ValueRef
    early_mission: ValueRef
    last_7d: ValueRef
    last_24h: ValueRef
    personal_baseline: ValueRef
    change_7d_vs_early: Change | None


class TwinExposure(ApiModel):
    mission_dose_msv: float
    last_30d_dose_msv: float
    spe_days: int
    career_total_msv: float
    career_limit_msv: float
    category: str
    note: str


class TwinSleep(ApiModel):
    nights: int
    mean_duration_hours: float | None
    mean_efficiency_pct: float | None
    category: str


class TwinCoverage(ApiModel):
    first_day: date | None
    last_day: date | None
    days_total: int
    days_stored: int
    days_regenerated: int
    retention_days: int


class TwinProfile(ApiModel):
    astronaut: Astronaut
    generated_at: datetime
    twin_updated_at: datetime | None
    last_measurement_at: datetime | None
    mission: TwinMission
    current: TwinCurrent
    resting_comparison: list[RestingComparison]
    exposure: TwinExposure
    sleep_7d: TwinSleep
    coverage: TwinCoverage
    categories: list[CategoryInfo]
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD


class TwinDay(ApiModel):
    day: date
    mission_day: int
    stage: str
    basis: Basis
    complete: bool
    category: Literal["simulated", "regenerated"]
    metrics: dict[str, dict[str, Any]] = Field(description="Per-signal daily statistics (derived)")
    activity: dict[str, Any]
    sleep: dict[str, Any] | None
    radiation: dict[str, Any] | None
    events: dict[str, Any]
    coverage: dict[str, Any]
    computed_at: datetime
    space_weather: dict[str, Any] = Field(description="Real NASA DONKI events that day (indicator category)")


class TwinTimeline(ApiModel):
    astronaut_id: str
    start: date
    end: date
    days: list[TwinDay]
    categories: list[CategoryInfo]
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD


class TrendPoint(ApiModel):
    day: date
    mission_day: int
    stage: str
    basis: Basis
    complete: bool
    value: float | None
    rolling_7d: float | None


class TrendFit(ApiModel):
    slope_per_30d: float
    ci95: list[float]
    n_days: int
    n_eff: float
    direction: str


class CumulativePoint(ApiModel):
    day: date
    value: float


class TwinTrend(ApiModel):
    astronaut_id: str
    metric: str
    statistic: str
    label: str
    unit: str
    points: list[TrendPoint]
    trend: TrendFit | None
    cumulative: list[CumulativePoint] | None
    category: str
    method: str
    notes: list[str]
    data_source: DataSource = DATA_SOURCE_FIELD


class StageSummary(ApiModel):
    key: str
    label: str
    first_day: int
    last_day: int | None
    n_days: int
    basis: dict[str, int]
    metrics: dict[str, dict[str, Any]]


class TwinStages(ApiModel):
    astronaut_id: str
    stages: list[StageSummary]
    statistic: str
    comparison: str
    notes: list[str]
    category: str
    data_source: DataSource = DATA_SOURCE_FIELD
