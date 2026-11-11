"""Personal-baseline deviation detector.

For each crew member and signal, the detector compares a reading with that person's expected
value for the time of day and current activity, then tracks the residual with an exponentially
weighted mean and variance. A sustained z-score beyond the limit is an *advisory* anomaly:
something unusual for this person, even when it is inside the fixed thresholds.

In this prototype the expected value comes from the crew member's baseline model. In a real
deployment it would be learned from pre-flight and early-mission data.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from app.simulator.physiology import NOISE_SIGMA

ExpectedFn = Callable[[str, object, str, float], dict[str, float]]

BASELINE_METRICS = ("heart_rate", "respiratory_rate", "spo2")


@dataclass
class _ResidualStats:
    mean: float
    var: float
    count: int = 0


@dataclass(frozen=True)
class Deviation:
    metric: str
    value: float
    expected: float
    z: float


class BaselineDetector:
    def __init__(
        self,
        expected_fn: ExpectedFn,
        *,
        alpha: float = 0.004,
        z_limit: float = 4.0,
        update_limit: float = 3.0,
    ) -> None:
        self.expected_fn = expected_fn
        self.alpha = alpha
        self.z_limit = z_limit
        self.update_limit = update_limit
        self._stats: dict[tuple[str, str], _ResidualStats] = {}

    def _stats_for(self, astronaut_id: str, metric: str) -> _ResidualStats:
        key = (astronaut_id, metric)
        if key not in self._stats:
            self._stats[key] = _ResidualStats(mean=0.0, var=(2 * NOISE_SIGMA[metric]) ** 2)
        return self._stats[key]

    def evaluate(self, reading) -> list[Deviation]:
        expected = self.expected_fn(
            reading.astronaut_id, reading.ts, reading.activity_state, reading.activity_met
        )
        out: list[Deviation] = []
        for metric in BASELINE_METRICS:
            stats = self._stats_for(reading.astronaut_id, metric)
            value = reading.value(metric)
            residual = value - expected[metric]
            std = max(math.sqrt(stats.var), 1.5 * NOISE_SIGMA[metric])
            z = (residual - stats.mean) / std
            if abs(z) < self.update_limit:
                # Only learn from unremarkable samples so anomalies do not shift the baseline.
                diff = residual - stats.mean
                stats.mean += self.alpha * diff
                stats.var = (1 - self.alpha) * (stats.var + self.alpha * diff * diff)
                stats.count += 1
            out.append(Deviation(metric, value, round(expected[metric], 2), round(z, 2)))
        return out

    def is_anomalous(self, deviation: Deviation) -> bool:
        return abs(deviation.z) >= self.z_limit
