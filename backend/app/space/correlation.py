"""Exploratory environment-health correlation engine.

Statistics (pure functions, tested in isolation):

* Pearson and Spearman correlation on pairwise-complete daily values.
* Effective sample size for autocorrelated series (Bretherton et al. 1999,
  n_eff = n (1 - r1x r1y) / (1 + r1x r1y)); p-values and Fisher-z intervals use n_eff.
* Trend-adjusted (partial) correlation, controlling for a linear time trend: a shared trend
  (solar cycle phase, mission phase) is a common confounder.
* Time-lagged correlation over -L..L days, with Benjamini-Hochberg FDR control across lags.
* Rolling correlation, and cross-correlation of first-differenced series (a light pre-whitening).

Correlation does not establish causation, and every result says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AstronautRow,
    EnvMeasurementRow,
    EnvMissionRow,
    RadiationDoseRow,
    SleepSessionRow,
    SpaceWeatherEventRow,
    VitalSampleRow,
)
from app.space import repository as repo
from app.space.eda import QUANTITY_LABELS

MIN_PAIRS = 5
CAUSATION = "Correlation does not establish causation."


# ============================================================================ statistics ==
def lag1_autocorr(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 4 or np.std(x) == 0:
        return 0.0
    r = np.corrcoef(x[:-1], x[1:])[0, 1]
    return float(r) if np.isfinite(r) else 0.0


def effective_n(n: int, r1x: float, r1y: float) -> float:
    prod = max(-0.95, min(0.95, r1x * r1y))
    return float(max(3.0, min(n, n * (1 - prod) / (1 + prod))))


def p_from_r(r: float, n_eff: float) -> float:
    if not np.isfinite(r) or n_eff <= 2:
        return float("nan")
    if abs(r) >= 1:
        return 0.0
    t = r * math.sqrt((n_eff - 2) / (1 - r * r))
    return float(2 * stats.t.sf(abs(t), df=n_eff - 2))


def fisher_ci(r: float, n_eff: float, level: float = 0.95) -> tuple[float, float]:
    if not np.isfinite(r) or n_eff <= 3:
        return (float("nan"), float("nan"))
    z = math.atanh(max(-0.999999, min(0.999999, r)))
    se = 1 / math.sqrt(n_eff - 3)
    k = stats.norm.ppf(0.5 + level / 2)
    return (math.tanh(z - k * se), math.tanh(z + k * se))


def bh_adjust(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values (NaN stays NaN)."""
    idx = [i for i, p in enumerate(pvalues) if p is not None and np.isfinite(p)]
    q = [float("nan")] * len(pvalues)
    if not idx:
        return q
    m = len(idx)
    order = sorted(idx, key=lambda i: pvalues[i])
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = min(1.0, running)
    return q


def strength(r: float | None) -> str:
    if r is None or not np.isfinite(r):
        return "undefined"
    a = abs(r)
    return "negligible" if a < 0.1 else "weak" if a < 0.3 else "moderate" if a < 0.5 else "strong"


def _pair(x: pd.Series, y: pd.Series) -> pd.DataFrame:
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1)
    return df.dropna()


def correlate(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    """Pearson + Spearman on pairwise-complete values, with autocorrelation-aware inference."""
    d = _pair(x, y)
    n = len(d)
    out: dict[str, Any] = {"n": n}
    if n < MIN_PAIRS or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        out.update(pearson=None, spearman=None, n_eff=None, reason="too few pairs or a constant series")
        return out
    xa, ya = d["x"].to_numpy(float), d["y"].to_numpy(float)
    r1x, r1y = lag1_autocorr(x.to_numpy(float)), lag1_autocorr(y.to_numpy(float))
    n_eff = effective_n(n, r1x, r1y)
    pr = float(stats.pearsonr(xa, ya)[0])
    sr = float(stats.spearmanr(xa, ya)[0])
    lo, hi = fisher_ci(pr, n_eff)
    slo, shi = fisher_ci(sr, n_eff)
    out.update(
        n_eff=round(n_eff, 1), lag1_autocorr_x=round(r1x, 3), lag1_autocorr_y=round(r1y, 3),
        pearson={"r": round(pr, 4), "p": p_from_r(pr, n_eff), "ci": [round(lo, 4), round(hi, 4)]},
        spearman={"r": round(sr, 4), "p": p_from_r(sr, n_eff), "ci": [round(slo, 4), round(shi, 4)]},
    )
    return out


def detrended(s: pd.Series) -> pd.Series:
    v = s.dropna()
    if len(v) < 3:
        return s * np.nan
    t = (v.index - v.index[0]).days.to_numpy(float) if isinstance(v.index, pd.DatetimeIndex) else np.arange(len(v), dtype=float)
    slope, intercept = np.polyfit(t, v.to_numpy(float), 1)
    resid = v - (slope * t + intercept)
    return resid.reindex(s.index)


def trend_adjusted(x: pd.Series, y: pd.Series) -> dict[str, Any] | None:
    d = _pair(x, y)
    if len(d) < MIN_PAIRS + 1:
        return None
    rx, ry = detrended(d["x"]), detrended(d["y"])
    if rx.std() == 0 or ry.std() == 0:
        return None
    r = float(np.corrcoef(rx, ry)[0, 1])
    n_eff = effective_n(len(d), lag1_autocorr(rx.to_numpy(float)), lag1_autocorr(ry.to_numpy(float)))
    return {"r": round(r, 4), "p": p_from_r(r, max(3.0, n_eff - 1)), "n_eff": round(n_eff, 1)}


def lagged(x: pd.Series, y: pd.Series, max_lag: int) -> list[dict[str, Any]]:
    """corr(x_t, y_{t+k}); k > 0 means y follows x by k days."""
    rows = []
    for k in range(-max_lag, max_lag + 1):
        ys = y.shift(-k)
        c = correlate(x, ys)
        p = c["pearson"]["p"] if c.get("pearson") else float("nan")
        rows.append({"lag_days": k, "n": c["n"], "r": c["pearson"]["r"] if c.get("pearson") else None,
                     "spearman": c["spearman"]["r"] if c.get("spearman") else None, "p": p})
    q = bh_adjust([r["p"] for r in rows])
    for r, qq in zip(rows, q):
        r["q"] = qq
    return rows


def rolling(x: pd.Series, y: pd.Series, window: int) -> list[dict[str, Any]]:
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1)
    rc = df["x"].rolling(window, min_periods=max(MIN_PAIRS, int(window * 0.7))).corr(df["y"])
    return [{"ts": ts, "r": round(float(v), 4)} for ts, v in rc.items() if np.isfinite(v)]


def cross_correlation(x: pd.Series, y: pd.Series, max_lag: int) -> list[dict[str, Any]]:
    """Lagged correlation of day-to-day changes; removes slow trends that inflate raw lags."""
    return [{"lag_days": r["lag_days"], "r": r["r"], "n": r["n"]} for r in lagged(x.diff(), y.diff(), max_lag)]


# ============================================================================== series ====
@dataclass(frozen=True)
class SeriesDef:
    id: str
    label: str
    unit: str
    category: str  # indicator | measured | simulated | estimate
    group: str
    description: str


def _daily_index(start: date, end: date) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="D")


def _day_expr(col, dialect: str):
    # SQLite stores naive UTC text; PostgreSQL TIMESTAMPTZ must be converted to UTC before taking the date.
    return func.date(col) if dialect == "sqlite" else func.date(func.timezone("UTC", col))


SWX_SERIES = {
    "swx:flare_count": ("Solar flares per day", "count", "FLR"),
    "swx:flare_max_log_flux": ("Strongest flare of the day (log10 peak X-ray flux)", "log10 W/m²", "FLR"),
    "swx:cme_count": ("CMEs per day", "count", "CME"),
    "swx:cme_max_speed": ("Fastest CME of the day", "km/s", "CME"),
    "swx:storm_level": ("Geomagnetic storm level (NOAA G, 0 = no storm reported)", "G level", "GST"),
    "swx:sep": ("Solar energetic particle event reported (0/1)", "0/1", "SEP"),
    "swx:rbe": ("Radiation belt enhancement reported (0/1)", "0/1", "RBE"),
}
CREW_SERIES = {
    "hr_mean": ("Mean heart rate", "bpm"),
    "hr_sleep": ("Mean heart rate during sleep", "bpm"),
    "spo2_mean": ("Mean SpO₂", "%"),
    "sleep_hours": ("Sleep duration (night ending that day)", "h"),
    "dose_msv": ("Simulated daily dose", "mSv/day"),
}
ISS_QUANTITIES = ("dose_total_mgy_day", "dose_gcr_mgy_day", "dose_saa_mgy_day", "temperature_c", "humidity_pct", "co2_ppm")


async def catalogue(session: AsyncSession) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    first, last = (await session.execute(select(func.min(SpaceWeatherEventRow.start_time),
                                                func.max(SpaceWeatherEventRow.start_time)))).one()
    for sid, (label, unit, etype) in SWX_SERIES.items():
        cov = await repo.donki_coverage(session, etype)
        out.append({"id": sid, "label": label, "unit": unit, "category": "indicator", "group": "Space weather (NASA DONKI)",
                    "description": f"Daily values from DONKI {etype} records; only days inside successfully queried ranges are used.",
                    "coverage": [{"start": a, "end": b} for a, b in _merge_ranges(cov)]})
    for a in (await session.scalars(select(AstronautRow).order_by(AstronautRow.id))).all():
        for key, (label, unit) in CREW_SERIES.items():
            out.append({"id": f"crew:{a.id}:{key}", "label": f"{a.name}: {label}", "unit": unit, "category": "simulated",
                        "group": f"Crew {a.id} (simulated)", "description": "Daily aggregate of simulated data.",
                        "coverage": []})
    out.append({"id": "mission:day", "label": "Mission day", "unit": "day", "category": "simulated", "group": "Mission",
                "description": "Days since the fictional mission start.", "coverage": []})
    for m in (await session.scalars(select(EnvMissionRow).where(EnvMissionRow.start_time.is_not(None))
                                    .order_by(EnvMissionRow.start_time))).all():
        for q in ISS_QUANTITIES:
            out.append({"id": f"iss:{m.name}:{q}", "label": f"{m.name}: {QUANTITY_LABELS[q]} (ISS)",
                        "unit": "mGy/day" if q.startswith("dose") else {"temperature_c": "°C", "humidity_pct": "%", "co2_ppm": "ppm"}[q],
                        "category": "measured", "group": f"ISS mission {m.name} ({m.start_time:%Y})",
                        "description": "Daily mean of EDA measurements (historical).",
                        "coverage": [{"start": m.start_time.date().isoformat(), "end": (m.end_time or m.start_time).date().isoformat()}]})
    return out


def _merge_ranges(ranges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[list[date]] = []
    for a, b in sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in ranges):
        if merged and a <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a.isoformat(), b.isoformat()) for a, b in merged]


def _covered_mask(index: pd.DatetimeIndex, ranges: list[tuple[str, str]]) -> np.ndarray:
    mask = np.zeros(len(index), dtype=bool)
    days = index.date
    for a, b in ranges:
        da, db = date.fromisoformat(a), date.fromisoformat(b)
        mask |= (days >= da) & (days <= db)
    return mask


async def load_series(session: AsyncSession, series_id: str, start: date, end: date,
                      mission_start: date | None = None) -> tuple[pd.Series, dict[str, Any]]:
    """Daily series on [start, end] (UTC days); NaN where no observation exists."""
    idx = _daily_index(start, end)
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    meta: dict[str, Any] = {"id": series_id}

    if series_id in SWX_SERIES:
        label, unit, etype = SWX_SERIES[series_id]
        meta.update(label=label, unit=unit, category="indicator")
        lo = datetime.combine(start, time(0), tzinfo=UTC)
        hi = datetime.combine(end + timedelta(days=1), time(0), tzinfo=UTC)
        events = (await session.scalars(select(SpaceWeatherEventRow).where(
            SpaceWeatherEventRow.event_type == etype, SpaceWeatherEventRow.start_time >= lo,
            SpaceWeatherEventRow.start_time < hi))).all()
        frame = pd.DataFrame([{"day": pd.Timestamp((e.peak_time or e.start_time).date(), tz="UTC"),
                               "mag": e.magnitude, "sev": e.severity} for e in events])
        s = pd.Series(np.nan, index=idx)
        if series_id.endswith(("_count", "sep", "rbe")):
            counts = frame.groupby("day").size() if len(frame) else pd.Series(dtype=float)
            s = counts.reindex(idx).fillna(0.0).astype(float)
            if series_id in ("swx:sep", "swx:rbe"):
                s = (s > 0).astype(float)
        elif series_id == "swx:storm_level":
            lv = frame.groupby("day")["sev"].max() if len(frame) else pd.Series(dtype=float)
            s = lv.reindex(idx).fillna(0.0).astype(float)
        else:
            mags = frame.dropna(subset=["mag"]).groupby("day")["mag"].max() if len(frame) else pd.Series(dtype=float)
            s = mags.reindex(idx).astype(float)
            if series_id == "swx:flare_max_log_flux":
                s = np.log10(s)
        cov = _merge_ranges(await repo.donki_coverage(session, etype))
        s[~_covered_mask(idx, cov)] = np.nan  # never assume "no event" on days nobody checked
        meta["coverage"] = cov
        return s, meta

    if series_id == "mission:day":
        meta.update(label="Mission day", unit="day", category="simulated")
        base = pd.Timestamp(mission_start or start, tz="UTC")
        return pd.Series(((idx - base).days).astype(float), index=idx), meta

    if series_id.startswith("crew:"):
        _, aid, key = series_id.split(":", 2)
        label, unit = CREW_SERIES[key]
        meta.update(label=f"{aid}: {label}", unit=unit, category="simulated")
        lo = datetime.combine(start, time(0), tzinfo=UTC)
        hi = datetime.combine(end + timedelta(days=1), time(0), tzinfo=UTC)
        if key in ("hr_mean", "spo2_mean", "hr_sleep"):
            col = VitalSampleRow.heart_rate if key != "spo2_mean" else VitalSampleRow.spo2
            day = _day_expr(VitalSampleRow.ts, dialect)
            cond = [VitalSampleRow.astronaut_id == aid, VitalSampleRow.ts >= lo, VitalSampleRow.ts < hi]
            if key == "hr_sleep":
                cond.append(VitalSampleRow.activity_state == "sleep")
            rows = (await session.execute(select(day, func.avg(col)).where(and_(*cond)).group_by(day))).all()
            data = {pd.Timestamp(str(d), tz="UTC"): float(v) for d, v in rows if v is not None}
        elif key == "sleep_hours":
            rows = (await session.scalars(select(SleepSessionRow).where(
                SleepSessionRow.astronaut_id == aid, SleepSessionRow.end >= lo, SleepSessionRow.end < hi))).all()
            data = {pd.Timestamp(r.end.date(), tz="UTC"): float(r.duration_hours) for r in rows}
        else:
            rows = (await session.scalars(select(RadiationDoseRow).where(
                RadiationDoseRow.astronaut_id == aid, RadiationDoseRow.day >= start, RadiationDoseRow.day <= end))).all()
            data = {pd.Timestamp(r.day, tz="UTC"): float(r.dose_msv) for r in rows}
        return pd.Series(data, dtype=float).reindex(idx), meta

    if series_id.startswith("iss:"):
        _, mission, quantity = series_id.split(":", 2)
        meta.update(label=f"{mission}: {QUANTITY_LABELS.get(quantity, quantity)} (ISS)", category="measured")
        rows = (await session.scalars(select(EnvMeasurementRow).where(
            EnvMeasurementRow.mission == mission, EnvMeasurementRow.quantity == quantity,
            EnvMeasurementRow.platform == "iss"))).all()
        meta["unit"] = rows[0].unit if rows else ""
        frame = pd.DataFrame([{"day": pd.Timestamp(r.ts.date(), tz="UTC"), "v": r.value} for r in rows if not r.approximate])
        s = frame.groupby("day")["v"].mean() if len(frame) else pd.Series(dtype=float)
        return s.reindex(idx).astype(float), meta

    raise KeyError(series_id)


def _provenance_warnings(mx: dict[str, Any], my: dict[str, Any]) -> list[str]:
    cats = {mx.get("category"), my.get("category")}
    out = []
    if "simulated" in cats and cats & {"indicator", "measured"}:
        out.append("One series is simulated. The ASTRA-MED simulator uses no NASA space-weather or ISS data, so no "
                   "physical relationship can exist; any correlation here is coincidental by construction.")
    if cats == {"simulated"}:
        out.append("Both series are simulated: a correlation reflects how the simulator was written, not physiology.")
    return out


async def analyze(session: AsyncSession, x_id: str, y_id: str, start: date, end: date, max_lag: int = 3,
                  rolling_window: int = 14, mission_start: date | None = None) -> dict[str, Any]:
    x, mx = await load_series(session, x_id, start, end, mission_start)
    y, my = await load_series(session, y_id, start, end, mission_start)
    warnings = _provenance_warnings(mx, my)
    base = correlate(x, y)
    n = base["n"]
    result: dict[str, Any] = {
        "x": mx | {"observations": int(x.notna().sum())}, "y": my | {"observations": int(y.notna().sum())},
        "start": start, "end": end, "n": n, "status": "ok",
    }
    if n < MIN_PAIRS:
        result.update(status="insufficient", warnings=warnings + [
            f"Only {n} days have both values (at least {MIN_PAIRS} needed). Check that the two series overlap in time."],
            interpretation=f"Not enough overlapping observations to estimate a correlation. {CAUSATION}")
        return result
    if n < 20:
        warnings.append(f"Small sample ({n} days): estimates are unstable and intervals are wide.")
    if base.get("n_eff") and base["n_eff"] < 0.7 * n:
        warnings.append(f"Both series are autocorrelated; the effective sample size is about {base['n_eff']:.0f} of {n} days.")
    for s, m in ((x, mx), (y, my)):
        if s.dropna().nunique() <= 2:
            warnings.append(f"{m.get('label')} takes only two values (event / no event); Pearson r is then a point-biserial correlation.")
    lags = lagged(x, y, max_lag)
    sig_lags = [r for r in lags if r["q"] is not None and np.isfinite(r["q"]) and r["q"] < 0.05]
    tests = len([r for r in lags if r["p"] is not None and np.isfinite(r["p"])])
    warnings.append(f"{tests} lagged tests were run; q-values control the false discovery rate across them (Benjamini-Hochberg).")
    warnings.append("Possible confounders not controlled here: solar-cycle phase, season, mission phase and schedule changes. "
                    "The trend-adjusted correlation removes only a linear time trend.")
    result.update(
        **{k: base[k] for k in ("pearson", "spearman", "n_eff", "lag1_autocorr_x", "lag1_autocorr_y") if k in base},
        trend_adjusted=trend_adjusted(x, y),
        lags=lags,
        cross_correlation=cross_correlation(x, y, max_lag),
        rolling=rolling(x, y, rolling_window),
        rolling_window=rolling_window,
        scatter=[{"ts": ts, "x": float(a), "y": float(b)} for ts, a, b in _pair(x, y).itertuples()],
        warnings=warnings,
    )
    r = base["pearson"]["r"] if base.get("pearson") else None
    p = base["pearson"]["p"] if base.get("pearson") else None
    lag0_q = next((row["q"] for row in lags if row["lag_days"] == 0), None)
    sig = lag0_q is not None and np.isfinite(lag0_q) and lag0_q < 0.05
    text = (f"The same-day estimate is {strength(r)} in size (Pearson r = {r:+.2f}, Spearman rho = {base['spearman']['r']:+.2f}, "
            f"n = {n}, effective n ≈ {base['n_eff']:.0f}, p = {p:.3g}). ")
    text += ("It stays below the 5% false-discovery threshold after correction. " if sig
             else "It is not statistically distinguishable from zero after correction, so this is no evidence of an association. ")
    if sig_lags:
        text += "Lags with q < 0.05: " + ", ".join(f"{row['lag_days']:+d} d (r = {row['r']:+.2f})" for row in sig_lags[:4]) + ". "
    text += CAUSATION
    if any("coincidental" in w for w in warnings):
        text += " Here, because one series is simulated, any apparent association cannot be physical."
    result["interpretation"] = text
    return result


async def matrix(session: AsyncSession, ids: list[str], start: date, end: date,
                 mission_start: date | None = None, method: str = "spearman") -> dict[str, Any]:
    series, metas = [], []
    for sid in ids:
        s, m = await load_series(session, sid, start, end, mission_start)
        series.append(s)
        metas.append(m | {"observations": int(s.notna().sum())})
    cells, pvals = [], []
    for i in range(len(ids)):
        for j in range(len(ids)):
            if i == j:
                cells.append({"i": i, "j": j, "r": 1.0, "n": int(series[i].notna().sum()), "p": None, "q": None})
                continue
            c = correlate(series[i], series[j])
            stat = c.get(method)
            cells.append({"i": i, "j": j, "r": stat["r"] if stat else None, "n": c["n"],
                          "p": stat["p"] if stat else None, "q": None})
            if i < j:
                pvals.append((len(cells) - 1, stat["p"] if stat else float("nan")))
    qs = bh_adjust([p for _, p in pvals])
    q_by_pair = {}
    for (cell_index, _), q in zip(pvals, qs):
        c = cells[cell_index]
        q_by_pair[(c["i"], c["j"])] = q
    for c in cells:
        if c["i"] != c["j"]:
            c["q"] = q_by_pair.get((min(c["i"], c["j"]), max(c["i"], c["j"])))
    warnings = [f"{len(pvals)} pairwise tests; q-values are Benjamini-Hochberg adjusted across the matrix.", CAUSATION]
    if any(m.get("category") == "simulated" for m in metas) and any(m.get("category") in ("indicator", "measured") for m in metas):
        warnings.insert(0, "The matrix mixes simulated and real series; correlations between them are coincidental by construction.")
    return {"series": metas, "method": method, "start": start, "end": end, "cells": cells, "warnings": warnings}
