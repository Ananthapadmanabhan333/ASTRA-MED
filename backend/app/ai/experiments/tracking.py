"""Experiment tracking: an index of every registered model version and its headline results.

Each training run is already an immutable version directory (config, dataset fingerprint, git
commit, library versions, SHA-256 per file, full results). This module reads them all and writes a
single comparable table, so a reviewer can see what changed between runs without opening each one.

    python -m app.ai.experiments.tracking            # writes experiments/results/experiment-index.{json,md}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.ai.registry import ModelRegistry

BACKEND = Path(__file__).resolve().parents[3]
RESULTS_DIR = BACKEND / "experiments" / "results"


def _headline(results: dict[str, Any]) -> dict[str, Any]:
    an, fc = results.get("anomaly", {}), results.get("forecast", {})
    ens = an.get("ensemble", {}).get("test", {})
    xgb = fc.get("models", {}).get("xgboost", {}).get("by_signal", {})
    hr = xgb.get("heart_rate", {})
    return {
        "ensemble_f1": ens.get("f1"),
        "ensemble_auroc": ens.get("auroc"),
        "ensemble_fpr": ens.get("false_alarm_rate"),
        "ensemble_fnr": ens.get("false_negative_rate", None if ens.get("recall") is None else round(1 - ens["recall"], 4)),
        "ensemble_event_recall": an.get("ensemble", {}).get("events", {}).get("event_recall"),
        "xgboost_hr_mae_1h": hr.get("1h", {}).get("mae"),
        "xgboost_hr_mae_24h": hr.get("24h", {}).get("mae"),
        "xgboost_hr_coverage_1h": hr.get("1h", {}).get("coverage"),
    }


def build_index(artifacts_root: Path) -> list[dict[str, Any]]:
    registry = ModelRegistry(artifacts_root)
    latest = registry.latest()
    rows = []
    for entry in registry.versions():
        version = entry["version"]
        path = Path(artifacts_root) / version
        try:
            manifest = registry.manifest(version)
            results = json.loads((path / "results.json").read_text())
        except (OSError, ValueError):
            continue
        cfg = results.get("config", {})
        rows.append({
            "version": version,
            "latest": version == latest,
            "created_at": manifest.get("created_at"),
            "git_commit": manifest.get("git_commit"),
            "config_hash": manifest.get("config_hash"),
            "dataset_fingerprint": manifest.get("dataset_fingerprint"),
            "seed": cfg.get("seed"),
            "runtime_seconds": results.get("runtime_seconds"),
            "libraries": manifest.get("libraries"),
            **_headline(results),
        })
    return rows


def render_index(rows: list[dict[str, Any]]) -> str:
    def f(v: Any, nd: int = 3) -> str:
        return "n/a" if v is None else f"{v:.{nd}f}" if isinstance(v, float) else str(v)

    lines = [
        "# Experiment index",
        "",
        "Every registered model version, oldest first. All results are on **simulated** data (chronological "
        "test split); they are not clinical performance. Full details: `backend/artifacts/<version>/report.md`.",
        "",
        "| Version | Latest | Commit | Config | Dataset | Seed | Ensemble F1 | AUROC | FPR | FNR | Events | "
        "XGB HR MAE 1h | 24h | Coverage 1h |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| `{r['version']}` | {'yes' if r['latest'] else ''} | {r['git_commit'] or 'n/a'} | {r['config_hash']} | "
            f"{r['dataset_fingerprint']} | {r['seed']} | {f(r['ensemble_f1'])} | {f(r['ensemble_auroc'])} | "
            f"{f(r['ensemble_fpr'], 4)} | {f(r['ensemble_fnr'])} | {f(r['ensemble_event_recall'], 2)} | "
            f"{f(r['xgboost_hr_mae_1h'])} | {f(r['xgboost_hr_mae_24h'])} | {f(r['xgboost_hr_coverage_1h'], 3)} |"
        )
    lines += ["", "Versions with the same config hash and dataset fingerprint were trained from the same "
              "configuration; identical metrics between them show the pipeline is reproducible.", ""]
    return "\n".join(lines)


def write_index(artifacts_root: Path, out_dir: Path = RESULTS_DIR) -> Path:
    rows = build_index(artifacts_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "experiment-index.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n")
    md = out_dir / "experiment-index.md"
    md.write_text(render_index(rows), encoding="utf-8", newline="\n")
    return md


if __name__ == "__main__":
    from app.core.config import get_settings

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().ai_artifacts_path
    print(write_index(root))
