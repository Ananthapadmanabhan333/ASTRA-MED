from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import DATA_SOURCE_FIELD, ApiModel, DataSource


class CrewStatusCounts(ApiModel):
    nominal: int
    advisory: int
    caution: int
    critical: int


class MissionStatus(ApiModel):
    mission_name: str
    phase: str
    mission_start: date
    mission_day: int
    mission_elapsed_seconds: float
    server_time: datetime
    earth_distance_au: float = Field(description="Modelled Earth–spacecraft distance")
    one_way_light_delay_s: float
    crew_count: int
    crew_status: CrewStatusCounts
    open_alerts: int
    critical_alerts: int
    active_scenarios: int
    habitat_dose_rate_msv_day: float
    simulator_running: bool
    data_source: DataSource = DATA_SOURCE_FIELD


class SystemHealth(ApiModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "error"]
    simulator: Literal["running", "stopped"]
    websocket_clients: int
    server_time: datetime
