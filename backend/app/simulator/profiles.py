"""Fictional crew profiles. Names and attributes are invented for the prototype."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Baseline:
    """Resting, awake values at the circadian midpoint."""

    heart_rate: float
    spo2: float
    systolic: float
    diastolic: float
    temperature_c: float
    respiratory_rate: float
    hrv_sdnn_ms: float


@dataclass(frozen=True)
class AstronautProfile:
    id: str
    name: str
    role: str
    specialty: str
    age: int
    sex: str
    height_cm: int
    mass_kg: float
    blood_type: str
    prior_career_dose_msv: float
    # Relative dose received inside the habitat (sleep-station shielding differs).
    shielding_factor: float
    # Scheduled sleep start, hours UTC (mission time), and target duration.
    sleep_start_hour: float
    sleep_target_hours: float
    # Personal tendencies used by the nightly sleep model.
    sleep_shortfall_hours: float
    sleep_onset_drift_hours: float
    exercise_start_hour: float
    exercise_minutes: int
    exercise_adherence: float
    baseline: Baseline


CREW: tuple[AstronautProfile, ...] = (
    AstronautProfile(
        id="AST-01",
        name="Maya Okafor",
        role="Commander",
        specialty="Test pilot, systems engineering",
        age=46,
        sex="F",
        height_cm=168,
        mass_kg=63.5,
        blood_type="O+",
        prior_career_dose_msv=96.0,
        shielding_factor=0.97,
        sleep_start_hour=22.0,
        sleep_target_hours=7.0,
        sleep_shortfall_hours=0.3,
        sleep_onset_drift_hours=0.2,
        exercise_start_hour=9.0,
        exercise_minutes=90,
        exercise_adherence=0.95,
        baseline=Baseline(62, 98.0, 116, 74, 36.70, 14.0, 52),
    ),
    AstronautProfile(
        id="AST-02",
        name="Lukas Brandt",
        role="Flight engineer",
        specialty="Life-support and propulsion systems",
        age=39,
        sex="M",
        height_cm=183,
        mass_kg=81.0,
        blood_type="A+",
        prior_career_dose_msv=48.0,
        shielding_factor=1.04,
        sleep_start_hour=23.0,
        sleep_target_hours=7.0,
        sleep_shortfall_hours=0.4,
        sleep_onset_drift_hours=0.3,
        exercise_start_hour=14.0,
        exercise_minutes=90,
        exercise_adherence=0.9,
        baseline=Baseline(58, 98.2, 122, 78, 36.60, 13.0, 61),
    ),
    AstronautProfile(
        id="AST-03",
        name="Priya Raman",
        role="Medical officer",
        specialty="Emergency medicine, space physiology",
        age=41,
        sex="F",
        height_cm=162,
        mass_kg=57.0,
        blood_type="B+",
        prior_career_dose_msv=0.0,
        shielding_factor=0.95,
        sleep_start_hour=21.5,
        sleep_target_hours=7.5,
        sleep_shortfall_hours=0.2,
        sleep_onset_drift_hours=0.15,
        exercise_start_hour=7.5,
        exercise_minutes=90,
        exercise_adherence=0.97,
        baseline=Baseline(66, 97.6, 112, 72, 36.80, 15.0, 45),
    ),
    AstronautProfile(
        id="AST-04",
        name="Tomás Ibarra",
        role="Mission specialist",
        specialty="Planetary geology",
        age=35,
        sex="M",
        height_cm=176,
        mass_kg=74.0,
        blood_type="O-",
        prior_career_dose_msv=0.0,
        shielding_factor=1.02,
        sleep_start_hour=22.5,
        sleep_target_hours=7.0,
        sleep_shortfall_hours=1.2,
        sleep_onset_drift_hours=0.9,
        exercise_start_hour=16.0,
        exercise_minutes=90,
        exercise_adherence=0.7,
        baseline=Baseline(64, 98.0, 118, 76, 36.70, 14.0, 48),
    ),
)

CREW_BY_ID: dict[str, AstronautProfile] = {p.id: p for p in CREW}
