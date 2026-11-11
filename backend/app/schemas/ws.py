"""WebSocket message contract for ``/ws/health-monitoring``.

These models are not attached to any HTTP route, so ``app.main`` injects them into the OpenAPI
components; the frontend generates its socket types from the same document.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.alerts import Alert
from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource
from app.schemas.health import VitalReading
from app.schemas.simulation import SimulationEvent


class EcgSegment(ApiModel):
    astronaut_id: str
    start: datetime
    sample_rate_hz: int
    values_mv: list[float]


class WsHello(ApiModel):
    type: Literal["hello"] = "hello"
    server_time: datetime
    tick_seconds: float
    ecg_sample_rate_hz: int
    astronaut_ids: list[str]
    latest: list[VitalReading]
    open_alerts: list[Alert]
    active_scenarios: list[SimulationEvent]
    data_source: DataSource = DATA_SOURCE_FIELD


class WsVitals(ApiModel):
    type: Literal["vitals"] = "vitals"
    ts: datetime
    readings: list[VitalReading]
    ecg: list[EcgSegment]
    data_source: DataSource = DATA_SOURCE_FIELD


AlertEventKind = Literal["opened", "escalated", "cleared", "recurred", "acknowledged", "resolved"]


class WsAlert(ApiModel):
    type: Literal["alert"] = "alert"
    event: AlertEventKind
    alert: Alert


class WsSimulation(ApiModel):
    type: Literal["simulation"] = "simulation"
    event: Literal["started", "ended", "cancelled"]
    scenario: SimulationEvent


class WsPong(ApiModel):
    type: Literal["pong"] = "pong"
    server_time: datetime


WsServerMessage = Annotated[
    WsHello | WsVitals | WsAlert | WsSimulation | WsPong, Field(discriminator="type")
]


class WsClientMessage(BaseModel):
    action: Literal["ping"]


WS_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    EcgSegment,
    WsHello,
    WsVitals,
    WsAlert,
    WsSimulation,
    WsPong,
    WsClientMessage,
)
