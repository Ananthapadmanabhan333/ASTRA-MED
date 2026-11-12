"""Data categories used across the twin, decision support and reports.

Every value shown to a user carries one of these, so simulated, derived, model and real NASA data
are never confused. ASTRA-MED has no real astronaut measurements: crew data is always simulated.
"""

from __future__ import annotations

CATEGORIES: dict[str, str] = {
    "simulated": "Simulated measurement from the ASTRA-MED crew simulator. Not real astronaut data.",
    "regenerated": "Simulated values recomputed by the deterministic simulator for days whose stored "
                   "samples were pruned (retention window). Same simulator, same seed; not stored data.",
    "derived": "Statistic computed from simulated measurements (mean, percentile, trend, z-score).",
    "estimate": "Estimate from a configured constant or published reference value, not a measurement.",
    "model": "Output of an experimental AI model trained on simulated data. Not clinically validated.",
    "configured": "Simulator configuration (e.g. a crew member's configured resting values).",
    "measured": "Real NASA measurement (ISS environment from OSDR EDA). Never a crew dose.",
    "indicator": "Real NASA space-weather indicator (DONKI). Context only, not a dose.",
}


def legend(*keys: str) -> list[dict[str, str]]:
    return [{"key": k, "description": CATEGORIES[k]} for k in (keys or CATEGORIES)]
