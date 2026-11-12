"""REST endpoints. Handlers stay thin: validate input, call a service, return a schema."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from app import __version__
from app.api.deps import Monitor, Session
from app.core.errors import NotFoundError
from app.core.timeutil import utcnow
from app.detection.rules import THRESHOLD_RULES
from app.repositories import alerts as alerts_repo
from app.repositories import astronauts as astronauts_repo
from app.repositories import events as events_repo
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.schemas.alerts import Alert, AlertAction, AlertStatus, ThresholdInfo
from app.schemas.astronaut import Astronaut, AstronautSummary
from app.schemas.common import ERROR_RESPONSES, Metric, Severity, TimeRange
from app.schemas.health import (
    ComparisonSeries,
    CrewSeries,
    HealthSnapshot,
    HistorySeries,
    SeriesPoint,
    SleepSession,
)
from app.schemas.insights import Insight
from app.schemas.mission import MissionStatus, SystemHealth
from app.schemas.radiation import RadiationOverview
from app.schemas.simulation import ScenarioInfo, SimulationEvent, SimulationEventCreate
from app.security.deps import require
from app.services import health as health_service
from app.services import history as history_service
from app.services import mappers
from app.services.insights import generate_insights
from app.services.mission import mission_status, radiation_overview
from app.simulator.scenarios import SCENARIOS

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)
# Unauthenticated liveness probe (no health data). Everything on ``router`` needs a signed-in user.
public_router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)

MaxPoints = Annotated[int, Query(ge=30, le=1000, description="Upper bound on returned points")]


# ------------------------------------------------------------------------ system ----
@public_router.get("/system/health", response_model=SystemHealth, tags=["system"])
async def system_health(monitor: Monitor, session: Session) -> SystemHealth:
    try:
        await session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "error"
    return SystemHealth(
        status="ok" if db == "ok" else "degraded",
        version=__version__,
        environment=monitor.settings.environment,
        database=db,  # type: ignore[arg-type]
        simulator="running" if monitor.running else "stopped",
        websocket_clients=monitor.hub.count,
        server_time=utcnow(),
    )


# -------------------------------------------------------------------- astronauts ----
@router.get("/astronauts", response_model=list[AstronautSummary], tags=["astronauts"])
async def list_astronauts(monitor: Monitor, session: Session) -> list[AstronautSummary]:
    """Crew roster with current status and latest simulated reading."""
    return await health_service.summaries(monitor, session, utcnow())


@router.get("/astronauts/{astronaut_id}", response_model=Astronaut, tags=["astronauts"])
async def get_astronaut(astronaut_id: str, session: Session) -> Astronaut:
    row = await health_service.require_astronaut(session, astronaut_id)
    return Astronaut.model_validate(row)


# ------------------------------------------------------------------------ health ----
@router.get("/health/compare", response_model=ComparisonSeries, tags=["health"])
async def compare_metric(
    session: Session,
    metric: Metric = "heart_rate",
    range: TimeRange = "24h",
    max_points: MaxPoints = 240,
) -> ComparisonSeries:
    """One metric for every crew member over the same window, for side-by-side comparison."""
    now = utcnow()
    start, end = history_service.window(range, now)
    resolution = history_service.resolution_for(range, max_points)
    series = []
    for row in await astronauts_repo.list_astronauts(session):
        rows = await vitals_repo.fetch_range(session, row.id, start, end, columns=(metric,))
        points = [
            SeriesPoint(ts=ts, value=round(vals[0], 2))
            for ts, vals, _ in history_service.bucket_rows(rows, start, resolution, 1)
        ]
        series.append(CrewSeries(astronaut_id=row.id, name=row.name, points=points))
    return ComparisonSeries(
        metric=metric, range=range, start=start, end=end, resolution_seconds=resolution, series=series
    )


@router.get("/health/{astronaut_id}", response_model=HealthSnapshot, tags=["health"])
async def health_snapshot(astronaut_id: str, monitor: Monitor, session: Session) -> HealthSnapshot:
    """Latest vitals plus sleep, activity, radiation, open alerts and running test scenarios."""
    return await health_service.snapshot(monitor, session, astronaut_id, utcnow())


@router.get("/health/{astronaut_id}/history", response_model=HistorySeries, tags=["health"])
async def health_history(
    astronaut_id: str,
    session: Session,
    range: TimeRange = "6h",
    max_points: MaxPoints = 360,
) -> HistorySeries:
    """Stored vitals for a time range, averaged into evenly spaced buckets."""
    await health_service.require_astronaut(session, astronaut_id)
    now = utcnow()
    start, end = history_service.window(range, now)
    resolution = history_service.resolution_for(range, max_points)
    rows = await vitals_repo.fetch_range(session, astronaut_id, start, end)
    return HistorySeries(
        astronaut_id=astronaut_id,
        range=range,
        start=start,
        end=end,
        resolution_seconds=resolution,
        points=history_service.history_points(rows, start, resolution),
    )


@router.get("/health/{astronaut_id}/sleep", response_model=list[SleepSession], tags=["health"])
async def sleep_history(
    astronaut_id: str, session: Session, days: Annotated[int, Query(ge=1, le=30)] = 7
) -> list[SleepSession]:
    await health_service.require_astronaut(session, astronaut_id)
    rows = await sr_repo.list_sleep(session, astronaut_id, utcnow().date() - timedelta(days=days), limit=days)
    return [mappers.sleep_schema(r) for r in rows]


# ----------------------------------------------------------------------- mission ----
@router.get("/mission/status", response_model=MissionStatus, tags=["mission"])
async def get_mission_status(monitor: Monitor) -> MissionStatus:
    return mission_status(monitor, utcnow())


@router.get("/radiation", response_model=RadiationOverview, tags=["mission"])
async def get_radiation(
    monitor: Monitor, session: Session, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> RadiationOverview:
    return await radiation_overview(monitor, session, utcnow(), days)


# ------------------------------------------------------------------------ alerts ----
@router.get("/alerts", response_model=list[Alert], tags=["alerts"])
async def list_alerts(
    session: Session,
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
    astronaut_id: str | None = None,
    hours: Annotated[int, Query(ge=1, le=720, description="Look-back window")] = 168,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[Alert]:
    rows = await alerts_repo.list_alerts(
        session,
        statuses=status,
        severities=severity,
        astronaut_id=astronaut_id,
        since=utcnow() - timedelta(hours=hours),
        limit=limit,
    )
    return [mappers.alert_schema(r) for r in rows]


@router.get("/monitoring/thresholds", response_model=list[ThresholdInfo], tags=["alerts"])
async def list_thresholds() -> list[ThresholdInfo]:
    """Prototype alert limits (not clinical criteria), so displays use the same numbers."""
    return [
        ThresholdInfo(
            key=r.key,
            metric=r.metric,
            direction=r.direction,
            title=r.title,
            unit=r.unit,
            caution=r.caution,
            critical=r.critical,
            overrides=dict(r.overrides),
        )
        for r in THRESHOLD_RULES
    ]


@router.get("/alerts/{alert_id}", response_model=Alert, tags=["alerts"])
async def get_alert(alert_id: str, monitor: Monitor, session: Session) -> Alert:
    live = monitor.evaluator.find(alert_id)
    if live:
        return mappers.alert_schema(live)
    row = await alerts_repo.get(session, alert_id)
    if row is None:
        raise NotFoundError(f"Alert {alert_id} not found.")
    return mappers.alert_schema(row)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert, tags=["alerts"],
             dependencies=[require("alerts:manage")])
async def acknowledge_alert(alert_id: str, monitor: Monitor, body: AlertAction | None = None) -> Alert:
    return await monitor.update_alert(alert_id, "acknowledge", body.note if body else None)


@router.post("/alerts/{alert_id}/resolve", response_model=Alert, tags=["alerts"],
             dependencies=[require("alerts:manage")])
async def resolve_alert(alert_id: str, monitor: Monitor, body: AlertAction | None = None) -> Alert:
    return await monitor.update_alert(alert_id, "resolve", body.note if body else None)


# ---------------------------------------------------------------------- insights ----
@router.get("/insights", response_model=list[Insight], tags=["insights"])
async def list_insights(
    monitor: Monitor, session: Session, astronaut_id: str | None = None
) -> list[Insight]:
    """Rule-generated decision-support insights. Not diagnoses."""
    if astronaut_id:
        await health_service.require_astronaut(session, astronaut_id)
    return await generate_insights(monitor, session, utcnow(), astronaut_id)


# -------------------------------------------------------------------- simulation ----
@router.get("/simulation/scenarios", response_model=list[ScenarioInfo], tags=["simulation"])
async def list_scenarios() -> list[ScenarioInfo]:
    return [
        ScenarioInfo(
            key=spec.key.value,
            label=spec.label,
            description=spec.description,
            default_duration_s=spec.default_duration_s,
            crew_wide=spec.crew_wide,
            affected_metrics=sorted(spec.effects) + (["rhythm"] if spec.irregular_rhythm else [])
            + (["radiation_dose_rate"] if spec.dose_rate_multiplier > 1 else [])
            + (["habitat_atmosphere"] if spec.habitat_effects else []),
        )
        for spec in SCENARIOS.values()
    ]


@router.get("/simulation/events", response_model=list[SimulationEvent], tags=["simulation"])
async def list_simulation_events(
    session: Session,
    astronaut_id: str | None = None,
    hours: Annotated[int, Query(ge=1, le=720)] = 48,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SimulationEvent]:
    now = utcnow()
    rows = await events_repo.list_events(
        session, astronaut_id=astronaut_id, since=now - timedelta(hours=hours), limit=limit
    )
    return [mappers.event_row_schema(r, now) for r in rows]


@router.post(
    "/simulation/events",
    response_model=SimulationEvent,
    status_code=201,
    tags=["simulation"],
    dependencies=[require("simulation:control")],
    responses={403: ERROR_RESPONSES[404] | {"description": "Simulation control disabled"},
               409: ERROR_RESPONSES[404] | {"description": "Scenario already running"}},
)
async def start_simulation_event(body: SimulationEventCreate, monitor: Monitor) -> SimulationEvent:
    """Inject a software test scenario into a crew member's simulated data."""
    return await monitor.start_scenario(body)


@router.delete("/simulation/events/{event_id}", response_model=SimulationEvent, tags=["simulation"],
               dependencies=[require("simulation:control")])
async def cancel_simulation_event(event_id: str, monitor: Monitor) -> SimulationEvent:
    return await monitor.cancel_scenario(event_id)
