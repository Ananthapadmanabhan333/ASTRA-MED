from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import DATA_SOURCE_FIELD, ActivityState, ApiModel, DataSource, Severity

AlertStatus = Literal["active", "acknowledged", "resolved"]
AlertCategory = Literal["threshold", "rhythm", "baseline"]


class Alert(ApiModel):
    id: str
    astronaut_id: str
    rule_key: str
    category: AlertCategory
    metric: str
    direction: Literal["high", "low"]
    severity: Severity
    status: AlertStatus
    title: str
    message: str
    unit: str
    trigger_value: float
    threshold_value: float | None
    peak_value: float
    activity_state: ActivityState | None
    scenario: str | None = Field(description="Injected test scenario active when the alert opened")
    opened_at: datetime
    updated_at: datetime
    condition_cleared_at: datetime | None = Field(
        description="When values returned within limits; the alert stays open until resolved"
    )
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    operator_note: str | None
    data_source: DataSource = DATA_SOURCE_FIELD


class AlertAction(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ThresholdInfo(ApiModel):
    key: str
    metric: str
    direction: Literal["high", "low"]
    title: str
    unit: str
    caution: float
    critical: float
    overrides: dict[str, tuple[float, float]] = Field(
        description="Activity-specific (caution, critical) limits"
    )
