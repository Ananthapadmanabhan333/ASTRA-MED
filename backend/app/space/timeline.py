"""Unified mission timeline.

Two modes, because the data live on different clocks:

* ``mission``: the fictional crew's mission (simulated physiology, alerts, AI detections,
  simulation scenarios) on the same UTC axis as real DONKI space-weather events for those dates.
* ``iss``: a historical ISS mission from EDA (measured cabin telemetry and dosimetry) with the
  real DONKI events that occurred during it.

All times are UTC; the frontend renders them in the selected display timezone.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import alerts as alerts_repo
from app.repositories import events as sim_repo
from app.repositories import vitals as vitals_repo
from app.services.history import bucket_rows
from app.space import donki
from app.space import repository as repo
from app.space.intel import VANTAGE_NOTE, alert_for

MAX_MISSION_RANGE = timedelta(days=31)
PROXIMITY_NOTE = "Closeness in time is not evidence of a causal link."


def _swx_item(e) -> dict[str, Any]:
    alert = alert_for(e)
    return {
        "id": f"swx-{e.id}", "lane": "space_weather", "ts": e.peak_time or e.start_time, "start": e.start_time,
        "end": e.end_time, "title": f"{donki.EVENT_TYPES[e.event_type]}" + (f" {e.scale}" if e.scale else ""),
        "detail": e.classification, "kind": e.event_type,
        "severity": alert["severity"] if alert else None, "category": e.category, "source": "NASA DONKI",
        "link": e.link,
    }


async def space_weather_items(session: AsyncSession, start: datetime, end: datetime,
                              types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    events = await repo.list_events(session, start, end, types or tuple(t for t in donki.EVENT_TYPES if t != "WSA"))
    return [_swx_item(e) for e in reversed(events)]


async def mission_timeline(session: AsyncSession, ai_service, start: datetime, end: datetime,
                           astronaut_id: str | None, include_ai: bool = True) -> dict[str, Any]:
    if end - start > MAX_MISSION_RANGE:
        start = end - MAX_MISSION_RANGE
    lanes: dict[str, dict[str, Any]] = {
        "space_weather": {"key": "space_weather", "label": "Space weather (NASA DONKI)", "category": "indicator", "items": []},
        "notifications": {"key": "notifications", "label": "DONKI notifications", "category": "indicator", "items": []},
        "crew_alerts": {"key": "crew_alerts", "label": "Crew alerts", "category": "simulated", "items": []},
        "ai": {"key": "ai", "label": "AI anomaly detections", "category": "simulated", "items": []},
        "simulation": {"key": "simulation", "label": "Simulation scenarios", "category": "simulated", "items": []},
    }
    lanes["space_weather"]["items"] = await space_weather_items(session, start, end)
    for n in reversed(await repo.list_notifications(session, start, end, limit=300)):
        lanes["notifications"]["items"].append({
            "id": f"note-{n.id}", "lane": "notifications", "ts": n.issue_time, "start": n.issue_time, "end": None,
            "title": f"{n.message_type} notification", "detail": n.summary, "kind": n.message_type,
            "severity": None, "category": "indicator", "source": "NASA DONKI", "link": n.url,
        })
    for a in reversed(await alerts_repo.list_alerts(session, astronaut_id=astronaut_id, since=start, limit=500)):
        if a.opened_at > end:
            continue
        lanes["crew_alerts"]["items"].append({
            "id": a.id, "lane": "crew_alerts", "ts": a.opened_at, "start": a.opened_at,
            "end": a.resolved_at or a.condition_cleared_at, "title": f"{a.astronaut_id}: {a.title}",
            "detail": a.message, "kind": a.metric, "severity": a.severity, "category": "simulated",
            "source": "ASTRA-MED simulator", "link": None, "astronaut_id": a.astronaut_id,
        })
    for s in reversed(await sim_repo.list_events(session, astronaut_id=astronaut_id, since=start - timedelta(days=1), limit=300)):
        if s.started_at > end or s.ends_at < start:
            continue
        lanes["simulation"]["items"].append({
            "id": s.id, "lane": "simulation", "ts": s.started_at, "start": s.started_at, "end": s.cancelled_at or s.ends_at,
            "title": f"Scenario: {s.scenario.replace('_', ' ')}", "detail": f"{s.astronaut_id or 'habitat'}, intensity {s.intensity:g}, {s.triggered_by}",
            "kind": s.scenario, "severity": None, "category": "simulated", "source": "ASTRA-MED simulator",
            "link": None, "astronaut_id": s.astronaut_id,
        })

    series: list[dict[str, Any]] = []
    notes: list[str] = []
    if astronaut_id:
        rows = await vitals_repo.fetch_range(session, astronaut_id, start, end, ("heart_rate", "spo2", "respiratory_rate"))
        buckets = bucket_rows(rows, start, 3600, 3)
        for i, (key, label, unit) in enumerate((("heart_rate", "Heart rate", "bpm"), ("spo2", "SpO₂", "%"),
                                                 ("respiratory_rate", "Respiratory rate", "breaths/min"))):
            series.append({"key": key, "label": label, "unit": unit, "category": "simulated",
                           "points": [{"ts": ts, "value": round(v[i], 2)} for ts, v, _ in buckets]})
        if include_ai and ai_service is not None and (end - start) <= timedelta(days=7):
            try:
                from app.schemas.ai import AnomalyDetectionRequest

                det = await ai_service.detect(AnomalyDetectionRequest(astronaut_id=astronaut_id, start=start, end=end,
                                                                      include_explanations=False))
                for d in det.get("detections", []):
                    signals = list(d.get("signals") or [])
                    lanes["ai"]["items"].append({
                        "id": f"ai-{astronaut_id}-{d['start']}", "lane": "ai", "ts": d["peak_ts"],
                        "start": d["start"], "end": d["end"],
                        "title": f"{astronaut_id}: anomaly ({', '.join(signals[:3]) or 'multivariate'})",
                        "detail": f"{d['kind'].replace('_', ' ')}, peak {d['peak_score']:.2f}x threshold, "
                                  f"{d['duration_minutes']:.0f} min",
                        "kind": "anomaly", "severity": None, "category": "simulated",
                        "source": "ASTRA-MED AI engine (experimental)", "link": None, "astronaut_id": astronaut_id,
                    })
            except Exception as exc:  # AI models may be untrained; the timeline still works
                notes.append(f"AI detections unavailable: {exc}")
        elif include_ai:
            notes.append("AI detections are computed for ranges up to 7 days with one crew member selected.")
    else:
        notes.append("Select a crew member to add physiological series and AI detections.")
    notes.append("Space-weather events are real NASA data; crew data are simulated and are not influenced by them.")
    notes.append(VANTAGE_NOTE)
    return {"mode": "mission", "start": start, "end": end, "astronaut_id": astronaut_id, "mission": None,
            "lanes": list(lanes.values()), "series": series, "notes": notes}


async def iss_timeline(session: AsyncSession, mission: str) -> dict[str, Any] | None:
    m = await repo.get_mission(session, mission)
    if m is None or m.start_time is None:
        return None
    start, end = m.start_time, m.end_time or m.start_time
    lanes = [
        {"key": "space_weather", "label": "Space weather (NASA DONKI)", "category": "indicator",
         "items": await space_weather_items(session, start - timedelta(days=1), end, donki.HISTORICAL_TYPES)},
        {"key": "milestones", "label": "Mission milestones (EDA)", "category": "metadata",
         "items": [{"id": f"ms-{i}", "lane": "milestones", "ts": datetime.fromisoformat(ms["time"]),
                    "start": datetime.fromisoformat(ms["time"]), "end": None, "title": ms["label"].replace("_", " "),
                    "detail": None, "kind": "milestone", "severity": None, "category": "metadata",
                    "source": "NASA OSDR EDA", "link": m.link} for i, ms in enumerate(m.milestones or [])]},
    ]
    series = []
    rows = await repo.measurements(session, mission, platform="iss")
    by_q: dict[str, list] = {}
    for r in rows:
        by_q.setdefault(r.quantity, []).append(r)
    from app.space.eda import QUANTITY_LABELS

    for q in ("dose_total_mgy_day", "temperature_c", "co2_ppm", "humidity_pct"):
        pts = by_q.get(q, [])
        if q != "dose_total_mgy_day":  # telemetry: daily means keep the timeline light
            daily: dict[datetime, list[float]] = {}
            for r in pts:
                daily.setdefault(r.ts.replace(hour=12, minute=0, second=0, microsecond=0), []).append(r.value)
            points = [{"ts": ts, "value": round(sum(v) / len(v), 3)} for ts, v in sorted(daily.items())]
        else:
            points = [{"ts": r.ts.replace(hour=12), "value": r.value, "approximate": r.approximate} for r in pts]
        if points:
            series.append({"key": q, "label": QUANTITY_LABELS[q], "unit": pts[0].unit, "category": "measured", "points": points})
    notes = [
        f"Historical ISS mission {m.name} ({start:%Y-%m-%d} to {end:%Y-%m-%d}). Measured environment data, not current telemetry.",
        "Doses are absorbed dose at the experiment location, not any astronaut's dose.",
    ]
    return {"mode": "iss", "start": start, "end": end, "astronaut_id": None, "mission": m.name,
            "lanes": lanes, "series": series, "notes": notes}


async def nearby_events(session: AsyncSession, ts: datetime, window_hours: float) -> dict[str, Any]:
    span = timedelta(hours=window_hours)
    events = await repo.list_events(session, ts - span, ts + span)
    items = []
    for e in events:
        ref = e.peak_time or e.start_time
        if abs(ref - ts) > span and not (e.end_time and e.start_time <= ts <= e.end_time):
            continue
        item = _swx_item(e)
        item["offset_hours"] = round((ref - ts).total_seconds() / 3600, 2)
        items.append(item)
    items.sort(key=lambda i: abs(i["offset_hours"]))
    return {"ts": ts, "window_hours": window_hours, "events": items, "note": PROXIMITY_NOTE + " " + VANTAGE_NOTE}
