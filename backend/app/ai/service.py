"""AI intelligence service: serves baselines, anomaly detection, forecasts, risk and explanations.

Live baselines are fitted per crew member from *stored* history (robust statistics) and updated
incrementally as new windows arrive. Trained models come from the latest registered, hash-verified
version. CPU-heavy work runs in worker threads so the 1 Hz monitoring loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.anomaly.detectors import TORCH_AVAILABLE, Detector, Ensemble, load_detectors
from app.ai.baseline import PersonalBaseline, rolling_stats
from app.ai.explain import (
    KIND_TEXT,
    SYNTHETIC_CAVEAT,
    Contributor,
    Explanation,
    anomaly_kind,
    build_contributors,
    confidence,
    data_limitations,
    describe_contributors,
    onset_kind,
    signal_shares,
    significance,
)
from app.ai.features import ALL_GROUPS, build_features
from app.ai.forecasting.data import HORIZON, LOOKBACK, STEP_MINUTES, SampleSet, SeriesArrays, to_steps
from app.ai.forecasting.models import (
    Climatology,
    Forecaster,
    Persistence,
    SeasonalNaive,
    SequenceForecaster,
    XGBoostForecaster,
    xgb_feature_group,
)
from app.ai.registry import ModelRegistry
from app.ai.risk import AnomalyState, ForecastState, RiskConfig, RiskInputs, SignalState, assess
from app.ai.signals import FORECAST_SIGNALS, LABELS, SIGNALS, UNITS, WINDOW_MINUTES
from app.ai.timeline import planned_steps
from app.ai.windows import drop_implausible, samples_to_frame, to_windows
from app.core.config import Settings
from app.core.errors import ApiError, InsufficientDataError, NotFoundError, ServiceUnavailableError
from app.core.timeutil import as_utc, utcnow
from app.detection.rules import THRESHOLD_RULES
from app.repositories import alerts as alerts_repo
from app.repositories import vitals as vitals_repo
from app.simulator.profiles import CREW_BY_ID

logger = logging.getLogger("astra.ai")

WARMUP = timedelta(hours=6)  # history fed to causal rolling features before an analysis window
REFIT_AFTER = timedelta(hours=6)
UPDATE_AFTER = timedelta(seconds=60)
PERSISTENCE_WINDOWS = 2
MAX_RANGE = timedelta(days=7)
SAMPLE_COLUMNS = (*SIGNALS, "activity_state", "activity_met")


class ValidationError422(ApiError):
    status_code = 422
    code = "validation_error"


# ------------------------------------------------------------------ model bundle ----
@dataclass
class ModelBundle:
    version: str
    manifest: dict[str, Any]
    detectors: dict[str, Detector]
    ensemble: Ensemble
    forecasters: dict[str, Forecaster]
    conformal: dict[str, np.ndarray]
    results: dict[str, Any]
    serving: str
    report: str | None

    @classmethod
    def load(cls, root: Path) -> ModelBundle | None:
        registry = ModelRegistry(root)
        version = registry.latest()
        if not version:
            return None
        path = registry.verify(version)  # refuses tampered or missing artifacts before unpickling
        detectors, ensemble = load_detectors(path / "anomaly")
        fdir = path / "forecast"
        fmeta = json.loads((fdir / "forecast.json").read_text())
        forecasters: dict[str, Forecaster] = {}
        for name in fmeta["models"]:
            if name == "xgboost":
                forecasters[name] = XGBoostForecaster.load(fdir)
            elif name in ("lstm", "gru", "tcn"):
                if TORCH_AVAILABLE and (fdir / f"{name}.pt").exists():
                    forecasters[name] = SequenceForecaster.load(fdir, name)
            else:
                forecasters[name] = {"persistence": Persistence, "seasonal_naive": SeasonalNaive,
                                     "climatology": Climatology}[name]()
        conformal = {k: np.asarray(v, dtype=np.float32) for k, v in json.loads((fdir / "conformal.json").read_text()).items()}
        results = json.loads((path / "results.json").read_text())
        report = (path / "report.md").read_text(encoding="utf-8") if (path / "report.md").exists() else None
        return cls(version, registry.manifest(version), detectors, ensemble, forecasters, conformal, results,
                   fmeta.get("serving", "xgboost"), report)


@dataclass
class _BaselineEntry:
    baseline: PersonalBaseline
    fitted_at: datetime
    updated_at: datetime
    last_window: pd.Timestamp | None
    windows_used: int


@dataclass
class Analysis:
    """Scored windows for one crew member (output of _analyse)."""

    windows: pd.DataFrame
    features: pd.DataFrame
    zscores: pd.DataFrame
    matrix: np.ndarray  # (n, detectors) calibrated scores
    score: np.ndarray  # ensemble score / threshold
    flagged: np.ndarray
    votes: np.ndarray
    detectors: list[str]
    weights: dict[str, float]


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class AIService:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession], monitor) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.monitor = monitor
        self.risk_config = RiskConfig.load()
        self._bundle: ModelBundle | None = None
        self._bundle_error: str | None = None
        self._bundle_loaded = False
        self._bundle_lock = asyncio.Lock()
        self._baselines: dict[str, _BaselineEntry] = {}
        self._baseline_locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[tuple, tuple[float, Any]] = {}

    # ------------------------------------------------------------------ models ----
    async def bundle(self) -> ModelBundle | None:
        if self._bundle_loaded:
            return self._bundle
        async with self._bundle_lock:
            if not self._bundle_loaded:
                try:
                    self._bundle = await asyncio.to_thread(ModelBundle.load, self.settings.ai_artifacts_path)
                    if self._bundle:
                        logger.info("AI models loaded: %s", self._bundle.version)
                    else:
                        logger.warning("no AI model version registered; run: python -m app.ai.train")
                except Exception as exc:  # integrity or deserialisation failure
                    self._bundle_error = f"{type(exc).__name__}: {exc}"
                    logger.exception("could not load AI models")
                self._bundle_loaded = True
        return self._bundle

    async def reload(self) -> ModelBundle | None:
        async with self._bundle_lock:
            self._bundle_loaded, self._bundle, self._bundle_error = False, None, None
            self._cache.clear()
        return await self.bundle()

    async def require_bundle(self) -> ModelBundle:
        bundle = await self.bundle()
        if bundle is None:
            reason = self._bundle_error or "No trained AI model version is registered."
            raise ServiceUnavailableError(f"{reason} Train one with: python -m app.ai.train")
        return bundle

    async def status(self) -> dict[str, Any]:
        bundle = await self.bundle()
        return {
            "enabled": self.settings.ai_enabled,
            "model_version": bundle.version if bundle else None,
            "loaded": bundle is not None,
            "error": self._bundle_error,
            "detectors": list(bundle.detectors) if bundle else [],
            "forecasters": list(bundle.forecasters) if bundle else [],
            "serving_forecaster": bundle.serving if bundle else None,
            "torch_available": TORCH_AVAILABLE,
        }

    # -------------------------------------------------------------------- cache ----
    async def _cached(self, key: tuple, factory):
        ttl = self.settings.ai_cache_seconds
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        value = await factory()
        if ttl > 0:
            self._cache[key] = (time.monotonic() + ttl, value)
        return value

    # --------------------------------------------------------------------- data ----
    def _require_astronaut(self, astronaut_id: str) -> None:
        if astronaut_id not in CREW_BY_ID:
            raise NotFoundError(f"Astronaut {astronaut_id} not found.")

    async def _samples(self, astronaut_id: str, start: datetime, end: datetime) -> pd.DataFrame:
        async with self.session_factory() as session:
            rows = await vitals_repo.fetch_range(session, astronaut_id, start, end, columns=SAMPLE_COLUMNS)
        return samples_to_frame([{"ts": r[0], **dict(zip(SAMPLE_COLUMNS, r[1:]))} for r in rows])

    @staticmethod
    def _regular(windows: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
        """Reindex onto every window in [start, end) so data gaps show up as missing windows."""
        start, end = as_utc(start), as_utc(end)  # request datetimes may carry pydantic's own tzinfo
        idx = pd.date_range(pd.Timestamp(start).floor(f"{WINDOW_MINUTES}min"), pd.Timestamp(end),
                            freq=f"{WINDOW_MINUTES}min", tz="UTC", name="ts", inclusive="left")
        out = windows.reindex(idx) if len(windows) else pd.DataFrame(index=idx, columns=windows.columns)
        out["n_samples"] = out["n_samples"].fillna(0).astype(int)
        for col in ("sleep_frac", "exercise_frac"):
            out[col] = out[col].astype(float)
        return out

    async def windows(self, astronaut_id: str, start: datetime, end: datetime) -> pd.DataFrame:
        samples = await self._samples(astronaut_id, start, end)
        return self._regular(to_windows(samples), start, end)

    async def baseline(self, astronaut_id: str) -> _BaselineEntry:
        self._require_astronaut(astronaut_id)
        lock = self._baseline_locks.setdefault(astronaut_id, asyncio.Lock())
        async with lock:
            now = utcnow()
            current = pd.Timestamp(now).floor(f"{WINDOW_MINUTES}min")  # exclude the partial window
            entry = self._baselines.get(astronaut_id)
            if entry is None or now - entry.fitted_at > REFIT_AFTER:
                samples = await self._samples(astronaut_id, now - timedelta(hours=self.settings.ai_history_hours), now)
                w = to_windows(samples)
                w = w[w.index < current]
                if w[list(SIGNALS)].notna().sum().sum() == 0:
                    raise InsufficientDataError(f"No stored measurements for {astronaut_id} yet.")
                baseline = await asyncio.to_thread(PersonalBaseline.fit, astronaut_id, w, self.settings.simulator_seed)
                entry = _BaselineEntry(baseline, now, now, w.index.max(), len(w))
                self._baselines[astronaut_id] = entry
            elif now - entry.updated_at > UPDATE_AFTER and entry.last_window is not None:
                since = entry.last_window + pd.Timedelta(minutes=WINDOW_MINUTES)
                samples = await self._samples(astronaut_id, since.to_pydatetime(), now)
                w = to_windows(samples)
                w = w[(w.index >= since) & (w.index < current)]
                if len(w):
                    await asyncio.to_thread(entry.baseline.update, w)
                    entry.last_window, entry.windows_used = w.index.max(), entry.windows_used + len(w)
                entry.updated_at = now
            return entry

    # ----------------------------------------------------------------- baseline ----
    async def baseline_report(self, astronaut_id: str) -> dict[str, Any]:
        entry = await self.baseline(astronaut_id)
        now = utcnow()
        w7 = await self.windows(astronaut_id, now - timedelta(days=7), now)
        return await asyncio.to_thread(self._baseline_report, astronaut_id, entry, w7)

    def _baseline_report(self, astronaut_id: str, entry: _BaselineEntry, w7: pd.DataFrame) -> dict[str, Any]:
        b = entry.baseline
        r24, r7 = rolling_stats(w7, 24), rolling_stats(w7, 24 * 7)
        signals = []
        levels: dict[str, str] = {}
        for s in SIGNALS:
            prof = b.profile(s)
            current = None
            recent = w7[s].dropna()
            if len(recent):
                ts = recent.index[-1]
                state = w7.loc[ts, "state"] if isinstance(w7.loc[ts, "state"], str) else "work"
                ref = b.reference(s, state, ts)
                levels[s] = ref.basis
                value = float(recent.iloc[-1])
                z = ref.z_or_none(value)
                pct = ref.percentile_or_none(value)
                current = {
                    "ts": ts.to_pydatetime(), "value": round(value, 2), "state": state,
                    "expected": round(ref.center, 2) if ref.comparable else None,
                    "z": None if z is None else round(z, 2),
                    "percentile": None if pct is None else round(pct, 1), "reference_level": ref.basis,
                    "assessment": ("no_baseline" if z is None else "high" if z >= 2 else "low" if z <= -2 else "within"),
                }
            signals.append({
                "signal": s, "label": LABELS[s], "unit": UNITS[s],
                "overall": {k: prof.get(k) for k in ("n", "mean", "std", "p5", "p25", "p50", "p75", "p95")},
                "by_state": prof["by_state"],
                "rolling_24h": r24.get(s, {"n": 0}),
                "rolling_7d": r7.get(s, {"n": 0}),
                "current": current,
            })
        hours = ((b.last_ts - b.first_ts).total_seconds() / 3600) if b.first_ts and b.last_ts else 0
        return {
            "astronaut_id": astronaut_id,
            "fitted_at": entry.fitted_at,
            "updated_at": entry.updated_at,
            "history_hours": self.settings.ai_history_hours,
            "windows_used": entry.windows_used,
            "first_ts": b.first_ts,
            "last_ts": b.last_ts,
            "method": (
                "Per signal, per activity state and per 4-hour time-of-day bucket: Welford running mean and "
                "standard deviation, reservoir-sampled percentiles, robust centre (median) and scale (IQR/1.349). "
                "Sparse cells fall back to the activity state, then overall. Updated incrementally as new "
                "5-minute windows arrive; refitted every 6 h."
            ),
            "signals": signals,
            "limitations": data_limitations(float(w7[list(SIGNALS)].isna().mean().mean()), levels, hours),
        }

    # ----------------------------------------------------------------- anomaly ----
    def _analyse(self, bundle: ModelBundle, baseline: PersonalBaseline, windows: pd.DataFrame,
                 detector_names: list[str]) -> Analysis:
        ff = build_features(windows, baseline, ALL_GROUPS)
        dets = {n: bundle.detectors[n] for n in detector_names}
        weights = {n: bundle.ensemble.weights.get(n, 1.0) for n in dets}
        ens = Ensemble(dets, weights)
        matrix = ens.normalised_matrix(ff.features)
        raw = ens.score_from_matrix(matrix)
        votes = (matrix >= 1.0).sum(axis=1)
        full = set(detector_names) == set(bundle.detectors) and bundle.ensemble.threshold
        if full:
            score = raw / bundle.ensemble.threshold
            flagged = score >= 1.0
        else:  # the calibrated ensemble threshold only applies to the full set; use a majority vote
            score = raw
            flagged = votes >= math.ceil(len(dets) / 2)
        return Analysis(windows, ff.features, ff.zscores, matrix, score, flagged, votes, list(dets), weights)

    def _contributions(self, a: Analysis, bundle: ModelBundle, i: int) -> np.ndarray:
        """Weighted per-feature attribution (over the full feature list) for row i."""
        names = list(a.features.columns)
        total = np.zeros(len(names))
        wsum = 0.0
        row = a.features.iloc[[i]]
        for n in a.detectors:
            det = bundle.detectors[n]
            w = a.weights.get(n, 1.0) or 0.0
            if w <= 0:
                continue
            c = det.contributions(det.matrix(row))[0]
            for value, fname in zip(c, det.feature_names):
                total[names.index(fname)] += w * value
            wsum += w
        return total / wsum if wsum else total

    def _refs(self, baseline: PersonalBaseline, windows: pd.DataFrame, ts: pd.Timestamp):
        state = windows.loc[ts, "state"] if isinstance(windows.loc[ts, "state"], str) else "work"
        values = {s: _f(windows.loc[ts, s]) for s in SIGNALS}
        refs = {s: baseline.reference(s, state, ts) for s in SIGNALS}
        return values, refs, state

    @staticmethod
    def _run_start(flagged: np.ndarray, i: int) -> int:
        while i > 0 and flagged[i - 1]:
            i -= 1
        return i

    def _explain_row(self, a: Analysis, bundle: ModelBundle, baseline: PersonalBaseline, i: int,
                     history_hours: float, onset: int | None = None) -> tuple[Explanation, str, list[str]]:
        names = list(a.features.columns)
        contrib = self._contributions(a, bundle, i)
        by_signal, by_group = signal_shares(contrib, names)
        ts = a.features.index[i]
        values, refs, state = self._refs(baseline, a.windows, ts)
        contributors = build_contributors(by_signal, values, refs)
        top = [c.signal for c in contributors[:3]]
        start = self._run_start(a.flagged, i) if onset is None else onset
        kind = onset_kind(a.zscores[top[0]].to_numpy(), start) if top else anomaly_kind(by_group)
        max_z = max((abs(c.z) for c in contributors if c.z is not None), default=0.0)
        missing = float(a.features["missing_frac"].iloc[i])
        support = min(1.0, min((refs[s].n for s in top), default=0) / 200)
        conf = confidence(
            0.5 * (a.votes[i] / len(a.detectors)) + 0.3 * (1 - missing) + 0.2 * support,
            [f"{int(a.votes[i])} of {len(a.detectors)} detectors agree",
             f"{1 - missing:.0%} of signals present in the window",
             f"baseline built from {min((refs[s].n for s in top), default=0)} comparable windows"],
        )
        desc = describe_contributors(contributors)
        explanation = Explanation(
            what_changed=f"{desc[0].upper() + desc[1:]}; the pattern {KIND_TEXT[kind]} (activity: {state}).",
            kind=kind,
            contributors=contributors,
            significance=significance(max_z, contributors[0].percentile if contributors else None),
            confidence=conf,
            limitations=data_limitations(missing, {s: refs[s].basis for s in top}, history_hours),
            method=("Weighted occlusion / reconstruction-error attribution across the ensemble's detectors, "
                    "folded into signals. Kind compares step vs ramp fits to the top signal's personal "
                    "z-scores around the first flagged window."),
        )
        return explanation, kind, top

    async def detect(self, req) -> dict[str, Any]:
        bundle = await self.require_bundle()
        aid = req.astronaut_id
        self._require_astronaut(aid)
        names = req.models or list(bundle.detectors)
        unknown = [n for n in names if n not in bundle.detectors]
        if unknown:
            raise ValidationError422(f"Unknown detector(s): {', '.join(unknown)}. Available: {', '.join(bundle.detectors)}.")
        entry = await self.baseline(aid)
        removed = 0
        if req.readings:
            supplied = samples_to_frame([r.model_dump() for r in req.readings])
            _, removed = drop_implausible(supplied)
            start, end = supplied["ts"].min().to_pydatetime(), supplied["ts"].max().to_pydatetime() + timedelta(minutes=WINDOW_MINUTES)
            if end - start > MAX_RANGE:
                raise ValidationError422("Supplied readings may span at most 7 days.")
            context = await self.windows(aid, start - WARMUP, start)
            sw = to_windows(supplied)
            windows = pd.concat([context[context.index < sw.index.min()], sw])
            windows = self._regular(windows, start - WARMUP, end)
            source = "supplied"
        else:
            end = as_utc(req.end) if req.end else utcnow()
            start = as_utc(req.start) if req.start else end - timedelta(hours=6)
            if end <= start or end - start > MAX_RANGE:
                raise ValidationError422("Use an analysis range between 5 minutes and 7 days (end after start).")
            windows = await self.windows(aid, start - WARMUP, end)
            source = "stored"
        b = entry.baseline
        history_hours = ((b.last_ts - b.first_ts).total_seconds() / 3600) if b.first_ts and b.last_ts else 0.0
        return await asyncio.to_thread(self._detect_sync, bundle, b, windows, names, start, end, source,
                                       req.include_explanations, removed, history_hours, aid)

    def _detect_sync(self, bundle, baseline, windows, names, start, end, source, explain, removed, history_hours, aid):
        a = self._analyse(bundle, baseline, windows, names)
        in_range = (a.features.index >= pd.Timestamp(start).floor(f"{WINDOW_MINUTES}min")) & (a.features.index < pd.Timestamp(end))
        idx = np.flatnonzero(in_range)
        timeline, detections = [], []
        cache: dict[int, tuple[Explanation, str, list[str]]] = {}

        def explain_at(i: int):
            if i not in cache:
                cache[i] = self._explain_row(a, bundle, baseline, i, history_hours)
            return cache[i]

        for i in idx:
            z = a.zscores.iloc[i]
            if a.flagged[i]:
                _, kind, top = explain_at(i)
            else:
                kind = None
                top = [s for s in z.abs().sort_values(ascending=False).index if abs(z[s]) >= 2][:2]
            timeline.append({
                "ts": a.features.index[i].to_pydatetime(),
                "ensemble_score": round(float(a.score[i]), 3),
                "flagged": bool(a.flagged[i]),
                "votes": int(a.votes[i]),
                "scores": {n: round(float(a.matrix[i, k]), 3) for k, n in enumerate(a.detectors)},
                "kind": kind,
                "top_signals": top,
                "missing_frac": round(float(a.features["missing_frac"].iloc[i]), 3),
            })
        # contiguous flagged segments that persist for at least PERSISTENCE_WINDOWS
        run: list[int] = []
        for i in [*idx, None]:
            if i is not None and a.flagged[i] and (not run or i == run[-1] + 1):
                run.append(i)
                continue
            if len(run) >= PERSISTENCE_WINDOWS:
                peak = max(run, key=lambda j: a.score[j])
                expl, kind, top = self._explain_row(a, bundle, baseline, peak, history_hours, onset=run[0])
                detections.append({
                    "start": a.features.index[run[0]].to_pydatetime(),
                    "end": (a.features.index[run[-1]] + pd.Timedelta(minutes=WINDOW_MINUTES)).to_pydatetime(),
                    "peak_ts": a.features.index[peak].to_pydatetime(),
                    "peak_score": round(float(a.score[peak]), 3),
                    "duration_minutes": len(run) * WINDOW_MINUTES,
                    "kind": kind,
                    "signals": top,
                    "votes": int(a.votes[peak]),
                    "explanation": expl.to_dict() if explain else None,
                })
            run = [i] if i is not None and a.flagged[i] else []
        sel = a.windows.iloc[idx]
        missing = float(sel[list(SIGNALS)].isna().mean().mean()) if len(sel) else 1.0
        return {
            "astronaut_id": aid,
            "model_version": bundle.version,
            "window_minutes": WINDOW_MINUTES,
            "start": start,
            "end": end,
            "source": source,
            "detectors": [
                {"name": n, "label": bundle.detectors[n].label, "description": bundle.detectors[n].description,
                 "threshold": bundle.detectors[n].threshold, "weight": round(a.weights.get(n, 0.0), 4)}
                for n in a.detectors
            ],
            "timeline": timeline,
            "detections": detections,
            "data_quality": {
                "windows": int(len(idx)),
                "windows_without_data": int((sel["n_samples"] == 0).sum()) if len(sel) else 0,
                "missing_fraction": round(missing, 3),
                "implausible_values_removed": int(removed),
            },
            "limitations": [
                "Detectors flag patterns that are unusual for this crew member; they do not identify a cause.",
                "Rhythm irregularity needs ECG beat timing, which 5-minute windows do not carry; use the live rhythm alerts.",
                f"Thresholds were calibrated for a {bundle.results['anomaly']['target_false_alarm_rate']:.0%} "
                "window false-alarm rate on simulated validation data.",
                SYNTHETIC_CAVEAT,
            ],
        }

    # ---------------------------------------------------------------- forecast ----
    async def forecast(self, astronaut_id: str, model: str | None = None, signals: list[str] | None = None) -> dict[str, Any]:
        bundle = await self.require_bundle()
        self._require_astronaut(astronaut_id)
        name = model or bundle.serving
        if name not in bundle.forecasters:
            raise ValidationError422(f"Unknown forecaster {name}. Available: {', '.join(bundle.forecasters)}.")
        chosen = signals or list(FORECAST_SIGNALS)
        bad = [s for s in chosen if s not in FORECAST_SIGNALS]
        if bad:
            raise ValidationError422(f"Cannot forecast {', '.join(bad)}. Forecast signals: {', '.join(FORECAST_SIGNALS)}.")

        async def run():
            entry = await self.baseline(astronaut_id)
            now = utcnow()
            windows = await self.windows(astronaut_id, now - timedelta(hours=LOOKBACK / 2 + 2), now)
            return await asyncio.to_thread(self._forecast_sync, bundle, entry.baseline, windows, name, astronaut_id, now)

        result = await self._cached(("forecast", astronaut_id, name), run)
        return {**result, "series": [s for s in result["series"] if s["signal"] in chosen]}

    def _forecast_sync(self, bundle, baseline, windows, name, aid, now):
        steps = to_steps(windows)
        origin = pd.Timestamp(now).floor(f"{STEP_MINUTES}min") - pd.Timedelta(minutes=STEP_MINUTES)
        hist_index = pd.date_range(end=origin, periods=LOOKBACK, freq=f"{STEP_MINUTES}min", tz="UTC")
        history = steps.reindex(hist_index)
        if history["heart_rate"].notna().sum() < LOOKBACK // 2:
            raise InsufficientDataError("Forecasting needs at least 12 h of stored data in the last 24 h.")
        history["state"] = history["state"].fillna("work")
        fut_index = pd.date_range(origin + pd.Timedelta(minutes=STEP_MINUTES), periods=HORIZON, freq=f"{STEP_MINUTES}min", tz="UTC")
        plan = planned_steps(aid, fut_index, self.settings.simulator_seed)
        future = pd.DataFrame(index=fut_index, columns=history.columns, dtype=float)
        future["activity_met"], future["sleep_frac"], future["state"] = plan["activity_met"], plan["sleep_frac"], plan["state"]
        combined = pd.concat([history, future])
        series = SeriesArrays.build(aid, combined, baseline)
        t = LOOKBACK - 1
        sample = SampleSet(
            past=series.past(t)[None], future=series.future_cov(t)[None],
            target=np.full((1, HORIZON, len(FORECAST_SIGNALS)), np.nan, np.float32),
            clim=series.climatology(t)[None], origin_ts=[hist_index[-1]], astronaut=[aid],
            scale=np.array([[series.norm.scale[s] for s in FORECAST_SIGNALS]], np.float32),
        )
        model = bundle.forecasters[name]
        pred = model.predict(sample)[0]
        q = bundle.conformal.get(name, np.zeros_like(pred))
        metrics = bundle.results["forecast"]["models"].get(name, {}).get("by_signal", {})
        out_series = []
        for j, sig in enumerate(FORECAST_SIGNALS):
            values = series.norm.denorm(sig, pred[:, j])
            lower = series.norm.denorm(sig, pred[:, j] - q[:, j])
            upper = series.norm.denorm(sig, pred[:, j] + q[:, j])
            horizons = []
            for h in (1, 6, 12, 24):
                k = h * 2 - 1
                state = plan["state"].iloc[k]
                limit, direction, crossing = self._limit(sig, state, values[k], lower[k], upper[k])
                m = metrics.get(sig, {}).get(f"{h}h", {})
                horizons.append({
                    "horizon_h": h, "ts": fut_index[k].to_pydatetime(), "value": round(float(values[k]), 2),
                    "lower": round(float(lower[k]), 2), "upper": round(float(upper[k]), 2),
                    "caution_limit": limit, "limit_direction": direction, "crossing": crossing,
                    "validation_mae": m.get("mae"), "validation_coverage": m.get("coverage"),
                })
            drivers = []
            if isinstance(model, XGBoostForecaster):
                contribs, names = model.shap(sample, j, 12)
                imp = pd.Series(np.abs(contribs[0, :-1]), index=names[:-1])
                grouped = imp.groupby([xgb_feature_group(n) for n in imp.index]).sum()
                grouped = (grouped / grouped.sum()).sort_values(ascending=False)
                drivers = [{"name": g, "share": round(float(v), 3)} for g, v in grouped.items() if v >= 0.02]
            now_val = _f(history[sig].dropna().iloc[-1]) if history[sig].notna().any() else None
            ref = baseline.reference(sig, plan["state"].iloc[-1], fut_index[-1])
            z24 = ref.z_or_none(values[-1])
            width = float(upper[23] - lower[23])
            coverage = metrics.get(sig, {}).get("12h", {}).get("coverage") or 0.0
            trend = values[-1] - (now_val if now_val is not None else values[0])
            verb = "rise" if trend > 0.5 * ref.scale else "fall" if trend < -0.5 * ref.scale else "stay near its current level"
            explanation = Explanation(
                what_changed=(
                    f"{LABELS[sig]} is forecast to {verb}: {('now ' + format(now_val, '.1f') + ', ') if now_val is not None else ''}"
                    f"{values[11]:.1f} in 6 h and {values[-1]:.1f} {UNITS[sig]} in 24 h "
                    f"(90% interval {lower[-1]:.1f} to {upper[-1]:.1f})."
                ),
                kind="forecast",
                contributors=[Contributor(signal=sig, label=LABELS[sig], share=1.0, value=round(float(values[-1]), 2),
                                          unit=UNITS[sig],
                                          baseline=round(ref.center, 2) if z24 is not None else None,
                                          z=None if z24 is None else round(z24, 2),
                                          percentile=None if z24 is None else round(ref.percentile(values[-1]), 1),
                                          direction=None if z24 is None else "above" if z24 >= 0 else "below")],
                significance=significance(0.0 if z24 is None else abs(z24)),
                confidence=confidence(
                    0.6 * max(0.0, 1 - width / (6 * ref.scale)) + 0.4 * coverage,
                    [f"12 h interval width {width:.2f} {UNITS[sig]}",
                     f"interval coverage on simulated test data {coverage:.0%}",
                     f"{history[sig].notna().mean():.0%} of the last 24 h observed"],
                ),
                limitations=[
                    "Assumes the planned crew timeline (sleep, exercise, work) is followed.",
                    "Uncertainty grows with the horizon; the 24 h forecast is close to the personal baseline by design.",
                    f"Error figures come from simulated test data (model {name}).",
                    SYNTHETIC_CAVEAT,
                ],
                method=(f"{model.label}; split-conformal 90% intervals. "
                        + ("Drivers are TreeSHAP shares at the 6 h horizon." if drivers else "No per-forecast attribution for this model type.")),
            )
            out_series.append({
                "signal": sig, "label": LABELS[sig], "unit": UNITS[sig],
                "history": [{"ts": ts.to_pydatetime(), "value": _f(v)} for ts, v in history[sig].items()],
                "forecast": [
                    {"ts": ts.to_pydatetime(), "horizon_h": (k + 1) / 2, "value": round(float(values[k]), 2),
                     "lower": round(float(lower[k]), 2), "upper": round(float(upper[k]), 2)}
                    for k, ts in enumerate(fut_index)
                ],
                "horizons": horizons,
                "drivers": drivers,
                "explanation": explanation.to_dict(),
            })
        return {
            "astronaut_id": aid, "model": name, "model_label": model.label, "model_version": bundle.version,
            "generated_at": now, "origin_ts": hist_index[-1].to_pydatetime(), "step_minutes": STEP_MINUTES,
            "interval_coverage_nominal": bundle.results["forecast"].get("interval_nominal_coverage", 0.9),
            "available_models": list(bundle.forecasters),
            "series": out_series,
            "limitations": [
                "Forecasts extrapolate simulated physiology; they are not validated predictions of real crew health.",
                SYNTHETIC_CAVEAT,
            ],
        }

    @staticmethod
    def _limit(sig: str, state: str, value: float, lower: float, upper: float):
        """Caution limit to compare a forecast with: a likely crossing first, then a possible one,
        otherwise the nearest limit. Returns (limit, direction, crossing)."""
        options = []
        for rule in THRESHOLD_RULES:
            if rule.metric != sig:
                continue
            caution, _ = rule.limits(state)
            if rule.direction == "high":
                crossing = "likely" if value >= caution else "possible" if upper >= caution else None
            else:
                crossing = "likely" if value <= caution else "possible" if lower <= caution else None
            rank = {"likely": 0, "possible": 1, None: 2}[crossing]
            options.append((rank, abs(caution - value), float(caution), rule.direction, crossing))
        if not options:
            return None, None, None
        _, _, limit, direction, crossing = min(options)
        return limit, direction, crossing

    # -------------------------------------------------------------------- risk ----
    async def risk(self, astronaut_id: str) -> dict[str, Any]:
        self._require_astronaut(astronaut_id)
        return await self._cached(("risk", astronaut_id), lambda: self._risk(astronaut_id))

    async def _risk(self, astronaut_id: str) -> dict[str, Any]:
        entry = await self.baseline(astronaut_id)
        bundle = await self.bundle()
        now = utcnow()
        windows = await self.windows(astronaut_id, now - WARMUP - timedelta(hours=2), now)
        forecast = None
        if bundle is not None and bundle.serving in bundle.forecasters:
            try:
                forecast = await self.forecast(astronaut_id)
            except InsufficientDataError:
                forecast = None
        alerts = [
            {"id": a.id, "severity": a.severity, "title": a.title, "metric": a.metric,
             "condition_cleared": a.condition_cleared_at is not None}
            for a in self.monitor.open_alerts_for(astronaut_id)
        ]
        b = entry.baseline
        history_hours = ((b.last_ts - b.first_ts).total_seconds() / 3600) if b.first_ts and b.last_ts else 0.0
        return await asyncio.to_thread(self._risk_sync, astronaut_id, b, bundle, windows, forecast, alerts, now, history_hours)

    def _risk_sync(self, aid, baseline, bundle, windows, forecast, alerts, now, history_hours):
        cfg = self.risk_config
        recent = windows[windows.index >= pd.Timestamp(now) - timedelta(hours=2)]
        ff = build_features(windows, baseline, ALL_GROUPS)
        z = ff.zscores
        signal_states, levels = [], {}
        for s in SIGNALS:
            col = recent[s].dropna()
            if col.empty or col.index[-1] < pd.Timestamp(now) - timedelta(minutes=20):
                signal_states.append(SignalState(s, None, None, None, None, "none"))
                continue
            ts = col.index[-1]
            values, refs, state = self._refs(baseline, windows, ts)
            ref = refs[s]
            if not ref.comparable:  # no baseline for this activity yet: report the value, score no deviation
                levels[s] = "none"
                signal_states.append(SignalState(s, round(float(col.iloc[-1]), 2), None, None, None, "none"))
                continue
            zv = ref.z(col.iloc[-1])
            zs = z[s].loc[:ts].dropna()
            run = 0
            for v in zs.iloc[::-1]:
                if abs(v) >= cfg.deviation_z_start and np.sign(v) == np.sign(zv):
                    run += 1
                else:
                    break
            levels[s] = ref.level
            signal_states.append(SignalState(
                s, round(float(col.iloc[-1]), 2), round(ref.center, 2), round(float(zv), 2),
                round(ref.percentile(col.iloc[-1]), 1), ref.level, deviating_minutes=run * WINDOW_MINUTES,
                trend_per_hour=float(ff.features[f"trend_{s}"].loc[ts]),
            ))
        anomaly = AnomalyState(available=False)
        if bundle is not None:
            a = self._analyse(bundle, baseline, windows, list(bundle.detectors))
            last = len(a.features) - 1
            while last > 0 and a.windows["n_samples"].iloc[last] == 0:
                last -= 1
            trailing = 0
            for i in range(last, -1, -1):
                if a.flagged[i]:
                    trailing += 1
                else:
                    break
            kind, top = None, []
            if a.flagged[last]:
                _, kind, top = self._explain_row(a, bundle, baseline, last, history_hours)
            anomaly = AnomalyState(True, round(float(a.score[last]), 3), int(a.votes[last]), len(a.detectors),
                                   trailing * WINDOW_MINUTES, kind, top)
        forecasts = []
        if forecast:
            for sf in forecast["series"]:
                for h in sf["horizons"]:
                    if h["caution_limit"] is not None:
                        forecasts.append(ForecastState(sf["signal"], h["horizon_h"], h["value"], h["lower"], h["upper"],
                                                       h["caution_limit"], h["limit_direction"]))
        missing = float(recent[list(SIGNALS)].isna().mean().mean()) if len(recent) else 1.0
        inputs = RiskInputs(aid, signal_states, anomaly, forecasts, alerts, missing, int((recent["n_samples"] > 0).sum()),
                            forecast is not None)
        result = assess(inputs, cfg)
        expl: Explanation = result["explanation"]
        expl.limitations = data_limitations(missing, levels, history_hours)
        profile = CREW_BY_ID[aid]
        return {
            "astronaut_id": aid, "name": profile.name, "generated_at": now,
            "model_version": bundle.version if bundle else None,
            **{k: result[k] for k in ("risk_score", "category", "category_label", "health_score", "warnings")},
            "explanation": expl.to_dict(),
            "anomaly": {"available": anomaly.available, "score": anomaly.score, "votes": anomaly.votes,
                        "n_detectors": anomaly.n_detectors, "flagged_minutes": anomaly.flagged_minutes, "kind": anomaly.kind},
            "limitations": [
                "Risk categories come from configurable rules (app/ai/risk_config.json), not a validated clinical model.",
                SYNTHETIC_CAVEAT,
            ],
        }

    async def crew_overview(self) -> dict[str, Any]:
        bundle = await self.bundle()
        crew = []
        for aid, profile in CREW_BY_ID.items():
            try:
                r = await self.risk(aid)
            except InsufficientDataError:
                continue
            crew.append({
                "astronaut_id": aid, "name": profile.name, "role": profile.role,
                "risk_score": r["risk_score"], "category": r["category"], "category_label": r["category_label"],
                "health_score": r["health_score"],
                "top_warning": r["warnings"][0]["title"] if r["warnings"] else None,
                "top_signals": [c["signal"] for c in r["explanation"]["contributors"][:3]],
                "confidence_level": r["explanation"]["confidence"]["level"],
                "warnings": r["warnings"][:3],
            })
        crew.sort(key=lambda c: -c["risk_score"])
        return {"generated_at": utcnow(), "model_version": bundle.version if bundle else None, "crew": crew}

    # ------------------------------------------------------------- explanations ----
    async def explain_alert(self, alert_id: str) -> dict[str, Any]:
        record = self.monitor.evaluator.find(alert_id)
        if record is None:
            async with self.session_factory() as session:
                row = await alerts_repo.get(session, alert_id)
            if row is None:
                raise NotFoundError(f"Alert {alert_id} not found.")
            record = alerts_repo.row_to_record(row)
        entry = await self.baseline(record.astronaut_id)
        bundle = await self.bundle()
        opened = record.opened_at
        windows = await self.windows(record.astronaut_id, opened - WARMUP - timedelta(hours=1), opened + timedelta(minutes=30))
        b = entry.baseline
        history_hours = ((b.last_ts - b.first_ts).total_seconds() / 3600) if b.first_ts and b.last_ts else 0.0
        return await asyncio.to_thread(self._explain_alert_sync, record, b, bundle, windows, history_hours)

    def _explain_alert_sync(self, record, baseline, bundle, windows, history_hours):
        ts = pd.Timestamp(record.opened_at).floor(f"{WINDOW_MINUTES}min")
        has = windows[list(SIGNALS)].notna().any(axis=1)
        near = windows.index[(windows.index <= ts + pd.Timedelta(minutes=10)) & has]
        if len(near) == 0:
            raise InsufficientDataError("No stored measurements around this alert to explain it.")
        ts = near[-1]
        values, refs, state = self._refs(baseline, windows, ts)
        context: list[dict] = []
        kind = "threshold_breach" if record.category == "threshold" else record.category
        if bundle is not None:
            a = self._analyse(bundle, baseline, windows, list(bundle.detectors))
            i = a.features.index.get_loc(ts)
            expl, akind, _ = self._explain_row(a, bundle, baseline, i, history_hours)
            contributors = expl.contributors
            conf = expl.confidence
            for k in np.flatnonzero((a.features.index >= ts - pd.Timedelta(hours=1)) & (a.features.index <= ts + pd.Timedelta(minutes=30))):
                context.append({
                    "ts": a.features.index[k].to_pydatetime(), "ensemble_score": round(float(a.score[k]), 3),
                    "flagged": bool(a.flagged[k]), "votes": int(a.votes[k]),
                    "scores": {n: round(float(a.matrix[k, j]), 3) for j, n in enumerate(a.detectors)},
                    "kind": None, "top_signals": [], "missing_frac": round(float(a.features["missing_frac"].iloc[k]), 3),
                })
            if a.flagged[i]:
                kind = akind
        else:
            shares = {s: max(0.0, abs(z) - 1.5) for s, v in values.items()
                      if v is not None and (z := refs[s].z_or_none(v)) is not None}
            contributors = build_contributors(shares, values, refs)
            conf = confidence(0.4, ["anomaly models unavailable; statistical deviations only"])
        rule = {
            "threshold": (f"Threshold rule {record.rule_key}: {LABELS.get(record.metric, record.metric).lower()} "
                          f"{'above' if record.direction == 'high' else 'below'} {record.threshold_value:g} {record.unit} "
                          f"for 5 consecutive seconds (activity: {record.activity_state})."),
            "rhythm": "Rhythm check: beat-to-beat irregularity of 0.12 or more in the synthetic ECG for 5 seconds.",
            "baseline": "Personal-baseline check: |z| of 4 or more against the expected value for 20 seconds.",
        }.get(record.category, record.rule_key)
        max_z = max((abs(c.z) for c in contributors if c.z is not None), default=0.0)
        explanation = Explanation(
            what_changed=(f"{record.message} Averaged over the surrounding 5-minute window: "
                          f"{describe_contributors(contributors)}."),
            kind=kind,
            contributors=contributors,
            significance=significance(max_z, contributors[0].percentile if contributors else None),
            confidence=conf,
            limitations=[
                "Live alerts are evaluated on 1 Hz data; this explanation uses 5-minute windows, so brief events look smaller.",
                *data_limitations(float(windows[list(SIGNALS)].isna().mean().mean()),
                                  {c.signal: refs[c.signal].basis for c in contributors}, history_hours),
            ],
            method="Alert rule plus the anomaly ensemble's attribution at the 5-minute window containing the alert.",
        )
        return {
            "alert_id": record.id, "astronaut_id": record.astronaut_id, "alert_title": record.title,
            "opened_at": record.opened_at, "rule": rule, "explanation": explanation.to_dict(),
            "anomaly_context": context, "model_version": bundle.version if bundle else None,
        }

    # -------------------------------------------------------------- performance ----
    async def performance(self) -> dict[str, Any]:
        bundle = await self.require_bundle()
        r = bundle.results
        registry = ModelRegistry(self.settings.ai_artifacts_path)
        return {
            "version": bundle.version, "created_at": r["created_at"], "git_commit": r.get("git_commit"),
            "runtime_seconds": r["runtime_seconds"], "dataset": r["dataset"], "anomaly": r["anomaly"],
            "forecast": r["forecast"], "limitations": r["limitations"],
            "versions": registry.versions(), "report_markdown": bundle.report,
        }
