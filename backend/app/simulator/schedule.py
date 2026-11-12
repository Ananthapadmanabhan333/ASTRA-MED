"""Daily timeline for each crew member: sleep, exercise countermeasures, work and rest.

Nightly sleep and daily exercise are drawn from deterministic per-day random streams, so
live simulation and backfilled history agree about what happened on any given day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache

from app.simulator.profiles import AstronautProfile
from app.simulator.seeding import rng_for

SLEEP = "sleep"
REST = "rest"
WORK = "work"
EXERCISE = "exercise"


@dataclass(frozen=True)
class NightPlan:
    night: date
    scheduled_start: datetime
    scheduled_end: datetime
    start: datetime
    end: datetime
    efficiency_pct: float

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class ExercisePlan:
    day: date
    start: datetime
    end: datetime

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time(0), tzinfo=UTC)


@lru_cache(maxsize=8192)  # pure and deterministic; results are immutable
def night_plan(profile: AstronautProfile, night: date, seed: int) -> NightPlan:
    rng = rng_for(seed, "sleep", profile.id, night.isoformat())
    scheduled_start = _day_start(night) + timedelta(hours=profile.sleep_start_hour)
    scheduled_end = scheduled_start + timedelta(hours=profile.sleep_target_hours)
    onset = max(-0.25, rng.normal(profile.sleep_onset_drift_hours, 0.35))
    duration = float(
        min(9.0, max(3.5, rng.normal(profile.sleep_target_hours - profile.sleep_shortfall_hours, 0.5)))
    )
    start = scheduled_start + timedelta(hours=onset)
    efficiency = float(min(98.0, max(70.0, rng.normal(91 - 4 * profile.sleep_shortfall_hours, 2.5))))
    return NightPlan(
        night=night,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        start=start,
        end=start + timedelta(hours=duration),
        efficiency_pct=round(efficiency, 1),
    )


@lru_cache(maxsize=8192)
def exercise_plan(profile: AstronautProfile, day: date, seed: int) -> ExercisePlan:
    rng = rng_for(seed, "exercise", profile.id, day.isoformat())
    minutes = profile.exercise_minutes * rng.uniform(0.85, 1.1)
    if rng.random() > profile.exercise_adherence:
        minutes *= rng.uniform(0.25, 0.45)  # shortened session
    start = _day_start(day) + timedelta(hours=profile.exercise_start_hour + rng.normal(0, 0.2))
    return ExercisePlan(day=day, start=start, end=start + timedelta(minutes=float(minutes)))


def sleep_window_at(profile: AstronautProfile, t: datetime, seed: int) -> NightPlan | None:
    for d in (t.date(), t.date() - timedelta(days=1)):
        plan = night_plan(profile, d, seed)
        if plan.start <= t < plan.end:
            return plan
    return None


def last_completed_night(profile: AstronautProfile, t: datetime, seed: int) -> NightPlan:
    d = t.date()
    for _ in range(3):
        plan = night_plan(profile, d, seed)
        if plan.end <= t:
            return plan
        d -= timedelta(days=1)
    return night_plan(profile, d, seed)


def activity_at(profile: AstronautProfile, t: datetime, seed: int) -> tuple[str, float]:
    """Return (activity_state, metabolic equivalent) for an instant."""
    if sleep_window_at(profile, t, seed):
        return SLEEP, 0.9

    ex = exercise_plan(profile, t.date(), seed)
    if ex.start <= t < ex.end:
        minutes_in = (t - ex.start).total_seconds() / 60
        minutes_left = (ex.end - t).total_seconds() / 60
        ramp = min(1.0, minutes_in / 8, minutes_left / 8)
        # Interval training: 8-minute cycles on top of a sustained load.
        load = 6.6 + 1.3 * math.sin(2 * math.pi * minutes_in / 8)
        return EXERCISE, 1.6 + (load - 1.6) * max(0.0, ramp)

    tonight = night_plan(profile, t.date(), seed)
    if tonight.scheduled_start - timedelta(hours=1) <= t < tonight.start:
        return REST, 1.2
    previous = night_plan(profile, t.date() - timedelta(days=1), seed)
    if previous.end <= t < previous.end + timedelta(minutes=40):
        return REST, 1.3

    hours = t.timestamp() / 3600
    wobble = 0.35 * math.sin(2 * math.pi * hours / 1.7) + 0.2 * math.sin(2 * math.pi * hours / 0.45)
    return WORK, 1.7 + wobble


def exercise_minutes_on(profile: AstronautProfile, day: date, until: datetime, seed: int) -> float:
    ex = exercise_plan(profile, day, seed)
    if until <= ex.start:
        return 0.0
    return (min(until, ex.end) - ex.start).total_seconds() / 60
