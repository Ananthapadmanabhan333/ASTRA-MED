from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource


class OverviewRisk(ApiModel):
    score: float
    category: str
    category_label: str


class OverviewCrew(ApiModel):
    astronaut_id: str
    name: str
    role: str
    status: str
    open_alerts: int
    risk: OverviewRisk | None
    systems: dict[str, str]
    patterns: list[str]
    summary: str
    last_reading_at: datetime | None
    resting_hr_mean: float | None
    sleep_mean_hours: float | None
    dose_period_msv: float
    alerts_in_period: dict[str, int]
    reports_in_period: int


class OverviewAlert(ApiModel):
    id: str
    astronaut_id: str
    title: str
    severity: str
    status: str
    opened_at: datetime
    scenario: str | None


class AlertDay(ApiModel):
    day: date
    critical: int
    caution: int
    advisory: int


class OverviewIncident(ApiModel):
    id: str
    title: str
    astronaut_id: str
    occurred_at: datetime
    review_status: str


class OverviewRun(ApiModel):
    id: str
    label: str
    severity: str
    astronaut_id: str | None
    started_at: datetime


class TrendPointLite(ApiModel):
    day: date
    value: float | None
    basis: str


class CrewTrend(ApiModel):
    astronaut_id: str
    points: list[TrendPointLite]


class SummaryStatement(ApiModel):
    kind: Literal["data", "derived", "model", "nasa"]
    text: str


class MissionSummary(ApiModel):
    statements: list[SummaryStatement]
    method: str


class MissionOverview(ApiModel):
    generated_at: datetime
    period: Literal["24h", "7d", "30d"]
    start: datetime
    end: datetime
    astronaut_id: str | None
    crew: list[OverviewCrew]
    active_alerts: list[OverviewAlert]
    alert_history: list[AlertDay]
    incidents: list[OverviewIncident]
    incidents_visible: bool
    runs: list[OverviewRun]
    trends: dict[str, list[CrewTrend]]
    environment: dict[str, Any]
    summary: MissionSummary
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD
