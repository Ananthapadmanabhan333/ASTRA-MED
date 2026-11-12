"""Anomaly detectors with one interface: fit, score, calibrate, explain, save/load.

Scores are oriented so that **higher means more anomalous**. A detector's threshold is chosen on
validation data to hit a target false-alarm rate; ``score / threshold >= 1`` means "flagged", which
puts every detector on a common scale for the ensemble.

Explanations are per-feature contributions that sum to 1 for each row:

* statistical: each signal's share of the personal-baseline deviation
* autoencoder: each feature's share of the reconstruction error
* Isolation Forest, LOF, One-Class SVM: occlusion. Reset one feature to its baseline value and
  measure how much the anomaly score falls. This is a model-agnostic attribution, not SHAP.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from app.ai.features import FEATURE_GROUPS

try:  # PyTorch is optional at runtime; the autoencoder is skipped without it.
    import torch
    from torch import nn

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    TORCH_AVAILABLE = False

STATS_FEATURES = FEATURE_GROUPS["level"] + FEATURE_GROUPS["sustained"]


def _normalise_rows(m: np.ndarray) -> np.ndarray:
    m = np.clip(m, 0.0, None)
    sums = m.sum(axis=1, keepdims=True)
    return np.divide(m, sums, out=np.zeros_like(m), where=sums > 0)


class Detector:
    name = "base"
    label = "Base detector"
    description = ""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.feature_names: list[str] = []
        self.threshold: float | None = None
        self.reference: np.ndarray | None = None

    # -- training ------------------------------------------------------------------
    def fit(self, X: np.ndarray, names: list[str]) -> Detector:
        self.feature_names = list(names)
        # Occlusion reference: "at personal baseline" (0 in z-space) for deviation features,
        # the training median for context and quality features.
        ref = np.median(X, axis=0)
        for i, n in enumerate(names):
            if n.split("_", 1)[0] in {"z", "d", "sust", "trend"}:
                ref[i] = 0.0
        self.reference = ref
        self._fit(X)
        return self

    def _fit(self, X: np.ndarray) -> None:
        raise NotImplementedError

    def score(self, X: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def calibrate(self, normal_scores: np.ndarray, false_alarm_rate: float = 0.01) -> float:
        self.threshold = float(np.quantile(normal_scores, 1 - false_alarm_rate))
        return self.threshold

    def normalised(self, X: np.ndarray) -> np.ndarray:
        if not self.threshold:
            raise RuntimeError(f"{self.name} is not calibrated")
        return self.score(X) / self.threshold

    def matrix(self, F: pd.DataFrame) -> np.ndarray:
        """This detector's own feature columns from a full feature frame."""
        return F[self.feature_names].to_numpy(dtype=float)

    # -- explanation -----------------------------------------------------------------
    def contributions(self, X: np.ndarray) -> np.ndarray:
        """Occlusion attribution (n, d); rows sum to 1 (or 0 when nothing stands out)."""
        assert self.reference is not None
        base = self.score(X)
        n, d = X.shape
        stacked = np.repeat(X[:, None, :], d, axis=1)
        idx = np.arange(d)
        stacked[:, idx, idx] = self.reference[idx]
        occluded = self.score(stacked.reshape(n * d, d)).reshape(n, d)
        return _normalise_rows(base[:, None] - occluded)

    # -- persistence -----------------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, directory / f"{self.name}.joblib")

    @staticmethod
    def load(path: Path) -> Detector:
        # joblib uses pickle, which can execute code. Only artifacts written by this project's
        # training pipeline are loaded, and app.ai.registry verifies each file's SHA-256 against
        # the registry before calling this. Never point this at files from an untrusted source.
        return joblib.load(path)

    def info(self) -> dict[str, Any]:
        return {"name": self.name, "label": self.label, "description": self.description,
                "threshold": self.threshold, "n_features": len(self.feature_names)}


class StatisticalDetector(Detector):
    name = "statistical"
    label = "Statistical (personal baseline)"
    description = "Largest robust z-score against the person's own time-of-day and activity baseline, with sustained deviation weighted up."

    SUSTAINED_WEIGHT = 1.5

    def _fit(self, X: np.ndarray) -> None:
        self._z = [self.feature_names.index(f) for f in FEATURE_GROUPS["level"] if f in self.feature_names]
        self._sust = [self.feature_names.index(f) for f in FEATURE_GROUPS["sustained"] if f in self.feature_names]

    def _terms(self, X: np.ndarray) -> np.ndarray:
        terms = np.abs(X[:, self._z])
        if self._sust:
            terms = np.maximum(terms, self.SUSTAINED_WEIGHT * np.abs(X[:, self._sust]))
        return terms

    def score(self, X: np.ndarray) -> np.ndarray:
        return self._terms(X).max(axis=1)

    def contributions(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros_like(X, dtype=float)
        terms = self._terms(X)
        out[:, self._z] = np.where(terms > 1.5, terms - 1.5, 0.0)  # only deviations beyond ~normal
        return _normalise_rows(out)


class IsolationForestDetector(Detector):
    name = "isolation_forest"
    label = "Isolation Forest"
    description = "Ensemble of random trees; anomalies are isolated in fewer splits."

    def _fit(self, X: np.ndarray) -> None:
        self.model = IsolationForest(n_estimators=300, max_samples=512, random_state=self.seed, n_jobs=-1)
        self.model.fit(X)

    def score(self, X: np.ndarray) -> np.ndarray:
        return -self.model.score_samples(X)


class LOFDetector(Detector):
    name = "lof"
    label = "Local Outlier Factor"
    description = "Density of each window relative to its 40 nearest normal neighbours."
    MAX_TRAIN = 12_000

    def _fit(self, X: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        sample = X[rng.choice(len(X), min(len(X), self.MAX_TRAIN), replace=False)]
        self.scaler = StandardScaler().fit(sample)
        self.model = LocalOutlierFactor(n_neighbors=40, novelty=True, n_jobs=-1)
        self.model.fit(self.scaler.transform(sample))

    def score(self, X: np.ndarray) -> np.ndarray:
        return -self.model.score_samples(self.scaler.transform(X))


class OneClassSVMDetector(Detector):
    name = "one_class_svm"
    label = "One-Class SVM"
    description = "RBF-kernel boundary around normal windows (nu = 0.02)."
    MAX_TRAIN = 4_000

    def _fit(self, X: np.ndarray) -> None:
        rng = np.random.default_rng(self.seed)
        sample = X[rng.choice(len(X), min(len(X), self.MAX_TRAIN), replace=False)]
        self.scaler = StandardScaler().fit(sample)
        self.model = OneClassSVM(kernel="rbf", gamma="scale", nu=0.02)
        self.model.fit(self.scaler.transform(sample))

    def score(self, X: np.ndarray) -> np.ndarray:
        return -self.model.decision_function(self.scaler.transform(X))


if TORCH_AVAILABLE:

    class _AE(nn.Module):
        def __init__(self, d: int) -> None:
            super().__init__()
            self.encoder = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, 16), nn.ReLU())
            self.decoder = nn.Sequential(nn.Linear(16, 64), nn.ReLU(), nn.Linear(64, d))

        def forward(self, x):  # noqa: D401
            return self.decoder(self.encoder(x))


class AutoencoderDetector(Detector):
    name = "autoencoder"
    label = "Autoencoder"
    description = "Neural network trained to reconstruct normal windows; large reconstruction error is anomalous."

    def __init__(self, seed: int = 0, epochs: int = 40, batch_size: int = 256, lr: float = 1e-3) -> None:
        super().__init__(seed)
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is not installed; the autoencoder detector is unavailable")
        self.epochs, self.batch_size, self.lr = epochs, batch_size, lr
        self.history: list[float] = []

    def _fit(self, X: np.ndarray) -> None:
        torch.manual_seed(self.seed)
        self.scaler = StandardScaler().fit(X)
        data = torch.tensor(self.scaler.transform(X), dtype=torch.float32)
        self.model = _AE(X.shape[1])
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        gen = torch.Generator().manual_seed(self.seed)
        self.model.train()
        for _ in range(self.epochs):
            perm = torch.randperm(len(data), generator=gen)
            total = 0.0
            for i in range(0, len(data), self.batch_size):
                batch = data[perm[i : i + self.batch_size]]
                opt.zero_grad()
                loss = ((self.model(batch) - batch) ** 2).mean()
                loss.backward()
                opt.step()
                total += loss.item() * len(batch)
            self.history.append(total / len(data))
        self.model.eval()

    def _errors(self, X: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            x = torch.tensor(self.scaler.transform(X), dtype=torch.float32)
            return ((self.model(x) - x) ** 2).numpy()

    def score(self, X: np.ndarray) -> np.ndarray:
        return self._errors(X).mean(axis=1)

    def contributions(self, X: np.ndarray) -> np.ndarray:
        return _normalise_rows(self._errors(X))

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), directory / "autoencoder.pt")
        state = {k: v for k, v in self.__dict__.items() if k != "model"}
        joblib.dump(state, directory / "autoencoder.meta.joblib")

    @staticmethod
    def load_from(directory: Path) -> AutoencoderDetector:
        # Trusted, hash-verified artifact only (see Detector.load). Weights load with weights_only=True.
        state = joblib.load(directory / "autoencoder.meta.joblib")
        det = AutoencoderDetector.__new__(AutoencoderDetector)
        det.__dict__.update(state)
        det.model = _AE(len(det.feature_names))
        det.model.load_state_dict(torch.load(directory / "autoencoder.pt", weights_only=True))
        det.model.eval()
        return det


DETECTOR_CLASSES: dict[str, type[Detector]] = {
    "statistical": StatisticalDetector,
    "isolation_forest": IsolationForestDetector,
    "lof": LOFDetector,
    "one_class_svm": OneClassSVMDetector,
    "autoencoder": AutoencoderDetector,
}


def available_detectors() -> list[str]:
    return [n for n in DETECTOR_CLASSES if n != "autoencoder" or TORCH_AVAILABLE]


class Ensemble:
    """Weighted mean of calibrated scores across detectors, plus a vote count.

    Weights come from validation data only (see the experiment runner); equal weights otherwise.
    """

    name = "ensemble"
    label = "Ensemble (weighted mean of calibrated scores)"

    def __init__(self, detectors: dict[str, Detector], weights: dict[str, float] | None = None) -> None:
        self.detectors = detectors
        self.weights = weights or {n: 1.0 for n in detectors}
        self.threshold: float | None = None

    def normalised_matrix(self, F: pd.DataFrame) -> np.ndarray:
        """(n, detectors) calibrated scores; each detector reads its own feature columns."""
        return np.column_stack([d.normalised(d.matrix(F)) for d in self.detectors.values()])

    def score_from_matrix(self, m: np.ndarray) -> np.ndarray:
        w = np.array([self.weights.get(n, 0.0) for n in self.detectors], dtype=float)
        w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / len(w))
        return m @ w

    def score(self, F: pd.DataFrame) -> np.ndarray:
        return self.score_from_matrix(self.normalised_matrix(F))

    def calibrate(self, normal_scores: np.ndarray, false_alarm_rate: float = 0.01) -> float:
        self.threshold = float(np.quantile(normal_scores, 1 - false_alarm_rate))
        return self.threshold


def save_detectors(detectors: dict[str, Detector], directory: Path, ensemble: Ensemble) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for d in detectors.values():
        d.save(directory)
    (directory / "anomaly.json").write_text(
        json.dumps(
            {
                "detectors": list(detectors),
                "feature_names": {n: d.feature_names for n, d in detectors.items()},
                "thresholds": {n: d.threshold for n, d in detectors.items()},
                "ensemble_threshold": ensemble.threshold,
                "ensemble_weights": ensemble.weights,
            },
            indent=2,
        )
    )


def load_detectors(directory: Path) -> tuple[dict[str, Detector], Ensemble]:
    meta = json.loads((directory / "anomaly.json").read_text())
    detectors: dict[str, Detector] = {}
    for name in meta["detectors"]:
        if name == "autoencoder":
            if TORCH_AVAILABLE and (directory / "autoencoder.pt").exists():
                detectors[name] = AutoencoderDetector.load_from(directory)
        else:
            detectors[name] = Detector.load(directory / f"{name}.joblib")
    ensemble = Ensemble(detectors, meta.get("ensemble_weights"))
    ensemble.threshold = meta.get("ensemble_threshold")
    return detectors, ensemble
