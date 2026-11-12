"""Signal definitions shared by the AI modules."""

from __future__ import annotations

from datetime import datetime

SIGNALS: tuple[str, ...] = (
    "heart_rate",
    "spo2",
    "systolic",
    "diastolic",
    "temperature_c",
    "respiratory_rate",
)
FORECAST_SIGNALS: tuple[str, ...] = ("heart_rate", "spo2", "respiratory_rate", "temperature_c")
STATES: tuple[str, ...] = ("sleep", "rest", "work", "exercise")

LABELS: dict[str, str] = {
    "heart_rate": "Heart rate",
    "spo2": "SpO2",
    "systolic": "Systolic pressure",
    "diastolic": "Diastolic pressure",
    "temperature_c": "Body temperature",
    "respiratory_rate": "Respiratory rate",
}
UNITS: dict[str, str] = {
    "heart_rate": "bpm",
    "spo2": "%",
    "systolic": "mmHg",
    "diastolic": "mmHg",
    "temperature_c": "°C",
    "respiratory_rate": "breaths/min",
}

# Values outside these ranges are physiologically implausible for a conscious crew member and
# are treated as sensor artefacts (missing), never as measurements.
PLAUSIBLE: dict[str, tuple[float, float]] = {
    "heart_rate": (25.0, 230.0),
    "spo2": (50.0, 100.0),
    "systolic": (60.0, 250.0),
    "diastolic": (30.0, 150.0),
    "temperature_c": (33.0, 42.0),
    "respiratory_rate": (3.0, 60.0),
}

# Minimum spread used when a personal baseline is very tight, so tiny noise is not over-scored.
SCALE_FLOOR: dict[str, float] = {
    "heart_rate": 1.5,
    "spo2": 0.3,
    "systolic": 2.0,
    "diastolic": 1.5,
    "temperature_c": 0.05,
    "respiratory_rate": 0.5,
}

WINDOW_MINUTES = 5
TOD_BUCKET_HOURS = 4
N_TOD_BUCKETS = 24 // TOD_BUCKET_HOURS


def tod_bucket(ts: datetime) -> int:
    return ts.hour // TOD_BUCKET_HOURS
