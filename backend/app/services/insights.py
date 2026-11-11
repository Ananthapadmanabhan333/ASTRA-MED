"""Generated decision-support insights.

Version 1 is a transparent rule engine: every insight lists the evidence it was derived from,
so an operator can verify it. Insights flag patterns worth a flight surgeon's attention; they
are not diagnoses and not clinical recommendations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AstronautRow
from app.detection.rules import METRIC_LABELS
from app.repositories import alerts as alerts_repo
from app.repositories import astronauts as astronauts_repo
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.schemas.insights import Evidence, Insight
from app.services.monitoring import MonitoringService
from app.simulator.radiation import CAREER_LIMIT_MSV
from app.simulator.schedule import exercise_minutes_on

SEVERITY_ORDER = {"caution": 0, "advisory": 1, "info": 2}


def _hhmm(hours: float) -> str:
    total = round(hours * 60) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _insight(row: AstronautRow, key: str, now: datetime, **kw) -> Insight:
    return Insight(id=f"{row.id}:{key}", astronaut_id=row.id, generated_at=now, **kw)


async def _sleep_insights(session: AsyncSession, row: AstronautRow, now: datetime) -> list[Insight]:
    nights = await sr_repo.list_sleep(session, row.id, now.date() - timedelta(days=8), limit=7)
    out: list[Insight] = []
    if len(nights) < 3:
        return out
    recent = nights[:3]
    recent_avg = mean(n.duration_hours for n in recent)
    shortfall = row.sleep_target_hours - recent_avg
    if shortfall >= 0.75:
        out.append(
            _insight(
                row, "sleep-debt", now,
                category="sleep",
                severity="caution" if shortfall >= 1.25 else "advisory",
                title="Accumulating sleep debt",
                summary=(
                    f"Sleep averaged {recent_avg:.1f} h over the last 3 nights against a "
                    f"{row.sleep_target_hours:.1f} h target."
                ),
                evidence=[
                    Evidence(label=f"Night of {n.night:%d %b}", value=f"{n.duration_hours:.1f} h, {n.efficiency_pct:.0f}% efficiency")
                    for n in recent
                ],
                suggested_action="Review workload scheduling and sleep-station conditions with the crew member.",
            )
        )
    offsets = [(n.start - n.scheduled_start).total_seconds() / 60 for n in nights]
    avg_offset = mean(offsets)
    if abs(avg_offset) >= 45:
        out.append(
            _insight(
                row, "circadian-drift", now,
                category="circadian",
                severity="advisory",
                title="Sleep onset drifting from schedule",
                summary=(
                    f"Sleep has started on average {abs(avg_offset):.0f} min "
                    f"{'after' if avg_offset > 0 else 'before'} the scheduled time over {len(nights)} nights."
                ),
                evidence=[
                    Evidence(label="Scheduled sleep start", value=f"{_hhmm(row.sleep_start_hour)} UTC"),
                    Evidence(label="Mean onset offset", value=f"{avg_offset:+.0f} min"),
                ],
                suggested_action="Consider adjusting lighting protocol or pre-sleep schedule.",
            )
        )
    return out


async def _cardio_insights(session: AsyncSession, row: AstronautRow, now: datetime) -> list[Insight]:
    states = ("work", "rest")
    recent = await vitals_repo.mean_metric(session, row.id, "heart_rate", now - timedelta(hours=24), now, states)
    prior = await vitals_repo.mean_metric(
        session, row.id, "heart_rate", now - timedelta(days=7), now - timedelta(hours=24), states
    )
    if recent is None or prior is None:
        return []
    delta = recent - prior
    if delta < 5:
        return []
    return [
        _insight(
            row, "resting-hr-trend", now,
            category="cardiovascular",
            severity="advisory",
            title="Resting heart rate trending up",
            summary=f"Awake resting heart rate is {delta:.1f} bpm above the previous 6-day average.",
            evidence=[
                Evidence(label="Last 24 h mean (awake, at rest)", value=f"{recent:.1f} bpm"),
                Evidence(label="Previous 6 days mean", value=f"{prior:.1f} bpm"),
            ],
            suggested_action="Check hydration, sleep and exercise load; review at the next medical conference.",
        )
    ]


async def _alert_insights(session: AsyncSession, row: AstronautRow, now: datetime) -> list[Insight]:
    counts = await alerts_repo.count_since(session, row.id, now - timedelta(hours=48))
    out = []
    for metric, count in counts:
        if count >= 2:
            label = METRIC_LABELS.get(metric, metric)
            out.append(
                _insight(
                    row, f"recurring-{metric}", now,
                    category="alerts",
                    severity="caution" if count >= 3 else "advisory",
                    title=f"Recurring {label.lower()} alerts",
                    summary=f"{count} {label.lower()} alerts opened in the last 48 hours.",
                    evidence=[Evidence(label="Alerts in 48 h", value=str(count))],
                    suggested_action="Look for a common trigger (activity, time of day, environment) across these alerts.",
                )
            )
    return out


async def _radiation_insights(session: AsyncSession, row: AstronautRow, now: datetime) -> list[Insight]:
    mission = await sr_repo.mission_total(session, row.id)
    career = row.prior_career_dose_msv + mission
    pct = 100 * career / CAREER_LIMIT_MSV
    if pct < 50:
        return []
    return [
        _insight(
            row, "radiation-career", now,
            category="radiation",
            severity="caution" if pct >= 75 else "advisory",
            title="Career radiation dose above half of reference limit",
            summary=f"Cumulative dose is {career:.0f} mSv, {pct:.0f}% of the 600 mSv reference limit.",
            evidence=[
                Evidence(label="Prior missions", value=f"{row.prior_career_dose_msv:.0f} mSv"),
                Evidence(label="This mission", value=f"{mission:.0f} mSv"),
            ],
            suggested_action="Prioritise storm-shelter use during solar particle events; review EVA planning.",
        )
    ]


def _exercise_insights(monitor: MonitoringService, row: AstronautRow, now: datetime) -> list[Insight]:
    profile = monitor.engine.profiles[row.id]
    days = [now.date() - timedelta(days=i) for i in (1, 2, 3)]
    minutes = [
        exercise_minutes_on(profile, d, now, monitor.engine.seed) for d in days
    ]
    short = [m for m in minutes if m < 0.6 * row.exercise_target_minutes]
    if len(short) < 2:
        return []
    return [
        _insight(
            row, "exercise-adherence", now,
            category="countermeasures",
            severity="advisory",
            title="Exercise countermeasures below plan",
            summary=f"{len(short)} of the last 3 days fell short of the {row.exercise_target_minutes}-minute exercise plan.",
            evidence=[
                Evidence(label=f"{d:%d %b}", value=f"{m:.0f} min") for d, m in zip(days, minutes)
            ],
            suggested_action="Protect exercise time to limit bone and muscle loss in microgravity.",
        )
    ]


def _scenario_insights(monitor: MonitoringService, row: AstronautRow, now: datetime) -> list[Insight]:
    return [
        _insight(
            row, f"scenario-{s.id}", now,
            category="alerts",
            severity="info",
            title="Test scenario in progress",
            summary=f"'{s.spec.label}' is being injected into this crew member's simulated data.",
            evidence=[
                Evidence(label="Triggered by", value=s.triggered_by),
                Evidence(label="Ends", value=f"{s.ends_at:%H:%M:%S} UTC"),
            ],
            suggested_action="Use this to verify that alerts and displays respond as expected.",
        )
        for s in monitor.active_scenarios(now, row.id)
        if s.astronaut_id
    ]


async def generate_insights(
    monitor: MonitoringService, session: AsyncSession, now: datetime, astronaut_id: str | None = None
) -> list[Insight]:
    rows = await astronauts_repo.list_astronauts(session)
    out: list[Insight] = []
    for row in rows:
        if astronaut_id and row.id != astronaut_id:
            continue
        out += await _sleep_insights(session, row, now)
        out += await _cardio_insights(session, row, now)
        out += await _alert_insights(session, row, now)
        out += await _radiation_insights(session, row, now)
        out += _exercise_insights(monitor, row, now)
        out += _scenario_insights(monitor, row, now)
    out.sort(key=lambda i: (SEVERITY_ORDER[i.severity], i.astronaut_id))
    return out
