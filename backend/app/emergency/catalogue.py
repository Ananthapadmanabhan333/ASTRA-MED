"""Emergency-simulator catalogue: each entry maps to one or more simulator scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.simulator.scenarios import Scenario

SEVERITY_INTENSITY: dict[str, float] = {"mild": 0.6, "moderate": 1.0, "severe": 1.4}
MIN_DURATION_S, MAX_DURATION_S = 30, 3600


@dataclass(frozen=True)
class EmergencyScenario:
    key: str
    label: str
    description: str
    components: tuple[tuple[Scenario, float], ...]  # (scenario, intensity factor)
    crew_wide: bool = False
    default_duration_s: int = 300
    overlay: str | None = None  # "sleep" | "habitat"
    observe: tuple[str, ...] = field(default_factory=tuple)  # signals worth watching


CATALOGUE: dict[str, EmergencyScenario] = {e.key: e for e in (
    EmergencyScenario(
        "hr_elevation", "Heart-rate elevation",
        "Heart rate rises well above the resting range while activity stays low.",
        ((Scenario.TACHYCARDIA, 1.0),), observe=("heart_rate", "systolic", "respiratory_rate"),
    ),
    EmergencyScenario(
        "desaturation", "Oxygen desaturation",
        "SpO2 falls with a compensatory rise in heart and breathing rate.",
        ((Scenario.DESATURATION, 1.0),), observe=("spo2", "heart_rate", "respiratory_rate"),
    ),
    EmergencyScenario(
        "abnormal_respiration", "Abnormal respiration",
        "Breathing rate rises far above the resting range.",
        ((Scenario.ABNORMAL_RESPIRATORY_RATE, 1.0),), observe=("respiratory_rate", "heart_rate", "spo2"),
    ),
    EmergencyScenario(
        "sleep_disruption", "Prolonged sleep disruption",
        "Raised heart and breathing rate as after repeated waking, and a what-if overlay that shortens "
        "the crew member's recent simulated nights (stored sleep records are not changed).",
        ((Scenario.SLEEP_DISRUPTION, 1.0),), default_duration_s=600, overlay="sleep",
        observe=("heart_rate", "respiratory_rate", "temperature_c"),
    ),
    EmergencyScenario(
        "multiple_deviations", "Multiple simultaneous deviations",
        "Heart rate, oxygen saturation and temperature deviate at the same time.",
        ((Scenario.TACHYCARDIA, 0.6), (Scenario.DESATURATION, 0.7), (Scenario.ELEVATED_TEMPERATURE, 0.8)),
        observe=("heart_rate", "spo2", "temperature_c", "respiratory_rate"),
    ),
    EmergencyScenario(
        "radiation_event", "Simulated radiation event",
        "A simulated solar particle event raises the habitat dose rate for the whole crew. It is not "
        "derived from any real NASA observation.",
        ((Scenario.SOLAR_PARTICLE_EVENT, 1.0),), crew_wide=True, default_duration_s=600,
        observe=("dose_rate",),
    ),
    EmergencyScenario(
        "environmental_anomaly", "Environmental system anomaly",
        "Simulated cabin CO2 and temperature rise for the whole crew, with a modest rise in breathing and "
        "heart rate in the synthetic vitals.",
        ((Scenario.HABITAT_ATMOSPHERE, 1.0),), crew_wide=True, default_duration_s=600, overlay="habitat",
        observe=("respiratory_rate", "heart_rate", "ppco2_mmhg", "cabin_temperature_c"),
    ),
)}
