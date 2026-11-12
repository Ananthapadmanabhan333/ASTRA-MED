from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from app.ai.datasets.synthetic import SyntheticConfig
from app.ai.features import ALL_GROUPS

# Candidate feature sets. Each learned detector picks one on *validation* data; the test split is
# only used to report every candidate's performance (the ablation table).
ANOMALY_ABLATIONS: dict[str, tuple[str, ...]] = {
    "all_features": ALL_GROUPS,
    "without_sudden": tuple(g for g in ALL_GROUPS if g != "sudden"),
    "without_context": tuple(g for g in ALL_GROUPS if g != "context"),
    "without_dynamics": ("level", "context", "quality"),
    "level_only": ("level",),
}

FORECAST_ABLATIONS: dict[str, tuple[str, ...]] = {
    "xgboost_without_planned_schedule": ("target_", "_baseline_at_target"),
    "xgboost_without_baseline_deviation": ("_deviation_",),
    "xgboost_without_recent_values": ("_now", "_lag", "_mean_", "_std_", "_slope_", "_deviation_"),
}


@dataclass(frozen=True)
class ExperimentConfig:
    name: str = "default"
    seed: int = 7
    dataset: SyntheticConfig = field(default_factory=SyntheticConfig)
    train_frac: float = 0.6
    val_frac: float = 0.2
    false_alarm_rate: float = 0.01
    persistence_windows: int = 2  # consecutive flagged windows before an operational warning
    detectors: tuple[str, ...] = ("statistical", "isolation_forest", "lof", "one_class_svm", "autoencoder")
    autoencoder_epochs: int = 40
    anomaly_ablations: tuple[str, ...] = tuple(ANOMALY_ABLATIONS)  # candidate feature sets
    ensemble_min_relative_auprc: float = 0.8  # ensemble members need >= 80% of the best validation AUPRC
    forecasters: tuple[str, ...] = ("persistence", "seasonal_naive", "climatology", "xgboost", "lstm", "gru", "tcn")
    forecast_ablations: tuple[str, ...] = tuple(FORECAST_ABLATIONS)
    nn_epochs: int = 60
    interval_alpha: float = 0.1
    serving_forecaster: str = "xgboost"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ExperimentConfig:
        d = dict(d)
        dataset = SyntheticConfig(**_tuples(d.pop("dataset", {})))
        return cls(dataset=dataset, **_tuples(d))

    @classmethod
    def from_file(cls, path: Path) -> ExperimentConfig:
        return cls.from_dict(json.loads(Path(path).read_text()))

    def quick(self) -> ExperimentConfig:
        """Small, fast variant for tests and smoke runs (not for reported results)."""
        return replace(
            self,
            name=f"{self.name}-quick",
            dataset=replace(self.dataset, days=12, crew=self.dataset.crew[:2], sudden_events_per_day=2.0,
                            gradual_events_per_week=2.0),
            autoencoder_epochs=3,
            nn_epochs=2,
            anomaly_ablations=("all_features", "level_only"),
            forecast_ablations=("xgboost_without_planned_schedule",),
        )


def _tuples(d: dict) -> dict:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in d.items()}
