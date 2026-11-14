"""Crew self-check: hand-entered glucose, mood and symptoms with plain-language status (phase 8)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ApiModel

Status = Literal["no_data", "normal", "attention", "contact"]
SYMPTOM_KEYS = ("headache", "nausea", "fatigue", "dizziness", "congestion", "back_pain", "sleep_problems",
                "vision_change", "chest_pain", "shortness_of_breath")


class SelfReportCreate(BaseModel):
    recorded_at: datetime | None = Field(default=None, description="When the check was taken (default: now; never in the future)")
    glucose_mg_dl: float | None = Field(default=None, ge=20, le=600, description="Blood glucose, mg/dL")
    glucose_context: Literal["fasting", "after_meal", "random"] | None = None
    mood: int | None = Field(default=None, ge=1, le=5, description="1 very low … 5 very good")
    symptoms: list[str] | None = Field(default=None, max_length=10,
                                       description="Symptom keys; an empty list records 'no symptoms', null means not checked")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("symptoms")
    @classmethod
    def _known(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        bad = [s for s in v if s not in SYMPTOM_KEYS]
        if bad:
            raise ValueError(f"unknown symptoms: {', '.join(bad)}")
        return v

    def has_content(self) -> bool:
        return any(x is not None for x in (self.glucose_mg_dl, self.mood, self.symptoms, self.note))


class SelfReport(ApiModel):
    id: str
    astronaut_id: str
    recorded_at: datetime
    created_at: datetime
    created_by: str
    glucose_mg_dl: float | None
    glucose_context: str | None
    glucose_status: Status | None
    mood: int | None
    symptoms_checked: bool
    symptoms: list[str]
    note: str | None
    data_source: str = "self_reported"


class SelfIndicator(ApiModel):
    key: str
    label: str
    system: str = Field(description="Body-system group used by the body map: metabolic, behavioural, general")
    value: float | None
    unit: str
    context: str | None
    at: datetime | None
    status: Status
    status_label: str
    guidance: str = Field(description="Process guidance (what to do next), never a diagnosis or a treatment")
    source: str
    reference: str | None


class SelfPrompt(ApiModel):
    key: str
    label: str
    how: str
    automatic: bool
    status: Literal["done", "due", "overdue"]
    last_at: datetime | None
    due_at: datetime | None
    detail: str | None = None


class SymptomInfo(ApiModel):
    key: str
    label: str
    level: Literal["attention", "contact"]


class SelfCheckSummary(ApiModel):
    astronaut_id: str
    name: str
    generated_at: datetime
    indicators: list[SelfIndicator]
    prompts: list[SelfPrompt]
    reports: list[SelfReport]
    symptom_catalogue: list[SymptomInfo]
    notes: list[str]
