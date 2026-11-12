"""Explanations shared by every AI output (module 5).

Each explanation answers five questions:
  1. What changed?                       what_changed (plain language) and kind
  2. Which signals contributed?          contributors (share, value, baseline, z, percentile)
  3. How significant was the deviation?  significance (graded by personal z-score)
  4. How confident is the model?         confidence (score, level and what it is based on)
  5. What data limitations exist?        limitations (always includes the synthetic-data caveat)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from app.ai.features import FEATURE_GROUPS
from app.ai.signals import LABELS, SIGNALS, UNITS

SYNTHETIC_CAVEAT = (
    "Models were trained and evaluated on simulated data only; this output is experimental decision "
    "support, not a diagnosis, and its real-world accuracy is unknown."
)


@dataclass
class Contributor:
    signal: str
    label: str
    share: float  # 0..1 of this explanation's total attribution
    value: float | None = None
    unit: str = ""
    baseline: float | None = None
    z: float | None = None
    percentile: float | None = None
    direction: str | None = None  # "above" | "below"


@dataclass
class Explanation:
    what_changed: str
    kind: str  # "sudden_change" | "gradual_deviation" | "sustained_offset" | "within_normal" | "forecast" | ...
    contributors: list[Contributor]
    significance: dict[str, Any]
    confidence: dict[str, Any]
    limitations: list[str] = field(default_factory=list)
    method: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def significance(max_abs_z: float, percentile: float | None = None) -> dict[str, Any]:
    if max_abs_z >= 4:
        level, text = "major", "far outside this crew member's usual range"
    elif max_abs_z >= 2.5:
        level, text = "notable", "clearly outside this crew member's usual range"
    elif max_abs_z >= 1.5:
        level, text = "minor", "at the edge of this crew member's usual range"
    else:
        level, text = "none", "within this crew member's usual range"
    out = {"level": level, "max_abs_z": round(float(max_abs_z), 2), "description": text}
    if percentile is not None:
        out["percentile"] = round(float(percentile), 1)
    return out


def confidence(score: float, basis: list[str]) -> dict[str, Any]:
    score = float(np.clip(score, 0, 1))
    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return {"score": round(score, 2), "level": level, "basis": basis}


def signal_shares(contrib: np.ndarray, feature_names: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Fold per-feature attribution into (per-signal share, per-feature-group share)."""
    by_signal: dict[str, float] = {}
    by_group: dict[str, float] = {}
    for value, name in zip(contrib, feature_names):
        group = next((g for g, names in FEATURE_GROUPS.items() if name in names), "other")
        by_group[group] = by_group.get(group, 0.0) + float(value)
        signal = next((s for s in SIGNALS if name.endswith(s)), None)
        key = signal or "context"
        by_signal[key] = by_signal.get(key, 0.0) + float(value)
    return by_signal, by_group


def anomaly_kind(by_group: dict[str, float]) -> str:
    sudden = by_group.get("sudden", 0.0)
    gradual = by_group.get("trend", 0.0) + by_group.get("sustained", 0.0)
    level = by_group.get("level", 0.0)
    if sudden >= max(gradual, level) and sudden > 0.2:
        return "sudden_change"
    if gradual >= level:
        return "gradual_deviation"
    return "sustained_offset"


def onset_kind(z: np.ndarray, onset: int, window_minutes: int = 5, before: int = 24, after: int = 6) -> str:
    """Classify how a deviation began from the top signal's personal z-score history.

    Around the first flagged window (2 h before to 30 min after), compare two shapes:
      step   flat, then a jump to a new level            -> "sudden_change"
      ramp   flat, then a steady rise (hinge function)   -> "gradual_deviation" (rising >= 30 min)
    A step must fit with >= 20% lower squared error (steps separate decisively); a ramp needs >= 10%
    (slow drifts are noisier). Otherwise it is a "sustained_offset".
    Independent of which features a detector uses, and easy to audit.
    """
    if onset is None or onset >= len(z) or not np.isfinite(z[onset]):
        return "sustained_offset"
    lo, hi = max(0, onset - before), min(len(z), onset + after + 1)
    y_all = np.asarray(z[lo:hi], dtype=float)
    t_all = np.arange(len(y_all), dtype=float)
    ok = np.isfinite(y_all)
    if ok.sum() < 8:
        return "sustained_offset"
    y, t = y_all[ok], t_all[ok]
    best_step, best_ramp, ramp_start = np.inf, np.inf, None
    for c in t[2:-1]:
        left, right = y[t < c], y[t >= c]
        step = float(((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum())
        best_step = min(best_step, step)
        x = np.clip(t - c, 0, None)
        A = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        ramp = float(((y - A @ coef) ** 2).sum())
        if ramp < best_ramp:
            best_ramp, ramp_start = ramp, c
    rising_minutes = (onset - (lo + ramp_start)) * window_minutes if ramp_start is not None else 0
    if best_step <= 0.8 * best_ramp:
        return "sudden_change"
    if best_ramp <= 0.9 * best_step and rising_minutes >= 30:
        return "gradual_deviation"
    return "sustained_offset"


KIND_TEXT = {
    "sudden_change": "changed abruptly within minutes",
    "gradual_deviation": "has drifted away from baseline over several hours",
    "sustained_offset": "is offset from baseline",
}


NEAR_BASELINE_Z = 0.5  # below this a signal is described as "near baseline", not as a deviation


def describe_contributors(contributors: list[Contributor], limit: int = 3) -> str:
    parts = []
    for c in contributors[:limit]:
        if c.value is None or c.baseline is None:
            parts.append(c.label.lower())
            continue
        delta = c.value - c.baseline
        if (c.z is not None and abs(c.z) < NEAR_BASELINE_Z) or round(abs(delta), 1) == 0:
            parts.append(f"{c.label.lower()} near baseline ({c.value:.1f} {c.unit})")
            continue
        parts.append(f"{c.label.lower()} {abs(delta):.1f} {c.unit} {'above' if delta > 0 else 'below'} baseline")
    if not parts:
        return "no single signal stands out"
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def build_contributors(
    shares: dict[str, float],
    values: dict[str, float | None],
    refs: dict[str, Any],
    min_share: float = 0.05,
) -> list[Contributor]:
    total = sum(v for k, v in shares.items() if k != "context") or 1.0
    out = []
    for signal, share in sorted(shares.items(), key=lambda kv: -kv[1]):
        if signal == "context" or share / total < min_share:
            continue
        v = values.get(signal)
        ref = refs.get(signal)
        c = Contributor(signal=signal, label=LABELS[signal], share=round(share / total, 3), unit=UNITS[signal])
        if v is not None and np.isfinite(v):
            c.value = round(float(v), 2)
        if v is not None and ref is not None and np.isfinite(v) and ref.comparable:
            c.baseline = round(float(ref.center), 2)
            c.z = round(float(ref.z(v)), 2)
            c.percentile = round(float(ref.percentile(v)), 1)
            c.direction = "above" if v >= ref.center else "below"
        out.append(c)
    return out


def data_limitations(missing_frac: float, baseline_levels: dict[str, str], history_hours: float) -> list[str]:
    notes = []
    if missing_frac > 0.2:
        notes.append(f"{missing_frac:.0%} of recent signal values were missing and were carried forward or set to baseline.")
    coarse = sorted(s for s, lvl in baseline_levels.items() if lvl == "state")
    if coarse:
        notes.append(
            "Baseline for " + ", ".join(LABELS[s].lower() for s in coarse)
            + " fell back to a coarser level (too few past windows for this activity and time of day)."
        )
    unscored = sorted(s for s, lvl in baseline_levels.items() if lvl == "none")
    if unscored:
        notes.append(
            "No personal baseline yet for " + ", ".join(LABELS[s].lower() for s in unscored)
            + " during the current activity, so they are not scored for deviation."
        )
    if history_hours < 72:
        notes.append(f"Only {history_hours:.0f} h of history are available; baselines firm up after several days.")
    notes.append(SYNTHETIC_CAVEAT)
    return notes
