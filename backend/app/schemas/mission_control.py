"""Phase 6 API contract: unified events and alerts, crew monitoring, command dashboard, mission
simulation sandbox, analytics and system reliability."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.alerts import Alert
from app.schemas.common import ActivityState, ApiModel
from app.schemas.health import VitalReading
from app.schemas.mission import MissionStatus

EventSeverity = Literal["info", "advisory", "caution", "critical"]
Context = Literal["operations", "simulation"]
DataOrigin = Literal["simulated", "sandbox", "nasa", "system"]
AlertCenterStatus = Literal["open", "acknowledged", "resolved"]


# ------------------------------------------------------------------- events ----
class MissionEvent(ApiModel):
    id: str
    source: str
    source_label: str
    kind: str
    category: str
    category_label: str
    severity: EventSeverity
    priority: int = Field(ge=1, le=4, description="1 critical, 2 high, 3 medium, 4 low")
    priority_label: str
    priority_score: float
    title: str
    summary: str | None = None
    astronaut_id: str | None = None
    context: Context
    simulation_id: str | None = None
    data_origin: DataOrigin
    data_origin_label: str
    classification: str | None = None
    classification_note: str | None = None
    experimental: bool
    confidence: float | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    occurred_at: datetime = Field(description="Source time in UTC (the simulation clock for sandbox events)")
    received_at: datetime = Field(description="Wall-clock UTC time the pipeline received the event")
    last_seen_at: datetime
    latency_s: float
    clock_skew_s: float | None = Field(default=None, description="Seconds a future source timestamp was clamped by")
    occurrences: int = Field(description="How many times this event was reported (duplicates merged)")
    payload: dict[str, Any]


class EventCounts(ApiModel):
    total: int
    by_category: dict[str, int]
    by_source: dict[str, int]
    by_priority: dict[str, int]
    by_origin: dict[str, int]
    by_severity: dict[str, int]


class EventLane(ApiModel):
    key: str
    label: str
    items: list[MissionEvent]


class MissionTimeline(ApiModel):
    start: datetime
    end: datetime
    astronaut_id: str | None
    context: Context
    simulation_id: str | None
    lanes: list[EventLane]
    counts: EventCounts
    notes: list[str]


# ------------------------------------------------------------------- alerts ----
class MissionAlert(ApiModel):
    id: str = Field(description="Alert identifier")
    source: str = Field(description="Source module")
    source_label: str
    source_ref: str
    event_id: str | None = None
    astronaut_id: str | None = None
    context: Context
    simulation_id: str | None = None
    data_origin: DataOrigin
    data_origin_label: str
    category: str
    category_label: str
    classification: str
    classification_label: str
    classification_note: str
    experimental: bool = Field(description="Experimental AI prediction: never a confirmed medical emergency")
    severity: EventSeverity
    priority: int = Field(ge=1, le=4)
    priority_label: str
    title: str
    summary: str | None = None
    status: AlertCenterStatus
    created_at: datetime = Field(description="When the condition was observed (source time)")
    updated_at: datetime
    received_at: datetime
    measurements: dict[str, Any] = Field(description="Supporting measurements")
    explanation: dict[str, Any] = Field(description="Rule or AI explanation")
    confidence: float | None = Field(default=None, description="0-1 for model output; null for deterministic rules")
    confidence_level: str | None = None
    uncertainty: list[str]
    correlations: dict[str, Any]
    condition_cleared_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    ack_note: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_notes: str | None = None
    occurrences: int
    data_source: Literal["simulated", "nasa"]


class MissionAlertAction(ApiModel):
    id: int
    alert_id: str
    ts: datetime
    action: str
    from_status: str | None = None
    to_status: str | None = None
    actor: str
    actor_role: str | None = None
    note: str | None = None
    detail: dict[str, Any]


class MissionAlertDetail(MissionAlert):
    actions: list[MissionAlertAction] = Field(description="Audit trail of every lifecycle transition")
    event: MissionEvent | None = None


class AlertCenterSummary(ApiModel):
    open: int
    acknowledged: int
    unresolved: int
    resolved_24h: int
    by_priority: dict[str, int]
    by_source: dict[str, int]
    experimental_open: int
    oldest_unresolved_at: datetime | None = None
    mean_minutes_to_acknowledge_7d: float | None = None
    context: str | None = None


class AlertCenterAction(BaseModel):
    note: str | None = Field(default=None, max_length=2000, description="Acknowledgement note or resolution notes")


# ------------------------------------------------------------ crew monitoring ----
class Deviation(ApiModel):
    signal: str
    label: str
    unit: str
    value: float
    expected: float | None = None
    z: float | None = None
    percentile: float | None = None
    basis: str
    flag: Literal["edge", "outside", "far"] | None = None


class Deviations(ApiModel):
    available: bool
    reason: str | None = None
    ts: datetime | None = None
    activity_state: str | None = None
    signals: list[Deviation] = []
    baseline_fitted_at: datetime | None = None
    windows_used: int | None = None
    method: str | None = None


class CrewAI(ApiModel):
    available: bool
    reason: str | None = None
    generated_at: datetime | None = None
    model_version: str | None = None
    risk_score: float | None = None
    category: str | None = None
    category_label: str | None = None
    health_score: int | None = None
    confidence: dict[str, Any] | None = None
    what_changed: str | None = None
    warnings: list[dict[str, Any]] = []
    anomaly: dict[str, Any] | None = None
    contributors: list[dict[str, Any]] = []


class CrewTrendPoint(ApiModel):
    day: date
    heart_rate: float | None = None
    spo2: float | None = None
    respiratory_rate: float | None = None
    temperature_c: float | None = None
    sleep_hours: float | None = None
    dose_msv: float | None = None


class CrewMonitorCard(ApiModel):
    astronaut_id: str
    name: str
    role: str
    specialty: str
    status: Literal["nominal", "advisory", "caution", "critical"]
    live: bool = Field(description="A reading arrived within the live window")
    last_reading_age_s: float | None = None
    latest: VitalReading | None = None
    deviations: Deviations
    open_rule_alerts: list[Alert]
    open_alerts: list[MissionAlert]
    ai: CrewAI
    trend_7d: list[CrewTrendPoint]
    active_scenarios: list[str]
    mission_dose_msv: float | None = None
    data_source: Literal["simulated"] = "simulated"


class CrewMonitoring(ApiModel):
    generated_at: datetime
    ai_sweep_at: datetime | None = None
    crew: list[CrewMonitorCard]
    notes: list[str]


# ------------------------------------------------------------------ dashboard ----
class ComponentStatus(ApiModel):
    key: str
    label: str
    status: Literal["ok", "degraded", "down", "disabled", "unavailable"]
    detail: str
    metrics: dict[str, Any] = {}


class DashboardSection(ApiModel):
    available: bool = True
    reason: str | None = None
    data: dict[str, Any] = {}


class MissionControlOverview(ApiModel):
    generated_at: datetime
    mission: MissionStatus | None = None
    crew: DashboardSection
    health_monitoring: DashboardSection
    alerts: DashboardSection
    ai: DashboardSection
    space_weather: DashboardSection
    environment: DashboardSection
    radiation_timeline: DashboardSection
    incidents: DashboardSection
    connectivity: list[ComponentStatus]
    simulation: dict[str, Any]
    notes: list[str]


# ---------------------------------------------------------------- simulation ----
class SimPreset(ApiModel):
    key: str
    label: str
    description: str
    duration_minutes: int
    speed: float
    crew_size: int
    script: list[dict[str, Any]]


class SimInjectionType(ApiModel):
    key: str
    kind: Literal["health", "environment", "space_weather"]
    label: str
    description: str
    crew_wide: bool
    default_duration_s: int
    event_only: bool


class SimCatalogue(ApiModel):
    presets: list[SimPreset]
    injections: list[SimInjectionType]
    max_speed: float
    max_minutes: int
    enabled: bool
    label: str


class SimStart(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    preset: str | None = None
    crew: list[str] | None = Field(default=None, min_length=1, max_length=8)
    speed: float | None = Field(default=None, ge=0.5, le=600)
    duration_minutes: int | None = Field(default=None, ge=5, le=7 * 24 * 60)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    ai_every_minutes: int | None = Field(default=None, ge=5, le=240)


class SimSpeed(BaseModel):
    speed: float = Field(ge=0.5, le=600)


class SimInject(BaseModel):
    injection: str
    astronaut_id: str | None = None
    intensity: float = Field(default=1.0, ge=0.3, le=1.5)
    duration_s: int | None = Field(default=None, ge=30, le=4 * 3600)
    at_minute: float | None = Field(default=None, ge=0, description="Simulated minutes after start; omit for now")


class SimTelemetryReading(BaseModel):
    astronaut_id: str
    ts: datetime = Field(description="Measurement time on the simulation clock (UTC)")
    heart_rate: float | None = Field(default=None, ge=20, le=250)
    spo2: float | None = Field(default=None, ge=50, le=100)
    systolic: float | None = Field(default=None, ge=60, le=260)
    diastolic: float | None = Field(default=None, ge=30, le=160)
    temperature_c: float | None = Field(default=None, ge=30, le=43)
    respiratory_rate: float | None = Field(default=None, ge=3, le=70)
    activity_state: ActivityState | None = None
    activity_met: float | None = Field(default=None, ge=0.5, le=20)
    rhythm: Literal["regular", "irregular"] | None = None


class SimTelemetryBatch(BaseModel):
    readings: list[SimTelemetryReading] = Field(min_length=1, max_length=2000)
    source: str = Field(default="external", max_length=16)


class SimIngestResult(ApiModel):
    simulation_id: str
    received: int
    accepted: int
    rejected: int
    issues: list[dict[str, Any]]
    alerts_opened: int
    sim_time: datetime


class SimCrewReading(ApiModel):
    astronaut_id: str
    name: str
    ts: datetime
    heart_rate: float
    spo2: float
    systolic: float
    diastolic: float
    temperature_c: float
    respiratory_rate: float
    activity_state: str
    rhythm: str
    scenario: str | None = None
    status: str
    dose_msv: float


class SimState(ApiModel):
    active: bool
    status: str
    context: Literal["simulation"] = "simulation"
    data_source: Literal["simulated"] = "simulated"
    label: str
    id: str | None = None
    name: str | None = None
    preset: str | None = None
    speed: float | None = None
    step_seconds: float | None = None
    crew: list[str] = []
    sim_start: datetime | None = None
    sim_time: datetime | None = None
    sim_end: datetime | None = None
    t_plus: str | None = None
    progress: float | None = None
    wall_started_at: datetime | None = None
    created_by: str | None = None
    latest: list[SimCrewReading] = []
    active_injections: list[dict[str, Any]] = []
    next_injection: dict[str, Any] | None = None
    habitat: dict[str, Any] = {}
    dose_rate_multiplier: float | None = None
    open_alerts: int = 0
    stats: dict[str, Any] = {}
    ai_status: str | None = None
    last_ai_at: datetime | None = None
    error: str | None = None


class SimRun(ApiModel):
    id: str
    name: str
    preset: str | None
    crew: list[str]
    status: str
    speed: float
    seed: int
    sim_start: datetime
    sim_time: datetime
    sim_end: datetime
    t_plus: str
    progress: float
    wall_started_at: datetime
    wall_updated_at: datetime
    wall_ended_at: datetime | None
    created_by: str
    config: dict[str, Any]
    injections: list[dict[str, Any]]
    analyses: dict[str, Any]
    stats: dict[str, Any]
    error: str | None
    context: Literal["simulation"] = "simulation"
    data_source: Literal["simulated"] = "simulated"
    label: str


class SimSeries(ApiModel):
    astronaut_id: str
    name: str
    points: list[dict[str, Any]]


class SimPlayback(ApiModel):
    simulation: SimRun
    resolution_seconds: float
    start: datetime
    end: datetime
    series: list[SimSeries]
    injections: list[dict[str, Any]]
    events: list[MissionEvent]
    alerts: list[MissionAlert]
    label: str


class SimFrame(ApiModel):
    simulation_id: str
    at: datetime
    t_plus: str
    crew: list[dict[str, Any]]
    active_injections: list[dict[str, Any]]
    alerts: list[MissionAlert]
    label: str


class SimReportBody(BaseModel):
    alert_id: str | None = None
    astronaut_id: str | None = None


# ------------------------------------------------------------------ analytics ----
class AnalyticsSummary(ApiModel):
    generated_at: datetime
    start: date
    end: date
    context: str
    astronaut_id: str | None
    crew_trends: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    sleep: list[dict[str, Any]]
    environment: list[dict[str, Any]]
    radiation: dict[str, Any]
    model_performance: dict[str, Any]
    alert_frequency: list[dict[str, Any]]
    alert_totals: dict[str, Any]
    event_distribution: EventCounts
    notes: list[str]


# --------------------------------------------------------------------- system ----
class SystemStatus(ApiModel):
    status: Literal["ok", "degraded", "down"]
    generated_at: datetime
    version: str
    environment: str
    uptime_s: float
    components: list[ComponentStatus]
    orchestrator: dict[str, Any]


class ConsistencyCheck(ApiModel):
    key: str
    label: str
    status: Literal["ok", "repaired", "warning", "error"]
    found: int
    repaired: int
    detail: str


class ConsistencyReport(ApiModel):
    ran_at: datetime
    repair: bool
    status: Literal["ok", "repaired", "warning", "error"]
    checks: list[ConsistencyCheck]


# ------------------------------------------------------------------ websocket ----
class WsMissionEvent(ApiModel):
    type: Literal["mission_event"] = "mission_event"
    event: Literal["created", "updated"]
    item: MissionEvent


class WsMissionAlert(ApiModel):
    type: Literal["mission_alert"] = "mission_alert"
    event: Literal["opened", "escalated", "updated", "acknowledged", "resolved"]
    alert: MissionAlert


class WsSimState(ApiModel):
    type: Literal["sim_state"] = "sim_state"
    state: SimState
