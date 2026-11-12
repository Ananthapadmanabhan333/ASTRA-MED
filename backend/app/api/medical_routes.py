"""Multisystem health intelligence and explainable decision support (phase 5).

Experimental decision support on simulated data: never a diagnosis or treatment recommendation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import Monitor, Session
from app.core.errors import NotFoundError
from app.core.timeutil import utcnow
from app.medical import DECISION_SUPPORT_DISCLAIMER
from app.medical.decision import SIGNIFICANT, escalation_for, load_workflow, packet
from app.medical.multisystem import MultisystemEngine
from app.repositories import alerts as alerts_repo
from app.schemas.common import ERROR_RESPONSES
from app.schemas.medical import CrewSystemsOverview, DecisionPacket, DecisionQueue, MultisystemAssessment
from app.services import health as health_service

router = APIRouter(prefix="/api", tags=["medical intelligence"], responses=ERROR_RESPONSES)


def get_engine(request: Request) -> MultisystemEngine:
    return request.app.state.multisystem


Engine = Annotated[MultisystemEngine, Depends(get_engine)]


@router.get("/multisystem", response_model=CrewSystemsOverview)
async def crew_systems(engine: Engine, session: Session, monitor: Monitor) -> CrewSystemsOverview:
    """Status of the six systems for every crew member."""
    now = utcnow()
    crew = []
    for aid in monitor.engine.profiles:
        a = await engine.assess(session, aid, now)
        crew.append({"astronaut_id": aid, "name": a["name"], "statuses": {s["key"]: s["status"] for s in a["systems"]},
                     "patterns": [p["label"] for p in a["patterns"]], "summary": a["summary"]})
    systems = [{"key": k, "label": v["label"]} for k, v in engine.cfg.systems.items()]
    return CrewSystemsOverview(generated_at=now, systems=systems, crew=crew)


@router.get("/multisystem/{astronaut_id}", response_model=MultisystemAssessment)
async def astronaut_systems(astronaut_id: str, engine: Engine, session: Session) -> MultisystemAssessment:
    """Cardiovascular, respiratory, thermoregulation, sleep/circadian, activity/recovery and radiation
    indicators: the inputs used, their status against this crew member's baseline, the Phase 3 model
    outputs that concern each system, and cross-system co-deviations."""
    await health_service.require_astronaut(session, astronaut_id)
    return MultisystemAssessment.model_validate(await engine.assess(session, astronaut_id))


@router.get("/decision-support/queue", response_model=DecisionQueue)
async def decision_queue(
    session: Session, monitor: Monitor,
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
    include_advisory: bool = False,
    include_closed: bool = False,
) -> DecisionQueue:
    """Significant alerts (caution and critical by default) with their review escalation level."""
    now = utcnow()
    severities = [*SIGNIFICANT, "advisory"] if include_advisory else list(SIGNIFICANT)
    statuses = None if include_closed else ["active", "acknowledged"]
    rows = await alerts_repo.list_alerts(session, statuses=statuses, severities=severities,
                                         since=now - timedelta(hours=hours), limit=200)
    workflow = load_workflow()
    items = []
    for r in rows:
        rec = monitor.evaluator.find(r.id) or alerts_repo.row_to_record(r)
        profile = monitor.engine.profiles.get(rec.astronaut_id)
        items.append({
            "alert_id": rec.id, "astronaut_id": rec.astronaut_id, "name": profile.name if profile else rec.astronaut_id,
            "title": rec.title, "severity": rec.severity, "status": rec.status, "opened_at": rec.opened_at,
            "simulated_test_scenario": rec.scenario, "escalation": escalation_for(rec.severity, None, workflow),
        })
    rank = {"critical": 0, "caution": 1, "advisory": 2}
    items.sort(key=lambda i: (rank.get(i["severity"], 3), -i["opened_at"].timestamp()))
    return DecisionQueue(generated_at=now, items=items, disclaimer=DECISION_SUPPORT_DISCLAIMER)


@router.get("/decision-support/alerts/{alert_id}", response_model=DecisionPacket)
async def decision_packet(alert_id: str, request: Request, engine: Engine, session: Session, monitor: Monitor) -> DecisionPacket:
    """Observation, measurements, baseline comparison, environmental context, AI output, confidence and
    uncertainty, data quality and the recommended medical review workflow for one alert."""
    record = monitor.evaluator.find(alert_id)
    if record is None:
        row = await alerts_repo.get(session, alert_id)
        if row is None:
            raise NotFoundError(f"Alert {alert_id} not found.")
        record = alerts_repo.row_to_record(row)
    data = await packet(session, monitor, request.app.state.ai, engine, record, utcnow())
    return DecisionPacket.model_validate(data)
