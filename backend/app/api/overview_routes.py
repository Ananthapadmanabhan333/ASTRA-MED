"""Mission health overview (phase 5): crew summaries, alert history, trends, environment and a
rule-generated mission summary built from the other services' outputs."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import Monitor, Session
from app.core.errors import ApiError, NotFoundError
from app.core.timeutil import utcnow
from app.db.models import AlertRow, EmergencyRunRow, IncidentReportRow
from app.medical import DECISION_SUPPORT_DISCLAIMER
from app.schemas.common import ERROR_RESPONSES
from app.schemas.overview import MissionOverview
from app.security.deps import CurrentUser
from app.services.health import crew_status
from app.space.intel import weather_summary

router = APIRouter(prefix="/api/overview", tags=["mission overview"], responses=ERROR_RESPONSES)

PERIODS = {"24h": 24, "7d": 168, "30d": 720}


def _mean(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 2) if v else None


@router.get("", response_model=MissionOverview)
async def overview(
    request: Request, session: Session, monitor: Monitor, principal: CurrentUser,
    period: Literal["24h", "7d", "30d"] = "7d",
    astronaut_id: Annotated[str | None, Query(description="Limit to one crew member")] = None,
) -> MissionOverview:
    crew = monitor.engine.profiles
    if astronaut_id and astronaut_id not in crew:
        raise NotFoundError(f"Astronaut {astronaut_id} not found.")
    now = utcnow()
    hours = PERIODS[period]
    since = now - timedelta(hours=hours)
    ids = [astronaut_id] if astronaut_id else list(crew)
    twin, ms_engine, ai = request.app.state.twin, request.app.state.multisystem, request.app.state.ai

    alerts = list((await session.scalars(select(AlertRow).where(
        AlertRow.opened_at >= since, AlertRow.astronaut_id.in_(ids)).order_by(AlertRow.opened_at.desc()))).all())
    reports = []
    if principal.can("reports:read"):
        reports = list((await session.scalars(select(IncidentReportRow).where(
            IncidentReportRow.created_at >= since, IncidentReportRow.astronaut_id.in_(ids))
            .order_by(IncidentReportRow.created_at.desc()))).all())
    runs = list((await session.scalars(select(EmergencyRunRow).where(EmergencyRunRow.started_at >= since)
                                       .order_by(EmergencyRunRow.started_at.desc()))).all())
    runs = [r for r in runs if r.astronaut_id is None or r.astronaut_id in ids]

    rows: list[dict[str, Any]] = []
    trends: dict[str, dict[str, list[dict[str, Any]]]] = {"heart_rate": {}, "sleep_duration_hours": {}}
    for aid in ids:
        await twin.ensure(aid)
        days = await twin.days(aid, since.date())
        trends["heart_rate"][aid] = [{"day": d.day, "value": (d.metrics.get("heart_rate") or {}).get("awake_rest_mean"),
                                      "basis": d.basis} for d in days]
        trends["sleep_duration_hours"][aid] = [{"day": d.day, "value": (d.sleep or {}).get("duration_hours"),
                                                "basis": d.basis} for d in days]
        ms = await ms_engine.assess(session, aid, now)
        risk = None
        try:
            r = await ai.risk(aid)
            risk = {"score": r["risk_score"], "category": r["category"], "category_label": r["category_label"]}
        except ApiError:
            risk = None
        mine = [a for a in alerts if a.astronaut_id == aid]
        latest = monitor.latest_reading(aid)
        rows.append({
            "astronaut_id": aid, "name": crew[aid].name, "role": crew[aid].role,
            "status": crew_status(monitor.open_alerts_for(aid)), "open_alerts": len(monitor.open_alerts_for(aid)),
            "risk": risk, "systems": {s["key"]: s["status"] for s in ms["systems"]},
            "patterns": [p["label"] for p in ms["patterns"]], "summary": ms["summary"],
            "last_reading_at": latest.ts if latest else None,
            "resting_hr_mean": _mean([p["value"] for p in trends["heart_rate"][aid]]),
            "sleep_mean_hours": _mean([p["value"] for p in trends["sleep_duration_hours"][aid]]),
            "dose_period_msv": round(sum((d.radiation or {}).get("dose_msv", 0.0) for d in days), 3),
            "alerts_in_period": dict(Counter(a.severity for a in mine)),
            "reports_in_period": sum(1 for r in reports if r.astronaut_id == aid),
        })

    per_day: dict[str, Counter] = defaultdict(Counter)
    for a in alerts:
        per_day[a.opened_at.date().isoformat()][a.severity] += 1
    history = []
    d = since.date()
    while d <= now.date():
        c = per_day.get(d.isoformat(), Counter())
        history.append({"day": d, "critical": c["critical"], "caution": c["caution"], "advisory": c["advisory"]})
        d += timedelta(days=1)

    ws = await weather_summary(session, now, max(1, hours // 24))
    fl = ws["strongest_flare"]
    environment = {
        "window_days": ws["window_days"], "counts": ws["counts"], "flare_classes": ws["flare_classes"],
        "strongest_flare": None if fl is None else {"classification": fl.classification, "start_time": fl.start_time},
        "category": "indicator",
        "note": "Real NASA DONKI indicators shown for context. Correlation does not establish causation; "
                "they are never converted into crew dose.",
        "simulated_dose_msv": round(sum(r["dose_period_msv"] for r in rows), 3),
    }

    # Rule-generated mission summary: every sentence restates numbers computed above.
    statements: list[dict[str, Any]] = []
    deviating = [r for r in rows if any(v in ("deviation", "marked_deviation") for v in r["systems"].values())]
    statements.append({"kind": "derived", "text": (
        f"{len(deviating)} of {len(rows)} crew member(s) show a deviation in at least one system"
        + (": " + "; ".join(f"{r['name']} ({', '.join(k.replace('_', ' ') for k, v in r['systems'].items() if v in ('deviation', 'marked_deviation'))})"
                            for r in deviating) if deviating else "") + ".")})
    rated = [r for r in rows if r["risk"]]
    if rated:
        top = max(rated, key=lambda r: r["risk"]["score"])
        statements.append({"kind": "model", "text": (
            f"Highest Phase 3 rule-based concern: {top['name']}, {top['risk']['category_label'].lower()} "
            f"({top['risk']['score']:.0f}/100). Experimental, not clinically validated.")})
    sev = Counter(a.severity for a in alerts)
    in_tests = sum(1 for a in alerts if a.scenario)
    statements.append({"kind": "data", "text": (
        f"{len(alerts)} alert(s) in the last {period}: {sev['critical']} critical, {sev['caution']} caution, "
        f"{sev['advisory']} advisory; {in_tests} occurred while a simulated test scenario was running.")})
    if runs:
        statements.append({"kind": "data", "text": f"{len(runs)} simulated emergency run(s) in the period."})
    if any(ws["counts"].values()):
        c = ws["counts"]
        statements.append({"kind": "nasa", "text": (
            f"NASA DONKI recorded {c.get('FLR', 0)} flare(s), {c.get('CME', 0)} CME(s), {c.get('SEP', 0)} SEP event(s) "
            f"and {c.get('GST', 0)} geomagnetic storm(s)" + (f"; strongest flare {fl.classification}" if fl else "")
            + ". Context only; not a crew dose.")})
    else:
        statements.append({"kind": "nasa", "text": "No NASA DONKI events are stored for this period."})
    if reports:
        open_reviews = sum(1 for r in reports if r.review_status in ("draft", "pending_review", "under_review"))
        statements.append({"kind": "data", "text": f"{len(reports)} incident report(s) created; {open_reviews} awaiting review."})

    return MissionOverview.model_validate({
        "generated_at": now, "period": period, "start": since, "end": now, "astronaut_id": astronaut_id,
        "crew": rows,
        "active_alerts": [{"id": a.id, "astronaut_id": a.astronaut_id, "title": a.title, "severity": a.severity,
                           "status": a.status, "opened_at": a.opened_at, "scenario": a.scenario}
                          for a in alerts if a.status != "resolved"][:30],
        "alert_history": history,
        "incidents": [{"id": r.id, "title": r.title, "astronaut_id": r.astronaut_id, "occurred_at": r.occurred_at,
                       "review_status": r.review_status} for r in reports[:30]],
        "incidents_visible": principal.can("reports:read"),
        "runs": [{"id": r.id, "label": r.label, "severity": r.severity, "astronaut_id": r.astronaut_id,
                  "started_at": r.started_at} for r in runs[:20]],
        "trends": {k: [{"astronaut_id": aid, "points": pts} for aid, pts in v.items()] for k, v in trends.items()},
        "environment": environment,
        "summary": {"statements": statements, "method": (
            "Generated by rules from the multisystem engine, Phase 3 risk rules, the alert log, the report log and "
            "NASA DONKI; each sentence restates values shown on this page.")},
        "disclaimer": DECISION_SUPPORT_DISCLAIMER,
    })
