"""Runtime configuration. Every value can be overridden with an ``ASTRA_``-prefixed env var."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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

    # AI intelligence engine (phase 3).
    ai_enabled: bool = True
    ai_artifacts_dir: str = ""  # empty: backend/artifacts
    ai_cache_seconds: float = Field(default=30.0, ge=0)
    ai_history_hours: int = Field(default=168, ge=24, le=720)  # history used to fit live baselines

    # NASA open data (phase 4). The API key stays on the backend: it is never returned by the API,
    # logged, or sent to the browser. Empty uses NASA's public DEMO_KEY (heavily rate limited).
    space_enabled: bool = True
    space_sync_enabled: bool = True  # background synchronisation with NASA services
    nasa_api_key: SecretStr = SecretStr("")
    donki_endpoints: str = "api.nasa.gov,ccmc"  # tried in order; see app/space/provenance.py
    donki_sync_minutes: int = Field(default=180, ge=15)
    donki_backfill_days: int = Field(default=180, ge=7, le=3650)
    eda_sync_hours: int = Field(default=168, ge=1)
    eda_missions: str = ""  # comma-separated EDA mission names to ingest; empty = all
    osdr_sync_hours: int = Field(default=24, ge=1)
    space_http_timeout_s: float = Field(default=45.0, gt=1, le=300)
    space_request_spacing_s: float = Field(default=1.0, ge=0, le=30)  # politeness gap per host

    @property
    def nasa_api_key_value(self) -> str:
        return self.nasa_api_key.get_secret_value().strip()

    @property
    def eda_mission_list(self) -> list[str]:
        return [m.strip() for m in self.eda_missions.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_artifacts_path(self) -> Path:
        if self.ai_artifacts_dir:
            return Path(self.ai_artifacts_dir)
        return Path(__file__).resolve().parents[2] / "artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
