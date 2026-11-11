"""Conversions from domain objects and ORM rows to API schemas."""

from __future__ import annotations

from datetime import datetime

from app.db.models import AlertRow, SimulationEventRow, SleepSessionRow, VitalSampleRow
from app.detection.evaluator import AlertRecord
from app.schemas.alerts import Alert
from app.schemas.health import SleepSession, VitalReading
from app.schemas.simulation import SimulationEvent
from app.schemas.ws import EcgSegment
from app.simulator.engine import EcgChunk
from app.simulator.engine import VitalReading as SimReading
from app.simulator.scenarios import SCENARIOS, ActiveScenario, Scenario


def reading_schema(r: SimReading | VitalSampleRow) -> VitalReading:
    return VitalReading.model_validate(r, from_attributes=True)


def ecg_schema(c: EcgChunk) -> EcgSegment:
    return EcgSegment(
        astronaut_id=c.astronaut_id,
        start=c.start,
        sample_rate_hz=c.sample_rate_hz,
        values_mv=c.values_mv,
    )


def alert_schema(a: AlertRecord | AlertRow) -> Alert:
    return Alert.model_validate(a, from_attributes=True)


def scenario_schema(s: ActiveScenario, now: datetime) -> SimulationEvent:
    return SimulationEvent(
        id=s.id,
        scenario=s.scenario.value,
        label=SCENARIOS[s.scenario].label,
        astronaut_id=s.astronaut_id,
        intensity=round(s.intensity, 2),
        started_at=s.started_at,
        ends_at=s.ends_at,
        cancelled_at=s.cancelled_at,
        triggered_by=s.triggered_by,  # type: ignore[arg-type]
        active=s.is_active(now),
    )


def event_row_schema(row: SimulationEventRow, now: datetime) -> SimulationEvent:
    end = row.cancelled_at or row.ends_at
    return SimulationEvent(
        id=row.id,
        scenario=row.scenario,  # type: ignore[arg-type]
        label=SCENARIOS[Scenario(row.scenario)].label,
        astronaut_id=row.astronaut_id,
        intensity=round(row.intensity, 2),
        started_at=row.started_at,
        ends_at=row.ends_at,
        cancelled_at=row.cancelled_at,
        triggered_by=row.triggered_by,  # type: ignore[arg-type]
        active=row.started_at <= now < end,
    )


def sleep_schema(row: SleepSessionRow) -> SleepSession:
    return SleepSession(
        astronaut_id=row.astronaut_id,
        night=row.night,
        scheduled_start=row.scheduled_start,
        scheduled_end=row.scheduled_end,
        start=row.start,
        end=row.end,
        duration_hours=row.duration_hours,
        efficiency_pct=row.efficiency_pct,
        onset_offset_minutes=round((row.start - row.scheduled_start).total_seconds() / 60, 1),
    )
