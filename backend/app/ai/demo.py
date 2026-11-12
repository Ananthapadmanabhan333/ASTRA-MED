"""Controlled demonstrations of the registered models (writes experiments/results/demo.md).

    python -m app.ai.demo

1. Anomaly detection on one simulated day with four known, injected situations:
     A  sudden oxygen desaturation (full intensity)
     B  subtle elevated heart rate that stays below the fixed alert limits
     C  gradual temperature drift over 12 hours
     D  sensor artefacts and a 40-minute data dropout (these must NOT alarm)
   The personal baseline comes from 7 earlier clean days (like a pre-flight baseline).
2. Forecasting on held-out simulated history: predicted vs actual at 1, 6, 12 and 24 h.

All data here is simulated; the demo shows the pipeline working, not clinical performance.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.ai.anomaly.detectors import Ensemble
from app.ai.anomaly.fixed import fixed_threshold_scores
from app.ai.baseline import PersonalBaseline
from app.ai.explain import onset_kind, signal_shares
from app.ai.features import ALL_GROUPS, build_features
from app.ai.forecasting.data import HORIZON, LOOKBACK, SampleSet, SeriesArrays, to_steps
from app.ai.service import ModelBundle
from app.ai.signals import FORECAST_SIGNALS, LABELS, SIGNALS, UNITS
from app.ai.windows import samples_to_frame, to_windows
from app.core.config import get_settings
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW, CREW_BY_ID
from app.simulator.scenarios import ActiveScenario, Scenario

BACKEND = Path(__file__).resolve().parents[2]
AID = "AST-03"
DAY = datetime(2026, 7, 1, tzinfo=UTC)


def _history(engine, profile, start, end, scenarios):
    rows = list(engine.history(profile, start, end, timedelta(minutes=5), scenarios))
    return samples_to_frame([{"ts": r.ts, **{s: getattr(r, s) for s in SIGNALS},
                              "activity_state": r.activity_state, "activity_met": r.activity_met} for r in rows])


def anomaly_demo(bundle: ModelBundle) -> list[str]:
    profile = CREW_BY_ID[AID]
    engine = SimulationEngine(CREW, seed=2026, random_events_per_hour=0)
    clean = _history(engine, profile, DAY - timedelta(days=7), DAY, [])
    baseline = PersonalBaseline.fit(AID, to_windows(clean))

    a_start, b_start = DAY + timedelta(hours=3), DAY + timedelta(hours=10)
    scen = [
        ActiveScenario("A", Scenario.DESATURATION, AID, 1.0, a_start, a_start + timedelta(minutes=60), "operator"),
        ActiveScenario("B", Scenario.TACHYCARDIA, AID, 0.45, b_start, b_start + timedelta(minutes=60), "operator"),
    ]
    day = _history(engine, profile, DAY - timedelta(hours=6), DAY + timedelta(days=1), scen)
    c_start, c_peak = DAY + timedelta(hours=14), DAY + timedelta(hours=22)
    ramp = ((day["ts"] - c_start).dt.total_seconds() / ((c_peak - c_start).total_seconds())).clip(0, 1)
    ramp = ramp.where(day["ts"] < DAY + timedelta(hours=24), 0)
    day["temperature_c"] += 0.9 * ramp
    day["heart_rate"] += 8 * ramp
    d_art = DAY + timedelta(hours=6)
    day.loc[day["ts"] == d_art, "heart_rate"] = 0.0  # implausible artefact
    day.loc[day["ts"] == d_art + timedelta(minutes=30), "spo2"] = 31.0
    drop = (day["ts"] >= DAY + timedelta(hours=7)) & (day["ts"] < DAY + timedelta(hours=7, minutes=40))
    day.loc[drop, list(SIGNALS)] = np.nan

    windows = to_windows(day)
    ff = build_features(windows, baseline, ALL_GROUPS)
    ens = Ensemble(bundle.detectors, bundle.ensemble.weights)
    matrix = ens.normalised_matrix(ff.features)
    score = ens.score_from_matrix(matrix) / bundle.ensemble.threshold
    flags = pd.Series(score >= 1.0, index=windows.index)
    fixed = pd.Series(fixed_threshold_scores(windows) >= 0, index=windows.index)
    names = list(ff.features.columns)

    situations = [
        ("A: sudden desaturation", a_start, a_start + timedelta(minutes=60), True),
        ("B: subtle heart-rate rise (below fixed limits)", b_start, b_start + timedelta(minutes=60), True),
        ("C: gradual temperature drift (12 h)", c_start, DAY + timedelta(hours=24), True),
        ("D: artefacts and 40-min dropout", d_art - timedelta(minutes=5), DAY + timedelta(hours=7, minutes=45), False),
    ]
    lines = [
        "## 1. Anomaly detection on controlled scenarios",
        "",
        f"Crew member {AID} ({profile.name}); baseline from 7 clean simulated days; analysis day {DAY:%Y-%m-%d} (UTC). "
        f"Model {bundle.version}.",
        "",
        "| Situation | Should alarm | Ensemble flagged | First flag | Peak score | Fixed thresholds flagged | Top signals (ensemble attribution) | Kind |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, lo, hi, should in situations:
        sel = (windows.index >= lo) & (windows.index < hi)
        hit = flags[sel]
        first = hit[hit].index.min() if hit.any() else None
        peak_i = int(np.argmax(np.where(sel, score, -np.inf)))
        contrib = np.zeros(len(names))
        for det_name, det in bundle.detectors.items():
            w = bundle.ensemble.weights.get(det_name, 0.0)
            if w <= 0:
                continue
            c = det.contributions(det.matrix(ff.features.iloc[[peak_i]]))[0]
            for v, f in zip(c, det.feature_names):
                contrib[names.index(f)] += w * v
        by_signal, _ = signal_shares(contrib, names)
        total = sum(v for k, v in by_signal.items() if k != "context") or 1
        top_signal = max((k for k in by_signal if k != "context"), key=lambda k: by_signal[k], default=None)
        kind = onset_kind(ff.zscores[top_signal].to_numpy(), windows.index.get_loc(first)) if first is not None and top_signal else None
        top = ", ".join(f"{LABELS[s]} {v / total:.0%}" for s, v in sorted(by_signal.items(), key=lambda kv: -kv[1])
                        if s != "context" and v / total >= 0.1)
        lines.append(
            f"| {label} | {'yes' if should else 'no'} | {int(hit.sum())} of {int(sel.sum())} windows | "
            f"{(first - lo).total_seconds() / 60:.0f} min after start | {score[peak_i]:.2f}x | "
            f"{int(fixed[sel].sum())} windows | {top or 'none'} | {kind.replace('_', ' ') if kind else 'n/a'} |"
            if first is not None else
            f"| {label} | {'yes' if should else 'no'} | 0 of {int(sel.sum())} windows | n/a | {score[peak_i]:.2f}x | "
            f"{int(fixed[sel].sum())} windows | {top or 'none'} | n/a |"
        )
    quiet = ~np.any([(windows.index >= lo) & (windows.index < hi) for _, lo, hi, _ in situations], axis=0)
    quiet &= windows.index >= DAY
    lines += [
        "",
        f"Outside the four situations the ensemble flagged {int(flags[quiet].sum())} of {int(quiet.sum())} windows "
        f"({flags[quiet].mean():.1%}); fixed thresholds flagged {int(fixed[quiet].sum())}.",
        "",
    ]
    return lines


def forecast_demo(bundle: ModelBundle) -> list[str]:
    from app.ai.datasets.synthetic import SyntheticConfig, chronological_split, generate
    from app.ai.pipeline import prepare

    cfg = SyntheticConfig(days=60, crew=(AID,), seed=31)
    data, _ = generate(cfg)
    split = chronological_split(cfg)
    P = prepare(data, split)
    steps = to_steps(P.windows[AID])
    series = SeriesArrays.build(AID, steps, P.baselines[AID])
    lines = [
        "## 2. Forecasting on held-out simulated history",
        "",
        f"Fresh simulated history for {AID} (seed {cfg.seed}, not used in training); baseline fitted on its first "
        f"{(split.train_end - pd.Timestamp(cfg.start, tz='UTC')).days} days. Forecast origins are taken from the test period.",
        "",
    ]
    test_idx = np.flatnonzero(series.index >= split.val_end)
    origins = [int(t) for t in test_idx[::96][:3] if t - LOOKBACK >= 0 and t + HORIZON < len(series.index)]
    for name in ("xgboost", "gru", "climatology"):
        if name not in bundle.forecasters:
            continue
        model, q = bundle.forecasters[name], bundle.conformal[name]
        rows, hits, errs = [], 0, {s: [] for s in FORECAST_SIGNALS}
        total = 0
        for t in origins:
            sample = SampleSet(series.past(t)[None], series.future_cov(t)[None], series.target(t)[None],
                               series.climatology(t)[None], [series.index[t]], [AID],
                               np.array([[series.norm.scale[s] for s in FORECAST_SIGNALS]], np.float32))
            pred = model.predict(sample)[0]
            for j, s in enumerate(FORECAST_SIGNALS):
                for h in (1, 6, 12, 24):
                    k = 2 * h - 1
                    actual = series.target(t)[k, j]
                    if not np.isfinite(actual):
                        continue
                    p = series.norm.denorm(s, pred[k, j])
                    lo, hi = series.norm.denorm(s, pred[k, j] - q[k, j]), series.norm.denorm(s, pred[k, j] + q[k, j])
                    a = series.norm.denorm(s, actual)
                    total += 1
                    hits += int(lo <= a <= hi)
                    errs[s].append(abs(p - a))
                    if s == "heart_rate":
                        rows.append(f"| {series.index[t]:%m-%d %H:%M} | {h} h | {a:.1f} | {p:.1f} | {lo:.1f} to {hi:.1f} | {'yes' if lo <= a <= hi else 'no'} |")
        lines += [f"### {model.label}", "",
                  "| Origin (UTC) | Horizon | Actual HR | Forecast | 90% interval | Inside |", "| --- | --- | --- | --- | --- | --- |",
                  *rows, "",
                  "Mean absolute error over these origins: " + ", ".join(
                      f"{LABELS[s]} {np.mean(v):.2f} {UNITS[s]}" for s, v in errs.items() if v) +
                  f". {hits} of {total} actual values fell inside the 90% interval.", ""]
    return lines


def main() -> int:
    settings = get_settings()
    bundle = ModelBundle.load(settings.ai_artifacts_path)
    if bundle is None:
        print("No trained model version. Run: python -m app.ai.train")
        return 1
    lines = [
        f"# ASTRA-MED AI demonstration ({bundle.version})",
        "",
        "> Simulated data only. This shows the pipeline working on controlled, known situations; it is not evidence "
        "of clinical performance.",
        "",
        *anomaly_demo(bundle),
        *forecast_demo(bundle),
    ]
    out = BACKEND / "experiments" / "results" / "demo.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
