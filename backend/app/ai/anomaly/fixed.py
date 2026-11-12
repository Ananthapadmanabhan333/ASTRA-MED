"""Reference scorer: the phase 2 fixed, activity-aware alert thresholds applied to windows.

It is not one of the learned detectors. It answers "what would the existing fixed limits have
caught?", so the learned models can be compared against it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.detection.rules import THRESHOLD_RULES


def fixed_threshold_scores(windows: pd.DataFrame) -> np.ndarray:
    """Largest normalised exceedance across rules: >= 0 means a caution limit is breached,
    >= 1 means the critical limit is breached. Missing values never breach."""
    states = windows["state"].fillna("work").astype(str).to_numpy()
    score = np.full(len(windows), -1.0)
    for rule in THRESHOLD_RULES:
        values = windows[rule.metric].to_numpy(dtype=float)
        caution = np.array([rule.limits(s)[0] for s in states])
        critical = np.array([rule.limits(s)[1] for s in states])
        span = np.abs(critical - caution)
        if rule.direction == "high":
            exceed = (values - caution) / span
        else:
            exceed = (caution - values) / span
        score = np.fmax(score, np.where(np.isfinite(exceed), exceed, -1.0))
    return score
