"""Forecasting data: 30-minute steps, personal normalisation, and origin-based samples.

A *sample* is anchored at an origin step t (the last observed step):
  past     the previous LOOKBACK steps of the four target signals plus activity, sleep and time
  future   the next HORIZON steps of *known* covariates: planned activity, planned sleep, time
           of day (a real mission timeline is planned ahead; in the simulator plan == actual)
  target   the next HORIZON steps of the four signals

Signals are normalised per crew member with their personal baseline centre and scale, so one
model can serve the whole crew.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ai.baseline import PersonalBaseline
from app.ai.signals import FORECAST_SIGNALS, SCALE_FLOOR

STEP_MINUTES = 30
STEPS_PER_HOUR = 60 // STEP_MINUTES
LOOKBACK = 48  # 24 h of history
HORIZON = 48  # forecast up to 24 h ahead
REPORT_HORIZONS_H = (1, 6, 12, 24)
REPORT_STEPS = tuple(h * STEPS_PER_HOUR for h in REPORT_HORIZONS_H)  # 2, 12, 24, 48

PAST_CHANNELS = (*FORECAST_SIGNALS, "met", "sleep", "tod_sin", "tod_cos", *(f"{s}_dev" for s in FORECAST_SIGNALS))
FUTURE_CHANNELS = ("met", "sleep", "tod_sin", "tod_cos")


def to_steps(windows: pd.DataFrame) -> pd.DataFrame:
    """5-minute windows → 30-minute steps (means; dominant state)."""
    rule = f"{STEP_MINUTES}min"
    agg = windows[[*FORECAST_SIGNALS, "activity_met", "sleep_frac"]].resample(rule).mean()
    states = windows["state"].fillna("work")
    agg["state"] = states.groupby(states.index.floor(rule)).agg(lambda s: s.value_counts().index[0])
    if "label" in windows:
        agg["label"] = windows["label"].resample(rule).max().fillna(False).astype(bool)
    return agg


@dataclass(frozen=True)
class Normaliser:
    center: dict[str, float]
    scale: dict[str, float]

    @classmethod
    def from_baseline(cls, baseline: PersonalBaseline) -> Normaliser:
        center, scale = {}, {}
        for s in FORECAST_SIGNALS:
            stats = baseline.cells.get(f"{s}|*|*")
            c, sc = stats.robust(SCALE_FLOOR[s]) if stats and stats.n else (0.0, SCALE_FLOOR[s])
            center[s], scale[s] = c, max(sc, 2 * SCALE_FLOOR[s])
        return cls(center, scale)

    def norm(self, s: str, v):
        return (v - self.center[s]) / self.scale[s]

    def denorm(self, s: str, v):
        return v * self.scale[s] + self.center[s]

    def to_dict(self) -> dict:
        return {"center": self.center, "scale": self.scale}

    @classmethod
    def from_dict(cls, d: dict) -> Normaliser:
        return cls(d["center"], d["scale"])


def covariates(index: pd.DatetimeIndex, met: np.ndarray, sleep: np.ndarray) -> np.ndarray:
    hours = index.hour + index.minute / 60
    return np.column_stack(
        [(np.nan_to_num(met, nan=1.7) - 1.7) / 2.0, np.nan_to_num(sleep), np.sin(2 * np.pi * hours / 24),
         np.cos(2 * np.pi * hours / 24)]
    ).astype(np.float32)


@dataclass
class SeriesArrays:
    """One crew member's step series in model-ready form."""

    astronaut_id: str
    index: pd.DatetimeIndex
    y: np.ndarray  # (T, 4) normalised signals, NaN where missing
    y_filled: np.ndarray  # (T, 4) carried forward, then 0 (= personal baseline)
    cov: np.ndarray  # (T, 4) known covariates
    states: np.ndarray  # (T,) dominant activity state
    norm: Normaliser
    baseline: PersonalBaseline
    clim: np.ndarray  # (T, 4) baseline expectation at every step, normalised
    dev: np.ndarray  # (T, 4) observed minus baseline expectation (carried forward, then 0)

    @classmethod
    def build(cls, astronaut_id: str, steps: pd.DataFrame, baseline: PersonalBaseline) -> SeriesArrays:
        norm = Normaliser.from_baseline(baseline)
        y = np.column_stack([norm.norm(s, steps[s].to_numpy(float)) for s in FORECAST_SIGNALS]).astype(np.float32)
        filled = pd.DataFrame(y).ffill(limit=4).fillna(0.0).to_numpy(np.float32)
        cov = covariates(steps.index, steps["activity_met"].to_numpy(float), steps["sleep_frac"].to_numpy(float))
        states = steps["state"].to_numpy()
        clim = np.array(
            [[norm.norm(s, baseline.expected(s, st, ts)) for s in FORECAST_SIGNALS] for ts, st in zip(steps.index, states)],
            dtype=np.float32,
        )
        dev = pd.DataFrame(y - clim).ffill(limit=4).fillna(0.0).to_numpy(np.float32)
        return cls(astronaut_id, steps.index, y, filled, cov, states, norm, baseline, clim, dev)

    def past(self, t: int) -> np.ndarray:
        """(LOOKBACK, 12) inputs ending at origin t inclusive: signals, covariates, deviations."""
        sl = slice(t - LOOKBACK + 1, t + 1)
        return np.concatenate([self.y_filled[sl], self.cov[sl], self.dev[sl]], axis=1)

    def future_cov(self, t: int) -> np.ndarray:
        return self.cov[t + 1 : t + 1 + HORIZON]

    def target(self, t: int) -> np.ndarray:
        return self.y[t + 1 : t + 1 + HORIZON]

    def climatology(self, t: int) -> np.ndarray:
        """Baseline expectation at each target step (normalised): the 'schedule-aware' baseline."""
        return self.clim[t + 1 : t + 1 + HORIZON]


def origins(series: SeriesArrays, part_mask: np.ndarray, stride: int = 1) -> np.ndarray:
    """Origin indices whose whole target horizon lies inside ``part_mask`` (True steps)."""
    T = len(series.index)
    candidates = np.arange(LOOKBACK - 1, T - HORIZON, stride)
    ok = [t for t in candidates if part_mask[t + 1 : t + 1 + HORIZON].all()]
    return np.asarray(ok, dtype=int)


@dataclass
class SampleSet:
    past: np.ndarray  # (N, LOOKBACK, 8)
    future: np.ndarray  # (N, HORIZON, 4)
    target: np.ndarray  # (N, HORIZON, 4) normalised, NaN where missing
    clim: np.ndarray  # (N, HORIZON, 4)
    origin_ts: list[pd.Timestamp]
    astronaut: list[str]
    scale: np.ndarray  # (N, 4) per-sample signal scale, to report errors in physical units

    def __len__(self) -> int:
        return len(self.past)


def build_samples(series_list: list[SeriesArrays], masks: dict[str, np.ndarray], stride: int = 1) -> SampleSet:
    past, fut, tgt, clim, ts, who, scale = [], [], [], [], [], [], []
    for s in series_list:
        for t in origins(s, masks[s.astronaut_id], stride):
            past.append(s.past(t))
            fut.append(s.future_cov(t))
            tgt.append(s.target(t))
            clim.append(s.climatology(t))
            ts.append(s.index[t])
            who.append(s.astronaut_id)
            scale.append([s.norm.scale[x] for x in FORECAST_SIGNALS])
    return SampleSet(
        np.asarray(past, np.float32), np.asarray(fut, np.float32), np.asarray(tgt, np.float32),
        np.asarray(clim, np.float32), ts, who, np.asarray(scale, np.float32),
    )
