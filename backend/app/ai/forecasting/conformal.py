"""Split-conformal prediction intervals.

For each model, signal and horizon step, take the absolute residuals on a calibration set the
model never trained or early-stopped on, and use their finite-sample-corrected (1 - alpha)
quantile as the interval half-width. Under exchangeability this gives at least (1 - alpha)
coverage; time series only approximately satisfy that, so test coverage is reported, not assumed.
"""

from __future__ import annotations

import math

import numpy as np


def conformal_quantiles(pred: np.ndarray, target: np.ndarray, alpha: float = 0.1) -> np.ndarray:
    """Half-widths of shape pred.shape[1:] (horizon, signals)."""
    resid = np.abs(pred - target)
    _, H, S = pred.shape
    q = np.full((H, S), np.nan, dtype=np.float32)
    for h in range(H):
        for s in range(S):
            r = np.sort(resid[:, h, s][np.isfinite(resid[:, h, s])])
            n = len(r)
            if n == 0:
                continue
            k = min(n, math.ceil((n + 1) * (1 - alpha)))
            q[h, s] = r[k - 1]
    return q


def intervals(pred: np.ndarray, half_width: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return pred - half_width[None], pred + half_width[None]
