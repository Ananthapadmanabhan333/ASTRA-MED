"""Emergency scenario simulator endpoints (phase 5). Every run is a simulated software test."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.errors import ForbiddenError
from app.core.timeutil import utcnow
from app.emergency.service import EmergencyService, catalogue_view, run_view
from app.schemas.common import ERROR_RESPONSES
from app.schemas.emergency import (
    EmergencyAnalysis,
    EmergencyRun,
    EmergencyRunCreate,
    EmergencyScenarioInfo,
    EmergencyTimeline,
)
from app.security.deps import CurrentUser, require
from app.security.rbac import Principal

router = APIRouter(prefix="/api/emergency", tags=["emergency simulator"], responses=ERROR_RESPONSES)


def get_service(request: Request) -> EmergencyService:
    return request.app.state.emergency


Service = Annotated[EmergencyService, Depends(get_service)]


@router.get("/scenarios", response_model=list[EmergencyScenarioInfo])
async def scenarios() -> list[EmergencyScenarioInfo]:
    """The scenario catalogue with severity levels and default durations."""
    return [EmergencyScenarioInfo.model_validate(s) for s in catalogue_view()]


@router.post("/runs", response_model=EmergencyRun, status_code=201)
async def start_run(body: EmergencyRunCreate, service: Service,
                    principal: Annotated[Principal, require("simulation:control")]) -> EmergencyRun:
    """Start a simulated emergency scenario (one running scenario per target)."""
    run = await service.start(body.scenario, body.astronaut_id, body.severity, body.duration_seconds, body.nights,
                              principal.username)
    return EmergencyRun.model_validate(run_view(run, utcnow()))


@router.get("/runs", response_model=list[EmergencyRun])
async def list_runs(service: Service, hours: Annotated[int, Query(ge=1, le=720)] = 72) -> list[EmergencyRun]:
    now = utcnow()
    return [EmergencyRun.model_validate(run_view(r, now)) for r in await service.list(hours)]


@router.get("/runs/{run_id}", response_model=EmergencyRun)
async def get_run(run_id: str, service: Service) -> EmergencyRun:
    return EmergencyRun.model_validate(run_view(await service.get(run_id), utcnow()))


@router.post("/runs/{run_id}/cancel", response_model=EmergencyRun, dependencies=[require("simulation:control")])
async def cancel_run(run_id: str, service: Service) -> EmergencyRun:
    return EmergencyRun.model_validate(run_view(await service.cancel(run_id), utcnow()))


@router.post("/runs/{run_id}/analyze", response_model=EmergencyAnalysis)
async def analyze_run(run_id: str, service: Service, principal: CurrentUser) -> EmergencyAnalysis:
    """Run the anomaly ensemble, risk rules, multisystem engine and alert escalation over the run window
    and store the result as a snapshot on the run."""
    if not (principal.can("simulation:control") or principal.can("reports:write")):
        raise ForbiddenError("Your role does not allow running analyses.",
                             details={"reason": "permission", "required": ["simulation:control|reports:write"]})
    return EmergencyAnalysis.model_validate(await service.analyze(run_id, principal.username))


@router.get("/runs/{run_id}/timeline", response_model=EmergencyTimeline)
async def run_timeline(run_id: str, service: Service, astronaut_id: str | None = None) -> EmergencyTimeline:
    """Vitals, events (scenario, alerts, analyses) and simulated environment for the run window."""
    return EmergencyTimeline.model_validate(await service.timeline(run_id, astronaut_id))
