"""Replication study: rerun the full evaluation on independent simulated datasets.

The headline evaluation uses one simulated dataset (seed 7). This script repeats the same
experiment configuration with different seeds for the simulator *and* the models, so each run sees a
different crew history, different injected events and different model initialisation. It reports
each metric's mean, standard deviation and range across runs, which shows how much of a difference
between two models could be noise.

Nothing is registered: artifacts go to a temporary directory and the serving model is untouched.

    python scripts/seed_study.py --seeds 7 11 23
    python scripts/seed_study.py --quick --seeds 1 2     # smoke run (not for reporting)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.experiments.config import ExperimentConfig  # noqa: E402
from app.ai.experiments.runner import run  # noqa: E402
from app.ai.registry import git_commit  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "experiments" / "results"


def collect(r: dict) -> dict[str, float | None]:
    m: dict[str, float | None] = {}
    an = r["anomaly"]
    for name, block in {**an["models"], "ensemble": an["ensemble"], "fixed_thresholds": an["fixed_thresholds"]}.items():
        if "test" not in block:
            continue
        t = block["test"]
        for k in ("precision", "recall", "f1", "auroc", "auprc", "false_alarm_rate", "false_negative_rate"):
            m[f"anomaly.{name}.{k}"] = t.get(k)
        m[f"anomaly.{name}.event_recall"] = block["events"]["event_recall"]
    for name, block in r["forecast"]["models"].items():
        for sig, by_h in block.get("by_signal", {}).items():
            for h in ("1h", "24h"):
                for k in ("mae", "rmse", "mape_pct", "coverage"):
                    if k in by_h[h]:
                        m[f"forecast.{name}.{sig}.{h}.{k}"] = by_h[h][k]
    return m


def summarise(per_seed: dict[int, dict[str, float | None]]) -> dict[str, dict]:
    keys = sorted({k for v in per_seed.values() for k in v})
    out = {}
    for k in keys:
        vals = [v[k] for v in per_seed.values() if v.get(k) is not None]
        if not vals:
            continue
        out[k] = {
            "mean": round(statistics.fmean(vals), 4),
            "sd": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "n": len(vals),
            "by_seed": {str(s): v.get(k) for s, v in per_seed.items()},
        }
    return out


def render(study: dict) -> str:
    s = study["summary"]
    seeds = study["seeds"]

    def cell(key: str, nd: int = 3) -> str:
        v = s.get(key)
        return "n/a" if v is None else f"{v['mean']:.{nd}f} ± {v['sd']:.{nd}f}"

    lines = [
        "# Replication across independent simulated datasets",
        "",
        "> **Synthetic data only.** Each run generates a new simulated crew history (different events, noise "
        "and missing data) and retrains every model with a new seed. The spread shows run-to-run variability "
        "of the method on simulated data; it is not evidence of real-world or clinical performance.",
        "",
        f"Seeds: {', '.join(map(str, seeds))} ({len(seeds)} runs). Configuration: `{study['config_name']}`. "
        f"Commit `{study['git_commit'] or 'unknown'}`. Generated {study['created_at']}. Values are mean ± sample "
        "standard deviation across runs.",
        "",
        "## Anomaly detection (test split)",
        "",
        "| Model | F1 | AUROC | AUPRC | False-positive rate | False-negative rate | Event recall |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in study["anomaly_models"]:
        p = f"anomaly.{name}."
        lines.append(f"| {name} | {cell(p + 'f1')} | {cell(p + 'auroc')} | {cell(p + 'auprc')} | "
                     f"{cell(p + 'false_alarm_rate', 4)} | {cell(p + 'false_negative_rate')} | {cell(p + 'event_recall', 2)} |")
    lines += ["", "## Forecasting (test split, physical units)", ""]
    for sig, unit in (("heart_rate", "bpm"), ("spo2", "%"), ("respiratory_rate", "breaths/min"), ("temperature_c", "°C")):
        lines += [f"### {sig.replace('_', ' ')} ({unit})", "",
                  "| Model | MAE 1h | MAE 24h | RMSE 1h | Coverage 1h (90% nominal) | MAPE 1h (%) |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for name in study["forecast_models"]:
            p = f"forecast.{name}.{sig}."
            lines.append(f"| {name} | {cell(p + '1h.mae')} | {cell(p + '24h.mae')} | {cell(p + '1h.rmse')} | "
                         f"{cell(p + '1h.coverage')} | {cell(p + '1h.mape_pct', 2) if (p + '1h.mape_pct') in s else 'not meaningful'} |")
        lines.append("")
    lines += [
        "## Reading the spread",
        "",
        "- Two models whose means differ by less than about two standard deviations should not be ranked "
        "against each other on this evidence.",
        "- With only a few runs the standard deviation is itself uncertain; it is a rough guide, not a "
        "confidence interval.",
        "- All runs share the simulator's physiology and event design, so this measures sensitivity to the "
        "random draw, not to a different population or real sensors.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 11, 23])
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    base = ExperimentConfig()
    if args.quick:
        base = base.quick()
    per_seed: dict[int, dict] = {}
    runtimes = {}
    with tempfile.TemporaryDirectory(prefix="astra-seed-study-") as tmp:
        for seed in args.seeds:
            cfg = replace(base, name=f"{base.name}-seed{seed}", seed=seed, dataset=replace(base.dataset, seed=seed))
            r = run(cfg, Path(tmp), register=False)
            per_seed[seed] = collect(r)
            runtimes[seed] = r["runtime_seconds"]
            anomaly_models = [n for n, b in r["anomaly"]["models"].items() if "test" in b] + ["ensemble", "fixed_thresholds"]
            forecast_models = [n for n, b in r["forecast"]["models"].items() if "by_signal" in b]
            print(f"seed {seed}: ensemble F1 {per_seed[seed]['anomaly.ensemble.f1']}, "
                  f"XGBoost HR MAE 1h {per_seed[seed].get('forecast.xgboost.heart_rate.1h.mae')}", flush=True)
    study = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(BACKEND),
        "config_name": base.name,
        "quick": args.quick,
        "seeds": args.seeds,
        "runtime_seconds": runtimes,
        "anomaly_models": anomaly_models,
        "forecast_models": forecast_models,
        "summary": summarise(per_seed),
    }
    stem = "seed-study-quick" if args.quick else "seed-study"
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{stem}.json").write_text(json.dumps(study, indent=2) + "\n", encoding="utf-8", newline="\n")
    (args.out / f"{stem}.md").write_text(render(study), encoding="utf-8", newline="\n")
    print(args.out / f"{stem}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
