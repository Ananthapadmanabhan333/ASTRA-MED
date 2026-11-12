"""Early-warning risk assessment (module 4): transparent, configurable rules.

Points from four sources add up to a 0-100 risk score:

  deviation  each signal beyond the personal-baseline z limit, scaled by how far and for how long
  anomaly    the multivariate ensemble flagging the recent windows, with a bonus for agreement
  trend      a forecast reaching a caution limit within the configured horizons
  alerts     open alerts from the live monitoring rules

No probabilistic risk model is used: none has been validated, and the rules are easier to audit.
The output is a prioritised concern level for a flight surgeon to review, never a diagnosis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.ai.explain import Contributor, Explanation, confidence, significance
from app.ai.signals import LABELS, UNITS

CONFIG_PATH = Path(__file__).with_name("risk_config.json")
CATEGORY_LABELS = {
    "normal": "Normal",
    "low_concern": "Low concern",
    "moderate_concern": "Moderate concern",
    "high_concern": "High concern",
}


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    deviation_z_start: float = 2.0
    deviation_points_per_z: float = 5.0
    deviation_cap_per_signal: float = 22.0
    duration_full_minutes: float = 60
    duration_min_factor: float = 0.4
    anomaly_points_at_threshold: float = 18.0
    anomaly_points_cap: float = 30.0
    anomaly_agreement_bonus: float = 2.0
    trend_points_likely: float = 14.0
    trend_points_possible: float = 6.0
    trend_horizons_hours: list[int] = [6, 12, 24]
    alert_points: dict[str, float] = {"critical": 40.0, "caution": 20.0, "advisory": 7.0}
    categories: dict[str, float] = {"low_concern": 12.0, "moderate_concern": 30.0, "high_concern": 55.0}
    confidence_min_windows: int = 12

    @classmethod
    def load(cls, path: Path | None = None) -> RiskConfig:
        p = path or CONFIG_PATH
        return cls.model_validate(json.loads(p.read_text())) if p.exists() else cls()


@dataclass
class SignalState:
    signal: str
    value: float | None
    baseline: float | None
    z: float | None
    percentile: float | None
    level: str
    deviating_minutes: float = 0.0
    trend_per_hour: float = 0.0


@dataclass
class AnomalyState:
    available: bool
    score: float = 0.0  # ensemble score / threshold (>= 1 is flagged)
    votes: int = 0
    n_detectors: int = 0
    flagged_minutes: float = 0.0
    kind: str | None = None
    top_signals: list[str] = field(default_factory=list)


@dataclass
class ForecastState:
    signal: str
    horizon_h: int
    value: float
    lower: float
    upper: float
    limit: float
    direction: str  # "high" | "low"

    @property
    def crossing(self) -> str | None:
        if self.direction == "high":
            return "likely" if self.value >= self.limit else "possible" if self.upper >= self.limit else None
        return "likely" if self.value <= self.limit else "possible" if self.lower <= self.limit else None


@dataclass
class RiskInputs:
    astronaut_id: str
    signals: list[SignalState]
    anomaly: AnomalyState
    forecasts: list[ForecastState]
    alerts: list[dict[str, Any]]
    missing_frac: float
    windows: int
    forecast_available: bool


def category_for(score: float, cfg: RiskConfig) -> str:
    c = cfg.categories
    if score >= c["high_concern"]:
        return "high_concern"
    if score >= c["moderate_concern"]:
        return "moderate_concern"
    if score >= c["low_concern"]:
        return "low_concern"
    return "normal"


def _duration_factor(minutes: float, cfg: RiskConfig) -> float:
    return max(cfg.duration_min_factor, min(1.0, minutes / cfg.duration_full_minutes))


def assess(inputs: RiskInputs, cfg: RiskConfig | None = None) -> dict[str, Any]:
    cfg = cfg or RiskConfig.load()
    components: list[dict[str, Any]] = []
    by_signal: dict[str, float] = {}

    for s in inputs.signals:
        if s.z is None or abs(s.z) < cfg.deviation_z_start:
            continue
        raw = min(cfg.deviation_cap_per_signal, (abs(s.z) - cfg.deviation_z_start + 1) * cfg.deviation_points_per_z)
        pts = raw * _duration_factor(s.deviating_minutes, cfg)
        direction = "above" if s.z > 0 else "below"
        components.append({
            "source": "deviation", "signals": [s.signal], "points": round(pts, 1),
            "title": f"{LABELS[s.signal]} {direction} personal baseline",
            "detail": (f"{LABELS[s.signal]} {s.value:.1f} {UNITS[s.signal]} vs baseline {s.baseline:.1f} "
                       f"(z = {s.z:+.1f}) for about {s.deviating_minutes:.0f} min."),
        })
        by_signal[s.signal] = by_signal.get(s.signal, 0.0) + pts

    a = inputs.anomaly
    if a.available and a.score >= 1.0:
        pts = min(cfg.anomaly_points_cap, cfg.anomaly_points_at_threshold * a.score)
        pts = pts * _duration_factor(a.flagged_minutes, cfg) + cfg.anomaly_agreement_bonus * max(0, a.votes - 1)
        kind = (a.kind or "anomaly").replace("_", " ")
        components.append({
            "source": "anomaly", "signals": a.top_signals, "points": round(pts, 1),
            "title": f"Multivariate pattern flagged ({kind})",
            "detail": (f"{a.votes} of {a.n_detectors} detectors flag the recent windows "
                       f"(ensemble {a.score:.2f}x threshold) for about {a.flagged_minutes:.0f} min."),
        })
        for sig in a.top_signals:
            by_signal[sig] = by_signal.get(sig, 0.0) + pts / max(1, len(a.top_signals))

    worst: dict[str, ForecastState] = {}
    for f in inputs.forecasts:
        if f.horizon_h not in cfg.trend_horizons_hours or f.crossing is None:
            continue
        prev = worst.get(f.signal)
        rank = {"likely": 2, "possible": 1}
        if prev is None or rank[f.crossing] > rank[prev.crossing] or (
            rank[f.crossing] == rank[prev.crossing] and f.horizon_h < prev.horizon_h
        ):
            worst[f.signal] = f
    for sig, f in worst.items():
        pts = cfg.trend_points_likely if f.crossing == "likely" else cfg.trend_points_possible
        components.append({
            "source": "trend", "signals": [sig], "points": round(pts, 1),
            "title": f"{LABELS[sig]} forecast {'reaches' if f.crossing == 'likely' else 'may reach'} caution limit",
            "detail": (f"Forecast {f.value:.1f} {UNITS[sig]} in {f.horizon_h} h (interval {f.lower:.1f} to {f.upper:.1f}); "
                       f"caution limit {f.limit:g} {UNITS[sig]}."),
        })
        by_signal[sig] = by_signal.get(sig, 0.0) + pts

    for alert in inputs.alerts:
        pts = cfg.alert_points.get(alert["severity"], 0.0) * (0.5 if alert.get("condition_cleared") else 1.0)
        components.append({
            "source": "alert", "signals": [alert["metric"]] if alert["metric"] in LABELS else [], "points": round(pts, 1),
            "title": f"Open {alert['severity']} alert: {alert['title']}",
            "detail": "Values have returned within limits; awaiting operator resolution." if alert.get("condition_cleared")
            else "Condition still present.",
            "alert_id": alert["id"],
        })
        if alert["metric"] in LABELS:
            by_signal[alert["metric"]] = by_signal.get(alert["metric"], 0.0) + pts

    score = min(100.0, sum(c["points"] for c in components))
    category = category_for(score, cfg)
    components.sort(key=lambda c: -c["points"])
    # A warning is by definition at least a low concern, whatever its individual points.
    warnings = [
        {**c, "priority": i + 1,
         "concern": "low_concern" if category_for(c["points"], cfg) == "normal" else category_for(c["points"], cfg)}
        for i, c in enumerate(components)
    ]

    total = sum(by_signal.values()) or 1.0
    refs = {s.signal: s for s in inputs.signals}
    contributors = [
        Contributor(
            signal=sig, label=LABELS[sig], share=round(v / total, 3), unit=UNITS[sig],
            value=refs[sig].value if sig in refs else None, baseline=refs[sig].baseline if sig in refs else None,
            z=round(refs[sig].z, 2) if sig in refs and refs[sig].z is not None else None,
            percentile=refs[sig].percentile if sig in refs else None,
            direction=("above" if (refs[sig].z or 0) >= 0 else "below") if sig in refs else None,
        )
        for sig, v in sorted(by_signal.items(), key=lambda kv: -kv[1])
    ]
    max_z = max((abs(s.z) for s in inputs.signals if s.z is not None), default=0.0)
    completeness = 1 - min(1.0, inputs.missing_frac)
    coverage = min(1.0, inputs.windows / max(1, cfg.confidence_min_windows))
    model_part = (0.5 if a.available else 0.0) + (0.5 if inputs.forecast_available else 0.0)
    conf = confidence(
        0.45 * completeness + 0.25 * coverage + 0.3 * model_part,
        [
            f"{completeness:.0%} of recent values present",
            f"{inputs.windows} recent windows analysed",
            "anomaly models loaded" if a.available else "anomaly models unavailable (statistical deviations only)",
            "forecast available" if inputs.forecast_available else "no forecast available",
        ],
    )
    if components:
        drivers = "; ".join(c["title"].lower() for c in components[:3])
        what = f"{CATEGORY_LABELS[category]} ({score:.0f}/100). Main drivers: {drivers}."
    else:
        what = "Normal (0/100). No signal is outside its personal baseline, no pattern is flagged, and no alert is open."
    explanation = Explanation(
        what_changed=what,
        kind="risk_assessment",
        contributors=contributors,
        significance=significance(max_z),
        confidence=conf,
        limitations=[],
        method="Configurable rules (app/ai/risk_config.json) combining baseline deviation, anomaly ensemble, forecast trend and open alerts.",
    )
    return {
        "risk_score": round(score, 1),
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "health_score": int(round(100 - score)),
        "warnings": warnings,
        "explanation": explanation,
    }
