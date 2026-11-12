"""Feature engineering for multivariate anomaly detection.

All features are *causal*: each window only uses itself and earlier windows, so the same code
serves training, evaluation and live inference without look-ahead leakage.

Groups (used for ablation studies):
  level      personal robust z-score of each signal (time-of-day and activity aware)
  sudden     change in z since the previous window (sudden changes)
  sustained  mean z over the trailing 2 h (persistent offsets)
  trend      slope of z per hour over the trailing 6 h (gradual deviations)
  context    activity load, sleep and exercise fractions, time of day, sleep and exercise in
             the last 24 h (the sleep-duration and physical-activity signals)
  quality    fraction of signals missing in the window
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ai.baseline import PersonalBaseline
from app.ai.signals import SIGNALS, WINDOW_MINUTES

WINDOWS_PER_HOUR = 60 // WINDOW_MINUTES
FFILL_LIMIT = 3  # carry a value forward at most 15 minutes
CLIP = 20.0

FEATURE_GROUPS: dict[str, list[str]] = {
    "level": [f"z_{s}" for s in SIGNALS],
    "sudden": [f"d_{s}" for s in SIGNALS],
    "sustained": [f"sust_{s}" for s in SIGNALS],
    "trend": [f"trend_{s}" for s in SIGNALS],
    "context": ["met", "sleep_frac", "exercise_frac", "tod_sin", "tod_cos", "sleep_24h", "exercise_24h"],
    "quality": ["missing_frac"],
}
ALL_GROUPS = tuple(FEATURE_GROUPS)


def feature_names(groups: tuple[str, ...] = ALL_GROUPS) -> list[str]:
    return [name for g in groups for name in FEATURE_GROUPS[g]]


@dataclass
class FeatureFrame:
    features: pd.DataFrame  # one row per window, columns = feature_names(groups)
    zscores: pd.DataFrame  # unclipped z per signal (NaN where missing even after carry-forward)
    missing: pd.DataFrame  # True where the raw window value was missing
    groups: tuple[str, ...]

    @property
    def names(self) -> list[str]:
        return list(self.features.columns)


def _rolling_slope(z: pd.Series, window: int) -> pd.Series:
    t = pd.Series(np.arange(len(z), dtype=float) / WINDOWS_PER_HOUR, index=z.index)
    cov = z.rolling(window, min_periods=window // 3).cov(t)
    var = t.rolling(window, min_periods=window // 3).var()
    return cov / var


def build_features(
    windows: pd.DataFrame, baseline: PersonalBaseline, groups: tuple[str, ...] = ALL_GROUPS
) -> FeatureFrame:
    """Turn one astronaut's windows into model features, using that astronaut's baseline."""
    missing = windows[list(SIGNALS)].isna()
    carried = windows.copy()
    carried[list(SIGNALS)] = carried[list(SIGNALS)].ffill(limit=FFILL_LIMIT)
    z = baseline.zscores(carried)
    z_filled = z.fillna(0.0)  # missing beyond the carry-forward limit = "at baseline", flagged below

    cols: dict[str, pd.Series] = {}
    for s in SIGNALS:
        zs = z_filled[s]
        cols[f"z_{s}"] = zs
        cols[f"d_{s}"] = zs.diff().fillna(0.0)
        cols[f"sust_{s}"] = zs.rolling(2 * WINDOWS_PER_HOUR, min_periods=3).mean().fillna(0.0)
        cols[f"trend_{s}"] = _rolling_slope(zs, 6 * WINDOWS_PER_HOUR).fillna(0.0)

    hours = windows.index.hour + windows.index.minute / 60
    sleep_frac = windows["sleep_frac"].fillna(0.0)
    exercise_frac = windows["exercise_frac"].fillna(0.0)
    day = 24 * WINDOWS_PER_HOUR
    cols["met"] = (windows["activity_met"].ffill().fillna(1.7) - 1.7) / 2.0
    cols["sleep_frac"] = sleep_frac
    cols["exercise_frac"] = exercise_frac
    cols["tod_sin"] = pd.Series(np.sin(2 * np.pi * hours / 24), index=windows.index)
    cols["tod_cos"] = pd.Series(np.cos(2 * np.pi * hours / 24), index=windows.index)
    sleep_hours = sleep_frac.rolling(day, min_periods=1).sum() * WINDOW_MINUTES / 60
    exercise_minutes = exercise_frac.rolling(day, min_periods=1).sum() * WINDOW_MINUTES
    cols["sleep_24h"] = (sleep_hours - 7.0) / 1.5
    cols["exercise_24h"] = (exercise_minutes - 90.0) / 45.0
    cols["missing_frac"] = missing.mean(axis=1).astype(float)

    frame = pd.DataFrame(cols, index=windows.index)
    names = feature_names(groups)
    features = frame[names].clip(-CLIP, CLIP).astype(float)
    return FeatureFrame(features=features, zscores=z, missing=missing, groups=groups)
