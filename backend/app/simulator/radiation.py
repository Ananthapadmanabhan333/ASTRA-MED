"""Simulated radiation dose for a crew in interplanetary cruise.

Reference magnitudes (used to make the simulation realistic, not as live measurements):
- Galactic cosmic ray dose-equivalent rate during Mars cruise, inside a spacecraft:
  ~1.84 mSv/day, measured by MSL's Radiation Assessment Detector (Zeitlin et al., Science 2013).
- NASA career effective-dose limit for astronauts: 600 mSv (NASA-STD-3001 Vol. 1, Rev. B, 2022).
"""

from __future__ import annotations

from app.simulator.profiles import AstronautProfile
from app.simulator.seeding import rng_for

GCR_DOSE_RATE_MSV_PER_DAY = 1.84
CAREER_LIMIT_MSV = 600.0

# Historical solar particle events during the simulated mission: (mission day, mSv in shelter).
HISTORICAL_SPES: dict[int, float] = {37: 6.8, 118: 9.4}


def daily_dose(profile: AstronautProfile, mission_day: int, seed: int) -> tuple[float, bool]:
    rng = rng_for(seed, "dose", profile.id, mission_day)
    dose = GCR_DOSE_RATE_MSV_PER_DAY * profile.shielding_factor * float(rng.normal(1.0, 0.035))
    spe = mission_day in HISTORICAL_SPES
    if spe:
        dose += HISTORICAL_SPES[mission_day] * profile.shielding_factor * float(rng.uniform(0.9, 1.1))
    return round(dose, 4), spe


def dose_rate_msv_per_second(profile: AstronautProfile, multiplier: float = 1.0) -> float:
    return GCR_DOSE_RATE_MSV_PER_DAY * profile.shielding_factor * multiplier / 86400.0
