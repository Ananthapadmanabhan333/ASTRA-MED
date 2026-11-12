"""API contract for NASA open data and space-environment intelligence (phase 4).

Every payload that carries data states its ``category`` (measured, indicator, model, estimate,
simulated, metadata) and its ``freshness``: when it was retrieved and whether it is live,
cached or an offline fallback.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel
from app.schemas.radiation import CrewRadiation

Category = Literal["measured", "indicator", "model", "estimate", "simulated", "metadata"]
FreshnessMode = Literal["live", "cached", "offline-fallback", "unavailable", "pending"]
SpaceSeverity = Literal["advisory", "caution"]


class Freshness(ApiModel):
    source_id: str
    retrieved_at: datetime | None
    mode: FreshnessMode
    message: str


# --------------------------------------------------------------------- space weather ----
class SpaceWeatherEvent(ApiModel):
    id: int
    event_type: str
    type_label: str
    category: Category
    start_time: datetime
    peak_time: datetime | None
    end_time: datetime | None
    classification: str | None
    scale: str | None = Field(description="NOAA scale level where the record supports one (R for flares, G for storms)")
    severity: int | None = Field(description="1-5 scale level or CME speed class; null = unclassified")
    severity_label: str
    magnitude: float | None
    magnitude_unit: str | None
    location: str | None
    description: str | None
    instruments: list[str]
    linked_ids: list[str]
    notification_ids: list[str]
    model_derived: bool
    link: str | None
    version: int
    submitted_at: datetime | None
    retrieved_at: datetime
    endpoint: str = Field(description="Which NASA endpoint served this record (api.nasa.gov or ccmc)")
    source: str = "NASA CCMC DONKI"


class SpaceWeatherEventDetail(SpaceWeatherEvent):
    raw: dict[str, Any] = Field(description="The original DONKI record, unchanged")


class SpaceNotification(ApiModel):
    id: int
    message_id: str
    message_type: str
    issue_time: datetime
    url: str | None
    summary: str | None
    retrieved_at: datetime
    category: Category = "indicator"


class SpaceAlert(BaseModel):
    id: str
    event_id: int
    event_type: str
    severity: SpaceSeverity
    status: Literal["active", "recent", "past"]
    title: str
    event_time: datetime
    rule: str
    category: Category
    note: str
    link: str | None


class EventList(BaseModel):
    events: list[SpaceWeatherEvent]
    total: int
    freshness: Freshness


class WeatherSummary(BaseModel):
    window_days: int
    counts: dict[str, int]
    flare_classes: dict[str, int]
    strongest_flare: SpaceWeatherEvent | None
    max_storm: SpaceWeatherEvent | None
    fastest_cme: SpaceWeatherEvent | None
    latest: dict[str, SpaceWeatherEvent | None]
    alerts: list[SpaceAlert]
    notifications: list[SpaceNotification]
    caveats: list[str]
    freshness: Freshness


# ------------------------------------------------------------------------- radiation ----
class MeasuredMissionDose(BaseModel):
    mission: str
    title: str
    start: datetime
    end: datetime
    days: int
    approximate_days: int
    mean_total_mgy_day: float | None
    mean_gcr_mgy_day: float | None
    mean_saa_mgy_day: float | None
    cumulative_mgy: float


class MeasuredBlock(BaseModel):
    label: str
    description: str
    unit: str
    category: Category = "measured"
    missions: list[MeasuredMissionDose]


class IndicatorBlock(BaseModel):
    label: str
    description: str
    category: Category = "indicator"
    window_days: int
    sep_events: int
    flares_r1_plus: int
    radiation_belt_enhancements: int
    storms_g1_plus: int
    fast_cmes: int
    events: list[SpaceWeatherEvent]


class EstimateBlock(BaseModel):
    label: str
    description: str
    category: Category = "estimate"
    unit: str
    rate_msv_day: float
    mission_days: int
    mission_to_date_msv: float


class SimulatedBlock(BaseModel):
    label: str
    description: str
    category: Category = "simulated"
    unit: str
    crew: list[CrewRadiation]
    reference_career_limit_msv: float


class ExposureDay(BaseModel):
    day: date
    estimate_msv: float = Field(description="Category C estimate, mSv")
    simulated_crew_mean_msv: float | None = Field(description="Category D simulated crew mean, mSv")
    simulated_spe: bool
    indicator_events: dict[str, int] = Field(description="Category B: radiation-relevant DONKI events that day")


class RadiationIntel(BaseModel):
    measured: MeasuredBlock
    indicators: IndicatorBlock
    estimate: EstimateBlock
    simulated: SimulatedBlock
    timeline: list[ExposureDay]
    alerts: list[SpaceAlert]
    rules: list[str]
    freshness: list[Freshness]


# ----------------------------------------------------------------------------- ISS ----
class Milestone(BaseModel):
    time: datetime
    label: str


class SeriesQualityOut(BaseModel):
    quantity: str
    platform: str
    unit: str
    raw_rows: int = Field(default=0, description="Rows in the NASA response carrying this field")
    raw_points: int = Field(description="Distinct timestamps")
    valid: int
    missing: int = Field(description="Timestamps with no usable value in any row")
    out_of_range: int = Field(description="Timestamps with a physically implausible value (excluded)")
    duplicates: int = Field(description="Extra rows at an already-seen timestamp, merged")
    conflicts: int = Field(default=0, description="Merged timestamps whose values disagreed (median kept)")
    completeness: float
    first: datetime | None
    last: datetime | None
    median_interval_min: float | None
    gaps: int
    longest_gap_hours: float
    approximate_points: int
    consistency_failures: int


class EnvMission(BaseModel):
    name: str
    title: str
    description: str | None
    link: str | None
    start_time: datetime | None
    end_time: datetime | None
    telemetry_synced_at: datetime | None
    radiation_synced_at: datetime | None
    has_telemetry: bool
    has_radiation: bool
    milestones: list[Milestone]


class EnvPoint(BaseModel):
    ts: datetime
    value: float
    min: float | None = None
    max: float | None = None
    n: int = 1
    approximate: bool = False


class EnvSeries(BaseModel):
    quantity: str
    label: str
    platform: Literal["iss", "ground"]
    unit: str
    resolution: str
    category: Category = "measured"
    points: list[EnvPoint]
    quality: SeriesQualityOut | None


class OsdrStudy(ApiModel):
    accession: str
    title: str
    description: str | None
    organism: str | None
    project_type: str | None
    flight_program: str | None
    mission_name: str | None
    mission_start: datetime | None
    mission_end: datetime | None
    assay_type: str | None
    material_type: str | None
    platform: str | None
    release_date: datetime | None
    data_source_accession: str | None
    link: str
    topics: list[str]
    retrieved_at: datetime
    category: Category = "metadata"


class EnvMissionDetail(BaseModel):
    mission: EnvMission
    series: list[EnvSeries]
    space_weather: list[SpaceWeatherEvent]
    studies: list[OsdrStudy]
    caveats: list[str]
    freshness: Freshness


class StudyTopic(BaseModel):
    key: str
    label: str
    term: str


class StudyList(BaseModel):
    items: list[OsdrStudy]
    total: int
    topics: list[StudyTopic]
    freshness: Freshness


# ------------------------------------------------------------------------- sources ----
class EndpointStatus(BaseModel):
    name: str
    base_url: str
    needs_key: bool
    note: str
    available: bool
    disabled_until: datetime | None
    reason: str | None
    rate_limit_remaining: int | None
    rate_limit_limit: int | None


class SyncRun(ApiModel):
    id: int
    task: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    endpoint: str | None
    records_received: int
    records_new: int
    records_updated: int
    duplicates: int
    invalid: int
    error: str | None


class SourceHealthOut(BaseModel):
    status: Literal["unknown", "healthy", "degraded", "offline"]
    last_attempt: datetime | None
    last_success: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    last_latency_ms: float | None
    consecutive_failures: int
    requests: int
    failures: int
    cache_hits: int
    last_endpoint: str | None


class QualityIndicators(BaseModel):
    records_received: int
    invalid: int
    duplicates: int
    invalid_rate: float
    sync_runs: int
    failed_runs: int
    last_sync_status: str | None


class DataSourceStatus(BaseModel):
    id: str
    name: str
    provider: str
    homepage: str
    data_format: str
    categories: list[Category]
    update_frequency: str
    units: dict[str, str]
    license: str
    license_url: str
    citation: str
    caveats: list[str]
    endpoints: list[EndpointStatus]
    collection_start: datetime | None
    collection_end: datetime | None
    records: int
    breakdown: dict[str, int]
    availability: FreshnessMode
    availability_message: str
    health: SourceHealthOut
    quality: QualityIndicators
    recent_runs: list[SyncRun]
    running: str | None


class EvaluatedSource(BaseModel):
    name: str
    url: str
    status: str


class SourcesResponse(BaseModel):
    sources: list[DataSourceStatus]
    evaluated: list[EvaluatedSource]
    api_key_configured: bool = Field(description="Whether a personal NASA API key is set (the key itself is never exposed)")
    sync_enabled: bool
    categories: dict[str, str]


class SyncRequest(BaseModel):
    source: Literal["donki", "eda", "osdr"]
    days: int | None = Field(default=None, ge=1, le=3650, description="DONKI: days back from today")
    missions: list[str] | None = Field(default=None, max_length=30, description="EDA: missions to (re)ingest")
    force: bool = False


class SyncResult(BaseModel):
    source: str
    started_at: datetime
    finished_at: datetime
    summary: dict[str, Any]


# ------------------------------------------------------------------------ timeline ----
class TimelineItem(BaseModel):
    id: str
    lane: str
    ts: datetime
    start: datetime
    end: datetime | None
    title: str
    detail: str | None
    kind: str
    severity: str | None
    category: Category
    source: str
    link: str | None
    astronaut_id: str | None = None


class TimelineLane(BaseModel):
    key: str
    label: str
    category: Category
    items: list[TimelineItem]


class TimelinePoint(BaseModel):
    ts: datetime
    value: float
    approximate: bool = False


class TimelineSeries(BaseModel):
    key: str
    label: str
    unit: str
    category: Category
    points: list[TimelinePoint]


class Timeline(BaseModel):
    mode: Literal["mission", "iss"]
    start: datetime
    end: datetime
    astronaut_id: str | None
    mission: str | None
    lanes: list[TimelineLane]
    series: list[TimelineSeries]
    notes: list[str]


class NearbyEvent(TimelineItem):
    offset_hours: float


class NearbyEvents(BaseModel):
    ts: datetime
    window_hours: float
    events: list[NearbyEvent]
    note: str


# --------------------------------------------------------------------- correlation ----
class DateRange(BaseModel):
    start: str = Field(description="ISO date (UTC day)")
    end: str


class CorrelationSeriesInfo(BaseModel):
    id: str
    label: str
    unit: str
    category: Category
    group: str
    description: str
    coverage: list[DateRange] = Field(description="Days known to be covered; empty for simulated crew series")


class CorrelationRequest(BaseModel):
    x: str
    y: str
    start: date
    end: date
    max_lag: int = Field(default=3, ge=0, le=14)
    rolling_window: int = Field(default=14, ge=5, le=90)


class CorrStat(BaseModel):
    r: float
    p: float | None
    ci: list[float]


class LagRow(BaseModel):
    lag_days: int
    n: int
    r: float | None
    spearman: float | None = None
    p: float | None
    q: float | None


class CrossRow(BaseModel):
    lag_days: int
    r: float | None
    n: int


class RollingPoint(BaseModel):
    ts: datetime
    r: float


class ScatterPoint(BaseModel):
    ts: datetime
    x: float
    y: float


class SeriesMeta(BaseModel):
    id: str
    label: str | None = None
    unit: str | None = None
    category: Category | None = None
    observations: int = 0


class TrendAdjusted(BaseModel):
    r: float
    p: float | None
    n_eff: float


class CorrelationResult(BaseModel):
    x: SeriesMeta
    y: SeriesMeta
    start: date
    end: date
    n: int
    status: Literal["ok", "insufficient"]
    pearson: CorrStat | None = None
    spearman: CorrStat | None = None
    n_eff: float | None = None
    lag1_autocorr_x: float | None = None
    lag1_autocorr_y: float | None = None
    trend_adjusted: TrendAdjusted | None = None
    lags: list[LagRow] = []
    cross_correlation: list[CrossRow] = []
    rolling: list[RollingPoint] = []
    rolling_window: int | None = None
    scatter: list[ScatterPoint] = []
    warnings: list[str]
    interpretation: str


class MatrixRequest(BaseModel):
    series: list[str] = Field(min_length=2, max_length=10)
    start: date
    end: date
    method: Literal["spearman", "pearson"] = "spearman"


class MatrixCell(BaseModel):
    i: int
    j: int
    r: float | None
    n: int
    p: float | None
    q: float | None


class MatrixResult(BaseModel):
    series: list[SeriesMeta]
    method: str
    start: date
    end: date
    cells: list[MatrixCell]
    warnings: list[str]
