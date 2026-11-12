from __future__ import annotations

import json

import numpy as np
import pytest

from app.ai.explain import (
    Contributor,
    anomaly_kind,
    build_contributors,
    describe_contributors,
    onset_kind,
    signal_shares,
    significance,
)
from app.ai.features import feature_names
from app.ai.risk import AnomalyState, ForecastState, RiskConfig, RiskInputs, SignalState, assess


def sig(name: str, z: float | None = 0.0, minutes: float = 0.0, value: float = 60.0, baseline: float = 60.0) -> SignalState:
    return SignalState(name, value, baseline, z, 50.0, "cell", deviating_minutes=minutes)


def inputs(**kw) -> RiskInputs:
    base = dict(
        astronaut_id="AST-01",
        signals=[sig("heart_rate"), sig("spo2")],
        anomaly=AnomalyState(available=True, n_detectors=5),
        forecasts=[],
        alerts=[],
        missing_frac=0.0,
        windows=24,
        forecast_available=True,
    )
    base.update(kw)
    return RiskInputs(**base)


CFG = RiskConfig()


def test_all_quiet_is_normal():
    r = assess(inputs(), CFG)
    assert (r["category"], r["risk_score"], r["health_score"]) == ("normal", 0.0, 100)
    assert r["warnings"] == []
    assert r["explanation"].confidence["level"] == "high"


def test_sustained_deviation_scores_more_than_a_brief_one():
    long = assess(inputs(signals=[sig("heart_rate", z=5.0, minutes=60, value=90)]), CFG)
    short = assess(inputs(signals=[sig("heart_rate", z=5.0, minutes=5, value=90)]), CFG)
    assert long["risk_score"] == pytest.approx(20.0)  # (5 - 2 + 1) * 5, full duration
    assert short["risk_score"] == pytest.approx(8.0)  # minimum duration factor 0.4
    assert long["category"] == "low_concern" and short["category"] == "normal"
    assert long["warnings"][0]["signals"] == ["heart_rate"]


def test_components_combine_into_categories_and_priorities():
    r = assess(
        inputs(
            signals=[sig("heart_rate", z=5.0, minutes=60, value=92), sig("spo2", z=-3.0, minutes=60, value=94)],
            anomaly=AnomalyState(True, score=1.5, votes=4, n_detectors=5, flagged_minutes=60, kind="sudden_change",
                                 top_signals=["heart_rate", "spo2"]),
            alerts=[{"id": "a1", "severity": "critical", "title": "Oxygen desaturation", "metric": "spo2"}],
        ),
        CFG,
    )
    assert r["category"] == "high_concern"
    points = [w["points"] for w in r["warnings"]]
    assert points == sorted(points, reverse=True)
    assert [w["priority"] for w in r["warnings"]] == list(range(1, len(points) + 1))
    assert {w["source"] for w in r["warnings"]} == {"deviation", "anomaly", "alert"}
    shares = [c.share for c in r["explanation"].contributors]
    assert sum(shares) == pytest.approx(1.0, abs=0.01)
    assert r["explanation"].contributors[0].signal == "spo2"  # alert + deviation + anomaly share


def test_forecast_crossing_logic():
    likely = ForecastState("heart_rate", 6, value=125, lower=115, upper=135, limit=120, direction="high")
    possible = ForecastState("spo2", 12, value=95, lower=93, upper=97, limit=94, direction="low")
    ignored = ForecastState("heart_rate", 1, value=150, lower=140, upper=160, limit=120, direction="high")
    assert (likely.crossing, possible.crossing) == ("likely", "possible")
    r = assess(inputs(forecasts=[likely, possible, ignored]), CFG)
    by_signal = {w["signals"][0]: w["points"] for w in r["warnings"]}
    assert by_signal == {"heart_rate": CFG.trend_points_likely, "spo2": CFG.trend_points_possible}
    assert all(w["concern"] != "normal" for w in r["warnings"])  # a warning is never labelled normal


def test_cleared_alert_counts_half_and_missing_data_lowers_confidence():
    alert = {"id": "a", "severity": "caution", "title": "x", "metric": "heart_rate", "condition_cleared": True}
    r = assess(inputs(alerts=[alert], missing_frac=0.8, windows=3,
                      anomaly=AnomalyState(available=False), forecast_available=False), CFG)
    assert r["risk_score"] == pytest.approx(10.0)
    assert r["explanation"].confidence["level"] == "low"


def test_config_file_changes_behaviour(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text(json.dumps({"categories": {"low_concern": 1, "moderate_concern": 2, "high_concern": 3}}))
    cfg = RiskConfig.load(path)
    r = assess(inputs(signals=[sig("heart_rate", z=2.5, minutes=60)]), cfg)
    assert r["category"] == "high_concern"


# ------------------------------------------------------------------ explanations ----
def test_signal_shares_and_anomaly_kind():
    names = feature_names()
    contrib = np.zeros(len(names))
    contrib[names.index("d_heart_rate")] = 0.6
    contrib[names.index("z_spo2")] = 0.3
    contrib[names.index("met")] = 0.1
    by_signal, by_group = signal_shares(contrib, names)
    assert by_signal["heart_rate"] == pytest.approx(0.6) and by_signal["context"] == pytest.approx(0.1)
    assert anomaly_kind(by_group) == "sudden_change"
    contrib[:] = 0
    contrib[names.index("trend_temperature_c")] = 0.5
    contrib[names.index("sust_temperature_c")] = 0.3
    contrib[names.index("z_temperature_c")] = 0.2
    assert anomaly_kind(signal_shares(contrib, names)[1]) == "gradual_deviation"


def test_significance_levels_and_contributor_filtering():
    assert [significance(z)["level"] for z in (0.5, 1.8, 3.0, 6.0)] == ["none", "minor", "notable", "major"]

    class Ref:
        center = 60.0
        comparable = True

        def z(self, v):
            return (v - 60) / 3

        def percentile(self, v):
            return 99.0

    out = build_contributors({"heart_rate": 0.8, "spo2": 0.02, "context": 0.18}, {"heart_rate": 72.0}, {"heart_rate": Ref()})
    assert [c.signal for c in out] == ["heart_rate"]
    assert (out[0].z, out[0].direction, out[0].baseline) == (4.0, "above", 60.0)

    class NoBaseline(Ref):
        comparable = False  # e.g. first workout: no exercise baseline yet

    out = build_contributors({"heart_rate": 1.0}, {"heart_rate": 120.0}, {"heart_rate": NoBaseline()})
    assert (out[0].value, out[0].z, out[0].baseline, out[0].direction) == (120.0, None, None, None)


def test_onset_kind_separates_sudden_gradual_and_offset():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.3, 40)
    step = np.concatenate([np.zeros(24), np.full(16, 5.0)]) + noise  # jump at index 24, plateau after
    assert onset_kind(step, 24) == "sudden_change"
    ramp = np.concatenate([np.zeros(12), np.linspace(0, 6, 28)]) + noise  # steady rise from index 12
    assert onset_kind(ramp, 24) == "gradual_deviation"
    flat = rng.normal(0, 1.0, 40)  # nothing systematic
    assert onset_kind(flat, 24) == "sustained_offset"
    assert onset_kind(np.array([np.nan]), 0) == "sustained_offset"


def test_describe_contributors_says_near_baseline_instead_of_zero_deviation():
    flat = Contributor(signal="respiratory_rate", label="Respiratory rate", share=0.4, unit="breaths/min",
                       value=15.3, baseline=15.3, z=0.0)
    high = Contributor(signal="heart_rate", label="Heart rate", share=0.3, unit="bpm", value=96.0, baseline=70.0, z=4.2)
    text = describe_contributors([flat, high])
    assert "0.0 breaths/min" not in text
    assert "respiratory rate near baseline (15.3 breaths/min)" in text
    assert "heart rate 26.0 bpm above baseline" in text
