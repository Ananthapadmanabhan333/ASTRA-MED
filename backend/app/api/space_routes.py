"""Space environment intelligence endpoints (phase 4): NASA open data, radiation intelligence,
mission timeline and the exploratory correlation engine. Responses come from the local store;
synchronisation with NASA runs in the background."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import Monitor, Session
from app.core.errors import ApiError, ForbiddenError, NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.db.models import SpaceNotificationRow, SpaceWeatherEventRow
from app.schemas.common import ERROR_RESPONSES
from app.schemas.space import (
    CorrelationRequest,
    CorrelationResult,
    CorrelationSeriesInfo,
    DataSourceStatus,
    EnvMission,
    EnvMissionDetail,
    EnvSeries,
    EventList,
    Freshness,
    MatrixRequest,
    MatrixResult,
    NearbyEvents,
    RadiationIntel,
    SourcesResponse,
    SpaceAlert,
    SpaceNotification,
    SpaceWeatherEvent,
    SpaceWeatherEventDetail,
    StudyList,
    StudyTopic,
    SyncRequest,
    SyncResult,
    Timeline,
    WeatherSummary,
)
from app.services.mission import radiation_overview
from app.space import classify, correlation, donki, eda, intel, osdr
from app.space import repository as repo
from app.space import timeline as tl
from app.space.provenance import CATEGORY_LABELS, EDA, EVALUATED_SOURCES
from app.space.service import SpaceDataService

router = APIRouter(prefix="/api/space", tags=["space"], responses=ERROR_RESPONSES)


class SpaceDisabledError(ApiError):
    status_code = 503
    code = "space_disabled"


def get_space(request: Request) -> SpaceDataService:
    svc = getattr(request.app.state, "space", None)
    if svc is None:
        raise SpaceDisabledError("The space environment module is disabled (ASTRA_SPACE_ENABLED=false).")
    return svc


Space = Annotated[SpaceDataService, Depends(get_space)]


def clean(value: Any) -> Any:
    """Replace NaN/inf with None so responses are valid JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean(v) for v in value]
    return value


def event_out(e: SpaceWeatherEventRow, detail: bool = False) -> SpaceWeatherEvent:
    data = {
        "id": e.id, "event_type": e.event_type, "type_label": donki.EVENT_TYPES.get(e.event_type, e.event_type),
        "category": e.category, "start_time": e.start_time, "peak_time": e.peak_time, "end_time": e.end_time,
        "classification": e.classification, "scale": e.scale, "severity": e.severity,
        "severity_label": classify.describe(e.event_type, e.severity), "magnitude": e.magnitude,
        "magnitude_unit": e.magnitude_unit, "location": e.location, "description": e.description,
        "instruments": e.instruments or [], "linked_ids": e.linked_ids or [], "notification_ids": e.notification_ids or [],
        "model_derived": e.model_derived, "link": e.link, "version": e.version, "submitted_at": e.submitted_at,
        "retrieved_at": e.retrieved_at, "endpoint": e.endpoint,
    }
    if detail:
        return SpaceWeatherEventDetail(**data, raw=e.raw)
    return SpaceWeatherEvent(**data)


def note_out(n: SpaceNotificationRow) -> SpaceNotification:
    return SpaceNotification(id=n.id, message_id=n.message_id, message_type=n.message_type, issue_time=n.issue_time,
                             url=n.url, summary=n.summary, retrieved_at=n.retrieved_at)


def alert_out(a: dict[str, Any]) -> SpaceAlert:
    return SpaceAlert(**{k: a[k] for k in SpaceAlert.model_fields})


def _parse_types(types: list[str] | None) -> list[str] | None:
    if not types:
        return None
    bad = [t for t in types if t.upper() not in donki.EVENT_TYPES]
    if bad:
        raise ApiError(f"Unknown event type(s): {', '.join(bad)}. Use {', '.join(donki.EVENT_TYPES)}.")
    return [t.upper() for t in types]


# ------------------------------------------------------------------------- sources ----
@router.get("/sources", response_model=SourcesResponse)
async def sources(space: Space) -> SourcesResponse:
    """Dataset inventory with provenance, licensing, availability and data-quality indicators."""
    out = []
    for s in await space.sources_status():
        info = s["info"]
        mirrors = {m["name"]: m for m in s["health"]["mirrors"]}
        endpoints = [{"name": ep.name, "base_url": ep.base_url, "needs_key": ep.needs_key, "note": ep.note,
                      "available": mirrors.get(ep.name, {}).get("available", True),
                      "disabled_until": mirrors.get(ep.name, {}).get("disabled_until"),
                      "reason": mirrors.get(ep.name, {}).get("reason"),
                      "rate_limit_remaining": mirrors.get(ep.name, {}).get("rate_limit_remaining"),
                      "rate_limit_limit": mirrors.get(ep.name, {}).get("rate_limit_limit")} for ep in info.endpoints]
        totals, stats = s["totals"], s["stats"]
        breakdown = stats.get("by_type") or {}
        if info.id == "eda":
            breakdown = {"missions with data": stats.get("missions_with_data", 0)}
        elif info.id == "donki":
            breakdown = {**breakdown, "notifications": stats.get("notifications", 0)}
        out.append(DataSourceStatus(
            id=info.id, name=info.name, provider=info.provider, homepage=info.homepage, data_format=info.data_format,
            categories=list(info.categories), update_frequency=info.update_frequency, units=info.units,
            license=info.license, license_url=info.license_url, citation=info.citation, caveats=list(info.caveats),
            endpoints=endpoints, collection_start=stats.get("first"), collection_end=stats.get("last"),
            records=stats.get("records", 0), breakdown=breakdown, availability=s["mode"],
            availability_message=s["message"],
            health={k: v for k, v in s["health"].items() if k != "mirrors"},
            quality={"records_received": totals["received"], "invalid": totals["invalid"],
                     "duplicates": totals["duplicates"],
                     "invalid_rate": round(totals["invalid"] / totals["received"], 4) if totals["received"] else 0.0,
                     "sync_runs": totals["runs"], "failed_runs": totals["failed_runs"],
                     "last_sync_status": s["runs"][0].status if s["runs"] else None},
            recent_runs=s["runs"], running=s["running"],
        ))
    return SourcesResponse(sources=out, evaluated=EVALUATED_SOURCES,
                           api_key_configured=bool(space.settings.nasa_api_key_value),
                           sync_enabled=space.settings.space_sync_enabled, categories=CATEGORY_LABELS)


@router.post("/sync", response_model=SyncResult)
async def sync(body: SyncRequest, space: Space) -> SyncResult:
    """Run a synchronisation now (operator action; gated like simulation controls)."""
    if not space.settings.simulation_control_enabled:
        raise ForbiddenError("Operator actions are disabled (ASTRA_SIMULATION_CONTROL_ENABLED=false).")
    started = utcnow()
    if body.source == "donki":
        if body.days:
            summary = await space.sync_donki(started - timedelta(days=body.days), started, task="donki:manual")
        else:
            summary = await space.sync_donki_recent()
    elif body.source == "eda":
        summary = await space.sync_eda(body.missions, force=body.force)
    else:
        summary = await space.sync_osdr()
    return SyncResult(source=body.source, started_at=started, finished_at=utcnow(), summary=clean(summary))


# ------------------------------------------------------------------- space weather ----
@router.get("/weather/summary", response_model=WeatherSummary)
async def weather_summary(session: Session, space: Space,
                          days: Annotated[int, Query(ge=1, le=365)] = 30) -> WeatherSummary:
    now = utcnow()
    s = await intel.weather_summary(session, now, days)
    notes = await repo.list_notifications(session, now - timedelta(days=days), now, limit=12)
    return WeatherSummary(
        window_days=days, counts=s["counts"], flare_classes=s["flare_classes"],
        strongest_flare=event_out(s["strongest_flare"]) if s["strongest_flare"] else None,
        max_storm=event_out(s["max_storm"]) if s["max_storm"] else None,
        fastest_cme=event_out(s["fastest_cme"]) if s["fastest_cme"] else None,
        latest={t: (event_out(e) if e else None) for t, e in s["latest"].items()},
        alerts=[alert_out(a) for a in await intel.space_alerts(session, now, days)],
        notifications=[note_out(n) for n in notes], caveats=s["caveats"],
        freshness=Freshness(**await space.freshness("donki")),
    )


@router.get("/weather/events", response_model=EventList)
async def weather_events(
    session: Session, space: Space,
    start: datetime | None = None, end: datetime | None = None,
    types: Annotated[list[str] | None, Query(description="FLR, CME, SEP, GST, RBE, IPS, HSS, MPC, WSA")] = None,
    min_severity: Annotated[int | None, Query(ge=0, le=5)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> EventList:
    end = as_utc(end) if end else utcnow()
    start = as_utc(start) if start else end - timedelta(days=30)
    if start > end:
        raise ApiError("start must be before end")
    rows = await repo.list_events(session, start, end, _parse_types(types), min_severity, limit)
    return EventList(events=[event_out(e) for e in rows], total=len(rows), freshness=Freshness(**await space.freshness("donki")))


@router.get("/weather/events/{event_id}", response_model=SpaceWeatherEventDetail)
async def weather_event(event_id: int, session: Session) -> SpaceWeatherEventDetail:
    e = await repo.get_event(session, event_id)
    if e is None:
        raise NotFoundError(f"Space-weather event {event_id} not found.")
    return event_out(e, detail=True)


@router.get("/weather/notifications", response_model=list[SpaceNotification])
async def weather_notifications(session: Session, days: Annotated[int, Query(ge=1, le=365)] = 30) -> list[SpaceNotification]:
    now = utcnow()
    return [note_out(n) for n in await repo.list_notifications(session, now - timedelta(days=days), now)]


@router.get("/alerts", response_model=list[SpaceAlert])
async def space_alerts(session: Session, days: Annotated[int, Query(ge=1, le=365)] = 30) -> list[SpaceAlert]:
    """Radiation-related environmental alerts derived from DONKI events (indicators, never doses)."""
    return [alert_out(a) for a in await intel.space_alerts(session, utcnow(), days)]


# ----------------------------------------------------------------------- radiation ----
@router.get("/radiation", response_model=RadiationIntel)
async def radiation(session: Session, monitor: Monitor, space: Space,
                    days: Annotated[int, Query(ge=1, le=120)] = 30) -> RadiationIntel:
    now = utcnow()
    overview = await radiation_overview(monitor, session, now, days)
    data = await intel.radiation_intelligence(session, overview, now, days, monitor.settings.mission_start_date)
    data["indicators"]["events"] = [event_out(e) for e in data["indicators"]["events"]]
    data["alerts"] = [alert_out(a) for a in data["alerts"]]
    data["freshness"] = [Freshness(**await space.freshness("donki")), Freshness(**await space.freshness("eda"))]
    return RadiationIntel(**data)


# ----------------------------------------------------------------------------- ISS ----
def merge_milestones(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """EDA's telemetry and dosimetry endpoints publish overlapping milestone lists ("Sac1" at a
    precise time, "Sac 1" at midnight). Merge by normalised label, keeping the precise time."""
    best: dict[str, dict[str, str]] = {}
    for x in items:
        if x["label"].strip().upper() in eda.EMPTY_LABELS:
            continue
        key = "".join(ch for ch in x["label"].lower() if ch.isalnum())
        midnight = x["time"][11:19] == "00:00:00"
        cur = best.get(key)
        if cur is None or (cur["time"][11:19] == "00:00:00" and not midnight):
            best[key] = x
    return sorted(best.values(), key=lambda x: x["time"])


def usable_quantities(m) -> set[str]:
    """Quantities with at least one valid value (some EDA missions publish only null telemetry)."""
    return {k.split(":")[0] for k, v in (m.quality or {}).items() if (v or {}).get("valid", 0) > 0}


def mission_out(m, quantities: set[str]) -> EnvMission:
    return EnvMission(
        name=m.name, title=m.title, description=m.description, link=m.link, start_time=m.start_time,
        end_time=m.end_time, telemetry_synced_at=m.telemetry_synced_at, radiation_synced_at=m.radiation_synced_at,
        has_telemetry=bool(quantities & set(eda.TELEMETRY)), has_radiation=bool(quantities & set(eda.DOSIMETRY)),
        milestones=[{"time": x["time"], "label": x["label"].replace("_", " ")} for x in merge_milestones(m.milestones or [])],
    )


def _resample(rows: list, resolution: str) -> tuple[list[dict[str, Any]], str]:
    """Aggregate hourly telemetry to 6 h or 1 d (count-weighted mean, overall min/max)."""
    if rows[0].resolution != "1h" or resolution == "1h":
        return ([{"ts": r.ts, "value": r.value, "min": r.min_value, "max": r.max_value, "n": r.n,
                  "approximate": r.approximate} for r in rows], rows[0].resolution)
    hours = 6 if resolution == "6h" else 24
    buckets: dict[datetime, list] = {}
    for r in rows:
        key = r.ts.replace(hour=(r.ts.hour // hours) * hours, minute=0, second=0, microsecond=0)
        buckets.setdefault(key, []).append(r)
    out = []
    for ts, rs in sorted(buckets.items()):
        n = sum(r.n for r in rs)
        out.append({"ts": ts, "value": round(sum(r.value * r.n for r in rs) / n, 4),
                    "min": min(r.min_value for r in rs if r.min_value is not None),
                    "max": max(r.max_value for r in rs if r.max_value is not None), "n": n, "approximate": False})
    return out, resolution


@router.get("/iss/missions", response_model=list[EnvMission])
async def iss_missions(session: Session) -> list[EnvMission]:
    out = []
    for m in await repo.list_missions(session):
        out.append(mission_out(m, usable_quantities(m)))
    return out


@router.get("/iss/missions/{name}", response_model=EnvMissionDetail)
async def iss_mission(name: str, session: Session, space: Space,
                      platform: Annotated[str | None, Query(pattern="^(iss|ground)$")] = None,
                      resolution: Annotated[str, Query(pattern="^(1h|6h|1d)$",
                                                       description="Telemetry aggregation; dosimetry stays daily")] = "6h",
                      ) -> EnvMissionDetail:
    m = await repo.get_mission(session, name)
    if m is None:
        raise NotFoundError(f"EDA mission {name} not found. Missions are listed at /api/space/iss/missions.")
    rows = await repo.measurements(session, name, platform=platform)
    grouped: dict[tuple[str, str], list] = {}
    for r in rows:
        grouped.setdefault((r.quantity, r.platform), []).append(r)
    series = []
    for (q, p), rs in grouped.items():
        qual = (m.quality or {}).get(f"{q}:{p}")
        points, res = _resample(rs, resolution)
        series.append(EnvSeries(quantity=q, label=eda.QUANTITY_LABELS.get(q, q), platform=p, unit=rs[0].unit,
                                resolution=res, points=points, quality=qual))
    events = []
    if m.start_time:
        events = await repo.list_events(session, m.start_time - timedelta(days=1), m.end_time or m.start_time,
                                        donki.HISTORICAL_TYPES)
    studies, _ = await repo.list_studies(session, mission=name, limit=20)
    return EnvMissionDetail(
        mission=mission_out(m, usable_quantities(m)), series=series,
        space_weather=[event_out(e) for e in events], studies=studies, caveats=list(EDA.caveats),
        freshness=Freshness(**await space.freshness("eda")),
    )


# ----------------------------------------------------------------------------- OSDR ----
@router.get("/osdr/studies", response_model=StudyList)
async def osdr_studies(
    session: Session, space: Space,
    topic: Annotated[str | None, Query(description="radiation, rodent, spaceflight, physiology, environment")] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    organism: str | None = None, project_type: str | None = None, mission: str | None = None,
    live: Annotated[bool, Query(description="Also query OSDR now for q (results are stored)")] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
) -> StudyList:
    if topic and topic not in osdr.TOPIC_KEYS:
        raise ApiError(f"Unknown topic {topic}. Use one of {', '.join(sorted(osdr.TOPIC_KEYS))}.")
    if live and q:
        await space.search_osdr_live(q)
    items, total = await repo.list_studies(session, topic, q, organism, project_type, mission, limit, offset)
    return StudyList(items=items, total=total, topics=[StudyTopic(key=k, label=lbl, term=t) for k, lbl, t in osdr.TOPICS],
                     freshness=Freshness(**await space.freshness("osdr")))


# ------------------------------------------------------------------------- timeline ----
@router.get("/timeline", response_model=Timeline)
async def timeline(
    request: Request, session: Session,
    mode: Annotated[str, Query(pattern="^(mission|iss)$")] = "mission",
    start: datetime | None = None, end: datetime | None = None,
    astronaut_id: str | None = None, mission: str | None = None,
    include_ai: bool = True,
) -> Timeline:
    if mode == "iss":
        if not mission:
            raise ApiError("mode=iss needs mission (an EDA mission name).")
        t = await tl.iss_timeline(session, mission)
        if t is None:
            raise NotFoundError(f"No stored data for ISS mission {mission}.")
        return Timeline(**t)
    end = as_utc(end) if end else utcnow()
    start = as_utc(start) if start else end - timedelta(days=7)
    if start >= end:
        raise ApiError("start must be before end")
    if astronaut_id and astronaut_id not in request.app.state.monitor.engine.profiles:
        raise NotFoundError(f"Astronaut {astronaut_id} not found.")
    ai = getattr(request.app.state, "ai", None)
    return Timeline(**await tl.mission_timeline(session, ai, start, end, astronaut_id, include_ai))


@router.get("/timeline/nearby", response_model=NearbyEvents)
async def timeline_nearby(session: Session, ts: datetime,
                          window_hours: Annotated[float, Query(gt=0, le=240)] = 48) -> NearbyEvents:
    """Space-weather events near a moment (for example a physiological anomaly)."""
    return NearbyEvents(**await tl.nearby_events(session, as_utc(ts), window_hours))


# ---------------------------------------------------------------------- correlation ----
@router.get("/correlation/series", response_model=list[CorrelationSeriesInfo])
async def correlation_series(session: Session) -> list[CorrelationSeriesInfo]:
    return await correlation.catalogue(session)


def _check_period(start: date, end: date) -> None:
    if start >= end:
        raise ApiError("start must be before end")
    if (end - start).days > 3 * 366:
        raise ApiError("The analysis window is limited to three years.")


@router.post("/correlation/analyze", response_model=CorrelationResult)
async def correlation_analyze(body: CorrelationRequest, session: Session, monitor: Monitor) -> CorrelationResult:
    """Exploratory pair analysis. Correlation does not establish causation."""
    _check_period(body.start, body.end)
    try:
        result = await correlation.analyze(session, body.x, body.y, body.start, body.end, body.max_lag,
                                           body.rolling_window, monitor.settings.mission_start_date)
    except KeyError as exc:
        raise NotFoundError(f"Unknown series {exc}. See /api/space/correlation/series.") from exc
    return CorrelationResult(**clean(result))


@router.post("/correlation/matrix", response_model=MatrixResult)
async def correlation_matrix(body: MatrixRequest, session: Session, monitor: Monitor) -> MatrixResult:
    _check_period(body.start, body.end)
    try:
        result = await correlation.matrix(session, body.series, body.start, body.end,
                                          monitor.settings.mission_start_date, body.method)
    except KeyError as exc:
        raise NotFoundError(f"Unknown series {exc}. See /api/space/correlation/series.") from exc
    return MatrixResult(**clean(result))

