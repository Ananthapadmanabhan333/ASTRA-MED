"""Database bootstrap: crew profiles plus deterministic backfilled history.

Backfill is incremental. A restart fills only the gap since the last stored sample, so history
stays continuous across restarts without duplicating rows.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.detection.evaluator import AlertRecord
from app.detection.rules import RHYTHM_RULE_KEY, RHYTHM_TITLE, THRESHOLD_RULES
from app.repositories import alerts as alerts_repo
from app.repositories import astronauts as astronauts_repo
from app.repositories import events as events_repo
from app.repositories import sleep_radiation as sr_repo
from app.repositories import vitals as vitals_repo
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import AstronautProfile
from app.simulator.radiation import daily_dose
from app.simulator.scenarios import ActiveScenario
from app.simulator.schedule import night_plan
from app.simulator.seeding import rng_for

logger = logging.getLogger("astra.seed")

SLEEP_HISTORY_NIGHTS = 14


def mission_day_for(settings: Settings, day: date) -> int:
    return max(0, (day - settings.mission_start_date).days)


def _align(t: datetime, interval: timedelta) -> datetime:
    step = interval.total_seconds()
    return datetime.fromtimestamp((t.timestamp() // step + 1) * step, tz=t.tzinfo)


def historical_alert(
    engine: SimulationEngine, profile: AstronautProfile, scenario: ActiveScenario
) -> AlertRecord | None:
    """Reconstruct the alert an operator would have handled for a past test scenario."""
    rng = rng_for(engine.seed, "history-alert", scenario.id)
    midpoint = scenario.started_at + (scenario.ends_at - scenario.started_at) / 2
    reading = engine.reading_at(profile, midpoint, [scenario], rng)
    opened = scenario.started_at + timedelta(seconds=float(rng.uniform(40, 120)))
    acknowledged = opened + timedelta(minutes=float(rng.uniform(1, 6)))
    resolved = scenario.ends_at + timedelta(minutes=float(rng.uniform(5, 25)))

    hit = None
    for rule in THRESHOLD_RULES:
        breach = rule.breach(reading.value(rule.metric), reading.activity_state)
        if breach and (hit is None or breach[0] == "critical"):
            hit = (rule, breach)
    common = dict(
        id=f"ha-{scenario.id}",
        astronaut_id=profile.id,
        status="resolved",
        opened_at=opened,
        updated_at=resolved,
        activity_state=reading.activity_state,
        scenario=scenario.scenario.value,
        condition_cleared_at=scenario.ends_at,
        acknowledged_at=acknowledged,
        resolved_at=resolved,
        operator_note="Reviewed during simulated flight-surgeon pass.",
    )
    if hit:
        rule, (severity, threshold) = hit
        value = reading.value(rule.metric)
        relation = "above" if rule.direction == "high" else "below"
        return AlertRecord(
            rule_key=rule.key,
            category="threshold",
            metric=rule.metric,
            direction=rule.direction,
            severity=severity,
            title=rule.title,
            message=f"{rule.title}: {value:g} {rule.unit}, {relation} the {severity} limit of {threshold:g} {rule.unit}.",
            unit=rule.unit,
            trigger_value=value,
            threshold_value=threshold,
            peak_value=value,
            **common,
        )
    if reading.rhythm == "irregular":
        return AlertRecord(
            rule_key=RHYTHM_RULE_KEY,
            category="rhythm",
            metric="hrv_rmssd_ms",
            direction="high",
            severity="caution",
            title=RHYTHM_TITLE,
            message="Beat-to-beat intervals in the synthetic ECG were irregular.",
            unit="ms",
            trigger_value=0.0,
            threshold_value=None,
            peak_value=0.0,
            **common,
        )
    return None


async def _backfill_vitals(
    session: AsyncSession, engine: SimulationEngine, settings: Settings, now: datetime
) -> None:
    interval = timedelta(minutes=settings.backfill_interval_minutes)
    window_start = now - timedelta(days=settings.backfill_days)
    scenarios = engine.historical_scenarios(window_start, now)

    total = 0
    for profile in engine.profiles.values():
        last = await vitals_repo.last_sample_ts(session, profile.id)
        start = max(window_start, last + interval) if last else window_start
        start = _align(start, interval)
        if start >= now:
            continue
        readings = list(engine.history(profile, start, now, interval, scenarios))
        total += await vitals_repo.insert_readings(session, readings)

    new_ids = {s.id for s in scenarios} - await events_repo.existing_ids(
        session, [s.id for s in scenarios]
    )
    fresh = [s for s in scenarios if s.id in new_ids]
    await events_repo.upsert(session, fresh)
    past_alerts = [
        a
        for s in fresh
        if s.astronaut_id and (a := historical_alert(engine, engine.profiles[s.astronaut_id], s))
    ]
    await alerts_repo.upsert(session, past_alerts)
    logger.info(
        "backfilled %d vital samples, %d past scenarios, %d past alerts",
        total, len(fresh), len(past_alerts),
    )


async def _backfill_sleep(session: AsyncSession, engine: SimulationEngine, now: datetime) -> None:
    for profile in engine.profiles.values():
        have = await sr_repo.existing_nights(session, profile.id)
        plans = []
        for back in range(SLEEP_HISTORY_NIGHTS, -1, -1):
            night = now.date() - timedelta(days=back)
            plan = night_plan(profile, night, engine.seed)
            if night not in have and plan.end <= now:
                plans.append(plan)
        await sr_repo.add_nights(session, profile.id, plans)


async def _backfill_radiation(
    session: AsyncSession, engine: SimulationEngine, settings: Settings, now: datetime
) -> None:
    today = now.date()
    first = max(settings.mission_start_date, today - timedelta(days=400))
    for profile in engine.profiles.values():
        have = await sr_repo.existing_dose_days(session, profile.id)
        day = first
        while day <= today:
            if day not in have:
                mday = mission_day_for(settings, day)
                dose, spe = daily_dose(profile, mday, engine.seed)
                if day == today:
                    elapsed = (now - datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo))
                    dose *= elapsed.total_seconds() / 86400
                    spe = False
                await sr_repo.add_dose(session, profile.id, day, mday, round(dose, 4), spe)
            day += timedelta(days=1)


async def seed_database(
    factory: async_sessionmaker[AsyncSession],
    engine: SimulationEngine,
    settings: Settings,
    now: datetime,
) -> None:
    async with factory() as session:
        await astronauts_repo.upsert_profiles(session, engine.profiles.values())
        await session.flush()
        await _backfill_vitals(session, engine, settings, now)
        await _backfill_sleep(session, engine, now)
        await _backfill_radiation(session, engine, settings, now)
        await vitals_repo.prune_before(
            session, now - timedelta(days=settings.history_retention_days)
        )
        await session.commit()
