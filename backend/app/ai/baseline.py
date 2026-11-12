"""Personalised physiological baselines (module 1).

Each crew member gets statistics per signal, per activity state, per 4-hour time-of-day bucket:

* running mean and standard deviation (Welford's algorithm, so updates are incremental and exact),
* a bounded reservoir sample for percentiles (p5, p25, p50, p75, p95),
* a *robust* centre and scale (median and IQR / 1.349) used for z-scores, so the occasional
  anomaly in the history does not inflate the baseline it is judged against.

Sparse cells fall back to the activity-state level, then to the person's overall statistics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.ai.signals import N_TOD_BUCKETS, SCALE_FLOOR, SIGNALS, STATES, TOD_BUCKET_HOURS

RESERVOIR_SIZE = 600
MIN_CELL_COUNT = 30  # windows needed before an activity × time-of-day cell is used
MIN_STATE_COUNT = 12  # windows (1 h) needed before a whole-activity reference is used
PERCENTILES = (5, 25, 50, 75, 95)


@dataclass
class CellStats:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0
    reservoir: list[float] = field(default_factory=list)
    seen: int = 0  # values offered to the reservoir (for Algorithm R)
    _robust_cache: dict = field(default_factory=dict, repr=False, compare=False)

    def update(self, values: np.ndarray, rng: np.random.Generator) -> None:
        self._robust_cache.clear()
        for v in values:
            if not math.isfinite(v):
                continue
            self.n += 1
            delta = v - self.mean
            self.mean += delta / self.n
            self.m2 += delta * (v - self.mean)
            self.seen += 1
            if len(self.reservoir) < RESERVOIR_SIZE:
                self.reservoir.append(float(v))
            else:
                j = int(rng.integers(0, self.seen))
                if j < RESERVOIR_SIZE:
                    self.reservoir[j] = float(v)

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / (self.n - 1)) if self.n > 1 else 0.0

    def percentiles(self) -> dict[str, float]:
        if not self.reservoir:
            return {}
        values = np.percentile(self.reservoir, PERCENTILES)
        return {f"p{p}": round(float(v), 3) for p, v in zip(PERCENTILES, values)}

    def robust(self, floor: float) -> tuple[float, float]:
        cached = self._robust_cache.get(floor)
        if cached is not None:
            return cached
        if not self.reservoir:
            result = (self.mean, max(self.std, floor))
        else:
            q25, q50, q75 = np.percentile(self.reservoir, (25, 50, 75))
            result = (float(q50), float(max((q75 - q25) / 1.349, 0.5 * self.std, floor)))
        self._robust_cache[floor] = result
        return result

    def rank(self, value: float) -> float:
        """Approximate percentile rank (0-100) of a value within this cell."""
        if not self.reservoir:
            return 50.0
        arr = np.sort(np.asarray(self.reservoir))
        return float(100.0 * np.searchsorted(arr, value, side="right") / len(arr))

    def to_dict(self) -> dict[str, Any]:
        return {"n": self.n, "mean": self.mean, "m2": self.m2, "reservoir": self.reservoir, "seen": self.seen}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CellStats:
        return cls(n=d["n"], mean=d["mean"], m2=d["m2"], reservoir=list(d["reservoir"]), seen=d["seen"])


@dataclass(frozen=True)
class Reference:
    """Baseline expectation for one signal in one context, plus how it was resolved."""

    center: float
    scale: float
    mean: float
    std: float
    n: int
    level: str  # "cell" | "state" | "overall" | "none"
    stats: CellStats
    # False when no reference exists for the requested activity and this one pools other activities
    # (or there is none at all). Its center still serves as a rough expectation for forecasting, but
    # comparing against it would score ordinary exercise or sleep as a deviation, so z() is NaN.
    comparable: bool = True

    def z(self, value: float) -> float:
        if not self.comparable:
            return math.nan
        return (value - self.center) / self.scale

    def z_or_none(self, value: float) -> float | None:
        z = self.z(value)
        return None if not math.isfinite(z) else z

    def percentile(self, value: float) -> float:
        return self.stats.rank(value)

    def percentile_or_none(self, value: float) -> float | None:
        return self.stats.rank(value) if self.comparable else None

    @property
    def basis(self) -> str:
        """Level to report: "none" when this reference cannot be compared against."""
        return self.level if self.comparable else "none"


@dataclass
class PersonalBaseline:
    astronaut_id: str
    seed: int = 0
    cells: dict[str, CellStats] = field(default_factory=dict)
    windows_seen: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    # ------------------------------------------------------------------ fitting ----
    @staticmethod
    def _key(signal: str, state: str | None = None, bucket: int | None = None) -> str:
        return f"{signal}|{state or '*'}|{'*' if bucket is None else bucket}"

    def _cell(self, key: str) -> CellStats:
        if key not in self.cells:
            self.cells[key] = CellStats()
        return self.cells[key]

    def update(self, windows: pd.DataFrame) -> PersonalBaseline:
        """Add windows (index: UTC timestamps; columns: signals + ``state``). Returns self."""
        if windows.empty:
            return self
        rng = np.random.default_rng(self.seed + self.windows_seen)
        states = windows["state"].fillna("work").astype(str)
        buckets = (windows.index.hour // TOD_BUCKET_HOURS).astype(int)
        for signal in SIGNALS:
            if signal not in windows:
                continue
            values = windows[signal].to_numpy(dtype=float)
            self._cell(self._key(signal)).update(values, rng)
            frame = pd.DataFrame({"v": values, "s": states.to_numpy(), "b": np.asarray(buckets)})
            for state, group in frame.groupby("s"):
                self._cell(self._key(signal, state)).update(group["v"].to_numpy(), rng)
                for bucket, sub in group.groupby("b"):
                    self._cell(self._key(signal, state, int(bucket))).update(sub["v"].to_numpy(), rng)
        self.windows_seen += len(windows)
        first, last = windows.index.min().to_pydatetime(), windows.index.max().to_pydatetime()
        self.first_ts = first if self.first_ts is None else min(self.first_ts, first)
        self.last_ts = last if self.last_ts is None else max(self.last_ts, last)
        return self

    @classmethod
    def fit(cls, astronaut_id: str, windows: pd.DataFrame, seed: int = 0) -> PersonalBaseline:
        return cls(astronaut_id=astronaut_id, seed=seed).update(windows)

    # ----------------------------------------------------------------- querying ----
    def reference(self, signal: str, state: str | None, ts: datetime | pd.Timestamp) -> Reference:
        """Most specific reference with enough data: activity × time of day, then the whole activity.

        It never silently compares one activity against the others. If the requested activity has too
        little history, the pooled reference is returned with ``comparable=False``.
        """
        bucket = ts.hour // TOD_BUCKET_HOURS
        floor = SCALE_FLOOR[signal]
        if state is None:
            candidates = [("overall", self._key(signal), MIN_CELL_COUNT)]
        else:
            candidates = [
                ("cell", self._key(signal, state, bucket), MIN_CELL_COUNT),
                ("state", self._key(signal, state), MIN_STATE_COUNT),
            ]
        for level, key, minimum in candidates:
            stats = self.cells.get(key)
            if stats is not None and stats.n >= minimum:
                center, scale = stats.robust(floor)
                return Reference(center, scale, stats.mean, stats.std, stats.n, level, stats)
        pooled = self.cells.get(self._key(signal))
        if pooled is not None and pooled.n >= MIN_CELL_COUNT:
            center, scale = pooled.robust(floor)
            return Reference(center, scale, pooled.mean, pooled.std, pooled.n, "overall", pooled, comparable=False)
        return Reference(0.0, floor, 0.0, 0.0, 0, "none", CellStats(), comparable=False)

    def zscores(self, windows: pd.DataFrame) -> pd.DataFrame:
        """Robust personal z-score per signal per window (NaN where the value is missing)."""
        out = pd.DataFrame(index=windows.index)
        states = windows["state"].fillna("work").astype(str).to_numpy()
        for signal in SIGNALS:
            values = windows[signal].to_numpy(dtype=float)
            z = np.full(len(values), np.nan)
            cache: dict[tuple[str, int], Reference] = {}
            for i, (ts, state, v) in enumerate(zip(windows.index, states, values)):
                if not math.isfinite(v):
                    continue
                key = (state, ts.hour // TOD_BUCKET_HOURS)
                ref = cache.get(key) or cache.setdefault(key, self.reference(signal, state, ts))
                z[i] = ref.z(v)
            out[signal] = z
        return out

    def expected(self, signal: str, state: str | None, ts: datetime | pd.Timestamp) -> float:
        return self.reference(signal, state, ts).center

    def profile(self, signal: str) -> dict[str, Any]:
        """Summary for display: overall stats, per activity state, and a 24-hour profile per state."""
        overall = self.cells.get(self._key(signal), CellStats())
        by_state: dict[str, Any] = {}
        for state in STATES:
            s = self.cells.get(self._key(signal, state))
            if s is None or s.n == 0:
                continue
            center, scale = s.robust(SCALE_FLOOR[signal])
            by_state[state] = {
                "n": s.n,
                "mean": round(s.mean, 3),
                "std": round(s.std, 3),
                "center": round(center, 3),
                "scale": round(scale, 3),
                **s.percentiles(),
                "by_time_of_day": [
                    self._bucket_summary(signal, state, b) for b in range(N_TOD_BUCKETS)
                ],
            }
        return {
            "n": overall.n,
            "mean": round(overall.mean, 3),
            "std": round(overall.std, 3),
            **overall.percentiles(),
            "by_state": by_state,
        }

    def _bucket_summary(self, signal: str, state: str, bucket: int) -> dict[str, Any]:
        s = self.cells.get(self._key(signal, state, bucket))
        start = bucket * TOD_BUCKET_HOURS
        if s is None or s.n == 0:
            return {"hours": f"{start:02d}-{start + TOD_BUCKET_HOURS:02d}", "n": 0}
        return {
            "hours": f"{start:02d}-{start + TOD_BUCKET_HOURS:02d}",
            "n": s.n,
            "mean": round(s.mean, 3),
            "std": round(s.std, 3),
            **s.percentiles(),
        }

    # ------------------------------------------------------------ serialisation ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "astronaut_id": self.astronaut_id,
            "seed": self.seed,
            "windows_seen": self.windows_seen,
            "first_ts": self.first_ts.isoformat() if self.first_ts else None,
            "last_ts": self.last_ts.isoformat() if self.last_ts else None,
            "cells": {k: v.to_dict() for k, v in self.cells.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PersonalBaseline:
        return cls(
            astronaut_id=d["astronaut_id"],
            seed=d.get("seed", 0),
            windows_seen=d.get("windows_seen", 0),
            first_ts=datetime.fromisoformat(d["first_ts"]) if d.get("first_ts") else None,
            last_ts=datetime.fromisoformat(d["last_ts"]) if d.get("last_ts") else None,
            cells={k: CellStats.from_dict(v) for k, v in d["cells"].items()},
        )


def rolling_stats(windows: pd.DataFrame, hours: int) -> dict[str, dict[str, float | None]]:
    """Mean, standard deviation and percentiles of each signal over the trailing ``hours``."""
    if windows.empty:
        return {}
    cutoff = windows.index.max() - pd.Timedelta(hours=hours)
    recent = windows[windows.index > cutoff]
    out: dict[str, dict[str, float | None]] = {}
    for signal in SIGNALS:
        v = recent[signal].dropna()
        if v.empty:
            out[signal] = {"n": 0, "mean": None, "std": None, "p5": None, "p50": None, "p95": None}
            continue
        p5, p50, p95 = np.percentile(v, (5, 50, 95))
        out[signal] = {
            "n": int(v.size),
            "mean": round(float(v.mean()), 3),
            "std": round(float(v.std(ddof=1)) if v.size > 1 else 0.0, 3),
            "p5": round(float(p5), 3),
            "p50": round(float(p50), 3),
            "p95": round(float(p95), 3),
        }
    return out
