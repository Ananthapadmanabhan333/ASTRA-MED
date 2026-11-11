from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DataSource = Literal["simulated"]
Severity = Literal["advisory", "caution", "critical"]
CrewStatus = Literal["nominal", "advisory", "caution", "critical"]
ActivityState = Literal["sleep", "rest", "work", "exercise"]
Rhythm = Literal["regular", "irregular"]
TimeRange = Literal["1h", "6h", "24h", "7d"]
Metric = Literal[
    "heart_rate",
    "spo2",
    "systolic",
    "diastolic",
    "temperature_c",
    "respiratory_rate",
    "activity_met",
]

DATA_SOURCE_FIELD = Field(
    default="simulated",
    description="Always 'simulated' in this prototype. No real astronaut data is used.",
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"},
    422: {"model": ErrorResponse, "description": "Invalid request parameters"},
}
