"""Platform reliability: component health and database consistency checks.

``components`` probes every moving part (API, database, simulator loop, WebSocket hub, AI models,
event orchestrator and its collectors, NASA sources, digital twin, simulation sandbox) and reports
``ok``, ``degraded``, ``down``, ``disabled`` or ``unavailable`` with a short reason.

``consistency`` cross-checks stores that must agree and, with ``repair=True``, fixes what is safe to
fix (mirrors and links). Evidence of tampering (a report whose digest no longer matches) is only
ever reported, never "repaired".
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text

from app import __version__
from app.core.timeutil import utcnow
from app.db.models import (
    AlertRow,
    IncidentReportRow,
    MissionAlertRow,
    MissionEventRow,
    MissionSimSampleRow,
    MissionSimulationRow,
    VitalSampleRow,
)
from app.mission.alerts import RULE_SOURCE, STATUS_FROM_RULE
from app.repositories import alerts as alerts_repo

logger = logging.getLogger("astra.mission.system")

STARTED = time.monotonic()
MIRROR_DAYS = 30


def _c(key: str, label: str, status: str, detail: str, **metrics: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status, "detail": detail, "metrics": metrics}


async def components(state, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or utcnow()
    settings = state.settings
    out = [_c("api", "Monitoring API", "ok", f"Version {__version__} ({settings.environment})",
              uptime_s=round(time.monotonic() - STARTED, 1))]

    started = time.perf_counter()
    try:
        async with state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - started) * 1000, 1)
        out.append(_c("database", "Database", "ok" if latency < 500 else "degraded",
                      f"{state.db_engine.dialect.name}, query in {latency} ms", latency_ms=latency,
                      dialect=state.db_engine.dialect.name))
    except Exception as exc:
        out.append(_c("database", "Database", "down", f"Unreachable: {type(exc).__name__}"))

    m = state.monitor
    age = (now - m.last_tick_at).total_seconds() if m.last_tick_at else None
    if not settings.simulator_enabled:
        out.append(_c("simulator", "Physiological simulator", "disabled", "Disabled by configuration."))
    elif not m.running:
        out.append(_c("simulator", "Physiological simulator", "down", "The tick loop is not running."))
    else:
        stale = age is None or age > max(5.0, 5 * settings.tick_seconds)
        out.append(_c("simulator", "Physiological simulator", "degraded" if stale else "ok",
                      (f"Last tick {age:.1f} s ago" if age is not None else "No tick yet")
                      + (f"; {m.tick_failures} failed ticks" if m.tick_failures else ""),
                      last_tick_age_s=None if age is None else round(age, 2), tick_failures=m.tick_failures,
                      last_error=m.last_tick_error))
    out.append(_c("websocket", "Live WebSocket", "ok", f"{m.hub.count} connected client(s)", clients=m.hub.count))

    try:
        st = await state.ai.status()
        if not st["enabled"]:
            out.append(_c("ai", "AI models", "disabled", "ASTRA_AI_ENABLED=false."))
        elif st["loaded"]:
            out.append(_c("ai", "AI models", "ok", f"Model version {st['model_version']}",
                          model_version=st["model_version"], detectors=len(st["detectors"]),
                          forecasters=len(st["forecasters"])))
        else:
            out.append(_c("ai", "AI models", "unavailable", st["error"] or "No trained model version; run python -m app.ai.train."))
    except Exception as exc:
        out.append(_c("ai", "AI models", "degraded", f"Status check failed: {type(exc).__name__}"))

    o = state.orchestrator.status()
    degraded = [c for c in o["collectors"] if c["state"] == "degraded"]
    out.append(_c("orchestrator", "Event orchestration", "down" if not o["running"] else
                  "degraded" if degraded or o["queue_depth"] > 1000 else "ok",
                  (f"Queue {o['queue_depth']}, {o['processed']} processed"
                   + (f"; degraded: {', '.join(c['name'] for c in degraded)}" if degraded else "")),
                  queue_depth=o["queue_depth"], processed=o["processed"], errors=o["errors"]))

    if state.space is None:
        out.append(_c("nasa", "NASA data sources", "disabled", "ASTRA_SPACE_ENABLED=false."))
    else:
        for sid, label in (("donki", "NASA DONKI space weather"), ("eda", "NASA OSDR environmental data"),
                           ("osdr", "NASA OSDR study catalogue")):
            try:
                f = await state.space.freshness(sid)
                status = {"live": "ok", "cached": "ok", "offline-fallback": "degraded", "pending": "unavailable",
                          "unavailable": "down"}.get(f["mode"], "degraded")
                out.append(_c(f"nasa_{sid}", label, status, f["message"], mode=f["mode"], retrieved_at=f["retrieved_at"]))
            except Exception as exc:
                out.append(_c(f"nasa_{sid}", label, "degraded", f"Status check failed: {type(exc).__name__}"))

    tw = state.twin
    last = max(tw.updated_at.values(), default=None)
    out.append(_c("twin", "Digital twin", "ok" if last else ("unavailable" if settings.twin_background else "disabled"),
                  f"Updated {(now - last).total_seconds() / 60:.0f} min ago" if last else
                  ("Building the first daily summaries" if settings.twin_background else "Background build disabled"),
                  updated_at=last))

    sb = state.sandbox.state()
    sim_status = "disabled" if not settings.mission_sim_enabled else \
        "degraded" if sb.get("status") == "failed" else "ok"
    out.append(_c("sandbox", "Mission simulation sandbox", sim_status,
                  f"{sb.get('name')}: {sb.get('status')} at {sb.get('t_plus')}" if sb.get("id") else "Idle",
                  run_status=sb.get("status"), simulation_id=sb.get("id")))
    return out


def overall(components_: list[dict[str, Any]]) -> str:
    core = {"database", "api"}
    if any(c["status"] == "down" and c["key"] in core for c in components_):
        return "down"
    if any(c["status"] in ("down", "degraded") for c in components_):
        return "degraded"
    return "ok"


# ------------------------------------------------------------------ consistency ----
def _check(key: str, label: str, found: int, repaired: int, detail: str, *, warn: bool = True) -> dict[str, Any]:
    status = "ok" if found == 0 else "repaired" if repaired >= found else "warning" if warn else "error"
    return {"key": key, "label": label, "status": status, "found": found, "repaired": repaired, "detail": detail}


async def consistency(state, repair: bool = False, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    checks: list[dict[str, Any]] = []
    factory = state.session_factory
    center = state.alert_center

    # 1. Every recent or open rule alert has a mirror in the alert centre with the same status.
    async with factory() as session:
        rule_rows = list((await session.scalars(select(AlertRow).where(
            (AlertRow.status != "resolved") | (AlertRow.opened_at >= now - timedelta(days=MIRROR_DAYS))))).all())
        mirrors = {r.source_ref: r for r in (await session.scalars(select(MissionAlertRow).where(
            MissionAlertRow.source == RULE_SOURCE, MissionAlertRow.context == "operations"))).all()}
    missing = [r for r in rule_rows if r.id not in mirrors]
    drift = [r for r in rule_rows if r.id in mirrors and STATUS_FROM_RULE.get(r.status) != mirrors[r.id].status]
    fixed = 0
    if repair:
        for r in [*missing, *drift]:
            rec = state.monitor.evaluator.find(r.id) or alerts_repo.row_to_record(r)
            try:
                await center.mirror_rule_alert("opened", rec, name=state.monitor.engine.profiles.get(r.astronaut_id).name
                                               if r.astronaut_id in state.monitor.engine.profiles else None)
                if rec.status != "active":
                    await center.mirror_rule_alert(STATUS_FROM_RULE[rec.status], rec)
                fixed += 1
            except Exception:
                logger.exception("could not repair mirror of %s", r.id)
    checks.append(_check("rule_alert_mirror", "Rule alerts mirrored in the alert centre", len(missing) + len(drift), fixed,
                         f"{len(rule_rows)} rule alerts checked (open, or opened in the last {MIRROR_DAYS} days); "
                         f"{len(missing)} without a mirror, {len(drift)} with a different status."))

    # 2. Mirrors of operations rule alerts whose source alert no longer exists.
    async with factory() as session:
        ids = set((await session.scalars(select(AlertRow.id))).all())
    orphans = [m for ref, m in mirrors.items() if ref not in ids]
    checks.append(_check("orphan_mirrors", "Alert-centre mirrors without a source alert", len(orphans), 0,
                         "Reported only: the mirror keeps the operator decisions recorded on it."))

    # 3. The detector's in-memory open alerts match the stored open alerts.
    stored_open = {r.id for r in rule_rows if r.status != "resolved"}
    live_open = {a.id for a in state.monitor.evaluator.open_alerts()}
    diff = stored_open ^ live_open
    checks.append(_check("detector_state", "Detector state matches stored open alerts", len(diff), 0,
                         "The monitor restores open alerts at start-up; a difference clears on the next restart."))

    # 4. Simulation runs marked active that no process is running (e.g. after a restart).
    active_id = state.sandbox.run.id if state.sandbox.run is not None and state.sandbox.run.status in ("running", "paused") else None
    async with factory() as session:
        result = await session.scalars(select(MissionSimulationRow).where(
            MissionSimulationRow.status.in_(("running", "paused"))))
        stale = list(result.all())
        stale = [r for r in stale if r.id != active_id]
        if repair:
            for r in stale:
                r.status, r.wall_ended_at = "interrupted", now
                r.error = "The API restarted while this run was active."
            await session.commit()
    checks.append(_check("interrupted_runs", "Simulation runs left active by a restart", len(stale),
                         len(stale) if repair else 0, "Marked as interrupted; their data stay available for playback."))

    # 5. Sandbox samples whose run no longer exists.
    async with factory() as session:
        orphan_samples = await session.scalar(
            select(func.count()).select_from(MissionSimSampleRow)
            .outerjoin(MissionSimulationRow, MissionSimSampleRow.simulation_id == MissionSimulationRow.id)
            .where(MissionSimulationRow.id.is_(None)))
        removed = 0
        if repair and orphan_samples:
            sub = select(MissionSimulationRow.id)
            res = await session.execute(MissionSimSampleRow.__table__.delete().where(
                MissionSimSampleRow.simulation_id.not_in(sub)))
            removed = res.rowcount or 0
            await session.commit()
    checks.append(_check("orphan_sim_samples", "Sandbox samples without a run", int(orphan_samples or 0), removed,
                         "Simulation isolation: sandbox samples live only in mission_sim_samples."))

    # 6. Alert-centre links to events that do not exist.
    async with factory() as session:
        broken = list((await session.scalars(
            select(MissionAlertRow).outerjoin(MissionEventRow, MissionAlertRow.event_id == MissionEventRow.id)
            .where(MissionAlertRow.event_id.is_not(None), MissionEventRow.id.is_(None)))).all())
        if repair:
            for r in broken:
                r.event_id = None
            await session.commit()
    checks.append(_check("alert_event_links", "Alert-centre links to missing events", len(broken),
                         len(broken) if repair else 0, "Broken links are cleared; the alert itself is kept."))

    # 7. Incident reports whose stored snapshot no longer matches its SHA-256 digest.
    from app.reports.service import digest

    async with factory() as session:
        reports = list((await session.scalars(select(IncidentReportRow))).all())
    modified = [r.id for r in reports if digest(r.content) != r.content_sha256]
    checks.append(_check("report_integrity", "Incident report snapshots intact", len(modified), 0,
                         f"{len(reports)} reports checked. A mismatch is evidence of modification and is never repaired."
                         + (f" Modified: {', '.join(modified[:5])}" if modified else ""), warn=False))

    # 8. Stored operations data from the future (clock problems).
    tolerance = timedelta(seconds=max(60.0, state.settings.mission_clock_skew_tolerance_s))
    async with factory() as session:
        future_vitals = await session.scalar(select(func.count()).select_from(VitalSampleRow)
                                             .where(VitalSampleRow.ts > now + tolerance))
        future_events = await session.scalar(select(func.count()).select_from(MissionEventRow)
                                             .where(MissionEventRow.context == "operations",
                                                    MissionEventRow.occurred_at > now + tolerance))
    checks.append(_check("future_timestamps", "No operations data stamped in the future",
                         int(future_vitals or 0) + int(future_events or 0), 0,
                         f"{future_vitals or 0} vital samples and {future_events or 0} events more than "
                         f"{tolerance.total_seconds():.0f} s ahead of the server clock."))

    order = {"ok": 0, "repaired": 1, "warning": 2, "error": 3}
    status = max((c["status"] for c in checks), key=lambda s: order[s], default="ok")
    return {"ran_at": now, "repair": repair, "status": status, "checks": checks}
