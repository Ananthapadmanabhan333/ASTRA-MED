"""Read models for the command dashboard, crew monitoring and the situational-awareness timeline.

Every figure comes from an existing service or store (monitor, AI sweep, twin, NASA store, alert
centre, event store). Each dashboard section is built independently: if one source fails, that
section reports ``available: false`` with the reason and the rest of the dashboard still loads.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.db.models import EmergencyRunRow, IncidentReportRow, RadiationDoseRow
from app.mission.alerts import alert_view
from app.mission.events import event_view
from app.mission.taxonomy import CATEGORIES, CATEGORY_LABELS
from app.repositories import sleep_radiation as sr_repo
from app.services import mappers
from app.services.health import crew_status
from app.services.mission import mission_status
from app.simulator.habitat import habitat_at

logger = logging.getLogger("astra.mission.views")

LIVE_WINDOW_S = 30.0


def _swx(e) -> dict[str, Any]:
    from app.space import donki

    return {"id": e.id, "event_type": e.event_type, "label": donki.EVENT_TYPES.get(e.event_type, e.event_type),
            "time": e.peak_time or e.start_time, "classification": e.classification, "scale": e.scale,
            "severity": e.severity, "magnitude": e.magnitude, "magnitude_unit": e.magnitude_unit, "link": e.link,
            "category": e.category}


async def _section(name: str, fn) -> dict[str, Any]:
    try:
        return {"available": True, "reason": None, "data": await fn()}
    except ApiError as exc:
        return {"available": False, "reason": exc.message, "data": {}}
    except Exception as exc:  # one failing source must not take down the dashboard
        logger.exception("dashboard section %s failed", name)
        return {"available": False, "reason": f"{name} unavailable ({type(exc).__name__}).", "data": {}}


# ---------------------------------------------------------------- crew monitoring ----
def _stat(metrics: dict[str, Any], metric: str) -> float | None:
    v = metrics.get(metric) or {}
    return v.get("awake_rest_mean") if v.get("awake_rest_mean") is not None else v.get("mean")


async def crew_monitoring(state, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    monitor, orch, center, twin, ai = state.monitor, state.orchestrator, state.alert_center, state.twin, state.ai
    unified = await center.list(statuses=["open", "acknowledged"], context="operations", limit=500)
    cards = []
    async with state.session_factory() as session:
        for aid, profile in monitor.engine.profiles.items():
            rec_alerts = monitor.open_alerts_for(aid)
            reading = monitor.latest_reading(aid)
            age = (now - reading.ts).total_seconds() if reading else None
            snap = orch.ai_snapshot.get(aid) or {}
            try:
                deviations = await ai.current_deviations(aid, reading)
            except ApiError as exc:
                deviations = {"available": False, "reason": exc.message, "signals": []}
            risk = snap.get("risk")
            ai_view = ({"available": True, **{k: risk.get(k) for k in (
                "generated_at", "model_version", "risk_score", "category", "category_label", "health_score",
                "confidence", "what_changed", "warnings", "anomaly", "contributors")}}
                if risk else {"available": False, "reason": snap.get("error") or "Waiting for the first AI sweep.",
                              "generated_at": snap.get("generated_at")})
            trend = []
            for d in await twin.days(aid, now.date() - timedelta(days=7)):
                m = d.metrics or {}
                trend.append({"day": d.day, "heart_rate": _stat(m, "heart_rate"), "spo2": _stat(m, "spo2"),
                              "respiratory_rate": _stat(m, "respiratory_rate"),
                              "temperature_c": _stat(m, "temperature_c"),
                              "sleep_hours": (d.sleep or {}).get("duration_hours"),
                              "dose_msv": (d.radiation or {}).get("dose_msv")})
            cards.append({
                "astronaut_id": aid, "name": profile.name, "role": profile.role, "specialty": profile.specialty,
                "status": crew_status(rec_alerts), "live": age is not None and age <= LIVE_WINDOW_S,
                "last_reading_age_s": None if age is None else round(age, 1),
                "latest": mappers.reading_schema(reading) if reading else None,
                "deviations": deviations,
                "open_rule_alerts": [mappers.alert_schema(a) for a in rec_alerts],
                "open_alerts": [alert_view(a) for a in unified if a.astronaut_id == aid],
                "ai": ai_view, "trend_7d": trend,
                "active_scenarios": [s.spec.label for s in monitor.active_scenarios(now, aid)],
                "mission_dose_msv": round(await sr_repo.mission_total(session, aid), 3),
            })
    sweep = orch.collectors["ai"].last_ok_at
    return {"generated_at": now, "ai_sweep_at": sweep, "crew": cards, "notes": [
        "All crew data are simulated; crew members are fictional.",
        "Baseline deviations compare the latest reading with the learned personal baseline (phase 3).",
        "AI risk comes from the most recent background sweep and is experimental, not a diagnosis.",
    ]}


# ------------------------------------------------------------------- dashboard ----
async def overview(state, principal, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    monitor, orch, center = state.monitor, state.orchestrator, state.alert_center
    status = mission_status(monitor, now)

    async def crew():
        live = [aid for aid, r in monitor.latest.items() if (now - r.ts).total_seconds() <= LIVE_WINDOW_S]
        return {"total": len(monitor.engine.profiles), "active": len(live), "live_window_s": LIVE_WINDOW_S,
                "status_counts": status.crew_status.model_dump(),
                "members": [{"astronaut_id": aid, "name": p.name, "role": p.role,
                             "status": crew_status(monitor.open_alerts_for(aid)),
                             "live": aid in live,
                             "heart_rate": getattr(monitor.latest.get(aid), "heart_rate", None),
                             "spo2": getattr(monitor.latest.get(aid), "spo2", None),
                             "activity_state": getattr(monitor.latest.get(aid), "activity_state", None),
                             "scenario": getattr(monitor.latest.get(aid), "scenario", None)}
                            for aid, p in monitor.engine.profiles.items()]}

    async def health():
        age = (now - monitor.last_tick_at).total_seconds() if monitor.last_tick_at else None
        from app.detection.rules import THRESHOLD_RULES

        state_ = "running" if monitor.running and age is not None and age < 10 else \
            "stalled" if monitor.running else "stopped"
        return {"simulator": state_, "last_tick_age_s": None if age is None else round(age, 2),
                "tick_seconds": monitor.settings.tick_seconds, "tick_failures": monitor.tick_failures,
                "websocket_clients": monitor.hub.count, "threshold_rules": len(THRESHOLD_RULES),
                "detectors": ["threshold", "rhythm", "baseline"],
                "open_rule_alerts": len(monitor.open_alerts_for()),
                "active_scenarios": [{"id": s.id, "label": s.spec.label, "astronaut_id": s.astronaut_id,
                                      "triggered_by": s.triggered_by, "ends_at": s.ends_at}
                                     for s in monitor.active_scenarios(now)]}

    async def alerts():
        summary = await center.summary("operations")
        top = await center.list(statuses=["open", "acknowledged"], context="operations", limit=8)
        sim = None
        if state.sandbox.run is not None:
            sim = await center.summary("simulation", state.sandbox.run.id)
        return {"summary": summary, "top": [alert_view(a) for a in top], "simulation_summary": sim}

    async def ai():
        bundle = await state.ai.bundle()
        crew_ = []
        for aid, p in monitor.engine.profiles.items():
            r = (orch.ai_snapshot.get(aid) or {}).get("risk")
            crew_.append({"astronaut_id": aid, "name": p.name,
                          **({k: r.get(k) for k in ("risk_score", "category", "category_label", "health_score")}
                             | {"confidence_level": (r.get("confidence") or {}).get("level"),
                                "top_warning": (r.get("warnings") or [{}])[0].get("title") if r.get("warnings") else None}
                             if r else {"risk_score": None, "category": None})})
        scored = [c for c in crew_ if c.get("risk_score") is not None]
        highest = max(scored, key=lambda c: c["risk_score"], default=None)
        c = orch.collectors["ai"]
        return {"model_loaded": bundle is not None, "model_version": bundle.version if bundle else None,
                "sweep_at": c.last_ok_at, "sweep_state": c.state, "crew": crew_, "highest": highest,
                "experimental": True,
                "note": "Experimental models trained on simulated data. Risk categories are review prompts, not diagnoses."}

    async def space():
        if state.space is None:
            raise ApiError("NASA space-environment data is disabled on this deployment.")
        if not principal.can("space:read"):
            raise ApiError("Your role does not include NASA space-environment data.")
        from app.space.intel import space_alerts, weather_summary

        async with state.session_factory() as session:
            ws = await weather_summary(session, now, 7)
            sa = await space_alerts(session, now, 7)
        fresh = await state.space.freshness("donki")
        latest = {t: _swx(e) for t, e in ws["latest"].items() if e is not None and t != "WSA"}
        return {"window_days": 7, "counts": {k: v for k, v in ws["counts"].items() if k != "WSA"},
                "flare_classes": ws["flare_classes"],
                "strongest_flare": _swx(ws["strongest_flare"]) if ws["strongest_flare"] else None,
                "max_storm": _swx(ws["max_storm"]) if ws["max_storm"] else None,
                "fastest_cme": _swx(ws["fastest_cme"]) if ws["fastest_cme"] else None,
                "latest": latest,
                "radiation_alerts": [{k: a[k] for k in ("id", "event_type", "severity", "title", "event_time", "status",
                                                        "rule", "link")} for a in sa[:6]],
                "freshness": fresh, "category": "indicator", "data_origin": "nasa",
                "note": "Real NASA DONKI data. Environmental indicators, not crew doses."}

    async def environment():
        habitat = habitat_at(now, monitor.active_scenarios(now))
        env_open = await center.list(statuses=["open", "acknowledged"], context="operations",
                                     categories=["environment", "radiation"], limit=20)
        return {"habitat": {k: {key: p[key] for key in ("label", "value", "unit", "nominal", "deviation_sigma")}
                            for k, p in habitat["parameters"].items()},
                "anomaly_scenario_id": habitat.get("anomaly_scenario_id"),
                "dose_rate_msv_day": status.habitat_dose_rate_msv_day,
                "open_alerts": [alert_view(a) for a in env_open],
                "collector": orch.collectors["environment"].view(), "category": "simulated",
                "note": habitat["note"]}

    async def radiation():
        start = now - timedelta(days=7)
        days: dict[str, dict[str, Any]] = defaultdict(lambda: {"crew_dose_msv": [], "spe": False, "events": 0})
        async with state.session_factory() as session:
            rows = (await session.scalars(select(RadiationDoseRow).where(RadiationDoseRow.day >= start.date()))).all()
            for r in rows:
                d = days[r.day.isoformat()]
                d["crew_dose_msv"].append(r.dose_msv)
                d["spe"] = d["spe"] or r.solar_particle_event
            events = []
            if state.space is not None and principal.can("space:read"):
                from app.space import donki
                from app.space import repository as repo
                from app.space.intel import alert_for

                for e in await repo.list_events(session, start, now, donki.RADIATION_RELEVANT):
                    if alert_for(e) is None:
                        continue
                    events.append(_swx(e) | {"alert_severity": alert_for(e)["severity"]})
                    days[(e.peak_time or e.start_time).date().isoformat()]["events"] += 1
        series = [{"day": k, "mean_crew_dose_msv": round(sum(v["crew_dose_msv"]) / len(v["crew_dose_msv"]), 4)
                   if v["crew_dose_msv"] else None, "simulated_spe": v["spe"], "nasa_events": v["events"]}
                  for k, v in sorted(days.items())]
        sim_events = await state.mission_events.list(categories=["radiation"], context="operations", start=start,
                                                     limit=30)
        return {"days": series, "nasa_events": sorted(events, key=lambda e: e["time"], reverse=True)[:30],
                "simulated_events": [event_view(e) for e in sim_events if e.data_origin != "nasa"],
                "notes": ["Daily doses are simulated (category D).",
                          "NASA events are environmental indicators (category B); they are never converted into doses."]}

    async def incidents():
        recent = await state.mission_events.list(context="operations", priorities=[1, 2, 3],
                                                 start=now - timedelta(hours=24), limit=12)
        reports = []
        async with state.session_factory() as session:
            if principal.can("reports:read"):
                for r in (await session.scalars(select(IncidentReportRow).order_by(IncidentReportRow.created_at.desc())
                                                .limit(5))).all():
                    reports.append({"id": r.id, "title": r.title, "astronaut_id": r.astronaut_id,
                                    "created_at": r.created_at, "review_status": r.review_status,
                                    "simulation": bool((r.content.get("source") or {}).get("simulation_id"))})
            runs = [{"id": r.id, "label": r.label, "astronaut_id": r.astronaut_id, "severity": r.severity,
                     "started_at": r.started_at, "ends_at": r.ends_at, "cancelled_at": r.cancelled_at}
                    for r in (await session.scalars(select(EmergencyRunRow).order_by(EmergencyRunRow.started_at.desc())
                                                    .limit(3))).all()]
        return {"recent_events": [event_view(e) for e in recent], "reports": reports, "emergency_runs": runs,
                "reports_visible": principal.can("reports:read")}

    from app.mission.system import components

    return {
        "generated_at": now, "mission": status,
        "crew": await _section("crew", crew),
        "health_monitoring": await _section("health monitoring", health),
        "alerts": await _section("alerts", alerts),
        "ai": await _section("AI", ai),
        "space_weather": await _section("space weather", space),
        "environment": await _section("environment", environment),
        "radiation_timeline": await _section("radiation timeline", radiation),
        "incidents": await _section("incidents", incidents),
        "connectivity": await components(state, now),
        "simulation": state.sandbox.state(),
        "notes": ["Crew data are simulated. NASA space-weather data are real and labelled as such.",
                  "Experimental AI output is a prompt for review, never a confirmed medical emergency."],
    }


# -------------------------------------------------------------------- timeline ----
LANE_ORDER = ("crew_physiology", "ai_prediction", "environment", "radiation", "solar_activity", "medical_incident",
              "simulation", "system")


async def timeline(events_service, *, start: datetime, end: datetime, astronaut_id: str | None, context: str,
                   simulation_id: str | None, categories: list[str] | None, limit: int = 1000) -> dict[str, Any]:
    rows = await events_service.list(categories=categories, astronaut_id=astronaut_id, context=context,
                                     simulation_id=simulation_id, start=start, end=end, limit=limit)
    lanes = {c: {"key": c, "label": CATEGORY_LABELS[c], "items": []} for c in LANE_ORDER if c in CATEGORIES}
    for r in reversed(rows):
        lanes.setdefault(r.category, {"key": r.category, "label": CATEGORY_LABELS.get(r.category, r.category),
                                      "items": []})["items"].append(event_view(r))
    selected = [lanes[c] for c in lanes if not categories or c in categories]
    counts = await events_service.counts(start, end, context, astronaut_id)
    notes = ["Times are UTC. Crew data are simulated; space-weather events from NASA DONKI are real.",
             "Events reported more than once are merged; 'occurrences' shows the count."]
    if context == "simulation":
        notes.append("Simulation sandbox: times are on the run's own simulation clock.")
    if astronaut_id:
        notes.append("Crew-wide events (environment, radiation, solar activity) are included for the selected crew member.")
    return {"start": start, "end": end, "astronaut_id": astronaut_id, "context": context,
            "simulation_id": simulation_id, "lanes": selected, "counts": counts, "notes": notes}
