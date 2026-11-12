"""Event simulation catalogue.

Each scenario is a *software test scenario*: a pattern injected into synthetic data so the
monitoring, alerting and UI paths can be exercised. None of them is a clinical diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Seconds over which an operator-cancelled scenario fades out.
CANCEL_RELEASE_S = 8.0


class Scenario(str, Enum):
    TACHYCARDIA = "tachycardia"
    BRADYCARDIA = "bradycardia"
    DESATURATION = "desaturation"
    ELEVATED_TEMPERATURE = "elevated_temperature"
    ABNORMAL_RESPIRATORY_RATE = "abnormal_respiratory_rate"
    IRREGULAR_RHYTHM = "irregular_rhythm"
    SOLAR_PARTICLE_EVENT = "solar_particle_event"
    # Phase 5 emergency-simulator scenarios (operator-triggered only; never picked at random).
    SLEEP_DISRUPTION = "sleep_disruption"
    HABITAT_ATMOSPHERE = "habitat_atmosphere"


@dataclass(frozen=True)
class ScenarioSpec:
    key: Scenario
    label: str
    description: str
    default_duration_s: int
    # Metric deltas at intensity 1.0, applied on top of normal physiology.
    effects: dict[str, float] = field(default_factory=dict)
    irregular_rhythm: bool = False
    crew_wide: bool = False
    dose_rate_multiplier: float = 1.0
    # Deltas applied to the simulated habitat atmosphere (app/simulator/habitat.py) at intensity 1.0.
    habitat_effects: dict[str, float] = field(default_factory=dict)


SCENARIOS: dict[Scenario, ScenarioSpec] = {
    Scenario.TACHYCARDIA: ScenarioSpec(
        Scenario.TACHYCARDIA,
        "Tachycardia-like elevated heart rate",
        "Heart rate rises well above the resting range while activity stays low.",
        240,
        {"heart_rate": 64, "respiratory_rate": 3, "systolic": 10, "diastolic": 4},
    ),
    Scenario.BRADYCARDIA: ScenarioSpec(
        Scenario.BRADYCARDIA,
        "Bradycardia-like low heart rate",
        "Heart rate falls below the expected range for the current activity.",
        240,
        {"heart_rate": -24, "systolic": -8, "diastolic": -4},
    ),
    Scenario.DESATURATION: ScenarioSpec(
        Scenario.DESATURATION,
        "Oxygen desaturation",
        "SpO2 drops below 92% with a compensatory rise in heart and breathing rate.",
        240,
        {"spo2": -10.0, "heart_rate": 12, "respiratory_rate": 6},
    ),
    Scenario.ELEVATED_TEMPERATURE: ScenarioSpec(
        Scenario.ELEVATED_TEMPERATURE,
        "Elevated body temperature",
        "Core temperature climbs toward 38.5 °C with a mild heart-rate increase.",
        480,
        {"temperature_c": 1.85, "heart_rate": 14, "respiratory_rate": 3},
    ),
    Scenario.ABNORMAL_RESPIRATORY_RATE: ScenarioSpec(
        Scenario.ABNORMAL_RESPIRATORY_RATE,
        "Abnormal respiratory rate",
        "Breathing rate rises far above the resting range.",
        240,
        {"respiratory_rate": 17, "heart_rate": 8},
    ),
    Scenario.IRREGULAR_RHYTHM: ScenarioSpec(
        Scenario.IRREGULAR_RHYTHM,
        "Irregular heart rhythm",
        "Beat-to-beat intervals become irregular in the synthetic ECG.",
        300,
        {"heart_rate": 20},
        irregular_rhythm=True,
    ),
    Scenario.SOLAR_PARTICLE_EVENT: ScenarioSpec(
        Scenario.SOLAR_PARTICLE_EVENT,
        "Solar particle event",
        "Habitat dose rate rises sharply for the whole crew; vitals are unaffected.",
        600,
        crew_wide=True,
        dose_rate_multiplier=40.0,
    ),
    Scenario.SLEEP_DISRUPTION: ScenarioSpec(
        Scenario.SLEEP_DISRUPTION,
        "Sleep disruption",
        "Heart and breathing rate stay raised as after repeated waking; the emergency simulator also "
        "shortens this crew member's simulated recent nights in an overlay (stored sleep is unchanged).",
        600,
        {"heart_rate": 9, "respiratory_rate": 2, "temperature_c": 0.15},
    ),
    Scenario.HABITAT_ATMOSPHERE: ScenarioSpec(
        Scenario.HABITAT_ATMOSPHERE,
        "Habitat atmosphere anomaly",
        "Simulated cabin CO2 partial pressure and temperature rise for the whole crew, with a modest "
        "rise in breathing and heart rate in the synthetic vitals.",
        600,
        {"respiratory_rate": 4, "heart_rate": 5},
        crew_wide=True,
        habitat_effects={"ppco2_mmhg": 3.0, "cabin_temperature_c": 2.0, "relative_humidity_pct": 8.0},
    ),
}


@dataclass
class ActiveScenario:
    id: str
    scenario: Scenario
    astronaut_id: str | None  # None for crew-wide scenarios
    intensity: float
    started_at: datetime
    ends_at: datetime
    triggered_by: str  # "operator" | "random"
    cancelled_at: datetime | None = None

    @property
    def spec(self) -> ScenarioSpec:
        return SCENARIOS[self.scenario]

    def affects(self, astronaut_id: str) -> bool:
        return self.astronaut_id is None or self.astronaut_id == astronaut_id

    @property
    def effective_end(self) -> datetime:
        if self.cancelled_at is not None:
            return min(self.ends_at, self.cancelled_at + timedelta(seconds=CANCEL_RELEASE_S))
        return self.ends_at

    def is_active(self, t: datetime) -> bool:
        return self.started_at <= t < self.effective_end

    def envelope(self, t: datetime) -> float:
        """Smooth 0→1→0 profile so injected events ramp in and out like physiology does."""
        if not self.is_active(t):
            return 0.0
        total = (self.ends_at - self.started_at).total_seconds()
        ramp = min(120.0, max(10.0, 0.15 * total))
        elapsed = (t - self.started_at).total_seconds()
        remaining = (self.ends_at - t).total_seconds()
        x = max(0.0, min(1.0, elapsed / ramp, remaining / ramp))
        level = x * x * (3 - 2 * x)  # smoothstep
        if self.cancelled_at is not None and t >= self.cancelled_at:
            level *= max(0.0, 1 - (t - self.cancelled_at).total_seconds() / CANCEL_RELEASE_S)
        return level
