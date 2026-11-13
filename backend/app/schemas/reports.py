from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource

ReviewStatus = Literal["draft", "pending_review", "under_review", "reviewed", "closed"]


class ReportCreate(BaseModel):
    alert_id: str | None = None
    run_id: str | None = Field(default=None, description="Emergency-simulator run")
    astronaut_id: str | None = None
    occurred_at: datetime | None = None
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _source(self) -> ReportCreate:
        if not (self.alert_id or self.run_id or self.astronaut_id):
            raise ValueError("Give an alert_id, a run_id or an astronaut_id.")
        return self


class ReviewUpdate(BaseModel):
    status: ReviewStatus
    note: str | None = Field(default=None, max_length=2000)


class ReviewEntry(ApiModel):
    ts: datetime
    by: str
    role: str
    to: ReviewStatus
    note: str | None = None
    from_: ReviewStatus | None = Field(default=None, alias="from")


class ReportSummary(ApiModel):
    id: str
    title: str
    astronaut_id: str
    astronaut_name: str | None
    alert_id: str | None
    run_id: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
    created_by: str
    review_status: ReviewStatus
    review_status_label: str
    review_history: list[dict[str, Any]]
    content_sha256: str
    integrity: Literal["intact", "modified"]
    severity: str | None
    simulation_id: str | None = Field(default=None, description="Mission simulation sandbox run (phase 6)")
    source_kind: Literal["alert", "emergency_run", "simulation", "manual"] = "manual"
    data_source: DataSource = DATA_SOURCE_FIELD


class IncidentReport(ReportSummary):
    content: dict[str, Any] = Field(description="Frozen snapshot of every report section")
