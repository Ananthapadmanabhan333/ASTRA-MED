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

    # Operator controls (simulation, sync, model reload). With authentication on, each also needs
    # the matching permission; this switch turns them off for everyone.
    simulation_control_enabled: bool = True

    # Authentication and access control (phase 5). Turning auth off grants every permission to
    # every caller and is refused when environment is "production".
    auth_enabled: bool = True
    auth_session_hours: float = Field(default=8.0, gt=0, le=24)  # absolute session lifetime
    auth_idle_minutes: int = Field(default=60, ge=5, le=720)  # sign out after inactivity
    auth_cookie_name: str = "astra_session"
    auth_cookie_secure: bool = False  # set true whenever the API is served over HTTPS
    auth_max_failed_logins: int = Field(default=5, ge=3, le=20)  # then the account locks
    auth_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    auth_login_attempts_per_minute: int = Field(default=10, ge=1, le=120)  # per client address
    audit_read_dedupe_seconds: int = Field(default=300, ge=0, le=3600)

    # Digital health twin (phase 5): background build of daily summaries, refreshed every 5 minutes.
    twin_background: bool = True

    # Medical data assistant (phase 5). "extractive" answers offline from retrieved passages.
    # "claude" also sends the question and retrieved passages to the Anthropic API; it needs
    # ANTHROPIC_API_KEY in the backend environment and the optional `anthropic` package.
    assistant_mode: str = "extractive"
    assistant_model: str = "claude-opus-5-5"
    assistant_max_passages: int = Field(default=6, ge=1, le=20)
    assistant_docs_dir: str = ""  # empty: the repository's docs/ folder
    assistant_knowledge_dir: str = ""  # empty: backend/knowledge

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

    # Unified mission control (phase 6): event orchestration, alert centre and collectors.
    mission_orchestrator_enabled: bool = True  # background collectors (AI sweep, space scan, environment)
    mission_ai_sweep_seconds: float = Field(default=120.0, ge=10, le=3600)
    mission_space_scan_seconds: float = Field(default=300.0, ge=30, le=86400)
    mission_env_check_seconds: float = Field(default=10.0, ge=1, le=600)
    mission_event_dedupe_minutes: float = Field(default=30.0, ge=1, le=1440)
    mission_clock_skew_tolerance_s: float = Field(default=5.0, ge=0, le=600)
    mission_space_alert_hours: int = Field(default=48, ge=1, le=720)  # DONKI events younger than this raise alerts
    mission_consistency_on_start: bool = True

    # Mission simulation sandbox (phase 6). Runs its own engine and clock and writes only to the
    # mission_simulations / mission_sim_samples tables, never to the live crew history.
    mission_sim_enabled: bool = True
    mission_sim_tick_seconds: float = Field(default=1.0, gt=0.05, le=10)  # wall-clock loop interval
    mission_sim_max_speed: float = Field(default=120.0, ge=1, le=600)
    mission_sim_max_minutes: int = Field(default=24 * 60, ge=5, le=7 * 24 * 60)  # longest sandbox mission (sim time)

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

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
