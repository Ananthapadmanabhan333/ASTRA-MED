"""Mission simulation scenario presets and the injection catalogue.

A preset is a scripted mission: a crew selection, a speed, a length in simulated minutes and a list
of injections at simulated-time offsets. Every injection is a software test event in the sandbox:

* ``health``: a phase 2 physiological scenario for one crew member (tachycardia-like, desaturation...)
* ``environment``: the simulated habitat-atmosphere anomaly (whole crew)
* ``space_weather``: a *simulated* solar particle event (raises the sandbox dose rate), or a
  simulated flare / geomagnetic storm marker with no physiological effect.

Nothing here is real space-weather data; real NASA events are only ever read from the DONKI store.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.simulator.scenarios import SCENARIOS, Scenario

HEALTH_SCENARIOS = (
    Scenario.TACHYCARDIA, Scenario.BRADYCARDIA, Scenario.DESATURATION, Scenario.ELEVATED_TEMPERATURE,
    Scenario.ABNORMAL_RESPIRATORY_RATE, Scenario.IRREGULAR_RHYTHM, Scenario.SLEEP_DISRUPTION,
)


@dataclass(frozen=True)
class InjectionType:
    key: str
    kind: str  # health | environment | space_weather
    label: str
    description: str
    crew_wide: bool
    scenario: str | None  # simulator scenario it drives; None for event-only markers
    default_duration_s: int
    severity: str  # severity of the sandbox event it publishes


def _health(s: Scenario) -> InjectionType:
    spec = SCENARIOS[s]
    return InjectionType(s.value, "health", spec.label, spec.description, False, s.value, spec.default_duration_s, "info")


INJECTIONS: dict[str, InjectionType] = {
    **{s.value: _health(s) for s in HEALTH_SCENARIOS},
    "habitat_atmosphere": InjectionType(
        "habitat_atmosphere", "environment", "Habitat atmosphere anomaly",
        SCENARIOS[Scenario.HABITAT_ATMOSPHERE].description, True, Scenario.HABITAT_ATMOSPHERE.value, 900, "advisory"),
    "solar_particle_event": InjectionType(
        "solar_particle_event", "space_weather", "Simulated solar particle event",
        "Sandbox habitat dose rate rises up to 40x for the whole crew; vitals are unaffected.", True,
        Scenario.SOLAR_PARTICLE_EVENT.value, 1200, "caution"),
    "solar_flare": InjectionType(
        "solar_flare", "space_weather", "Simulated X-class solar flare (marker)",
        "Event marker only: a simulated flare with no direct physiological or dose effect in the sandbox.", True,
        None, 0, "advisory"),
    "geomagnetic_storm": InjectionType(
        "geomagnetic_storm", "space_weather", "Simulated geomagnetic storm (marker)",
        "Event marker only: a simulated G3 storm. In deep space it has no direct crew effect.", True,
        None, 0, "info"),
}


@dataclass(frozen=True)
class ScriptStep:
    at_minute: float  # simulated minutes after mission start
    injection: str
    astronaut: int | None = None  # index into the run's crew list; None for crew-wide
    intensity: float = 1.0
    duration_s: int | None = None


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    description: str
    duration_minutes: int
    speed: float
    crew_size: int
    script: tuple[ScriptStep, ...] = field(default_factory=tuple)

    def view(self) -> dict[str, Any]:
        d = asdict(self)
        d["script"] = [
            {**asdict(s), "label": INJECTIONS[s.injection].label, "kind": INJECTIONS[s.injection].kind}
            for s in self.script
        ]
        return d


PRESETS: dict[str, Preset] = {p.key: p for p in (
    Preset(
        "nominal_transit", "Nominal transit day",
        "Four crew members through an ordinary stretch of the transit: no injected events. Use it to see normal "
        "variation, the live baselines and how quiet a nominal mission looks.",
        duration_minutes=180, speed=30, crew_size=4),
    Preset(
        "desaturation_emergency", "Medical emergency: oxygen desaturation",
        "A severe desaturation for one crew member early in the run, followed by a compensatory rise in breathing "
        "rate. Exercises rule alerts, AI anomaly detection and the incident report path.",
        duration_minutes=90, speed=20, crew_size=2,
        script=(ScriptStep(6, "desaturation", 0, 1.3, 1500),)),
    Preset(
        "solar_particle_event", "Solar particle event response",
        "A simulated solar particle event raises the sandbox dose rate for the whole crew; later one crew member "
        "shows a stress-like heart-rate rise. Compare with the real NASA events shown alongside.",
        duration_minutes=120, speed=30, crew_size=4,
        script=(ScriptStep(3, "solar_flare"), ScriptStep(8, "solar_particle_event", None, 1.0, 2400),
                ScriptStep(25, "tachycardia", 2, 1.0, 900), ScriptStep(70, "geomagnetic_storm"))),
    Preset(
        "cabin_atmosphere_fault", "Cabin atmosphere fault",
        "A simulated CO2 build-up in the habitat raises breathing and heart rate for everyone, then one crew member "
        "desaturates while the atmosphere is still off nominal.",
        duration_minutes=120, speed=30, crew_size=3,
        script=(ScriptStep(5, "habitat_atmosphere", None, 1.2, 2400), ScriptStep(20, "desaturation", 1, 1.0, 1200))),
    Preset(
        "multi_casualty_cascade", "Multi-system cascade",
        "Overlapping events across the crew: an elevated temperature, an irregular rhythm, an abnormal breathing rate "
        "and a sleep disruption, so prioritisation and de-duplication have work to do.",
        duration_minutes=150, speed=40, crew_size=4,
        script=(ScriptStep(4, "elevated_temperature", 0, 1.2, 3000), ScriptStep(15, "irregular_rhythm", 3, 1.1, 1200),
                ScriptStep(30, "abnormal_respiratory_rate", 1, 1.2, 1200), ScriptStep(50, "sleep_disruption", 2, 1.0, 1800))),
)}
