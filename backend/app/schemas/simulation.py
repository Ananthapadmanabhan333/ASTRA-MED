from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel

ScenarioKey = Literal[
    "tachycardia",
    "bradycardia",
    "desaturation",
    "elevated_temperature",
    "abnormal_respiratory_rate",
    "irregular_rhythm",
    "solar_particle_event",
]


class ScenarioInfo(ApiModel):
    key: ScenarioKey
    label: str
    description: str
    default_duration_s: int
    crew_wide: bool
    affected_metrics: list[str]


class SimulationEvent(ApiModel):
    id: str
    scenario: ScenarioKey
    label: str
    astronaut_id: str | None = Field(description="Null for crew-wide scenarios")
    intensity: float
    started_at: datetime
    ends_at: datetime
    cancelled_at: datetime | None
    triggered_by: Literal["operator", "random"]
    active: bool


class SimulationEventCreate(BaseModel):
    scenario: ScenarioKey
    astronaut_id: str | None = Field(
        default=None, description="Required unless the scenario is crew-wide"
    )
    intensity: float = Field(default=1.0, ge=0.3, le=1.5)
    duration_seconds: int | None = Field(default=None, ge=30, le=3600)
