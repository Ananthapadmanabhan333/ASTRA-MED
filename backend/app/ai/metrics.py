"""Evaluation metrics for anomaly detection and forecasting."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from app.ai.signals import WINDOW_MINUTES

WINDOWS_PER_DAY = 24 * 60 // WINDOW_MINUTES


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def classification(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float]:
    """Window-level metrics at a threshold, plus threshold-free AUROC/AUPRC."""
    y = np.asarray(y_true, dtype=bool)
    flags = np.asarray(scores) >= threshold
    tp = int(np.sum(flags & y))
    fp = int(np.sum(flags & ~y))
    fn = int(np.sum(~flags & y))
    tn = int(np.sum(~flags & ~y))
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    both = len(np.unique(y)) == 2
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(_safe_div(2 * precision * recall, precision + recall), 4),
        "auroc": round(float(roc_auc_score(y, scores)), 4) if both else math.nan,
        "auprc": round(float(average_precision_score(y, scores)), 4) if both else math.nan,
        "false_alarm_rate": round(_safe_div(fp, fp + tn), 5),
        "false_alarms_per_day": round(_safe_div(fp, (fp + tn) / WINDOWS_PER_DAY), 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def event_detection(
    flags: np.ndarray, labels: np.ndarray, event_ids: np.ndarray, kinds: np.ndarray, ts: pd.DatetimeIndex
) -> dict[str, float | dict]:
    """Share of labelled events flagged at least once, and minutes from first label to first flag."""
    frame = pd.DataFrame({"flag": flags, "label": labels, "event": event_ids, "kind": kinds}, index=ts)
    frame = frame[frame["label"] & frame["event"].notna()]
    results: dict[str, list] = {}
    delays: dict[str, list] = {}
    for _event, group in frame.groupby("event"):
        kind = group["kind"].iloc[0]
        hit = group["flag"].any()
        results.setdefault(kind, []).append(bool(hit))
        if hit:
            first_flag = group.index[group["flag"].to_numpy()][0]
            delays.setdefault(kind, []).append((first_flag - group.index[0]).total_seconds() / 60)
    out: dict[str, float | dict] = {}
    all_hits = [h for v in results.values() for h in v]
    all_delays = [d for v in delays.values() for d in v]
    out["events"] = len(all_hits)
    out["event_recall"] = round(_safe_div(sum(all_hits), len(all_hits)), 4)
    out["median_delay_min"] = round(float(np.median(all_delays)), 1) if all_delays else math.nan
    out["by_kind"] = {
        k: {
            "events": len(v),
            "recall": round(_safe_div(sum(v), len(v)), 4),
            "median_delay_min": round(float(np.median(delays[k])), 1) if delays.get(k) else math.nan,
        }
        for k, v in sorted(results.items())
    }
    return out


def regression(y: np.ndarray, pred: np.ndarray, lo: np.ndarray | None = None, hi: np.ndarray | None = None) -> dict[str, float]:
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    ok = np.isfinite(y) & np.isfinite(pred)
    err = pred[ok] - y[ok]
    out = {
        "n": int(ok.sum()),
        "mae": round(float(np.mean(np.abs(err))), 4) if ok.any() else math.nan,
        "rmse": round(float(np.sqrt(np.mean(err**2))), 4) if ok.any() else math.nan,
    }
    if lo is not None and hi is not None:
        lo, hi = np.asarray(lo, float)[ok], np.asarray(hi, float)[ok]
        out["coverage"] = round(float(np.mean((y[ok] >= lo) & (y[ok] <= hi))), 4)
        out["mean_width"] = round(float(np.mean(hi - lo)), 4)
    return out
