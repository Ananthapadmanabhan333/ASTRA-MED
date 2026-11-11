"""Runtime configuration. Every value can be overridden with an ``ASTRA_``-prefixed env var."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASTRA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ASTRA-MED API"
    environment: str = "development"
    log_level: str = "INFO"

    # Storage. PostgreSQL in Docker; SQLite is accepted for tests and offline development.
    database_url: str = "sqlite+aiosqlite:///./astra_med.db"
    history_retention_days: int = Field(default=30, ge=1)

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Simulator.
    simulator_enabled: bool = True
    simulator_seed: int = 2026
    tick_seconds: float = Field(default=1.0, gt=0.05, le=10)
    persist_every_ticks: int = Field(default=5, ge=1)
    ecg_sample_rate_hz: int = Field(default=125, ge=50, le=500)
    random_events_per_hour: float = Field(default=6.0, ge=0)
    backfill_days: int = Field(default=7, ge=0, le=30)
    backfill_interval_minutes: int = Field(default=5, ge=1, le=60)
    mission_start_date: date = date(2026, 6, 20)
    mission_name: str = "Helios-7"
    mission_phase: str = "Mars transit"

    # Operator controls. Disable in any shared deployment until authentication exists.
    simulation_control_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
