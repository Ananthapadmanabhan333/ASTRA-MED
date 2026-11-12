"""Read models for the twin endpoints: profile, timeline, longitudinal trends and mission stages."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models import AstronautRow, SpaceWeatherEventRow, TwinDailyRow
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.services import mappers
from app.services.health import crew_status
from app.services.monitoring import MonitoringService
from app.simulator.radiation import CAREER_LIMIT_MSV
from app.twin import TWIN_DISCLAIMER
from app.twin import summary as S
from app.twin.categories import legend
from app.twin.service import TwinService, daily_series
from app.twin.stages import STAGES, stage_for

EARLY_STAGE = STAGES[0]
TREND_METRICS = (*S.METRICS, "sleep_duration_hours", "sleep_efficiency_pct", "dose_msv", "exercise_minutes")
TREND_LABELS = S.LABELS | {
    "sleep_duration_hours": "Sleep duration", "sleep_efficiency_pct": "Sleep efficiency",
    "dose_msv": "Daily dose (simulated)", "exercise_minutes": "Exercise",
}
TREND_UNITS = S.UNITS | {"sleep_duration_hours": "h", "sleep_efficiency_pct": "%", "dose_msv": "mSv",
                         "exercise_minutes": "min"}
NO_ADAPTATION_NOTE = (
    "The simulator does not model long-term physiological adaptation to spaceflight, so differences "
    "between stages reflect day-to-day variation and test scenarios, not adaptation."
)


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


def _round(metric: str, v: float | None) -> float | None:
    return S._r(metric, v) if metric in S.METRICS else (None if v is None else round(v, 3) + 0.0)


async def space_by_day(session: AsyncSession, first: date, last: date) -> dict[date, dict[str, Any]]:
    """Real NASA DONKI events per day: count and highest scale per type (indicator category)."""
    start = datetime.combine(first, time(0), tzinfo=UTC)
    stop = datetime.combine(last + timedelta(days=1), time(0), tzinfo=UTC)
    rows = (await session.execute(
        select(SpaceWeatherEventRow.event_type, SpaceWeatherEventRow.start_time, SpaceWeatherEventRow.scale,
               SpaceWeatherEventRow.severity)
        .where(SpaceWeatherEventRow.start_time >= start, SpaceWeatherEventRow.start_time < stop,
               SpaceWeatherEventRow.event_type.in_(("FLR", "CME", "SEP", "GST")))
    )).all()
    out: dict[date, dict[str, Any]] = defaultdict(dict)
    for etype, ts, scale, severity in rows:
        d = ts.date()
        if d < first or d > last:
            continue
        slot = out[d].setdefault(etype, {"count": 0, "max_severity": 0, "max_scale": None})
        slot["count"] += 1
        if (severity or 0) > slot["max_severity"]:
            slot["max_severity"], slot["max_scale"] = severity, scale
    return out


def day_view(r: TwinDailyRow, space: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "day": r.day, "mission_day": r.mission_day, "stage": r.stage, "basis": r.basis, "complete": r.complete,
        "category": "simulated" if r.basis == "stored" else "regenerated",
        "metrics": r.metrics, "activity": r.activity, "sleep": r.sleep, "radiation": r.radiation,
        "events": r.events, "coverage": r.coverage, "computed_at": r.computed_at,
        "space_weather": space or {},
    }


async def profile(twin: TwinService, ai, session: AsyncSession, row: AstronautRow, monitor: MonitoringService,
                  now: datetime) -> dict[str, Any]:
    aid = row.id
    days = await twin.days(aid)
    mission_day = (now.date() - twin.settings.mission_start_date).days
    live = monitor.latest_reading(aid)
    source = live if live is not None else await vitals_repo.latest(session, aid)
    latest = mappers.reading_schema(source) if source is not None else None
    latest_ts = latest.ts if latest else None
    alerts = monitor.open_alerts_for(aid)
    scenarios = monitor.active_scenarios(now, aid)

    # Resting (awake, no scenario) comparison: configured values, early mission, last 7 days, last 24 h.
    early = [d for d in days if EARLY_STAGE.contains(d.mission_day)]
    week = [d for d in days if d.day > now.date() - timedelta(days=7)]
    personal: dict[str, Any] = {}
    if ai is not None:
        try:
            report = await ai.baseline_report(aid)
            for sig in report.get("signals", []):
                awake = [sig["by_state"][s] for s in ("rest", "work") if s in sig["by_state"]]
                if awake:
                    personal[sig["signal"]] = round(float(np.mean([a["center"] for a in awake])), 2)
        except ApiError:
            personal = {}
    rows_24h = await vitals_repo.fetch_range(session, aid, now - timedelta(hours=24), now,
                                             columns=("heart_rate", "spo2", "systolic", "diastolic", "temperature_c",
                                                      "respiratory_rate", "hrv_rmssd_ms", "activity_state", "scenario"))
    df24 = S.frame(rows_24h, ("ts", "heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate",
                              "hrv_rmssd_ms", "activity_state", "scenario"))
    m24 = S.summarize_metrics(df24)
    comparison = []
    configured = row.baseline or {}
    for m in S.METRICS:
        e = _mean([(d.metrics.get(m) or {}).get("awake_rest_mean") for d in early])
        w = _mean([(d.metrics.get(m) or {}).get("awake_rest_mean") for d in week])
        last = (m24.get(m) or {}).get("awake_rest_mean")
        change = None
        if e is not None and w is not None:
            change = {"abs": _round(m, w - e), "pct": round(100 * (w - e) / e, 2) if e else None}
        comparison.append({
            "metric": m, "label": S.LABELS[m], "unit": S.UNITS[m],
            "configured": {"value": configured.get(m if m != "hrv_rmssd_ms" else "hrv_sdnn_ms"),
                           "category": "configured",
                           "note": "Simulator setting" + (" (SDNN, not RMSSD)" if m == "hrv_rmssd_ms" else "")},
            "early_mission": {"value": _round(m, e), "n_days": len(early), "category": "derived",
                              "basis": sorted({d.basis for d in early})},
            "last_7d": {"value": _round(m, w), "n_days": len(week), "category": "derived"},
            "last_24h": {"value": last, "n": (m24.get(m) or {}).get("awake_rest_n", 0), "category": "derived"},
            "personal_baseline": {"value": personal.get(m), "category": "model",
                                  "note": "Phase 3 learned baseline (awake rest/work), last 7 days of samples"},
            "change_7d_vs_early": change,
        })

    total = await sr_repo.mission_total(session, aid)
    last30 = sum((d.radiation or {}).get("dose_msv", 0.0) for d in days if d.day > now.date() - timedelta(days=30))
    spe_days = sum(1 for d in days if (d.radiation or {}).get("solar_particle_event"))
    sleep_week = [d.sleep for d in week if d.sleep]
    stage = stage_for(mission_day)
    return {
        "astronaut": row,
        "generated_at": now,
        "twin_updated_at": twin.updated_at.get(aid),
        "last_measurement_at": latest_ts,
        "mission": {"day": mission_day, "stage": {"key": stage.key, "label": stage.label},
                    "stages": [{"key": s.key, "label": s.label, "first_day": s.first_day, "last_day": s.last_day}
                               for s in STAGES]},
        "current": {
            "reading": latest, "status": crew_status(alerts), "open_alerts": len(alerts),
            "active_scenarios": [s.spec.label for s in scenarios], "category": "simulated",
        },
        "resting_comparison": comparison,
        "exposure": {
            "mission_dose_msv": round(total, 3), "last_30d_dose_msv": round(last30, 3), "spe_days": spe_days,
            "career_total_msv": round(row.prior_career_dose_msv + total, 2),
            "career_limit_msv": CAREER_LIMIT_MSV, "category": "simulated",
            "note": "Simulated crew dose. Real NASA ISS dosimetry is shown separately and never added to it.",
        },
        "sleep_7d": {
            "nights": len(sleep_week),
            "mean_duration_hours": _round("x", _mean([s["duration_hours"] for s in sleep_week])),
            "mean_efficiency_pct": _round("x", _mean([s["efficiency_pct"] for s in sleep_week])),
            "category": "simulated",
        },
        "coverage": {
            "first_day": days[0].day if days else None, "last_day": days[-1].day if days else None,
            "days_total": len(days), "days_stored": sum(1 for d in days if d.basis == "stored"),
            "days_regenerated": sum(1 for d in days if d.basis == "regenerated"),
            "retention_days": twin.settings.history_retention_days,
        },
        "categories": legend("simulated", "regenerated", "derived", "configured", "model", "indicator"),
        "disclaimer": TWIN_DISCLAIMER,
    }


def trend(rows: list[TwinDailyRow], metric: str, statistic: str) -> dict[str, Any]:
    df = daily_series(rows, metric, statistic)
    points = []
    values = df["value"].tolist() if not df.empty else []
    for i, rec in enumerate(df.to_dict("records") if not df.empty else []):
        window = [v for v in values[max(0, i - 6): i + 1] if v is not None]
        points.append({
            "day": rec["day"], "mission_day": rec["mission_day"], "stage": rec["stage"], "basis": rec["basis"],
            "complete": rec["complete"], "value": rec["value"],
            "rolling_7d": _round(metric, float(np.mean(window))) if len(window) >= 4 else None,
        })
    complete = df[df["complete"]] if not df.empty else df
    fit = S.series_trend(complete["mission_day"].tolist(), complete["value"].tolist()) if not df.empty else None
    cumulative = None
    if metric == "dose_msv":
        run = 0.0
        cumulative = []
        for p in points:
            run += p["value"] or 0.0
            cumulative.append({"day": p["day"], "value": round(run, 3)})
    return {
        "metric": metric, "statistic": statistic, "label": TREND_LABELS.get(metric, metric),
        "unit": TREND_UNITS.get(metric, ""), "points": points, "trend": fit, "cumulative": cumulative,
        "category": "derived",
        "method": "Daily values; 7-day rolling mean (needs 4+ days); OLS slope per 30 days on complete days, "
                  "95% CI with degrees of freedom reduced for lag-1 autocorrelation of residuals.",
        "notes": [NO_ADAPTATION_NOTE] if metric in S.METRICS else [],
    }


def stages(rows: list[TwinDailyRow], metrics: tuple[str, ...]) -> dict[str, Any]:
    from scipy import stats as st

    out = []
    reference: dict[str, list[float]] = {}
    for stage in STAGES:
        in_stage = [r for r in rows if r.stage == stage.key and r.complete]
        if not in_stage:
            continue
        entry: dict[str, Any] = {"key": stage.key, "label": stage.label, "first_day": stage.first_day,
                                 "last_day": stage.last_day, "n_days": len(in_stage),
                                 "basis": dict(sorted({b: sum(1 for r in in_stage if r.basis == b)
                                                       for b in {r.basis for r in in_stage}}.items())),
                                 "metrics": {}}
        for m in metrics:
            stat = "awake_rest_mean" if m in S.METRICS else "value"
            vals = [v for v in daily_series(in_stage, m, stat)["value"].tolist() if v is not None and not
                    (isinstance(v, float) and math.isnan(v))]
            if not vals:
                continue
            block: dict[str, Any] = {"mean": _round(m, float(np.mean(vals))),
                                     "sd": _round(m, float(np.std(vals, ddof=1))) if len(vals) > 1 else None,
                                     "n_days": len(vals)}
            if m not in reference:
                reference[m] = vals
            elif len(vals) > 1 and len(reference[m]) > 1:
                ref = reference[m]
                diff = float(np.mean(vals) - np.mean(ref))
                va, vb = np.var(vals, ddof=1) / len(vals), np.var(ref, ddof=1) / len(ref)
                se = math.sqrt(va + vb)
                dof = (va + vb) ** 2 / ((va**2) / (len(vals) - 1) + (vb**2) / (len(ref) - 1)) if se > 0 else 1
                t = st.t.ppf(0.975, max(1.0, dof))
                block["vs_first_stage"] = {"diff": _round(m, diff),
                                           "ci95": [_round(m, diff - t * se), _round(m, diff + t * se)]}
            entry["metrics"][m] = block
        out.append(entry)
    return {"stages": out, "statistic": "Mean of daily awake-rest means (vital signs) or daily values",
            "comparison": "Difference from the first stage with data, Welch 95% CI (days treated as independent).",
            "notes": [NO_ADAPTATION_NOTE], "category": "derived"}
