"""Forecasting models. All predict (N, HORIZON, 4) personal-normalised values.

Baselines (no training): persistence, seasonal naive (same time yesterday) and schedule-aware
climatology (the person's baseline expectation for the planned activity at the target time).

Learned models:
  xgboost  gradient-boosted trees, one model per signal with the horizon as a feature, on
           engineered lag, rolling, cross-signal and known-future features. Explained with
           XGBoost's native TreeSHAP (exact SHAP values for tree ensembles).
  lstm/gru recurrent encoder over the last 24 h, plus the planned next 24 h, predicting a
           correction to climatology.
  tcn      dilated causal convolutions (receptive field covers 24 h), same head.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.ai.forecasting.data import (
    FUTURE_CHANNELS,
    HORIZON,
    LOOKBACK,
    PAST_CHANNELS,
    STEPS_PER_HOUR,
    SampleSet,
)
from app.ai.signals import FORECAST_SIGNALS

try:
    import torch
    from torch import nn

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False

N_SIG = len(FORECAST_SIGNALS)


class Forecaster:
    name = "base"
    label = "Base"
    family = "baseline"
    trainable = False

    def fit(self, train: SampleSet, val: SampleSet) -> Forecaster:
        return self

    def predict(self, s: SampleSet) -> np.ndarray:
        raise NotImplementedError

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)

    def info(self) -> dict:
        return {"name": self.name, "label": self.label, "family": self.family}


class Persistence(Forecaster):
    name, label = "persistence", "Persistence (last value)"

    def predict(self, s: SampleSet) -> np.ndarray:
        return np.repeat(s.past[:, -1:, :N_SIG], HORIZON, axis=1)


class SeasonalNaive(Forecaster):
    name, label = "seasonal_naive", "Seasonal naive (same time yesterday)"

    def predict(self, s: SampleSet) -> np.ndarray:
        assert LOOKBACK == HORIZON  # step t+1+h maps to past index h
        return s.past[:, :, :N_SIG].copy()


class Climatology(Forecaster):
    name, label = "climatology", "Personal climatology (baseline for planned activity)"

    def predict(self, s: SampleSet) -> np.ndarray:
        return s.clim.copy()


# ---------------------------------------------------------------------- XGBoost ----
XGB_HORIZON_STEPS = (1, 2, 3, 4, 6, 8, 12, 16, 20, 24, 30, 36, 42, 48)


def xgb_feature_names(j: int) -> list[str]:
    own = FORECAST_SIGNALS[j]
    others = [s for k, s in enumerate(FORECAST_SIGNALS) if k != j]
    return [
        f"{own}_now", f"{own}_lag30m", f"{own}_lag1h", f"{own}_lag2h", f"{own}_lag6h", f"{own}_lag12h",
        f"{own}_same_time_yesterday", f"{own}_mean_3h", f"{own}_mean_12h", f"{own}_std_12h", f"{own}_slope_3h",
        *[f"{o}_now" for o in others],
        "activity_now", "asleep_now",
        "target_activity", "target_asleep", "target_tod_sin", "target_tod_cos",
        "horizon_hours", f"{own}_baseline_at_target",
        f"{own}_deviation_now", f"{own}_deviation_mean_3h",
    ]


# Human-readable groups for explanations.
def xgb_feature_group(name: str) -> str:
    if name.endswith("_baseline_at_target"):
        return "Personal baseline for the planned activity"
    if "_deviation_" in name:
        return "Current deviation from personal baseline"
    if name.startswith("target_"):
        return "Planned activity and time of day at the target time"
    if name == "horizon_hours":
        return "How far ahead"
    if name in ("activity_now", "asleep_now"):
        return "Current activity"
    if name.endswith("_same_time_yesterday"):
        return "Same time yesterday"
    if any(k in name for k in ("_mean_", "_std_", "_slope_")):
        return "Recent trend"
    if "_lag" in name:
        return "Recent values"
    if name.endswith("_now"):
        return "Current values"
    return name


def _xgb_features(s: SampleSet, j: int, steps: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows = sample × horizon. Returns (X, y, (sample_idx, step))."""
    own = s.past[:, :, j]
    others = [k for k in range(N_SIG) if k != j]
    base = np.column_stack(
        [
            own[:, -1], own[:, -2], own[:, -3], own[:, -5], own[:, -13], own[:, -25],
            np.zeros(len(own)),  # placeholder: same time yesterday depends on the horizon
            own[:, -6:].mean(1), own[:, -24:].mean(1), own[:, -24:].std(1), (own[:, -1] - own[:, -6]) / 5,
            *[s.past[:, -1, k] for k in others],
            s.past[:, -1, N_SIG], s.past[:, -1, N_SIG + 1],
        ]
    )
    rows, ys, keys = [], [], []
    for h in steps:
        b = base.copy()
        b[:, 6] = own[:, h - 1]
        rows.append(
            np.column_stack([
                b, s.future[:, h - 1, :], np.full(len(own), h / STEPS_PER_HOUR), s.clim[:, h - 1, j],
                s.past[:, -1, 2 * N_SIG + j], s.past[:, -6:, 2 * N_SIG + j].mean(1),
            ])
        )
        ys.append(s.target[:, h - 1, j])
        keys.append(np.column_stack([np.arange(len(own)), np.full(len(own), h)]))
    return np.vstack(rows).astype(np.float32), np.concatenate(ys), np.vstack(keys)


class XGBoostForecaster(Forecaster):
    name, label, family, trainable = "xgboost", "XGBoost (engineered features)", "tree", True

    def __init__(self, seed: int = 0, n_estimators: int = 600, max_depth: int = 5, learning_rate: float = 0.05,
                 exclude: tuple[str, ...] = ()) -> None:
        """``exclude``: substrings of feature names to drop (used for ablation studies)."""
        self.seed = seed
        self.exclude = tuple(exclude)
        self.params = {
            "objective": "reg:squarederror", "max_depth": max_depth, "eta": learning_rate,
            "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5, "seed": seed, "nthread": 4,
        }
        self.n_estimators = n_estimators
        self.boosters: dict[str, object] = {}
        self.best_iterations: dict[str, int] = {}

    def _keep(self, j: int) -> tuple[list[int], list[str]]:
        names = xgb_feature_names(j)
        keep = [i for i, n in enumerate(names) if not any(p in n for p in self.exclude)]
        return keep, [names[i] for i in keep]

    def fit(self, train: SampleSet, val: SampleSet) -> XGBoostForecaster:
        import xgboost as xgb

        for j, sig in enumerate(FORECAST_SIGNALS):
            keep, names = self._keep(j)
            Xtr, ytr, _ = _xgb_features(train, j, XGB_HORIZON_STEPS)
            Xva, yva, _ = _xgb_features(val, j, XGB_HORIZON_STEPS)
            ok_tr, ok_va = np.isfinite(ytr), np.isfinite(yva)
            dtr = xgb.DMatrix(Xtr[ok_tr][:, keep], label=ytr[ok_tr], feature_names=names)
            dva = xgb.DMatrix(Xva[ok_va][:, keep], label=yva[ok_va], feature_names=names)
            booster = xgb.train(
                self.params, dtr, num_boost_round=self.n_estimators, evals=[(dva, "val")],
                early_stopping_rounds=40, verbose_eval=False,
            )
            self.boosters[sig] = booster
            self.best_iterations[sig] = int(booster.best_iteration)
        return self

    def predict_steps(self, s: SampleSet, j: int) -> tuple[np.ndarray, np.ndarray]:
        import xgboost as xgb

        sig = FORECAST_SIGNALS[j]
        keep, names = self._keep(j)
        X, _, keys = _xgb_features(s, j, XGB_HORIZON_STEPS)
        booster = self.boosters[sig]
        pred = booster.predict(
            xgb.DMatrix(X[:, keep], feature_names=names), iteration_range=(0, self.best_iterations[sig] + 1)
        )
        return pred, keys

    def predict(self, s: SampleSet) -> np.ndarray:
        out = np.zeros((len(s), HORIZON, N_SIG), dtype=np.float32)
        grid = np.arange(1, HORIZON + 1)
        for j in range(N_SIG):
            pred, keys = self.predict_steps(s, j)
            table = np.zeros((len(s), len(XGB_HORIZON_STEPS)), dtype=np.float32)
            for col, h in enumerate(XGB_HORIZON_STEPS):
                table[:, col] = pred[keys[:, 1] == h]
            for i in range(len(s)):
                out[i, :, j] = np.interp(grid, XGB_HORIZON_STEPS, table[i])
        return out

    def shap(self, s: SampleSet, j: int, step: int) -> tuple[np.ndarray, list[str]]:
        """Exact TreeSHAP contributions (N, n_features + bias) for one signal and horizon step."""
        import xgboost as xgb

        sig = FORECAST_SIGNALS[j]
        keep, names = self._keep(j)
        X, _, _ = _xgb_features(s, j, (step,))
        contribs = self.boosters[sig].predict(
            xgb.DMatrix(X[:, keep], feature_names=names),
            pred_contribs=True, iteration_range=(0, self.best_iterations[sig] + 1),
        )
        return contribs, [*names, "bias"]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for sig, booster in self.boosters.items():
            booster.save_model(str(directory / f"xgboost_{sig}.json"))  # JSON: no pickle involved
        (directory / "xgboost.meta.json").write_text(
            json.dumps({"params": self.params, "n_estimators": self.n_estimators, "best_iterations": self.best_iterations,
                        "exclude": list(self.exclude)}, indent=2)
        )

    @classmethod
    def load(cls, directory: Path) -> XGBoostForecaster:
        import xgboost as xgb

        meta = json.loads((directory / "xgboost.meta.json").read_text())
        model = cls(seed=meta["params"]["seed"], exclude=tuple(meta.get("exclude", ())))
        model.params, model.n_estimators, model.best_iterations = meta["params"], meta["n_estimators"], meta["best_iterations"]
        for sig in FORECAST_SIGNALS:
            booster = xgb.Booster()
            booster.load_model(str(directory / f"xgboost_{sig}.json"))
            model.boosters[sig] = booster
        return model


# ---------------------------------------------------------------- neural models ----
if TORCH_AVAILABLE:

    class _TCNBlock(nn.Module):
        def __init__(self, c_in: int, c_out: int, dilation: int, kernel: int = 3) -> None:
            super().__init__()
            self.pad = (kernel - 1) * dilation
            self.conv1 = nn.Conv1d(c_in, c_out, kernel, dilation=dilation)
            self.conv2 = nn.Conv1d(c_out, c_out, kernel, dilation=dilation)
            self.skip = nn.Conv1d(c_in, c_out, 1) if c_in != c_out else nn.Identity()
            self.act = nn.ReLU()

        def forward(self, x):
            y = self.act(self.conv1(nn.functional.pad(x, (self.pad, 0))))
            y = self.act(self.conv2(nn.functional.pad(y, (self.pad, 0))))
            return self.act(y + self.skip(x))

    class _SeqNet(nn.Module):
        def __init__(self, arch: str, hidden: int = 64) -> None:
            super().__init__()
            self.arch = arch
            c_in = len(PAST_CHANNELS)
            if arch == "lstm":
                self.encoder = nn.LSTM(c_in, hidden, batch_first=True)
                enc_dim = hidden
            elif arch == "gru":
                self.encoder = nn.GRU(c_in, hidden, batch_first=True)
                enc_dim = hidden
            else:  # tcn: dilations 1..16, kernel 3 -> receptive field 1 + 2*2*(1+2+4+8+16) = 125 steps
                ch = 32
                self.encoder = nn.Sequential(*[_TCNBlock(c_in if i == 0 else ch, ch, d) for i, d in enumerate((1, 2, 4, 8, 16))])
                enc_dim = ch
            head_in = enc_dim + HORIZON * len(FUTURE_CHANNELS) + N_SIG
            self.head = nn.Sequential(nn.Linear(head_in, 256), nn.ReLU(), nn.Dropout(0.1), nn.Linear(256, HORIZON * N_SIG))

        def forward(self, past, future, clim):
            if self.arch in ("lstm", "gru"):
                out, _ = self.encoder(past)
                enc = out[:, -1]
            else:
                enc = self.encoder(past.transpose(1, 2))[:, :, -1]
            z = torch.cat([enc, future.flatten(1), past[:, -1, :N_SIG]], dim=1)
            return clim + self.head(z).view(-1, HORIZON, N_SIG)


class SequenceForecaster(Forecaster):
    family, trainable = "neural", True
    LABELS = {"lstm": "LSTM", "gru": "GRU", "tcn": "Temporal Convolutional Network"}

    def __init__(self, arch: str, seed: int = 0, epochs: int = 60, batch_size: int = 128, lr: float = 1e-3,
                 patience: int = 10) -> None:
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is not installed; neural forecasters are unavailable")
        self.arch, self.seed, self.epochs, self.batch_size, self.lr, self.patience = arch, seed, epochs, batch_size, lr, patience
        self.name, self.label = arch, self.LABELS[arch]
        self.history: list[dict] = []
        self.net = None

    @staticmethod
    def _tensors(s: SampleSet):
        target = np.nan_to_num(s.target, nan=0.0)
        mask = np.isfinite(s.target).astype(np.float32)
        return [torch.tensor(a) for a in (s.past, s.future, s.clim, target, mask)]

    def fit(self, train: SampleSet, val: SampleSet) -> SequenceForecaster:
        torch.manual_seed(self.seed)
        self.net = _SeqNet(self.arch)
        opt = torch.optim.Adam(self.net.parameters(), lr=self.lr, weight_decay=1e-5)
        tr, va = self._tensors(train), self._tensors(val)
        gen = torch.Generator().manual_seed(self.seed)
        best, best_state, bad = float("inf"), None, 0
        for epoch in range(self.epochs):
            self.net.train()
            perm = torch.randperm(len(tr[0]), generator=gen)
            for i in range(0, len(perm), self.batch_size):
                idx = perm[i : i + self.batch_size]
                p, f, c, y, m = (t[idx] for t in tr)
                opt.zero_grad()
                loss = (((self.net(p, f, c) - y) ** 2) * m).sum() / m.sum().clamp(min=1)
                loss.backward()
                opt.step()
            self.net.eval()
            with torch.no_grad():
                p, f, c, y, m = va
                val_loss = float((((self.net(p, f, c) - y) ** 2) * m).sum() / m.sum().clamp(min=1))
            self.history.append({"epoch": epoch + 1, "val_mse": round(val_loss, 5)})
            if val_loss < best - 1e-5:
                best, bad = val_loss, 0
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
            else:
                bad += 1
                if bad >= self.patience:
                    break
        if best_state is not None:
            self.net.load_state_dict(best_state)
        self.net.eval()
        return self

    def predict(self, s: SampleSet) -> np.ndarray:
        p, f, c, _, _ = self._tensors(s)
        with torch.no_grad():
            return self.net(p, f, c).numpy()

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        torch.save(self.net.state_dict(), directory / f"{self.arch}.pt")
        (directory / f"{self.arch}.meta.json").write_text(
            json.dumps({"arch": self.arch, "seed": self.seed, "epochs_run": len(self.history), "history": self.history}, indent=2)
        )

    @classmethod
    def load(cls, directory: Path, arch: str) -> SequenceForecaster:
        meta = json.loads((directory / f"{arch}.meta.json").read_text())
        model = cls(arch, seed=meta["seed"])
        model.history = meta["history"]
        model.net = _SeqNet(arch)
        model.net.load_state_dict(torch.load(directory / f"{arch}.pt", weights_only=True))
        model.net.eval()
        return model


def baseline_forecasters() -> list[Forecaster]:
    return [Persistence(), SeasonalNaive(), Climatology()]
