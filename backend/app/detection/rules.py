"""Activity-aware threshold rules.

Limits are deliberately simple, round numbers chosen to exercise the alerting pipeline. They
are *not* clinical criteria and have not been reviewed by a flight surgeon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["advisory", "caution", "critical"]
SEVERITY_RANK: dict[str, int] = {"advisory": 0, "caution": 1, "critical": 2}


@dataclass(frozen=True)
class ThresholdRule:
    key: str
    metric: str
    direction: Literal["high", "low"]
    caution: float
    critical: float
    title: str
    unit: str
    # Activity-specific (caution, critical) limits, e.g. higher heart-rate limits during exercise.
    overrides: dict[str, tuple[float, float]] = field(default_factory=dict)

    def limits(self, activity_state: str) -> tuple[float, float]:
        return self.overrides.get(activity_state, (self.caution, self.critical))

    def breach(self, value: float, activity_state: str) -> tuple[Severity, float] | None:
        """Return (severity, threshold crossed) or None if within limits."""
        caution, critical = self.limits(activity_state)
        if self.direction == "high":
            if value >= critical:
                return "critical", critical
            if value >= caution:
                return "caution", caution
        else:
            if value <= critical:
                return "critical", critical
            if value <= caution:
                return "caution", caution
        return None

    def is_worse(self, a: float, b: float) -> bool:
        return a > b if self.direction == "high" else a < b


THRESHOLD_RULES: tuple[ThresholdRule, ...] = (
    ThresholdRule(
        "heart_rate:high", "heart_rate", "high", 120, 140, "Elevated heart rate", "bpm",
        {"exercise": (172, 188)},
    ),
    ThresholdRule(
        "heart_rate:low", "heart_rate", "low", 45, 40, "Low heart rate", "bpm",
        {"sleep": (40, 36)},
    ),
    ThresholdRule("spo2:low", "spo2", "low", 94, 90, "Oxygen desaturation", "%"),
    ThresholdRule(
        "temperature_c:high", "temperature_c", "high", 37.8, 38.4, "Elevated body temperature", "°C"
    ),
    ThresholdRule(
        "respiratory_rate:high", "respiratory_rate", "high", 24, 30,
        "Elevated respiratory rate", "breaths/min", {"exercise": (34, 40)},
    ),
    ThresholdRule(
        "respiratory_rate:low", "respiratory_rate", "low", 9, 7, "Low respiratory rate", "breaths/min"
    ),
    ThresholdRule(
        "systolic:high", "systolic", "high", 150, 170, "Elevated systolic pressure", "mmHg",
        {"exercise": (195, 215)},
    ),
)

RHYTHM_RULE_KEY = "rhythm:irregular"
RHYTHM_TITLE = "Irregular rhythm pattern"

METRIC_UNITS: dict[str, str] = {
    "heart_rate": "bpm",
    "spo2": "%",
    "systolic": "mmHg",
    "diastolic": "mmHg",
    "temperature_c": "°C",
    "respiratory_rate": "breaths/min",
    "hrv_rmssd_ms": "ms",
}

METRIC_LABELS: dict[str, str] = {
    "heart_rate": "Heart rate",
    "spo2": "SpO2",
    "systolic": "Systolic pressure",
    "diastolic": "Diastolic pressure",
    "temperature_c": "Body temperature",
    "respiratory_rate": "Respiratory rate",
    "hrv_rmssd_ms": "Beat-to-beat variability",
}
