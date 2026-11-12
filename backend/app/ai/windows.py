"""Aggregate raw samples (1 Hz live or 5-minute backfill) into fixed analysis windows.

A window holds the per-signal *median* (robust to noise and isolated spikes), the dominant
activity state, the fraction of time asleep or exercising, and a sample count. Implausible values
are dropped before aggregation; windows with no valid value for a signal keep NaN so that later
stages can impute explicitly and record the gap.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from app.ai.signals import PLAUSIBLE, SIGNALS, WINDOW_MINUTES


def samples_to_frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Rows need ``ts`` plus any of the signal columns, ``activity_state`` and ``activity_met``."""
    df = pd.DataFrame(list(rows))
    if df.empty:
        return pd.DataFrame(columns=["ts", *SIGNALS, "activity_state", "activity_met"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in (*SIGNALS, "activity_met"):
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "activity_state" not in df:
        df["activity_state"] = None
    return df.sort_values("ts").reset_index(drop=True)


def drop_implausible(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Replace physiologically implausible values with NaN; return the frame and how many were removed."""
    df = df.copy()
    removed = 0
    for signal, (lo, hi) in PLAUSIBLE.items():
        if signal in df:
            bad = (df[signal] < lo) | (df[signal] > hi)
            removed += int(bad.sum())
            df.loc[bad, signal] = np.nan
    return df, removed


def to_windows(df: pd.DataFrame, minutes: int = WINDOW_MINUTES, fill_gaps: bool = True) -> pd.DataFrame:
    """Aggregate a sample frame into a regular window index (UTC, left-labelled)."""
    if df.empty:
        cols = [*SIGNALS, "activity_met", "state", "sleep_frac", "exercise_frac", "n_samples"]
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    df, _ = drop_implausible(df)
    df = df.assign(window=df["ts"].dt.floor(f"{minutes}min"))
    grouped = df.groupby("window")
    out = grouped[list(SIGNALS)].median()
    out["activity_met"] = grouped["activity_met"].mean()
    # Dominant activity state per window, vectorised (counts per state, then the largest).
    counts = df.groupby(["window", "activity_state"]).size().unstack(fill_value=0)
    out["state"] = counts.idxmax(axis=1).where(counts.sum(axis=1) > 0) if not counts.empty else None
    n = grouped.size()
    for state, col in (("sleep", "sleep_frac"), ("exercise", "exercise_frac")):
        out[col] = (counts[state] / n) if state in counts else 0.0
    out["n_samples"] = n
    if fill_gaps:
        full = pd.date_range(out.index.min(), out.index.max(), freq=f"{minutes}min", tz="UTC", name="ts")
        out = out.reindex(full)
        out["n_samples"] = out["n_samples"].fillna(0).astype(int)
    out.index.name = "ts"
    return out
