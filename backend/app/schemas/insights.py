from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource

InsightCategory = Literal[
    "sleep", "circadian", "cardiovascular", "respiratory", "radiation", "countermeasures", "alerts"
]


class Evidence(ApiModel):
    label: str
    value: str


class Insight(ApiModel):
    id: str
    astronaut_id: str
    category: InsightCategory
    severity: Literal["info", "advisory", "caution"]
    title: str
    summary: str
    evidence: list[Evidence]
    suggested_action: str
    generated_at: datetime
    method: Literal["rule-based"] = Field(
        default="rule-based", description="How the insight was produced; no ML or LLM in v1"
    )
    data_source: DataSource = DATA_SOURCE_FIELD
