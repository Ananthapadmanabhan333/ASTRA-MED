from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource

EmergencyKey = Literal[
    "hr_elevation", "desaturation", "abnormal_respiration", "sleep_disruption", "multiple_deviations",
    "radiation_event", "environmental_anomaly",
]
SeverityLevel = Literal["mild", "moderate", "severe"]
RunStatus = Literal["running", "completed", "cancelled"]


class SeverityOption(ApiModel):
    key: SeverityLevel
    intensity: float


class ComponentInfo(ApiModel):
    scenario: str
    factor: float


class EmergencyScenarioInfo(ApiModel):
    key: EmergencyKey
    label: str
    description: str
    crew_wide: bool
    default_duration_s: int
    overlay: Literal["sleep", "habitat"] | None
    observe: list[str]
    components: list[ComponentInfo]
    severities: list[SeverityOption]


class EmergencyRunCreate(BaseModel):
    scenario: EmergencyKey
    astronaut_id: str | None = Field(default=None, description="Required unless the scenario is crew-wide")
    severity: SeverityLevel = "moderate"
    duration_seconds: int | None = Field(default=None, ge=30, le=3600)
    nights: int = Field(default=3, ge=1, le=7, description="Sleep disruption: recent nights in the what-if overlay")


class RunComponent(ApiModel):
    event_id: str
    scenario: str
    label: str
    intensity: float
    astronaut_id: str | None


class EmergencyRun(ApiModel):
    id: str
    scenario: EmergencyKey
    label: str
    astronaut_id: str | None
    severity: SeverityLevel
    intensity: float
    duration_s: int
    started_at: datetime
    ends_at: datetime
    cancelled_at: datetime | None
    status: RunStatus
    created_by: str | None
    components: list[RunComponent]
    overlay: dict[str, Any] | None
    analyses: list[dict[str, Any]]
    label_simulated: str
    data_source: DataSource = DATA_SOURCE_FIELD


class EmergencyAnalysis(ApiModel):
    id: str
    ts: datetime
    requested_by: str
    run_status: RunStatus
    window: dict[str, datetime]
    crew: list[dict[str, Any]]
    label: str
    note: str


class TimelineEvent(ApiModel):
    ts: datetime
    kind: str
    label: str
    severity: str | None = None
    alert_id: str | None = None
    analysis_id: str | None = None


class EmergencyTimeline(ApiModel):
    run_id: str
    astronaut_id: str
    start: datetime
    end: datetime
    status: RunStatus
    vitals: list[dict[str, Any]]
    events: list[TimelineEvent]
    environment: list[dict[str, Any]]
    overlay: dict[str, Any] | None
    label: str
    data_source: DataSource = DATA_SOURCE_FIELD
