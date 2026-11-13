"""Mission analytics: daily aggregates over a date range, with CSV / JSON / Markdown export.

Sources: twin daily summaries (crew trends), rule alerts and AI events (anomalies), sleep sessions,
mission events (environment, distribution), simulated doses and NASA DONKI events (radiation),
the unified alert centre (alert frequency) and the model registry's evaluation results (model
performance, measured on the simulated test split - not on real crew data).
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select

from app.core.timeutil import utcnow
from app.db.models import (
    AlertRow,
    MissionAlertRow,
    MissionEventRow,
    RadiationDoseRow,
    SleepSessionRow,
    TwinDailyRow,
)
from app.simulator.profiles import CREW_BY_ID

MAX_DAYS = 120
TREND_METRICS = ("heart_rate", "spo2", "respiratory_rate", "temperature_c", "hrv_rmssd_ms")


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time(0), tzinfo=UTC), datetime.combine(end + timedelta(days=1), time(0), tzinfo=UTC)


def _stat(metrics: dict[str, Any], m: str) -> float | None:
    v = (metrics or {}).get(m) or {}
    return v.get("awake_rest_mean") if v.get("awake_rest_mean") is not None else v.get("mean")


async def summary(state, *, start: date | None, end: date | None, context: str = "operations",
                  astronaut_id: str | None = None) -> dict[str, Any]:
    today = utcnow().date()
    end = min(end or today, today)
    start = start or end - timedelta(days=13)
    if start > end:
        start, end = end, start
    if (end - start).days >= MAX_DAYS:
        start = end - timedelta(days=MAX_DAYS - 1)
    t0, t1 = _bounds(start, end)
    days = _days(start, end)
    crew = [astronaut_id] if astronaut_id else list(CREW_BY_ID)
    notes: list[str] = []

    async with state.session_factory() as session:
        twin_rows = list((await session.scalars(select(TwinDailyRow).where(
            TwinDailyRow.day >= start, TwinDailyRow.day <= end, TwinDailyRow.astronaut_id.in_(crew))
            .order_by(TwinDailyRow.day))).all())
        rule_alerts = list((await session.scalars(select(AlertRow).where(
            AlertRow.opened_at >= t0, AlertRow.opened_at < t1, AlertRow.astronaut_id.in_(crew)))).all())
        sleep = list((await session.scalars(select(SleepSessionRow).where(
            SleepSessionRow.night >= start, SleepSessionRow.night <= end, SleepSessionRow.astronaut_id.in_(crew))
            .order_by(SleepSessionRow.night))).all())
        doses = list((await session.scalars(select(RadiationDoseRow).where(
            RadiationDoseRow.day >= start, RadiationDoseRow.day <= end, RadiationDoseRow.astronaut_id.in_(crew)))).all())
        ev_stmt = select(MissionEventRow).where(MissionEventRow.occurred_at >= t0, MissionEventRow.occurred_at < t1)
        al_stmt = select(MissionAlertRow).where(MissionAlertRow.created_at >= t0, MissionAlertRow.created_at < t1)
        if context != "all":
            ev_stmt = ev_stmt.where(MissionEventRow.context == context)
            al_stmt = al_stmt.where(MissionAlertRow.context == context)
        if astronaut_id:
            ev_stmt = ev_stmt.where((MissionEventRow.astronaut_id == astronaut_id) | MissionEventRow.astronaut_id.is_(None))
            al_stmt = al_stmt.where((MissionAlertRow.astronaut_id == astronaut_id) | MissionAlertRow.astronaut_id.is_(None))
        events = list((await session.scalars(ev_stmt)).all())
        unified = list((await session.scalars(al_stmt)).all())
        swx = []
        if state.space is not None:
            from app.space import donki
            from app.space import repository as repo

            swx = await repo.list_events(session, t0, t1, donki.RADIATION_RELEVANT)

    # Crew health trends (twin daily summaries).
    trends = []
    for aid in crew:
        rows = [r for r in twin_rows if r.astronaut_id == aid]
        trends.append({"astronaut_id": aid, "name": CREW_BY_ID[aid].name, "points": [
            {"day": r.day, **{m: _stat(r.metrics, m) for m in TREND_METRICS},
             "exercise_minutes": (r.activity or {}).get("exercise_minutes"), "basis": r.basis, "complete": r.complete}
            for r in rows]})
    if not twin_rows:
        notes.append("No digital-twin daily summaries in this range yet (the twin builds them in the background).")

    # Physiological anomalies over time: rule alerts by category and severity, plus AI detections.
    anomalies = {d: Counter() for d in days}
    for a in rule_alerts:
        c = anomalies.setdefault(a.opened_at.date(), Counter())
        c[a.category] += 1
        c[a.severity] += 1
        c["rule_total"] += 1
    for e in events:
        if e.source == "anomaly_detection" and e.occurred_at.date() in anomalies:
            anomalies[e.occurred_at.date()]["ai_detections"] += 1
    anomaly_rows = [{"day": d, **{k: anomalies[d].get(k, 0) for k in (
        "threshold", "rhythm", "baseline", "advisory", "caution", "critical", "rule_total", "ai_detections")}}
        for d in days]

    # Sleep patterns.
    sleep_out = []
    for aid in crew:
        nights = [s for s in sleep if s.astronaut_id == aid]
        durations = [s.duration_hours for s in nights]
        sleep_out.append({"astronaut_id": aid, "name": CREW_BY_ID[aid].name,
                          "mean_duration_hours": round(sum(durations) / len(durations), 2) if durations else None,
                          "nights": [{"night": s.night, "duration_hours": round(s.duration_hours, 2),
                                      "efficiency_pct": round(s.efficiency_pct, 1),
                                      "onset_offset_min": round((s.start - s.scheduled_start).total_seconds() / 60, 1)}
                                     for s in nights]})

    # Environmental changes and radiation history.
    dose_by_day: dict[date, list[float]] = defaultdict(list)
    spe_days: set[date] = set()
    for r in doses:
        dose_by_day[r.day].append(r.dose_msv)
        if r.solar_particle_event:
            spe_days.add(r.day)
    env_counts = {d: Counter() for d in days}
    for e in events:
        if e.category in ("environment", "radiation", "solar_activity") and e.occurred_at.date() in env_counts:
            env_counts[e.occurred_at.date()][e.category] += 1
    environment = [{"day": d, "environment_events": env_counts[d].get("environment", 0),
                    "radiation_events": env_counts[d].get("radiation", 0),
                    "solar_activity_events": env_counts[d].get("solar_activity", 0),
                    "mean_crew_dose_msv": round(sum(dose_by_day[d]) / len(dose_by_day[d]), 4) if dose_by_day[d] else None,
                    "simulated_spe": d in spe_days} for d in days]
    swx_by_day = {d: Counter() for d in days}
    for e in swx:
        day = (e.peak_time or e.start_time).date()
        if day in swx_by_day:
            swx_by_day[day][e.event_type] += 1
    radiation = {
        "donki_by_day": [{"day": d, **{t: swx_by_day[d].get(t, 0) for t in ("FLR", "CME", "SEP", "GST", "RBE")}}
                         for d in days],
        "donki_totals": dict(Counter(e.event_type for e in swx)),
        "simulated_spe_days": sorted(spe_days),
        "cumulative_crew_dose_msv": {aid: round(sum(r.dose_msv for r in doses if r.astronaut_id == aid), 3) for aid in crew},
        "notes": ["DONKI counts are real NASA environmental indicators.",
                  "Doses are simulated (category D); indicators are never converted into doses."],
    }

    # Model prediction performance (offline evaluation) and operational AI alert outcomes.
    perf: dict[str, Any] = {"available": False}
    bundle = await state.ai.bundle()
    if bundle is not None:
        res = bundle.results
        anomaly = res.get("anomaly", {})
        forecast = res.get("forecast", {})
        metric_keys = ("precision", "recall", "f1", "auroc", "auprc", "false_alarms_per_day")
        ens = anomaly.get("ensemble") or {}
        detectors = [{"name": "ensemble", "label": ens.get("label", "Calibrated ensemble"),
                      **{k: (ens.get("test") or {}).get(k) for k in metric_keys},
                      "event_recall": (ens.get("events") or {}).get("event_recall")}]
        for name, v in (anomaly.get("models") or {}).items():
            detectors.append({"name": name, "label": v.get("label", name), **{k: (v.get("test") or {}).get(k) for k in metric_keys},
                              "event_recall": (v.get("events") or {}).get("event_recall")})
        forecasters = []
        for name, v in (forecast.get("models") or {}).items():
            row: dict[str, Any] = {"name": name, "label": v.get("label", name), "family": v.get("family")}
            for sig, by_h in (v.get("by_signal") or {}).items():
                for h in ("1h", "6h", "24h"):
                    m = by_h.get(h) or {}
                    row[f"{sig}_{h}_mae"] = m.get("mae")
                    row[f"{sig}_{h}_coverage"] = m.get("coverage")
            row["skill_hr_6h"] = ((v.get("skill_vs_climatology") or {}).get("heart_rate") or {}).get("6h")
            forecasters.append(row)
        perf = {
            "available": True, "model_version": bundle.version, "basis": "Chronological test split of the simulated dataset",
            "anomaly": {"target_false_alarm_rate": anomaly.get("target_false_alarm_rate"),
                        "test_windows": anomaly.get("test_windows"), "detectors": detectors},
            "forecast": {"serving": bundle.serving, "interval_nominal_coverage": forecast.get("interval_nominal_coverage"),
                         "models": forecasters},
        }
    ai_alerts = [a for a in unified if a.classification == "experimental_ai"]
    perf["operational"] = {
        "ai_alerts": len(ai_alerts),
        "acknowledged": sum(1 for a in ai_alerts if a.acknowledged_at),
        "resolved": sum(1 for a in ai_alerts if a.status == "resolved"),
        "note": "Operational counts show how AI alerts were handled. With simulated data there is no ground truth to "
                "score them against; the evaluation metrics above come from the labelled simulated test split.",
    }

    # Alert frequency (unified alert centre).
    freq = {d: Counter() for d in days}
    for a in unified:
        d = a.created_at.date()
        if d in freq:
            freq[d][f"p{a.priority}"] += 1
            freq[d]["total"] += 1
    alert_rows = [{"day": d, **{k: freq[d].get(k, 0) for k in ("p1", "p2", "p3", "p4", "total")}} for d in days]
    totals = {"total": len(unified), "by_source": dict(Counter(a.source for a in unified)),
              "by_status": dict(Counter(a.status for a in unified)),
              "by_classification": dict(Counter(a.classification for a in unified)),
              "by_astronaut": dict(Counter(a.astronaut_id or "crew-wide" for a in unified))}

    dist = {"total": len(events)}
    for key, attr in (("by_category", "category"), ("by_source", "source"), ("by_priority", "priority"),
                      ("by_origin", "data_origin"), ("by_severity", "severity")):
        dist[key] = {str(k): v for k, v in Counter(getattr(e, attr) for e in events).items()}
    if not events:
        notes.append("The unified event store starts recording when phase 6 is first started; earlier days show "
                     "rule alerts, sleep, doses and NASA events only.")
    notes.append("All crew data are simulated. Model metrics come from simulated test data, not real crew data.")
    return {"generated_at": utcnow(), "start": start, "end": end, "context": context, "astronaut_id": astronaut_id,
            "crew_trends": trends, "anomalies": anomaly_rows, "sleep": sleep_out, "environment": environment,
            "radiation": radiation, "model_performance": perf, "alert_frequency": alert_rows, "alert_totals": totals,
            "event_distribution": dist, "notes": notes}


def _json(obj: Any) -> Any:
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    raise TypeError(type(obj).__name__)


def export(data: dict[str, Any], fmt: str) -> tuple[str, str, str]:
    """(body, media type, file extension)."""
    stamp = f"{data['start']}_{data['end']}"
    if fmt == "json":
        return json.dumps(data, default=_json, indent=2), "application/json", f"astra-med-analytics-{stamp}.json"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["# ASTRA-MED mission analytics (simulated crew data; NASA DONKI counts are real)"])
        w.writerow(["day", "rule_alerts", "ai_detections", "alerts_p1", "alerts_p2", "alerts_p3", "alerts_p4",
                    "environment_events", "radiation_events", "solar_activity_events", "mean_crew_dose_msv",
                    "simulated_spe", "donki_flr", "donki_cme", "donki_sep", "donki_gst", "donki_rbe"])
        by_day = lambda rows: {r["day"]: r for r in rows}  # noqa: E731
        an, al, en, rd = (by_day(data["anomalies"]), by_day(data["alert_frequency"]), by_day(data["environment"]),
                          by_day(data["radiation"]["donki_by_day"]))
        for d in sorted(an):
            w.writerow([d.isoformat(), an[d]["rule_total"], an[d]["ai_detections"], al[d]["p1"], al[d]["p2"],
                        al[d]["p3"], al[d]["p4"], en[d]["environment_events"], en[d]["radiation_events"],
                        en[d]["solar_activity_events"], en[d]["mean_crew_dose_msv"], en[d]["simulated_spe"],
                        rd[d]["FLR"], rd[d]["CME"], rd[d]["SEP"], rd[d]["GST"], rd[d]["RBE"]])
        w.writerow([])
        w.writerow(["astronaut_id", "day", *TREND_METRICS])
        for t in data["crew_trends"]:
            for p in t["points"]:
                w.writerow([t["astronaut_id"], p["day"].isoformat(), *[p.get(m) for m in TREND_METRICS]])
        return buf.getvalue(), "text/csv", f"astra-med-analytics-{stamp}.csv"
    # markdown summary
    lines = [f"# ASTRA-MED mission analytics, {data['start']} to {data['end']}", "",
             f"Context: {data['context']}{' - ' + data['astronaut_id'] if data['astronaut_id'] else ''}. "
             f"Generated {data['generated_at']:%Y-%m-%d %H:%M} UTC.", "",
             "> All crew data are simulated; crew members are fictional. NASA DONKI counts are real environmental "
             "indicators. Model metrics come from simulated test data.", "",
             "## Alerts", "", f"- Unified alerts: {data['alert_totals']['total']}",
             *[f"- {k.replace('_', ' ')}: {v}" for k, v in sorted(data['alert_totals']['by_source'].items())],
             "", "## Physiological anomalies", "",
             f"- Rule alerts: {sum(r['rule_total'] for r in data['anomalies'])} "
             f"(critical {sum(r['critical'] for r in data['anomalies'])}, caution {sum(r['caution'] for r in data['anomalies'])}, "
             f"advisory {sum(r['advisory'] for r in data['anomalies'])})",
             f"- AI anomaly detections (experimental): {sum(r['ai_detections'] for r in data['anomalies'])}",
             "", "## Sleep", "",
             *[f"- {s['name']}: mean {s['mean_duration_hours']} h over {len(s['nights'])} nights" for s in data["sleep"]],
             "", "## Radiation and space weather", "",
             f"- DONKI radiation-relevant events: {data['radiation']['donki_totals'] or 'none'}",
             f"- Simulated SPE days: {len(data['radiation']['simulated_spe_days'])}",
             *[f"- {aid} cumulative simulated dose in range: {v} mSv" for aid, v in data["radiation"]["cumulative_crew_dose_msv"].items()],
             "", "## Mission events", "", f"- Total: {data['event_distribution']['total']}",
             *[f"- {k}: {v}" for k, v in sorted(data['event_distribution'].get('by_category', {}).items())],
             "", "## Model performance (simulated test split)", ""]
    perf = data["model_performance"]
    if perf.get("available"):
        lines.append(f"- Model version {perf['model_version']}, serving forecaster {perf['forecast']['serving']}")
        lines.append(f"- AI alerts handled: {perf['operational']['ai_alerts']} raised, "
                     f"{perf['operational']['acknowledged']} acknowledged, {perf['operational']['resolved']} resolved")
    else:
        lines.append("- No trained model version loaded.")
    lines += ["", *[f"_{n}_" for n in data["notes"]], ""]
    return "\n".join(lines), "text/markdown", f"astra-med-analytics-{stamp}.md"
