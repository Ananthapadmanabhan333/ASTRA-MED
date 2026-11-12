"""Daily summaries of one crew member's simulated samples (pure functions, no I/O)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

METRICS: tuple[str, ...] = (
    "heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate", "hrv_rmssd_ms",
)
UNITS = {
    "heart_rate": "bpm", "spo2": "%", "systolic": "mmHg", "diastolic": "mmHg", "temperature_c": "°C",
    "respiratory_rate": "br/min", "hrv_rmssd_ms": "ms",
}
LABELS = {
    "heart_rate": "Heart rate", "spo2": "SpO₂", "systolic": "Systolic BP", "diastolic": "Diastolic BP",
    "temperature_c": "Temperature", "respiratory_rate": "Respiratory rate", "hrv_rmssd_ms": "HRV (RMSSD)",
}
DECIMALS = {"temperature_c": 2, "spo2": 2}
# "Awake at rest" = rest or desk work, no test scenario running: comparable from day to day.
AWAKE_REST_STATES = ("rest", "work")
STATISTICS = ("mean", "awake_rest_mean", "sleep_mean", "p05", "p95")


def _r(metric: str, v: float | None) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), DECIMALS.get(metric, 1)) + 0.0  # + 0.0 turns -0.0 into 0.0


def frame(rows: list[tuple] | list[dict], columns: tuple[str, ...]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(columns)) if rows and not isinstance(rows[0], dict) else pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=list(columns))
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts")


def sample_interval_s(df: pd.DataFrame) -> float | None:
    if len(df) < 2:
        return None
    diffs = df["ts"].diff().dt.total_seconds().dropna()
    diffs = diffs[diffs > 0]
    return float(diffs.median()) if len(diffs) else None


def summarize_metrics(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if df.empty:
        return out
    quiet = df["scenario"].isna() if "scenario" in df else pd.Series(True, index=df.index)
    awake = df["activity_state"].isin(AWAKE_REST_STATES) & quiet
    asleep = (df["activity_state"] == "sleep") & quiet
    for m in METRICS:
        if m not in df:
            continue
        s = pd.to_numeric(df[m], errors="coerce").dropna()
        if s.empty:
            continue
        aw = pd.to_numeric(df.loc[awake, m], errors="coerce").dropna()
        sl = pd.to_numeric(df.loc[asleep, m], errors="coerce").dropna()
        out[m] = {
            "n": int(s.size),
            "mean": _r(m, s.mean()),
            "sd": _r(m, s.std(ddof=1)) if s.size > 1 else None,
            "min": _r(m, s.min()),
            "p05": _r(m, s.quantile(0.05)),
            "p50": _r(m, s.median()),
            "p95": _r(m, s.quantile(0.95)),
            "max": _r(m, s.max()),
            "awake_rest_mean": _r(m, aw.mean()) if aw.size else None,
            "awake_rest_n": int(aw.size),
            "sleep_mean": _r(m, sl.mean()) if sl.size else None,
            "sleep_n": int(sl.size),
        }
    return out


def summarize_activity(df: pd.DataFrame, interval_s: float | None) -> dict[str, Any]:
    if df.empty or not interval_s:
        return {}
    minutes = (df["activity_state"].value_counts() * interval_s / 60).round(0)
    scenario_minutes = float(df["scenario"].notna().sum() * interval_s / 60) if "scenario" in df else 0.0
    irregular = float((df["rhythm"] == "irregular").sum() * interval_s / 60) if "rhythm" in df else 0.0
    return {
        "minutes_by_state": {k: int(v) for k, v in minutes.items()},
        "exercise_minutes": int(minutes.get("exercise", 0)),
        "mean_met": round(float(pd.to_numeric(df["activity_met"], errors="coerce").mean()), 2),
        "scenario_minutes": int(round(scenario_minutes)),
        "irregular_rhythm_minutes": int(round(irregular)),
    }


def coverage(df: pd.DataFrame, interval_s: float | None, day_seconds: float = 86400.0) -> dict[str, Any]:
    if df.empty:
        return {"samples": 0, "interval_s": None, "hours_covered": 0, "completeness": 0.0}
    hours = int(df["ts"].dt.floor("h").nunique())
    completeness = min(1.0, len(df) * (interval_s or 0) / day_seconds) if interval_s else 0.0
    return {
        "samples": int(len(df)),
        "interval_s": round(interval_s, 1) if interval_s else None,
        "hours_covered": hours,
        "completeness": round(completeness, 3),
    }


def series_trend(days: list[int], values: list[float | None]) -> dict[str, Any] | None:
    """OLS slope per 30 days with a 95% CI whose degrees of freedom shrink for autocorrelation."""
    from scipy import stats

    pts = [(d, v) for d, v in zip(days, values) if v is not None]
    if len(pts) < 7:
        return None
    x = np.array([p[0] for p in pts], dtype=float)
    y = np.array([p[1] for p in pts], dtype=float)
    if np.ptp(y) == 0:
        return {"slope_per_30d": 0.0, "ci95": [0.0, 0.0], "n_days": len(pts), "n_eff": float(len(pts)),
                "direction": "flat"}
    fit = stats.linregress(x, y)
    resid = y - (fit.intercept + fit.slope * x)
    r1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 3 else 0.0
    r1 = 0.0 if math.isnan(r1) else max(-0.99, min(0.99, r1))
    n_eff = min(float(len(pts)), max(3.0, len(pts) * (1 - r1) / (1 + r1)))
    se = fit.stderr * math.sqrt(max(1.0, (len(pts) - 2) / max(1.0, n_eff - 2)))
    t = stats.t.ppf(0.975, max(1.0, n_eff - 2))
    lo, hi = (fit.slope - t * se) * 30, (fit.slope + t * se) * 30
    direction = "no clear trend" if lo <= 0 <= hi else ("rising" if fit.slope > 0 else "falling")
    return {
        "slope_per_30d": round(fit.slope * 30, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "n_days": len(pts),
        "n_eff": round(n_eff, 1),
        "direction": direction,
    }
