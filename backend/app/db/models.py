"""Relational schema. Every measurement row carries ``data_source`` so simulated data can never
be mistaken for real measurements, even when exported."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on PostgreSQL and SQLite alike."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


PK = BigInteger().with_variant(Integer, "sqlite")
SIMULATED = "simulated"


class Base(DeclarativeBase):
    pass


class AstronautRow(Base):
    __tablename__ = "astronauts"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(80))
    specialty: Mapped[str] = mapped_column(String(160))
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(8))
    height_cm: Mapped[int] = mapped_column(Integer)
    mass_kg: Mapped[float] = mapped_column(Float)
    blood_type: Mapped[str] = mapped_column(String(4))
    prior_career_dose_msv: Mapped[float] = mapped_column(Float)
    sleep_start_hour: Mapped[float] = mapped_column(Float)
    sleep_target_hours: Mapped[float] = mapped_column(Float)
    exercise_target_minutes: Mapped[int] = mapped_column(Integer)
    baseline: Mapped[dict] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(16), default=SIMULATED)


class VitalSampleRow(Base):
    __tablename__ = "vital_samples"
    __table_args__ = (Index("ix_vitals_astronaut_ts", "astronaut_id", "ts"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronauts.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(UTCDateTime)
    heart_rate: Mapped[float] = mapped_column(Float)
    spo2: Mapped[float] = mapped_column(Float)
    systolic: Mapped[float] = mapped_column(Float)
    diastolic: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float)
    respiratory_rate: Mapped[float] = mapped_column(Float)
    activity_state: Mapped[str] = mapped_column(String(16))
    activity_met: Mapped[float] = mapped_column(Float)
    rhythm: Mapped[str] = mapped_column(String(16))
    hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_source: Mapped[str] = mapped_column(String(16), default=SIMULATED)


class AlertRow(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_status_opened", "status", "opened_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronauts.id", ondelete="CASCADE"), index=True)
    rule_key: Mapped[str] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(16))
    trigger_value: Mapped[float] = mapped_column(Float)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_value: Mapped[float] = mapped_column(Float)
    activity_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    condition_cleared_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str] = mapped_column(String(16), default=SIMULATED)


class SimulationEventRow(Base):
    __tablename__ = "simulation_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(40))
    astronaut_id: Mapped[str | None] = mapped_column(
        ForeignKey("astronauts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    intensity: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(16))


class SleepSessionRow(Base):
    __tablename__ = "sleep_sessions"
    __table_args__ = (UniqueConstraint("astronaut_id", "night", name="uq_sleep_night"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronauts.id", ondelete="CASCADE"))
    night: Mapped[date] = mapped_column(Date)
    scheduled_start: Mapped[datetime] = mapped_column(UTCDateTime)
    scheduled_end: Mapped[datetime] = mapped_column(UTCDateTime)
    start: Mapped[datetime] = mapped_column(UTCDateTime)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_hours: Mapped[float] = mapped_column(Float)
    efficiency_pct: Mapped[float] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(String(16), default=SIMULATED)


class RadiationDoseRow(Base):
    __tablename__ = "radiation_doses"
    __table_args__ = (UniqueConstraint("astronaut_id", "day", name="uq_dose_day"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronauts.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    mission_day: Mapped[int] = mapped_column(Integer)
    dose_msv: Mapped[float] = mapped_column(Float)
    solar_particle_event: Mapped[bool] = mapped_column(Boolean, default=False)
    data_source: Mapped[str] = mapped_column(String(16), default=SIMULATED)


# --------------------------------------------------------------------------------------------
# Phase 4: NASA open data. These tables hold real, externally sourced data. Every row records
# its source, the endpoint it came from, when it was retrieved and its data category, and keeps
# the original record so normalisation can always be audited.
# --------------------------------------------------------------------------------------------


class SpaceWeatherEventRow(Base):
    __tablename__ = "space_weather_events"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_swx_event"),
        Index("ix_swx_type_start", "event_type", "start_time"),
        Index("ix_swx_start", "start_time"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(16))  # FLR, CME, SEP, GST, RBE, IPS, HSS, MPC, WSA
    external_id: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(16))  # indicator | model
    start_time: Mapped[datetime] = mapped_column(UTCDateTime)
    peak_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    classification: Mapped[str | None] = mapped_column(Text, nullable=True)
    scale: Mapped[str | None] = mapped_column(String(8), nullable=True)  # R3, G2 ...
    severity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-5, None = unclassified
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    magnitude_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruments: Mapped[list] = mapped_column(JSON, default=list)
    linked_ids: Mapped[list] = mapped_column(JSON, default=list)
    notification_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_derived: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    endpoint: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON)


class SpaceNotificationRow(Base):
    __tablename__ = "space_notifications"
    __table_args__ = (
        UniqueConstraint("source_id", "message_id", name="uq_swx_notification"),
        Index("ix_swx_notification_time", "issue_time"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32))
    message_id: Mapped[str] = mapped_column(String(64))
    message_type: Mapped[str] = mapped_column(String(32))
    issue_time: Mapped[datetime] = mapped_column(UTCDateTime)
    url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    endpoint: Mapped[str] = mapped_column(String(64))


class EnvMissionRow(Base):
    __tablename__ = "env_missions"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(32), default="eda")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    telemetry_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    radiation_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    space_weather_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class EnvMeasurementRow(Base):
    __tablename__ = "env_measurements"
    __table_args__ = (
        UniqueConstraint("mission", "quantity", "platform", "ts", name="uq_env_measurement"),
        Index("ix_env_mission_quantity", "mission", "quantity", "platform", "ts"),
    )

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    mission: Mapped[str] = mapped_column(ForeignKey("env_missions.name", ondelete="CASCADE"))
    quantity: Mapped[str] = mapped_column(String(32))
    platform: Mapped[str] = mapped_column(String(16))  # iss | ground
    ts: Mapped[datetime] = mapped_column(UTCDateTime)  # start of the aggregation interval
    resolution: Mapped[str] = mapped_column(String(8))  # 1h for telemetry, 1d for dosimetry
    value: Mapped[float] = mapped_column(Float)  # interval mean
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    n: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[str] = mapped_column(String(16))
    approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(16), default="measured")


class OsdrStudyRow(Base):
    __tablename__ = "osdr_studies"

    accession: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organism: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flight_program: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mission_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mission_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    mission_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    assay_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    material_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_date: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    data_source_accession: Mapped[str | None] = mapped_column(String(64), nullable=True)
    link: Mapped[str] = mapped_column(String(255))
    topics: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    endpoint: Mapped[str] = mapped_column(String(64))


class DataSyncRunRow(Base):
    __tablename__ = "data_sync_runs"
    __table_args__ = (Index("ix_sync_source_started", "source_id", "started_at"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # ok | partial | failed
    endpoint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_new: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
