"""Digital health twin endpoints (phase 5). All crew data is simulated; see TWIN_DISCLAIMER."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import Monitor, Session
from app.core.errors import ConflictError
from app.core.timeutil import utcnow
from app.schemas.common import ERROR_RESPONSES
from app.schemas.twin import TwinDay, TwinProfile, TwinStages, TwinTimeline, TwinTrend
from app.services import health as health_service
from app.twin import TWIN_DISCLAIMER, views
from app.twin.categories import legend
from app.twin.service import TwinService

router = APIRouter(prefix="/api/twin", tags=["digital twin"], responses=ERROR_RESPONSES)

TrendMetric = Literal[
    "heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate", "hrv_rmssd_ms",
    "sleep_duration_hours", "sleep_efficiency_pct", "dose_msv", "exercise_minutes",
]
Statistic = Literal["awake_rest_mean", "mean", "sleep_mean", "p05", "p95"]


def get_twin(request: Request) -> TwinService:
    return request.app.state.twin


Twin = Annotated[TwinService, Depends(get_twin)]


@router.get("/{astronaut_id}", response_model=TwinProfile)
async def twin_profile(astronaut_id: str, twin: Twin, monitor: Monitor, session: Session, request: Request) -> TwinProfile:
    """Profile, current state, resting values vs early mission / configured / learned baselines, exposure."""
    row = await health_service.require_astronaut(session, astronaut_id)
    await twin.ensure(astronaut_id)
    data = await views.profile(twin, request.app.state.ai, session, row, monitor, utcnow())
    return TwinProfile.model_validate(data)


@router.get("/{astronaut_id}/timeline", response_model=TwinTimeline)
async def twin_timeline(
    astronaut_id: str, twin: Twin, session: Session,
    days: Annotated[int, Query(ge=1, le=400, description="Most recent days (ignored when start is given)")] = 30,
    start: date | None = None, end: date | None = None,
) -> TwinTimeline:
    """One entry per mission day: summaries, sleep, simulated dose, alerts, scenarios and real NASA
    space-weather indicators for the same date."""
    await health_service.require_astronaut(session, astronaut_id)
    await twin.ensure(astronaut_id)
    last = end or utcnow().date()
    first = start or last - timedelta(days=days - 1)
    if first > last:
        raise ConflictError("start must not be after end.")
    rows = await twin.days(astronaut_id, first, last)
    space = await views.space_by_day(session, first, last)
    return TwinTimeline(
        astronaut_id=astronaut_id, start=first, end=last,
        days=[TwinDay.model_validate(views.day_view(r, space.get(r.day))) for r in rows],
        categories=legend("simulated", "regenerated", "derived", "indicator"), disclaimer=TWIN_DISCLAIMER,
    )


@router.get("/{astronaut_id}/trends", response_model=TwinTrend)
async def twin_trend(
    astronaut_id: str, twin: Twin, session: Session,
    metric: TrendMetric = "heart_rate", statistic: Statistic = "awake_rest_mean",
    days: Annotated[int | None, Query(ge=7, le=400, description="Limit to the most recent days")] = None,
) -> TwinTrend:
    """Longitudinal daily series of one signal with a 7-day rolling mean and an autocorrelation-aware trend."""
    await health_service.require_astronaut(session, astronaut_id)
    await twin.ensure(astronaut_id)
    first = utcnow().date() - timedelta(days=days - 1) if days else None
    rows = await twin.days(astronaut_id, first)
    return TwinTrend(astronaut_id=astronaut_id, **views.trend(rows, metric, statistic))


@router.get("/{astronaut_id}/stages", response_model=TwinStages)
async def twin_stages(astronaut_id: str, twin: Twin, session: Session) -> TwinStages:
    """Per mission stage: mean daily values and the change from the first stage."""
    await health_service.require_astronaut(session, astronaut_id)
    await twin.ensure(astronaut_id)
    rows = await twin.days(astronaut_id)
    return TwinStages(astronaut_id=astronaut_id, **views.stages(rows, views.TREND_METRICS))
