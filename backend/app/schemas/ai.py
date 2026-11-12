"""API contract for the AI intelligence engine (phase 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DATA_SOURCE_FIELD, ActivityState, ApiModel, DataSource

AI_DISCLAIMER = (
    "Experimental decision support trained and evaluated on simulated data only. Not a medical device, "
    "not clinically validated, and never a diagnosis."
)
DISCLAIMER_FIELD = Field(default=AI_DISCLAIMER)

RiskCategory = Literal["normal", "low_concern", "moderate_concern", "high_concern"]


# ------------------------------------------------------------------ explanation ----
class Contributor(ApiModel):
    signal: str
    label: str
    share: float = Field(description="Share of the total attribution, 0-1")
    value: float | None = None
    unit: str = ""
    baseline: float | None = Field(default=None, description="Personal baseline centre for the context")
    z: float | None = Field(default=None, description="Robust personal z-score")
    percentile: float | None = Field(default=None, description="Percentile within the personal baseline")
    direction: Literal["above", "below"] | None = None


class Significance(ApiModel):
    level: Literal["none", "minor", "notable", "major"]
    max_abs_z: float
    description: str
    percentile: float | None = None


class Confidence(ApiModel):
    score: float = Field(description="0-1 heuristic: detector agreement, data completeness, baseline support")
    level: Literal["low", "medium", "high"]
    basis: list[str]


class Explanation(ApiModel):
    what_changed: str
    kind: str
    contributors: list[Contributor]
    significance: Significance
    confidence: Confidence
    limitations: list[str]
    method: str


class Driver(ApiModel):
    name: str
    share: float


# --------------------------------------------------------------------- baseline ----
class BaselineStats(ApiModel):
    n: int
    mean: float | None = None
    std: float | None = None
    p5: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p95: float | None = None


class TimeOfDayStats(BaselineStats):
    hours: str


class StateBaseline(BaselineStats):
    center: float
    scale: float
    by_time_of_day: list[TimeOfDayStats]


class CurrentComparison(ApiModel):
    ts: datetime
    value: float
    state: ActivityState
    expected: float | None = Field(description="Null when there is no baseline for the current activity yet")
    z: float | None
    percentile: float | None
    reference_level: Literal["cell", "state", "overall", "none"]
    assessment: Literal["within", "high", "low", "no_baseline"]


class SignalBaseline(ApiModel):
    signal: str
    label: str
    unit: str
    overall: BaselineStats
    by_state: dict[str, StateBaseline]
    rolling_24h: BaselineStats
    rolling_7d: BaselineStats
    current: CurrentComparison | None


class BaselineResponse(ApiModel):
    astronaut_id: str
    fitted_at: datetime
    updated_at: datetime
    history_hours: int
    windows_used: int
    first_ts: datetime | None
    last_ts: datetime | None
    method: str
    signals: list[SignalBaseline]
    limitations: list[str]
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


# ---------------------------------------------------------------------- anomaly ----
class ReadingIn(BaseModel):
    ts: datetime
    heart_rate: float | None = Field(default=None, ge=0, le=300)
    spo2: float | None = Field(default=None, ge=0, le=100)
    systolic: float | None = Field(default=None, ge=0, le=300)
    diastolic: float | None = Field(default=None, ge=0, le=200)
    temperature_c: float | None = Field(default=None, ge=25, le=45)
    respiratory_rate: float | None = Field(default=None, ge=0, le=80)
    activity_state: ActivityState | None = None
    activity_met: float | None = Field(default=None, ge=0, le=20)


class AnomalyDetectionRequest(BaseModel):
    astronaut_id: str
    start: datetime | None = Field(default=None, description="Analyse stored data from here (default: 6 h ago)")
    end: datetime | None = Field(default=None, description="Analyse stored data until here (default: now)")
    readings: list[ReadingIn] | None = Field(
        default=None, max_length=20_000,
        description="Optional measurements to analyse instead of stored data; missing values may be null",
    )
    models: list[str] | None = Field(default=None, description="Detector subset (default: all)")
    include_explanations: bool = True


class DetectorInfo(ApiModel):
    name: str
    label: str
    description: str
    threshold: float | None
    weight: float


class AnomalyPoint(ApiModel):
    ts: datetime
    ensemble_score: float = Field(description="Ensemble score / its threshold; >= 1 is flagged")
    flagged: bool
    votes: int
    scores: dict[str, float] = Field(description="Each detector's score / its threshold")
    kind: str | None
    top_signals: list[str]
    missing_frac: float


class Detection(ApiModel):
    start: datetime
    end: datetime
    peak_ts: datetime
    peak_score: float
    duration_minutes: float
    kind: str
    signals: list[str]
    votes: int
    explanation: Explanation | None


class DataQuality(ApiModel):
    windows: int
    windows_without_data: int
    missing_fraction: float
    implausible_values_removed: int


class AnomalyDetectionResponse(ApiModel):
    astronaut_id: str
    model_version: str
    window_minutes: int
    start: datetime
    end: datetime
    source: Literal["stored", "supplied"]
    detectors: list[DetectorInfo]
    timeline: list[AnomalyPoint]
    detections: list[Detection]
    data_quality: DataQuality
    limitations: list[str]
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


# --------------------------------------------------------------------- forecast ----
class HistoryValue(ApiModel):
    ts: datetime
    value: float | None


class ForecastPoint(ApiModel):
    ts: datetime
    horizon_h: float
    value: float
    lower: float
    upper: float


class HorizonSummary(ApiModel):
    horizon_h: int
    ts: datetime
    value: float
    lower: float
    upper: float
    caution_limit: float | None
    limit_direction: Literal["high", "low"] | None
    crossing: Literal["likely", "possible"] | None
    validation_mae: float | None = Field(description="Test-split MAE for this model, signal and horizon (simulated data)")
    validation_coverage: float | None


class SignalForecast(ApiModel):
    signal: str
    label: str
    unit: str
    history: list[HistoryValue]
    forecast: list[ForecastPoint]
    horizons: list[HorizonSummary]
    drivers: list[Driver] = Field(description="What drives the forecast (TreeSHAP share for XGBoost)")
    explanation: Explanation


class ForecastResponse(ApiModel):
    astronaut_id: str
    model: str
    model_label: str
    model_version: str
    generated_at: datetime
    origin_ts: datetime
    step_minutes: int
    interval_coverage_nominal: float
    available_models: list[str]
    series: list[SignalForecast]
    limitations: list[str]
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


# ------------------------------------------------------------------------- risk ----
class RiskWarning(ApiModel):
    priority: int
    source: Literal["deviation", "anomaly", "trend", "alert"]
    concern: RiskCategory
    title: str
    detail: str
    signals: list[str]
    points: float
    alert_id: str | None = None


class AnomalySummary(ApiModel):
    available: bool
    score: float
    votes: int
    n_detectors: int
    flagged_minutes: float
    kind: str | None


class RiskAssessmentResponse(ApiModel):
    astronaut_id: str
    name: str
    generated_at: datetime
    model_version: str | None
    risk_score: float
    category: RiskCategory
    category_label: str
    health_score: int = Field(description="100 minus the risk score; a display convenience, not a clinical score")
    warnings: list[RiskWarning]
    explanation: Explanation
    anomaly: AnomalySummary
    limitations: list[str]
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


class CrewRiskSummary(ApiModel):
    astronaut_id: str
    name: str
    role: str
    risk_score: float
    category: RiskCategory
    category_label: str
    health_score: int
    top_warning: str | None
    top_signals: list[str]
    confidence_level: Literal["low", "medium", "high"]
    warnings: list[RiskWarning]


class CrewRiskOverview(ApiModel):
    generated_at: datetime
    model_version: str | None
    crew: list[CrewRiskSummary]
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


# ------------------------------------------------------------------ performance ----
class ModelVersionInfo(ApiModel):
    version: str
    created_at: str | None
    config_hash: str | None


class ModelPerformanceResponse(ApiModel):
    version: str
    created_at: str
    git_commit: str | None
    runtime_seconds: float
    dataset: dict[str, Any]
    anomaly: dict[str, Any]
    forecast: dict[str, Any]
    limitations: list[str]
    versions: list[ModelVersionInfo]
    report_markdown: str | None
    disclaimer: str = DISCLAIMER_FIELD


class AlertExplanationResponse(ApiModel):
    alert_id: str
    astronaut_id: str
    alert_title: str
    opened_at: datetime
    rule: str
    explanation: Explanation
    anomaly_context: list[AnomalyPoint]
    model_version: str | None
    disclaimer: str = DISCLAIMER_FIELD
    data_source: DataSource = DATA_SOURCE_FIELD


class AIStatus(ApiModel):
    enabled: bool
    model_version: str | None
    loaded: bool
    error: str | None
    detectors: list[str]
    forecasters: list[str]
    serving_forecaster: str | None
    torch_available: bool
