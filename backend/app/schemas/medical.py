from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource

FeatureStatus = Literal["within_baseline", "deviation", "marked_deviation", "insufficient_data", "info"]
SystemStatus = Literal["within_baseline", "deviation", "marked_deviation", "insufficient_data"]


class SystemFeature(ApiModel):
    key: str
    label: str
    value: float | str | None
    unit: str
    reference: float | None
    reference_label: str | None
    z: float | None = Field(description="SD from the reference (statistical, not clinical)")
    direction: Literal["above", "below"] | None
    status: FeatureStatus
    category: str
    source: str
    note: str | None


class SystemAlert(ApiModel):
    id: str
    title: str
    severity: str
    metric: str


class SystemAIOutput(ApiModel):
    source: str
    title: str
    detail: str
    concern: str | None
    category: str


class SystemQuality(ApiModel):
    inputs: int
    assessed: int
    missing: list[str]


class SystemAssessment(ApiModel):
    key: str
    label: str
    description: str
    status: SystemStatus
    features: list[SystemFeature]
    open_alerts: list[SystemAlert]
    ai_outputs: list[SystemAIOutput]
    explanation: str
    data_quality: SystemQuality


class CrossSystemPattern(ApiModel):
    key: str
    label: str
    systems: list[str]
    evidence: list[str]
    review: str
    note: str


class MultisystemAI(ApiModel):
    risk_score: float
    category: str
    category_label: str
    model_version: str | None
    anomaly: dict[str, Any] | None
    confidence: dict[str, Any]


class MultisystemConfigInfo(ApiModel):
    z_deviation: float
    z_marked: float
    source: str
    note: str


class MultisystemQuality(ApiModel):
    notes: list[str]
    reading_age_s: float | None


class MultisystemAssessment(ApiModel):
    astronaut_id: str
    name: str
    generated_at: datetime
    reading_ts: datetime | None
    summary: str
    systems: list[SystemAssessment]
    patterns: list[CrossSystemPattern]
    ai: MultisystemAI | None
    habitat: dict[str, Any] | None
    overlay: dict[str, Any] | None
    config: MultisystemConfigInfo
    data_quality: MultisystemQuality
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD


class CrewSystemsRow(ApiModel):
    astronaut_id: str
    name: str
    statuses: dict[str, SystemStatus]
    patterns: list[str]
    summary: str


class CrewSystemsOverview(ApiModel):
    generated_at: datetime
    systems: list[dict[str, str]]
    crew: list[CrewSystemsRow]
    data_source: DataSource = DATA_SOURCE_FIELD


# ------------------------------------------------------------- decision support ----
class ReviewEscalation(ApiModel):
    level: Literal["immediate", "prompt", "routine"]
    label: str
    who: str
    why: str
    severity_basis: str
    reasons: list[str]
    requires_medical_review: bool


class ReviewStep(ApiModel):
    key: str
    label: str
    role: str
    role_label: str


class ReviewWorkflow(ApiModel):
    escalation: ReviewEscalation
    steps: list[ReviewStep]
    alert_status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    source: str
    note: str


class DecisionPacket(ApiModel):
    alert_id: str
    generated_at: datetime
    observation: dict[str, Any]
    measurements: dict[str, Any]
    baseline_comparison: dict[str, Any]
    environmental_context: dict[str, Any]
    ai_output: dict[str, Any]
    confidence_uncertainty: dict[str, Any]
    data_quality: dict[str, Any]
    review_workflow: ReviewWorkflow
    concurrent_patterns: list[CrossSystemPattern]
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD


class QueueItem(ApiModel):
    alert_id: str
    astronaut_id: str
    name: str
    title: str
    severity: str
    status: str
    opened_at: datetime
    simulated_test_scenario: str | None
    escalation: ReviewEscalation


class DecisionQueue(ApiModel):
    generated_at: datetime
    items: list[QueueItem]
    disclaimer: str
