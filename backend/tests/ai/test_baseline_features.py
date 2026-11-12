from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ai.baseline import MIN_CELL_COUNT, MIN_STATE_COUNT, PersonalBaseline, rolling_stats
from app.ai.datasets.synthetic import SyntheticConfig, chronological_split, generate
from app.ai.features import ALL_GROUPS, build_features, feature_names
from app.ai.signals import SIGNALS
from app.ai.windows import drop_implausible, samples_to_frame, to_windows

START = pd.Timestamp("2026-01-05", tz="UTC")


def synthetic_windows(days: int = 6, seed: int = 1, hr_sleep: float = 52.0, hr_work: float = 66.0) -> pd.DataFrame:
    """Hand-made windows: sleep 00-07 UTC, work otherwise, with known means."""
    idx = pd.date_range(START, periods=days * 288, freq="5min", tz="UTC", name="ts")
    rng = np.random.default_rng(seed)
    asleep = idx.hour < 7
    df = pd.DataFrame(index=idx)
    df["heart_rate"] = np.where(asleep, hr_sleep, hr_work) + rng.normal(0, 2, len(idx))
    df["spo2"] = 98 + rng.normal(0, 0.3, len(idx))
    df["systolic"] = 118 + rng.normal(0, 3, len(idx))
    df["diastolic"] = 76 + rng.normal(0, 2, len(idx))
    df["temperature_c"] = 36.8 + rng.normal(0, 0.05, len(idx))
    df["respiratory_rate"] = 14 + rng.normal(0, 0.5, len(idx))
    df["state"] = np.where(asleep, "sleep", "work")
    df["activity_met"] = np.where(asleep, 0.9, 1.7)
    df["sleep_frac"] = asleep.astype(float)
    df["exercise_frac"] = 0.0
    df["n_samples"] = 1
    return df


# --------------------------------------------------------------------- baselines ----
def test_running_stats_match_numpy_and_update_equals_batch():
    w = synthetic_windows()
    batch = PersonalBaseline.fit("AST-01", w)
    incremental = PersonalBaseline("AST-01")
    for chunk in np.array_split(np.arange(len(w)), 7):
        incremental.update(w.iloc[chunk])
    overall = batch.cells["heart_rate|*|*"]
    assert overall.n == len(w)
    assert overall.mean == pytest.approx(w["heart_rate"].mean(), rel=1e-9)
    assert overall.std == pytest.approx(w["heart_rate"].std(ddof=1), rel=1e-9)
    inc = incremental.cells["heart_rate|*|*"]
    assert (inc.n, inc.mean) == (overall.n, pytest.approx(overall.mean))
    assert incremental.windows_seen == batch.windows_seen == len(w)


def test_baseline_is_activity_and_time_of_day_aware():
    b = PersonalBaseline.fit("AST-01", synthetic_windows())
    night = START + pd.Timedelta(hours=3)
    day = START + pd.Timedelta(hours=14)
    sleep_ref = b.reference("heart_rate", "sleep", night)
    work_ref = b.reference("heart_rate", "work", day)
    assert sleep_ref.level == work_ref.level == "cell"
    assert sleep_ref.center == pytest.approx(52, abs=0.6)
    assert work_ref.center == pytest.approx(66, abs=0.6)
    # The same 60 bpm is high for this person asleep and low at work.
    assert sleep_ref.z(60) > 3 and work_ref.z(60) < -2


def test_robust_centre_resists_contaminated_history():
    w = synthetic_windows()
    dirty = w.copy()
    spikes = dirty.sample(frac=0.05, random_state=0).index
    dirty.loc[spikes, "heart_rate"] += 60
    clean_ref = PersonalBaseline.fit("A", w).reference("heart_rate", "work", START + pd.Timedelta(hours=14))
    dirty_ref = PersonalBaseline.fit("A", dirty).reference("heart_rate", "work", START + pd.Timedelta(hours=14))
    assert abs(dirty_ref.center - clean_ref.center) < 1.0  # median barely moves
    assert dirty_ref.mean - clean_ref.mean > 2.0  # the plain mean does move


def test_thin_activity_is_never_scored_against_other_activities():
    w = synthetic_windows(days=1)  # sleep and work only, no exercise yet
    b = PersonalBaseline.fit("A", w)
    exercise = START + pd.Timedelta(hours=10)
    ref = b.reference("heart_rate", "exercise", exercise)
    # A pooled sleep+work reference would make an ordinary 120 bpm workout look like z ~ 10.
    assert ref.level == "overall" and not ref.comparable and ref.basis == "none"
    assert np.isnan(ref.z(120.0)) and ref.z_or_none(120.0) is None and ref.percentile_or_none(120.0) is None
    assert 55 < ref.center < 70  # still usable as a rough expectation (forecast climatology)

    # One hour of exercise history is enough for a whole-activity reference.
    workout = w.iloc[120:120 + MIN_STATE_COUNT].copy()
    workout["state"], workout["heart_rate"] = "exercise", 120.0
    b.update(workout)
    ref = b.reference("heart_rate", "exercise", exercise)
    assert ref.level == "state" and ref.comparable and abs(ref.z(120.0)) < 1

    # Unknown activity: the pooled reference is the right comparison.
    assert b.reference("heart_rate", None, exercise).comparable
    assert PersonalBaseline.fit("A", w.iloc[: MIN_CELL_COUNT - 5]).reference("heart_rate", "sleep", START).level == "state"
    small = PersonalBaseline.fit("A", w.iloc[: MIN_STATE_COUNT - 2])  # under an hour of sleep, nothing else
    assert small.reference("heart_rate", "sleep", START).level == "none"
    assert small.reference("heart_rate", "work", START).basis == "none"


def test_percentiles_reservoir_and_rank():
    b = PersonalBaseline.fit("A", synthetic_windows(days=8))
    cell = b.cells["heart_rate|work|*"]
    assert len(cell.reservoir) <= 600 < cell.n
    p = cell.percentiles()
    assert p["p5"] < p["p25"] < p["p50"] < p["p75"] < p["p95"]
    assert 40 < cell.rank(66) < 60


def test_serialisation_round_trip():
    b = PersonalBaseline.fit("AST-02", synthetic_windows(days=2))
    again = PersonalBaseline.from_dict(b.to_dict())
    ts = START + pd.Timedelta(hours=14)
    assert again.reference("heart_rate", "work", ts).center == b.reference("heart_rate", "work", ts).center
    assert again.windows_seen == b.windows_seen and again.last_ts == b.last_ts


def test_profile_and_rolling_stats():
    w = synthetic_windows(days=3)
    b = PersonalBaseline.fit("A", w)
    prof = b.profile("heart_rate")
    assert set(prof["by_state"]) == {"sleep", "work"}
    assert len(prof["by_state"]["work"]["by_time_of_day"]) == 6
    roll = rolling_stats(w, hours=24)
    assert roll["heart_rate"]["n"] == 288 and roll["heart_rate"]["p5"] < roll["heart_rate"]["p95"]


# ----------------------------------------------------------------------- windows ----
def test_windows_drop_artefacts_and_use_robust_median():
    ts = pd.date_range(START, periods=120, freq="5s", tz="UTC")  # 10 minutes at 1 Hz-ish
    rows = [
        {"ts": t, "heart_rate": 62.0, "spo2": 98.0, "activity_state": "work", "activity_met": 1.7}
        for t in ts
    ]
    rows[5]["heart_rate"] = 0.0  # implausible: dropped
    rows[6]["heart_rate"] = 180.0  # plausible spike: median ignores it
    frame = samples_to_frame(rows)
    cleaned, removed = drop_implausible(frame)
    assert removed == 1 and np.isnan(cleaned.loc[5, "heart_rate"])
    w = to_windows(frame)
    assert len(w) == 2 and (w["heart_rate"] == 62.0).all()
    assert (w["state"] == "work").all() and (w["n_samples"] == 60).all()


def test_windows_fill_gaps_with_missing_rows():
    rows = [{"ts": START, "heart_rate": 60.0}, {"ts": START + pd.Timedelta(minutes=20), "heart_rate": 61.0}]
    w = to_windows(samples_to_frame(rows))
    assert len(w) == 5 and w["heart_rate"].isna().sum() == 3 and w["n_samples"].iloc[1] == 0


# ---------------------------------------------------------------------- features ----
def test_features_are_causal_and_complete():
    w = synthetic_windows(days=3)
    b = PersonalBaseline.fit("A", w.iloc[:288])
    full = build_features(w, b).features
    prefix = build_features(w.iloc[:400], b).features
    assert list(full.columns) == feature_names(ALL_GROUPS)
    pd.testing.assert_frame_equal(full.iloc[:400], prefix)  # appending the future changes nothing
    assert np.isfinite(full.to_numpy()).all()


def test_features_flag_missing_and_detect_level_shift():
    w = synthetic_windows(days=3)
    b = PersonalBaseline.fit("A", w.iloc[:576])
    w2 = w.copy()
    w2.iloc[700:720, w2.columns.get_loc("heart_rate")] += 25  # sudden rise during work
    w2.iloc[800:810, [w2.columns.get_loc(s) for s in SIGNALS]] = np.nan
    f = build_features(w2, b)
    assert f.features["z_heart_rate"].iloc[710] > 8
    assert f.features["d_heart_rate"].iloc[700] > 8
    assert f.features["missing_frac"].iloc[805] == 1.0
    assert f.missing.iloc[805].all()


# ----------------------------------------------------------------------- dataset ----
def test_synthetic_dataset_is_reproducible_and_labelled():
    cfg = SyntheticConfig(days=4, crew=("AST-01", "AST-03"), seed=11)
    a, events_a = generate(cfg)
    b, _ = generate(cfg)
    pd.testing.assert_frame_equal(a, b)
    assert set(a["astronaut_id"]) == {"AST-01", "AST-03"}
    assert len(a) == 2 * 4 * 288
    assert (a["data_source"] == "simulated").all()
    assert a["label"].any() and not a.loc[a["artefact"], "label"].all()
    assert {e.kind for e in events_a} <= {"sudden", "gradual"}
    assert cfg.fingerprint() == SyntheticConfig(days=4, crew=("AST-01", "AST-03"), seed=11).fingerprint()


def test_chronological_split_has_no_overlap():
    cfg = SyntheticConfig(days=10)
    split = chronological_split(cfg)
    ts = pd.date_range(cfg.start, periods=10 * 288, freq="5min", tz="UTC")
    names = split.name(ts)
    first = {n: ts[names == n].min() for n in ("train", "val", "test")}
    last = {n: ts[names == n].max() for n in ("train", "val", "test")}
    assert last["train"] < first["val"] and last["val"] < first["test"]
    assert (names == "train").sum() == 6 * 288
