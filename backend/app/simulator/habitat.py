"""Simulated habitat atmosphere (phase 5), used only by the environmental-anomaly test scenario.

ASTRA-MED has no real life-support telemetry. These values are produced by the simulator: a
configured nominal level with small deterministic variation, plus the deltas of any running
``habitat_atmosphere`` scenario. Deviation is expressed in units of the simulator's own nominal
variation; it is not a safety limit or an exposure guideline.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.simulator.scenarios import ActiveScenario


@dataclass(frozen=True)
class HabitatParameter:
    key: str
    label: str
    unit: str
    nominal: float  # simulator setting
    variation: float  # simulated 1-sigma variation around nominal
    decimals: int


PARAMETERS: tuple[HabitatParameter, ...] = (
    HabitatParameter("ppco2_mmhg", "Cabin CO₂ partial pressure", "mmHg", 2.5, 0.2, 2),
    HabitatParameter("cabin_temperature_c", "Cabin temperature", "°C", 22.5, 0.3, 1),
    HabitatParameter("relative_humidity_pct", "Relative humidity", "%", 45.0, 2.0, 1),
)
BY_KEY = {p.key: p for p in PARAMETERS}


def _wobble(key: str, t: datetime) -> float:
    """Deterministic, smooth variation in [-1, 1] (no RNG state, reproducible for any instant)."""
    s = t.timestamp()
    phase = sum(map(ord, key)) % 17
    return 0.6 * math.sin(2 * math.pi * s / 86400 + phase) + 0.4 * math.sin(2 * math.pi * s / 5400 + 2 * phase)


def habitat_at(t: datetime, scenarios: Sequence[ActiveScenario]) -> dict[str, dict]:
    deltas: dict[str, float] = {}
    anomaly: str | None = None
    for s in scenarios:
        effects = s.spec.habitat_effects
        if not effects:
            continue
        level = s.envelope(t)
        if level <= 0:
            continue
        anomaly = anomaly or s.id
        for k, v in effects.items():
            deltas[k] = deltas.get(k, 0.0) + v * s.intensity * level
    out = {}
    for p in PARAMETERS:
        value = p.nominal + p.variation * _wobble(p.key, t) + deltas.get(p.key, 0.0)
        out[p.key] = {
            "label": p.label, "unit": p.unit, "value": round(value, p.decimals),
            "nominal": p.nominal, "variation": p.variation,
            "deviation_sigma": round((value - p.nominal) / p.variation, 2),
            "category": "simulated",
        }
    return {"parameters": out, "anomaly_scenario_id": anomaly, "ts": t, "category": "simulated",
            "note": "Simulated cabin atmosphere: nominal values are simulator settings, not limits."}
