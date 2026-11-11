"""Equilibrium physiology: what each vital sign tends toward at a given moment.

The model combines a personal baseline, a circadian rhythm anchored to each person's sleep
schedule, and the metabolic load of their current activity. Live simulation then adds
first-order lag, correlated noise and injected scenarios on top (see ``engine.py``).
Coefficients are plausible textbook magnitudes chosen for demonstration, not fitted values.
"""

from __future__ import annotations

import math
from datetime import datetime

from app.core.timeutil import hours_of_day
from app.simulator.profiles import AstronautProfile
from app.simulator.schedule import SLEEP

METRICS = (
    "heart_rate",
    "spo2",
    "systolic",
    "diastolic",
    "temperature_c",
    "respiratory_rate",
)

# Seconds for each signal to close ~63% of the gap to a new target.
LAG_SECONDS = {
    "heart_rate": 20.0,
    "spo2": 15.0,
    "systolic": 40.0,
    "diastolic": 40.0,
    "temperature_c": 900.0,
    "respiratory_rate": 20.0,
}

# Standard deviation of the slow, correlated noise on each signal.
NOISE_SIGMA = {
    "heart_rate": 1.6,
    "spo2": 0.35,
    "systolic": 2.6,
    "diastolic": 1.8,
    "temperature_c": 0.04,
    "respiratory_rate": 0.6,
}

LIMITS = {
    "heart_rate": (28.0, 210.0),
    "spo2": (70.0, 100.0),
    "systolic": (70.0, 220.0),
    "diastolic": (40.0, 130.0),
    "temperature_c": (34.5, 41.0),
    "respiratory_rate": (5.0, 45.0),
}


def circadian_phase(profile: AstronautProfile, t: datetime) -> float:
    """Cosine term that peaks ~10 h after scheduled wake and bottoms out ~2 h before it."""
    wake = (profile.sleep_start_hour + profile.sleep_target_hours) % 24
    peak = (wake + 10) % 24
    return math.cos(2 * math.pi * (hours_of_day(t) - peak) / 24)


def target_vitals(
    profile: AstronautProfile, t: datetime, activity_state: str, met: float
) -> dict[str, float]:
    b = profile.baseline
    c = circadian_phase(profile, t)
    load = met - 1.5
    asleep = activity_state == SLEEP
    return {
        "heart_rate": b.heart_rate + 3.0 * c + 9.5 * load - (4.0 if asleep else 0.0),
        "spo2": b.spo2 - 0.15 * max(0.0, met - 3.0) - (0.8 if asleep else 0.0),
        "systolic": b.systolic + 2.5 * c + 4.5 * load - (8.0 if asleep else 0.0),
        "diastolic": b.diastolic + 1.5 * c + 0.8 * load - (6.0 if asleep else 0.0),
        "temperature_c": b.temperature_c + 0.35 * c + 0.08 * max(0.0, met - 2.0),
        "respiratory_rate": b.respiratory_rate + 1.8 * load - (1.5 if asleep else 0.0),
    }


def clamp_metric(metric: str, value: float) -> float:
    lo, hi = LIMITS[metric]
    return min(hi, max(lo, value))
