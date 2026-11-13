"""Shared vocabulary of the unified mission event and alert pipeline.

Priority is computed, never typed in by a producer, so that every module is ranked on one scale:

    score = severity base + crew-specific bonus + escalation bonus, then capped by classification

    P1 critical  score >= 80   (rule-based detections of critical values only)
    P2 high      score >= 60
    P3 medium    score >= 35
    P4 low       otherwise

Experimental AI output is capped at P3 and can never be "critical": a model prediction is a prompt
for review, not a confirmed medical emergency. NASA environmental indicators are capped at P2: they
describe the space environment, not a dose received by anyone.
"""

from __future__ import annotations

from typing import Literal

Source = Literal[
    "physiological_monitoring",  # phase 2 threshold / rhythm / baseline rules
    "anomaly_detection",  # phase 3 anomaly ensemble (experimental)
    "predictive_forecast",  # phase 3 forecasts and risk assessment (experimental)
    "space_weather",  # phase 4 NASA DONKI (real data)
    "environment_monitoring",  # simulated habitat atmosphere and dose rate
    "emergency_simulation",  # phase 5 emergency simulator runs
    "mission_simulation",  # phase 6 sandbox runs
    "incident_reports",  # phase 5 incident reports
    "system",  # platform health
]
SOURCES: tuple[str, ...] = Source.__args__  # type: ignore[attr-defined]

SOURCE_LABELS: dict[str, str] = {
    "physiological_monitoring": "Physiological monitoring",
    "anomaly_detection": "AI anomaly detection",
    "predictive_forecast": "AI predictive forecasting",
    "space_weather": "NASA space weather",
    "environment_monitoring": "Environmental monitoring",
    "emergency_simulation": "Emergency simulator",
    "mission_simulation": "Mission simulation",
    "incident_reports": "Incident reports",
    "system": "System",
}

Category = Literal[
    "crew_physiology", "ai_prediction", "environment", "radiation", "solar_activity",
    "medical_incident", "simulation", "system",
]
CATEGORIES: tuple[str, ...] = Category.__args__  # type: ignore[attr-defined]

CATEGORY_LABELS: dict[str, str] = {
    "crew_physiology": "Crew physiology",
    "ai_prediction": "AI predictions",
    "environment": "Environment",
    "radiation": "Radiation",
    "solar_activity": "Solar activity",
    "medical_incident": "Medical incidents",
    "simulation": "Simulation control",
    "system": "System",
}

EventSeverity = Literal["info", "advisory", "caution", "critical"]
SEVERITIES: tuple[str, ...] = ("info", "advisory", "caution", "critical")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

# Where a record's data come from. Crew data are always simulated in ASTRA-MED; "sandbox" marks the
# mission simulation sandbox; "nasa" is real NASA open data.
DataOrigin = Literal["simulated", "sandbox", "nasa", "system"]
ORIGIN_LABELS: dict[str, str] = {
    "simulated": "Simulated crew stream",
    "sandbox": "Mission simulation sandbox",
    "nasa": "Real NASA open data",
    "system": "Platform",
}

Context = Literal["operations", "simulation"]

Classification = Literal[
    "rule_detection",  # deterministic rule on simulated measurements
    "experimental_ai",  # model output: never a confirmed emergency
    "environmental_indicator",  # NASA space-weather indicator, not a crew dose
    "simulated_environment",  # simulated habitat / dose-rate model
    "simulation_scenario",  # an operator-injected or scripted test scenario
]
CLASSIFICATION_LABELS: dict[str, str] = {
    "rule_detection": "Rule-based detection",
    "experimental_ai": "Experimental AI prediction",
    "environmental_indicator": "Environmental indicator (NASA)",
    "simulated_environment": "Simulated environment",
    "simulation_scenario": "Simulation scenario",
}
CLASSIFICATION_NOTES: dict[str, str] = {
    "rule_detection": "Prototype rule applied to simulated measurements. Limits are software test values, not clinical criteria.",
    "experimental_ai": "Experimental model output trained on simulated data. It is a prompt for review by qualified "
                       "personnel and is not a confirmed medical emergency or a diagnosis.",
    "environmental_indicator": "Real NASA DONKI space-weather indicator. It describes the space environment, not a "
                               "radiation dose received by any crew member.",
    "simulated_environment": "Value from the simulator's habitat model; nominal levels are simulator settings, not limits.",
    "simulation_scenario": "Injected software test scenario.",
}

SEVERITY_BASE = {"critical": 90.0, "caution": 65.0, "advisory": 40.0, "info": 15.0}
CLASSIFICATION_CAP = {
    "rule_detection": 100.0,
    "experimental_ai": 59.0,  # never above P3
    "environmental_indicator": 79.0,  # never above P2
    "simulated_environment": 100.0,
    "simulation_scenario": 59.0,
}
PRIORITY_LABELS = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}


def priority_for(severity: str, classification: str, *, astronaut_specific: bool = False,
                 escalated: bool = False) -> tuple[int, float]:
    """(priority level 1..4, score 0..100) on the shared scale described in the module docstring."""
    score = SEVERITY_BASE.get(severity, 15.0)
    if astronaut_specific and severity != "info":
        score += 5.0
    if escalated:
        score += 5.0
    score = min(score, CLASSIFICATION_CAP.get(classification, 100.0), 100.0)
    level = 1 if score >= 80 else 2 if score >= 60 else 3 if score >= 35 else 4
    return level, round(score, 1)


def cap_ai_severity(severity: str) -> str:
    """Experimental AI output is never reported as critical."""
    return "caution" if severity == "critical" else severity


def worse(a: str, b: str) -> str:
    return a if SEVERITY_RANK.get(a, 0) >= SEVERITY_RANK.get(b, 0) else b
