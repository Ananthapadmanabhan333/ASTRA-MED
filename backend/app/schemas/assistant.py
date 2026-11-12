from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource

StatementKind = Literal["data", "derived", "model", "nasa", "documentation", "reference", "safety", "configured",
                        "mixed", "uncited"]


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    astronaut_id: str | None = Field(default=None, description="Crew member in focus when the question names none")


class Statement(ApiModel):
    text: str
    citations: list[str]
    kind: StatementKind


class AnswerSource(ApiModel):
    id: str = Field(description="D# = data record, S# = retrieved passage")
    kind: StatementKind
    kind_label: str
    title: str
    detail: str | None
    excerpt: str | None
    url: str | None
    path: str | None
    link: str | None
    score: float | None
    source_type: str | None


class AssistantEscalation(ApiModel):
    required: bool
    reasons: list[str]
    message: str | None
    who: str | None


class AssistantAction(ApiModel):
    type: Literal["create_report"]
    alert_id: str
    label: str


class Understood(ApiModel):
    tasks: list[str]
    astronaut_ids: list[str]
    metrics: list[str]
    hours: int | None


class KnowledgeType(ApiModel):
    key: str
    label: str


class AssistantAnswer(ApiModel):
    question: str
    generated_at: datetime
    mode: Literal["extractive", "claude"]
    model_note: str | None
    answer: str
    statements: list[Statement]
    sources: list[AnswerSource]
    missing_information: list[str]
    declined: list[str]
    escalation: AssistantEscalation
    actions: list[AssistantAction]
    understood: Understood
    knowledge_types: list[KnowledgeType]
    disclaimer: str
    data_source: DataSource = DATA_SOURCE_FIELD


class AssistantStatus(ApiModel):
    mode: dict[str, Any]
    passages: int
    by_source: dict[str, int]
    source_types: list[dict[str, Any]]
    references: list[dict[str, Any]]
    built_at: float
    reference_note: str | None
    disclaimer: str
