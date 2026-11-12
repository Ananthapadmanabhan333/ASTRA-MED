"""Shared data preparation for experiments: windows, train-only baselines, features, labels.

Leakage controls:
* baselines (and therefore every z-score) are fitted on *training* windows only, and only on
  clean ones (no labelled or partially labelled event);
* features are causal, so a window never sees later data;
* splits are chronological and day-aligned (see datasets.synthetic.chronological_split).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.ai.baseline import PersonalBaseline
from app.ai.datasets.synthetic import Split
from app.ai.features import ALL_GROUPS, FeatureFrame, build_features
from app.ai.signals import WINDOW_MINUTES
from app.ai.windows import to_windows

LABEL_COLUMNS = ("label", "event_level", "event_id", "event_type", "event_kind", "artefact")


def _labels_per_window(samples: pd.DataFrame) -> pd.DataFrame:
    s = samples.assign(window=samples["ts"].dt.floor(f"{WINDOW_MINUTES}min"))
    g = s.groupby("window")
    out = pd.DataFrame(
        {
            "label": g["label"].max().astype(bool),
            "event_level": g["event_level"].max(),
            "event_id": g["event_id"].first(),
            "event_type": g["event_type"].first(),
            "event_kind": g["event_kind"].first(),
            "artefact": g["artefact"].max().astype(bool),
        }
    )
    out.index.name = "ts"
    return out


@dataclass
class PreparedData:
    split: Split
    groups: tuple[str, ...]
    windows: dict[str, pd.DataFrame] = field(default_factory=dict)
    baselines: dict[str, PersonalBaseline] = field(default_factory=dict)
    features: dict[str, FeatureFrame] = field(default_factory=dict)

    @property
    def feature_names(self) -> list[str]:
        return next(iter(self.features.values())).names

    def stacked(self, part: str, clean_only: bool = False) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """(X, y, meta) for one split across all crew. ``clean_only`` keeps windows with no event."""
        xs, ys, metas = [], [], []
        for aid, ff in self.features.items():
            w = self.windows[aid]
            mask = self.split.name(w.index) == part
            if clean_only:
                mask &= (w["event_level"].fillna(0).to_numpy() == 0) & ~w["artefact"].to_numpy()
            xs.append(ff.features.to_numpy()[mask])
            ys.append(w["label"].to_numpy()[mask])
            meta = w.loc[mask, ["state", *LABEL_COLUMNS]].copy()
            meta["astronaut_id"] = aid
            metas.append(meta)
        return np.vstack(xs), np.concatenate(ys), pd.concat(metas)


def prepare(samples: pd.DataFrame, split: Split, groups: tuple[str, ...] = ALL_GROUPS, seed: int = 0) -> PreparedData:
    prepared = PreparedData(split=split, groups=groups)
    for aid, group in samples.groupby("astronaut_id", sort=True):
        windows = to_windows(group)
        labels = _labels_per_window(group).reindex(windows.index)
        labels["label"] = labels["label"].fillna(False).astype(bool)
        labels["artefact"] = labels["artefact"].fillna(False).astype(bool)
        windows = windows.join(labels)
        train_clean = windows[
            (split.name(windows.index) == "train")
            & (windows["event_level"].fillna(0) == 0)
        ]
        baseline = PersonalBaseline.fit(aid, train_clean, seed=seed)
        prepared.windows[aid] = windows
        prepared.baselines[aid] = baseline
        prepared.features[aid] = build_features(windows, baseline, groups)
    return prepared
