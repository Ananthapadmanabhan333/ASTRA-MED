"""Run the full experiment: data → anomaly models → forecasters → ablations → artifacts → report.

Every number in the saved results is computed here from the chronological test split. Nothing is
estimated, copied or hand-edited. The data is simulated, so the results describe how well each
method recovers the simulator's injected events and dynamics, not clinical performance.
"""

from __future__ import annotations

import json
import logging
import platform
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app.ai.anomaly.detectors import (
    DETECTOR_CLASSES,
    STATS_FEATURES,
    AutoencoderDetector,
    Detector,
    Ensemble,
    available_detectors,
    save_detectors,
)
from app.ai.anomaly.fixed import fixed_threshold_scores
from app.ai.datasets.synthetic import Split, chronological_split, generate
from app.ai.experiments.config import ANOMALY_ABLATIONS, FORECAST_ABLATIONS, ExperimentConfig
from app.ai.features import feature_names
from app.ai.forecasting.conformal import conformal_quantiles, intervals
from app.ai.forecasting.data import REPORT_HORIZONS_H, REPORT_STEPS, SeriesArrays, build_samples, to_steps
from app.ai.forecasting.models import (
    TORCH_AVAILABLE,
    Climatology,
    Persistence,
    SeasonalNaive,
    SequenceForecaster,
    XGBoostForecaster,
    xgb_feature_group,
)
from app.ai.metrics import classification, event_detection, regression
from app.ai.pipeline import PreparedData, prepare
from app.ai.registry import ModelRegistry, config_hash, git_commit
from app.ai.signals import FORECAST_SIGNALS, WINDOW_MINUTES

logger = logging.getLogger("astra.ai.experiment")

LIMITATIONS = [
    "All data is simulated by the ASTRA-MED simulator. Results show how well each method recovers "
    "the simulator's injected events and dynamics; they say nothing about accuracy on real astronauts.",
    "The simulator's physiology, the injected events and the evaluation labels share one design, which "
    "makes the task easier than real monitoring, where events are unlabelled, heterogeneous and rare.",
    "Planned activity equals actual activity in the simulator; real crew timelines deviate from plan.",
    "Detection thresholds are calibrated on labelled validation data to a 1% window false-alarm rate. "
    "A real deployment would have no labels and would need clinician-reviewed calibration.",
    "Prediction intervals are split-conformal; their coverage guarantee assumes exchangeability, which "
    "time series only approximate. Test coverage is measured and reported, not assumed.",
    "No model here has been validated on astronaut or patient populations. Outputs are experimental "
    "decision support and must never be used as a diagnosis.",
]


def _seed_everything(seed: int) -> None:
    np.random.seed(seed)
    if TORCH_AVAILABLE:
        import torch

        torch.manual_seed(seed)
        torch.set_num_threads(4)


# ----------------------------------------------------------------- dataset info ----
def dataset_summary(data: pd.DataFrame, events: list, split: Split, cfg: ExperimentConfig) -> dict[str, Any]:
    parts = split.name(data["ts"])
    per_split = {}
    for part in ("train", "val", "test"):
        sel = data[parts == part]
        per_split[part] = {
            "windows": int(len(sel)),
            "label_rate": round(float(sel["label"].mean()), 4),
            "start": str(sel["ts"].min()),
            "end": str(sel["ts"].max()),
        }
    return {
        "source": "synthetic (ASTRA-MED simulator)",
        "real_data": "none: no public astronaut vital-sign time series is available without a data-use agreement",
        "fingerprint": cfg.dataset.fingerprint(),
        "config": cfg.dataset.to_dict(),
        "crew": list(cfg.dataset.crew),
        "samples": int(len(data)),
        "interval_minutes": cfg.dataset.interval_minutes,
        "split": split.to_dict(),
        "splits": per_split,
        "events": {
            "total": len(events),
            "sudden": sum(e.kind == "sudden" for e in events),
            "gradual": sum(e.kind == "gradual" for e in events),
            "subtle": sum(e.subtle for e in events),
            "by_type": pd.Series([e.type for e in events]).value_counts().to_dict(),
        },
        "defects": {
            "missing_rate": round(float(data[["heart_rate", "spo2", "temperature_c"]].isna().mean().mean()), 4),
            "artefacts": int(data["artefact"].sum()),
        },
    }


# --------------------------------------------------------------------- anomaly ----
def _persistent(flags: np.ndarray, astronaut: np.ndarray, k: int) -> np.ndarray:
    """A window counts only if it and the previous k-1 windows (same person) are all flagged."""
    out = np.zeros_like(flags)
    for aid in np.unique(astronaut):
        idx = np.flatnonzero(astronaut == aid)
        f = pd.Series(flags[idx].astype(int))
        out[idx] = f.rolling(k, min_periods=k).min().fillna(0).to_numpy().astype(bool)
    return out


def _evaluate_scores(scores: np.ndarray, threshold: float, y: np.ndarray, meta: pd.DataFrame,
                     ambiguous: np.ndarray, subtle_by_event: dict[str, bool], k: int) -> dict[str, Any]:
    keep = ~ambiguous
    flags = scores >= threshold
    events = event_detection(flags, y, meta["event_id"].to_numpy(), meta["event_kind"].to_numpy(), meta.index)
    by_type = event_detection(flags, y, meta["event_id"].to_numpy(), meta["event_type"].to_numpy(), meta.index)["by_kind"]
    intensity = np.array(["subtle" if subtle_by_event.get(e) else "full" for e in meta["event_id"].to_numpy()], dtype=object)
    by_intensity = event_detection(flags, y, meta["event_id"].to_numpy(), intensity, meta.index)["by_kind"]
    persistent = _persistent(flags, meta["astronaut_id"].to_numpy(), k)
    normal = keep & ~y
    days = normal.sum() * WINDOW_MINUTES / 1440
    return {
        "threshold": round(float(threshold), 5),
        "test": classification(y[keep], scores[keep], threshold),
        "events": events,
        "events_by_type": by_type,
        "events_by_intensity": by_intensity,
        "operational": {
            "persistence_windows": k,
            "false_warnings_per_crew_day": round(float((persistent & normal).sum() / max(days, 1e-9)), 3),
            "event_recall": event_detection(persistent, y, meta["event_id"].to_numpy(), meta["event_kind"].to_numpy(), meta.index)["event_recall"],
        },
    }


def _new_detector(name: str, cfg: ExperimentConfig) -> Detector:
    cls = DETECTOR_CLASSES[name]
    return cls(seed=cfg.seed, epochs=cfg.autoencoder_epochs) if cls is AutoencoderDetector else cls(seed=cfg.seed)


def _candidates(name: str, cfg: ExperimentConfig) -> dict[str, list[str]]:
    if name == "statistical":  # fixed by design: personal z-scores and their sustained mean
        return {"level_sustained": list(STATS_FEATURES)}
    return {k: feature_names(ANOMALY_ABLATIONS[k]) for k in cfg.anomaly_ablations}


def run_anomaly(cfg: ExperimentConfig, P: PreparedData, subtle: dict[str, bool]) -> tuple[dict, dict[str, Detector], Ensemble]:
    names = P.feature_names
    Xtr, _, _ = P.stacked("train", clean_only=True)
    Xv, yv, mv = P.stacked("val")
    Xt, yt, mt = P.stacked("test")
    Ftr, Fv, Ft = (pd.DataFrame(X, columns=names) for X in (Xtr, Xv, Xt))
    amb_v = ((mv["event_level"].fillna(0) > 0) & ~mv["label"]).to_numpy()
    amb_t = ((mt["event_level"].fillna(0) > 0) & ~mt["label"]).to_numpy()
    base_rate = float(yv[~amb_v].mean())

    detectors: dict[str, Detector] = {}
    results: dict[str, Any] = {}
    ablations: dict[str, Any] = {}
    val_norm: dict[str, np.ndarray] = {}
    test_norm: dict[str, np.ndarray] = {}
    for name in cfg.detectors:
        if name not in available_detectors():
            results[name] = {"skipped": "dependency not installed"}
            continue
        candidates: dict[str, Any] = {}
        best: tuple | None = None
        for cand, cols in _candidates(name, cfg).items():
            det = _new_detector(name, cfg)
            t = time.perf_counter()
            det.fit(Ftr[cols].to_numpy(), cols)
            fit_s = time.perf_counter() - t
            sv = det.score(Fv[cols].to_numpy())
            positives = bool(yv[~amb_v].any())
            val_auprc = float(average_precision_score(yv[~amb_v], sv[~amb_v])) if positives else 0.0
            det.calibrate(sv[~amb_v & ~yv], cfg.false_alarm_rate)
            t = time.perf_counter()
            st = det.score(Ft[cols].to_numpy())
            score_ms = (time.perf_counter() - t) / len(Xt) * 1e6
            ev = _evaluate_scores(st, det.threshold, yt, mt, amb_t, subtle, cfg.persistence_windows)
            kinds = ev["events"]["by_kind"]
            candidates[cand] = {
                "n_features": len(cols),
                "val_auprc": round(val_auprc, 4),
                "test": {
                    "auroc": ev["test"]["auroc"],
                    "f1": ev["test"]["f1"],
                    "event_recall": ev["events"]["event_recall"],
                    "sudden_recall": kinds.get("sudden", {}).get("recall"),
                    "gradual_recall": kinds.get("gradual", {}).get("recall"),
                },
            }
            if best is None or val_auprc > best[0]:
                best = (val_auprc, cand, det, sv, st, ev, fit_s, score_ms)
        val_auprc, cand, det, sv, st, ev, fit_s, score_ms = best
        results[name] = {
            "label": det.label,
            "description": det.description,
            "selected_features": cand,
            "n_features": len(det.feature_names),
            "fit_seconds": round(fit_s, 2),
            "score_ms_per_1k_windows": round(score_ms, 2),
            "val_auprc": round(val_auprc, 4),
            **ev,
        }
        ablations[name] = {"selected": cand, "candidates": candidates}
        detectors[name] = det
        val_norm[name], test_norm[name] = sv / det.threshold, st / det.threshold
        logger.info("anomaly %-17s [%s] val AUPRC %.3f test F1 %.3f", name, cand, val_auprc, ev["test"]["f1"])

    best_auprc = max(results[n]["val_auprc"] for n in detectors)
    weights = {
        n: (
            max(0.0, results[n]["val_auprc"] - base_rate)
            if results[n]["val_auprc"] >= cfg.ensemble_min_relative_auprc * best_auprc
            else 0.0
        )
        for n in detectors
    }
    ensemble = Ensemble(detectors, weights)
    ev = ensemble.score_from_matrix(np.column_stack([val_norm[n] for n in detectors]))
    ensemble.calibrate(ev[~amb_v & ~yv], cfg.false_alarm_rate)
    et = ensemble.score_from_matrix(np.column_stack([test_norm[n] for n in detectors]))
    ens_result = {
        "label": ensemble.label,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "member_rule": (
            f"validation AUPRC >= {cfg.ensemble_min_relative_auprc:.0%} of the best; weight = AUPRC above base rate"
        ),
        **_evaluate_scores(et, ensemble.threshold, yt, mt, amb_t, subtle, cfg.persistence_windows),
    }
    fx = np.concatenate(
        [fixed_threshold_scores(P.windows[a][P.split.name(P.windows[a].index) == "test"]) for a in sorted(P.windows)]
    )
    fixed = {
        "label": "Fixed thresholds (phase 2 alert rules)",
        **_evaluate_scores(fx, 0.0, yt, mt, amb_t, subtle, cfg.persistence_windows),
    }
    summary = {
        "feature_names": names,
        "train_windows": int(len(Xtr)),
        "val_windows": int(len(Xv)),
        "test_windows": int(len(Xt)),
        "test_label_rate": round(float(yt[~amb_t].mean()), 4),
        "ambiguous_test_windows_excluded": int(amb_t.sum()),
        "target_false_alarm_rate": cfg.false_alarm_rate,
        "selection": "feature set per detector chosen by validation AUPRC; test used once for reporting",
        "models": results,
        "ensemble": ens_result,
        "fixed_thresholds": fixed,
        "ablations": ablations,
    }
    return summary, detectors, ensemble


# -------------------------------------------------------------------- forecast ----
def _forecast_sets(P: PreparedData):
    split = P.split
    start = min(w.index.min() for w in P.windows.values())
    mid = split.train_end + (split.val_end - split.train_end) / 2
    series = [SeriesArrays.build(a, to_steps(P.windows[a]), P.baselines[a]) for a in sorted(P.windows)]

    def masks(lo, hi):
        return {s.astronaut_id: np.asarray((s.index >= lo) & (s.index < hi)) for s in series}

    return (
        build_samples(series, masks(start, split.train_end)),
        build_samples(series, masks(split.train_end, mid)),  # early stopping / selection
        build_samples(series, masks(mid, split.val_end)),  # conformal calibration only
        build_samples(series, masks(split.val_end, split.end + pd.Timedelta(days=1))),
    )


def _forecast_metrics(pred: np.ndarray, q: np.ndarray, s) -> dict[str, dict[str, dict]]:
    lo, hi = intervals(pred, q)
    out: dict[str, dict[str, dict]] = {}
    for j, sig in enumerate(FORECAST_SIGNALS):
        out[sig] = {}
        for h_hours, step in zip(REPORT_HORIZONS_H, REPORT_STEPS):
            k = step - 1
            scale = s.scale[:, j]
            out[sig][f"{h_hours}h"] = regression(
                s.target[:, k, j] * scale, pred[:, k, j] * scale, lo[:, k, j] * scale, hi[:, k, j] * scale
            )
    return out


def _make_forecaster(name: str, cfg: ExperimentConfig):
    if name == "persistence":
        return Persistence()
    if name == "seasonal_naive":
        return SeasonalNaive()
    if name == "climatology":
        return Climatology()
    if name == "xgboost":
        return XGBoostForecaster(seed=cfg.seed)
    if name in ("lstm", "gru", "tcn"):
        return SequenceForecaster(name, seed=cfg.seed, epochs=cfg.nn_epochs) if TORCH_AVAILABLE else None
    raise ValueError(name)


def run_forecast(cfg: ExperimentConfig, P: PreparedData) -> tuple[dict, dict[str, Any], dict[str, np.ndarray]]:
    train, val, cal, test = _forecast_sets(P)
    results: dict[str, Any] = {}
    models: dict[str, Any] = {}
    conformal: dict[str, np.ndarray] = {}
    for name in cfg.forecasters:
        model = _make_forecaster(name, cfg)
        if model is None:
            results[name] = {"skipped": "dependency not installed"}
            continue
        t = time.perf_counter()
        model.fit(train, val)
        fit_s = time.perf_counter() - t
        q = conformal_quantiles(model.predict(cal), cal.target, cfg.interval_alpha)
        pred = model.predict(test)
        results[name] = {
            "label": model.label,
            "family": model.family,
            "fit_seconds": round(fit_s, 2),
            "by_signal": _forecast_metrics(pred, q, test),
        }
        if hasattr(model, "history") and model.history:
            results[name]["epochs_run"] = len(model.history)
        models[name], conformal[name] = model, q
        logger.info("forecast %-15s HR 1h MAE %.2f", name, results[name]["by_signal"]["heart_rate"]["1h"]["mae"])

    clim = results.get("climatology", {}).get("by_signal")
    for r in results.values():
        if "by_signal" not in r or not clim:
            continue
        r["skill_vs_climatology"] = {
            sig: {h: round(1 - r["by_signal"][sig][h]["mae"] / clim[sig][h]["mae"], 4) for h in r["by_signal"][sig]}
            for sig in FORECAST_SIGNALS
        }

    shap_summary: dict[str, Any] = {}
    if "xgboost" in models:
        for j, sig in enumerate(FORECAST_SIGNALS):
            shap_summary[sig] = {}
            for h_hours, step in zip(REPORT_HORIZONS_H, REPORT_STEPS):
                contribs, names = models["xgboost"].shap(test, j, step)
                imp = pd.Series(np.abs(contribs[:, :-1]).mean(axis=0), index=names[:-1])
                grouped = imp.groupby([xgb_feature_group(n) for n in imp.index]).sum()
                shap_summary[sig][f"{h_hours}h"] = (grouped / grouped.sum()).round(4).sort_values(ascending=False).to_dict()

    summary = {
        "step_minutes": 30,
        "lookback_hours": 24,
        "horizons_hours": list(REPORT_HORIZONS_H),
        "interval_nominal_coverage": 1 - cfg.interval_alpha,
        "samples": {"train": len(train), "early_stopping": len(val), "calibration": len(cal), "test": len(test)},
        "models": results,
        "xgboost_shap_importance": shap_summary,
    }
    return summary, models, conformal


def run_forecast_ablations(cfg: ExperimentConfig, P: PreparedData) -> dict:
    if not cfg.forecast_ablations:
        return {}
    train, val, cal, test = _forecast_sets(P)
    out: dict[str, Any] = {}
    for ablation in cfg.forecast_ablations:
        model = XGBoostForecaster(seed=cfg.seed, exclude=FORECAST_ABLATIONS[ablation]).fit(train, val)
        q = conformal_quantiles(model.predict(cal), cal.target, cfg.interval_alpha)
        metrics = _forecast_metrics(model.predict(test), q, test)
        out[ablation] = {
            "excluded_feature_patterns": list(FORECAST_ABLATIONS[ablation]),
            "mae": {sig: {h: metrics[sig][h]["mae"] for h in metrics[sig]} for sig in FORECAST_SIGNALS},
        }
    return out


# ------------------------------------------------------------------------- run ----
def run(cfg: ExperimentConfig, artifacts_root: Path, register: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    _seed_everything(cfg.seed)
    data, events = generate(cfg.dataset)
    split = chronological_split(cfg.dataset, cfg.train_frac, cfg.val_frac)
    subtle = {e.id: e.subtle for e in events}
    logger.info("dataset %s: %d samples, %d events", cfg.dataset.fingerprint(), len(data), len(events))

    P = prepare(data, split, seed=cfg.seed)
    anomaly, detectors, ensemble = run_anomaly(cfg, P, subtle)
    forecast, forecasters, conformal = run_forecast(cfg, P)
    forecast["ablations"] = run_forecast_ablations(cfg, P)

    registry = ModelRegistry(artifacts_root)
    cfg_dict = cfg.to_dict()
    version, path = registry.new_version(config_hash(cfg_dict))
    save_detectors(detectors, path / "anomaly", ensemble)
    for model in forecasters.values():
        model.save(path / "forecast")
    (path / "forecast" / "conformal.json").write_text(
        json.dumps({n: np.round(q, 5).tolist() for n, q in conformal.items()}, indent=2)
    )
    (path / "forecast" / "forecast.json").write_text(
        json.dumps({"models": list(forecasters), "serving": cfg.serving_forecaster,
                    "interval_alpha": cfg.interval_alpha}, indent=2)
    )
    (path / "config.json").write_text(json.dumps(cfg_dict, indent=2, default=str))

    results = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(Path(__file__).resolve().parent),
        "runtime_seconds": round(time.perf_counter() - started, 1),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "config": cfg_dict,
        "dataset": dataset_summary(data, events, split, cfg),
        "anomaly": anomaly,
        "forecast": forecast,
        "limitations": LIMITATIONS,
    }
    results = clean_json(results)
    (path / "results.json").write_text(json.dumps(results, indent=2, default=_json_default, allow_nan=False))
    from app.ai.experiments.report import render_report

    (path / "report.md").write_text(render_report(results), encoding="utf-8")
    if register:
        registry.register(version, {
            "created_at": results["created_at"],
            "config_hash": config_hash(cfg_dict),
            "git_commit": results["git_commit"],
            "dataset_fingerprint": cfg.dataset.fingerprint(),
            "detectors": list(detectors),
            "forecasters": list(forecasters),
            "serving_forecaster": cfg.serving_forecaster,
        })
    logger.info("experiment %s finished in %.0fs", version, results["runtime_seconds"])
    return results


def clean_json(o: Any) -> Any:
    """Recursively convert NaN/inf to None and numpy scalars to Python, so output is strict JSON."""
    if isinstance(o, dict):
        return {str(k): clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not np.isfinite(f) else f
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, float) and np.isnan(o):
        return None
    return str(o)


def quick_config(base: ExperimentConfig | None = None) -> ExperimentConfig:
    return (base or ExperimentConfig()).quick()


__all__ = ["run", "quick_config", "ExperimentConfig", "replace"]
