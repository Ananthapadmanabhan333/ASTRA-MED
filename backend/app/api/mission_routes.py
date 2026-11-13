"""Phase 6 endpoints: command dashboard, crew monitoring, events and timeline, alert centre,
mission simulation sandbox, analytics and system reliability.

Every router here is mounted with ``require("health:read")`` except ``system_router`` (any
signed-in user: it carries no health data). Writes add their own permission.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.core.errors import ForbiddenError, NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.mission import analytics as analytics_mod
from app.mission import system as system_mod
from app.mission import views
from app.mission.alerts import action_view, alert_view
from app.mission.events import event_view
from app.mission.sandbox import run_view
from app.mission.taxonomy import CATEGORIES, SOURCES
from app.schemas.common import ERROR_RESPONSES
from app.schemas.mission_control import (
    AlertCenterAction,
    AlertCenterStatus,
    AlertCenterSummary,
    AnalyticsSummary,
    ConsistencyReport,
    Context,
    CrewMonitoring,
    EventCounts,
    MissionAlert,
    MissionAlertDetail,
    MissionControlOverview,
    MissionEvent,
    MissionTimeline,
    SimCatalogue,
    SimFrame,
    SimIngestResult,
    SimInject,
    SimPlayback,
    SimReportBody,
    SimRun,
    SimSpeed,
    SimStart,
    SimState,
    SimTelemetryBatch,
    SystemStatus,
)
from app.schemas.reports import IncidentReport
from app.security.deps import CurrentUser, require
from app.security.rbac import Principal

router = APIRouter(prefix="/api", responses=ERROR_RESPONSES)
system_router = APIRouter(prefix="/api/system", tags=["system"], responses=ERROR_RESPONSES)

Limit = Annotated[int, Query(ge=1, le=1000)]


def _state(request: Request):
    return request.app.state


def require_any(*permissions: str):
    async def checker(principal: CurrentUser) -> Principal:
        if not any(principal.can(p) for p in permissions):
            raise ForbiddenError("Your role does not allow this.",
                                 details={"reason": "permission", "required": list(permissions), "any_of": True})
        return principal

    return Depends(checker)


# ---------------------------------------------------------------- dashboard ----
@router.get("/mission-control/overview", response_model=MissionControlOverview, tags=["mission control"])
async def mission_control_overview(request: Request, principal: CurrentUser) -> dict:
    """Consolidated command dashboard. Each section reports its own availability."""
    return await views.overview(_state(request), principal)


@router.get("/crew/monitoring", response_model=CrewMonitoring, tags=["mission control"])
async def crew_monitoring(request: Request) -> dict:
    """Every crew member: current measurements, baseline deviations, open alerts, AI risk and 7-day trend."""
    return await views.crew_monitoring(_state(request))


# ------------------------------------------------------------------- events ----
def _range(start: datetime | None, end: datetime | None, hours: int) -> tuple[datetime, datetime]:
    end = as_utc(end) if end else utcnow()
    start = as_utc(start) if start else end - timedelta(hours=hours)
    if start > end:
        start, end = end, start
    return start, end


@router.get("/events", response_model=list[MissionEvent], tags=["events"])
async def list_events(
    request: Request,
    category: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    priority: Annotated[list[int] | None, Query()] = None,
    astronaut_id: str | None = None,
    context: Context | None = "operations",
    simulation_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Limit = 200,
) -> list[dict]:
    """Unified event history (newest first) from every module, with filters."""
    s, e = _range(start, end, hours) if (start or end or not simulation_id) else (None, None)
    rows = await _state(request).mission_events.list(
        categories=category, sources=source, severities=severity, priorities=priority, astronaut_id=astronaut_id,
        context=context, simulation_id=simulation_id, start=s, end=e, q=q, limit=limit)
    return [event_view(r) for r in rows]


@router.get("/events/counts", response_model=EventCounts, tags=["events"])
async def event_counts(request: Request, context: Context = "operations", astronaut_id: str | None = None,
                       start: datetime | None = None, end: datetime | None = None,
                       hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24) -> dict:
    s, e = _range(start, end, hours)
    return await _state(request).mission_events.counts(s, e, context, astronaut_id)


@router.get("/events/timeline", response_model=MissionTimeline, tags=["events"])
async def event_timeline(
    request: Request,
    category: Annotated[list[str] | None, Query()] = None,
    astronaut_id: str | None = None,
    context: Context = "operations",
    simulation_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 31)] = 24,
) -> dict:
    """Situational awareness: events in lanes by category, filtered by crew member, category and time range."""
    bad = [c for c in category or [] if c not in CATEGORIES]
    if bad:
        raise NotFoundError(f"Unknown categories: {', '.join(bad)}. Known: {', '.join(CATEGORIES)}.")
    if simulation_id and not (start or end):
        row = await _state(request).sandbox.get_row(simulation_id)
        s, e = row.sim_start, max(row.sim_time, row.sim_start + timedelta(minutes=1))
        context = "simulation"
    else:
        s, e = _range(start, end, hours)
    return await views.timeline(_state(request).mission_events, start=s, end=e, astronaut_id=astronaut_id,
                                context=context, simulation_id=simulation_id, categories=category)


@router.get("/events/{event_id}", response_model=MissionEvent, tags=["events"])
async def get_event(event_id: str, request: Request) -> dict:
    row = await _state(request).mission_events.get(event_id)
    if row is None:
        raise NotFoundError(f"Event {event_id} not found.")
    return event_view(row)


# -------------------------------------------------------------- alert centre ----
@router.get("/alert-center", response_model=list[MissionAlert], tags=["alert centre"])
async def alert_center_list(
    request: Request,
    status: Annotated[list[AlertCenterStatus] | None, Query()] = None,
    priority: Annotated[list[int] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    category: Annotated[list[str] | None, Query()] = None,
    classification: Annotated[list[str] | None, Query()] = None,
    astronaut_id: str | None = None,
    context: Context | None = "operations",
    simulation_id: str | None = None,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 168,
    limit: Limit = 200,
) -> list[dict]:
    """Unified alerts, unresolved first, then by priority and time. Unresolved alerts always show."""
    bad = [s for s in source or [] if s not in SOURCES]
    if bad:
        raise NotFoundError(f"Unknown sources: {', '.join(bad)}.")
    rows = await _state(request).alert_center.list(
        statuses=status, priorities=priority, sources=source, categories=category, classifications=classification,
        astronaut_id=astronaut_id, context=context, simulation_id=simulation_id,
        since=utcnow() - timedelta(hours=hours), limit=limit)
    return [alert_view(r) for r in rows]


@router.get("/alert-center/summary", response_model=AlertCenterSummary, tags=["alert centre"])
async def alert_center_summary(request: Request, context: Context | None = "operations",
                               simulation_id: str | None = None) -> dict:
    return await _state(request).alert_center.summary(context, simulation_id)


@router.get("/alert-center/{alert_id}", response_model=MissionAlertDetail, tags=["alert centre"])
async def alert_center_get(alert_id: str, request: Request) -> dict:
    """One alert with its supporting measurements, explanation, correlations and full lifecycle trail."""
    row, actions = await _state(request).alert_center.get(alert_id)
    event = await _state(request).mission_events.get(row.event_id) if row.event_id else None
    return {**alert_view(row), "actions": [action_view(a) for a in actions],
            "event": event_view(event) if event else None}


@router.post("/alert-center/{alert_id}/acknowledge", response_model=MissionAlert, tags=["alert centre"],
             dependencies=[require("alerts:manage")])
async def alert_center_acknowledge(alert_id: str, request: Request, principal: CurrentUser,
                                   body: AlertCenterAction | None = None) -> dict:
    row = await _state(request).alert_center.act(alert_id, "acknowledge", actor=principal.username,
                                                 role=principal.role, note=body.note if body else None)
    return alert_view(row)


@router.post("/alert-center/{alert_id}/resolve", response_model=MissionAlert, tags=["alert centre"],
             dependencies=[require("alerts:manage")])
async def alert_center_resolve(alert_id: str, request: Request, principal: CurrentUser, body: AlertCenterAction) -> dict:
    """Resolve with resolution notes (required)."""
    row = await _state(request).alert_center.act(alert_id, "resolve", actor=principal.username, role=principal.role,
                                                 note=body.note)
    return alert_view(row)


# ---------------------------------------------------------- mission simulation ----
@router.get("/mission-sim/catalogue", response_model=SimCatalogue, tags=["mission simulation"])
async def sim_catalogue(request: Request) -> dict:
    st = _state(request)
    from app.mission.sandbox import SANDBOX_LABEL

    return {"presets": st.sandbox.presets(), "injections": st.sandbox.injection_types(),
            "max_speed": st.settings.mission_sim_max_speed, "max_minutes": st.settings.mission_sim_max_minutes,
            "enabled": st.settings.mission_sim_enabled and st.settings.simulation_control_enabled,
            "label": SANDBOX_LABEL}


@router.get("/mission-sim/state", response_model=SimState, tags=["mission simulation"])
async def sim_state(request: Request) -> dict:
    """The active (or most recent) sandbox run's live state; ``status: idle`` when there is none."""
    return _state(request).sandbox.state()


@router.get("/mission-sim/runs", response_model=list[SimRun], tags=["mission simulation"])
async def sim_runs(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 30) -> list[dict]:
    return [run_view(r) for r in await _state(request).sandbox.list_runs(limit)]


@router.post("/mission-sim/runs", response_model=SimState, status_code=201, tags=["mission simulation"],
             dependencies=[require("simulation:control")])
async def sim_start(body: SimStart, request: Request, principal: CurrentUser) -> dict:
    """Start a sandbox mission (preset or custom crew, speed and length)."""
    sb = _state(request).sandbox
    run = await sb.start(name=body.name, preset=body.preset, crew=body.crew, speed=body.speed,
                         duration_minutes=body.duration_minutes, seed=body.seed,
                         ai_every_minutes=body.ai_every_minutes, created_by=principal.username)
    return sb.state(run)


@router.get("/mission-sim/runs/{run_id}", response_model=SimRun, tags=["mission simulation"])
async def sim_get(run_id: str, request: Request) -> dict:
    return run_view(await _state(request).sandbox.get_row(run_id))


def _control(action: str):
    async def handler(run_id: str, request: Request, principal: CurrentUser) -> dict:
        sb = _state(request).sandbox
        if action == "reset":
            await sb.reset(run_id, by=principal.username)
            return sb.state()
        run = await getattr(sb, action)(run_id, by=principal.username)
        return sb.state(run)

    handler.__name__ = f"sim_{action}"
    handler.__doc__ = {"pause": "Freeze the simulation clock.", "resume": "Continue a paused run.",
                       "stop": "End the run now; its alerts stay open for review and reports.",
                       "reset": "Abandon the run, close its open sandbox alerts and return to idle. Data are kept for playback."}[action]
    return handler


for _action in ("pause", "resume", "stop", "reset"):
    router.add_api_route(f"/mission-sim/runs/{{run_id}}/{_action}", _control(_action), methods=["POST"],
                         response_model=SimState, tags=["mission simulation"],
                         dependencies=[require("simulation:control")])


@router.post("/mission-sim/runs/{run_id}/speed", response_model=SimState, tags=["mission simulation"],
             dependencies=[require("simulation:control")])
async def sim_speed(run_id: str, body: SimSpeed, request: Request) -> dict:
    sb = _state(request).sandbox
    return sb.state(await sb.set_speed(body.speed, run_id))


@router.post("/mission-sim/runs/{run_id}/inject", tags=["mission simulation"],
             dependencies=[require("simulation:control")])
async def sim_inject(run_id: str, body: SimInject, request: Request, principal: CurrentUser) -> dict:
    """Inject a health anomaly, environmental event or simulated space-weather event (now or at a time)."""
    from app.mission.sandbox import _jsonable

    out = await _state(request).sandbox.inject(injection=body.injection, astronaut_id=body.astronaut_id,
                                               intensity=body.intensity, duration_s=body.duration_s,
                                               at_minute=body.at_minute, by=principal.username, run_id=run_id)
    return _jsonable(out)


@router.post("/mission-sim/runs/{run_id}/telemetry", response_model=SimIngestResult, tags=["mission simulation"],
             dependencies=[require("simulation:control")])
async def sim_telemetry(run_id: str, body: SimTelemetryBatch, request: Request) -> dict:
    """Send measurements to the backend for a sandbox run; they pass through rule detection like generated ones."""
    return await _state(request).sandbox.ingest(run_id, [r.model_dump() for r in body.readings], source=body.source)


@router.post("/mission-sim/runs/{run_id}/analyze", tags=["mission simulation"],
             dependencies=[require("simulation:control")])
async def sim_analyze(run_id: str, request: Request) -> dict:
    """Run the phase 3 models over the sandbox stream now (anomaly ensemble, forecast, risk)."""
    from app.mission.sandbox import _jsonable

    return _jsonable(await _state(request).sandbox.analyze(run_id=run_id))


@router.get("/mission-sim/runs/{run_id}/playback", response_model=SimPlayback, tags=["mission simulation"])
async def sim_playback(run_id: str, request: Request, max_points: Annotated[int, Query(ge=20, le=2000)] = 240) -> dict:
    return await _state(request).sandbox.playback(run_id, max_points)


@router.get("/mission-sim/runs/{run_id}/frame", response_model=SimFrame, tags=["mission simulation"])
async def sim_frame(run_id: str, at: datetime, request: Request) -> dict:
    return await _state(request).sandbox.frame(run_id, at)


@router.post("/mission-sim/runs/{run_id}/report", response_model=IncidentReport, status_code=201,
             tags=["mission simulation"], dependencies=[require("reports:write")])
async def sim_report(run_id: str, body: SimReportBody, request: Request, principal: CurrentUser) -> dict:
    """Freeze a sandbox incident into an incident report (draft, same review workflow)."""
    from app.reports.service import report_view

    row = await _state(request).sandbox.create_report(run_id, alert_id=body.alert_id, astronaut_id=body.astronaut_id,
                                                      principal=principal)
    return report_view(row)


# ------------------------------------------------------------------ analytics ----
@router.get("/analytics/summary", response_model=AnalyticsSummary, tags=["analytics"])
async def analytics_summary(request: Request, start: date | None = None, end: date | None = None,
                            context: Literal["operations", "simulation", "all"] = "operations",
                            astronaut_id: str | None = None) -> dict:
    return await analytics_mod.summary(_state(request), start=start, end=end, context=context, astronaut_id=astronaut_id)


@router.get("/analytics/export", tags=["analytics"],
            responses={200: {"content": {"text/csv": {}, "application/json": {}, "text/markdown": {}}}})
async def analytics_export(request: Request, format: Literal["csv", "json", "md"] = "csv", start: date | None = None,
                           end: date | None = None, context: Literal["operations", "simulation", "all"] = "operations",
                           astronaut_id: str | None = None) -> Response:
    """Exportable summary of the same analytics (CSV daily table, full JSON, or a Markdown report)."""
    data = await analytics_mod.summary(_state(request), start=start, end=end, context=context, astronaut_id=astronaut_id)
    body, media, filename = analytics_mod.export(data, format)
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --------------------------------------------------------------------- system ----
@system_router.get("/status", response_model=SystemStatus)
async def system_status(request: Request, principal: CurrentUser) -> dict:
    """Deep health check of every component (no health data)."""
    st = _state(request)
    now = utcnow()
    comps = await system_mod.components(st, now)
    from app import __version__

    return {"status": system_mod.overall(comps), "generated_at": now, "version": __version__,
            "environment": st.settings.environment, "uptime_s": comps[0]["metrics"]["uptime_s"], "components": comps,
            "orchestrator": st.orchestrator.status()}


@system_router.get("/consistency", response_model=ConsistencyReport,
                   dependencies=[require_any("audit:read", "simulation:control")])
async def system_consistency(request: Request) -> dict:
    """Run the database consistency checks without changing anything."""
    return await system_mod.consistency(_state(request), repair=False)


@system_router.post("/consistency/repair", response_model=ConsistencyReport,
                    dependencies=[require_any("audit:read", "simulation:control")])
async def system_consistency_repair(request: Request) -> dict:
    """Run the checks and repair what is safe to repair (mirrors, links, interrupted runs, orphans)."""
    return await system_mod.consistency(_state(request), repair=True)
