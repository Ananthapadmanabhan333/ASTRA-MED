"""Statistics of the correlation engine on series with known properties."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.space import correlation as C

IDX = pd.date_range("2026-01-01", periods=150, freq="D", tz="UTC")


def series(values) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=float), index=IDX[: len(values)])


def test_known_lag_is_recovered_and_survives_fdr():
    rng = np.random.default_rng(1)
    x = series(rng.normal(size=150))
    y = x.shift(3) * 0.7 + series(rng.normal(scale=0.5, size=150))
    lags = C.lagged(x, y, 5)
    best = max(lags, key=lambda r: abs(r["r"] or 0))
    assert best["lag_days"] == 3 and best["r"] > 0.7 and best["q"] < 1e-6
    assert next(r for r in lags if r["lag_days"] == 0)["q"] > 0.05


def test_independent_series_are_not_significant():
    rng = np.random.default_rng(2)
    c = C.correlate(series(rng.normal(size=150)), series(rng.normal(size=150)))
    assert abs(c["pearson"]["r"]) < 0.2 and c["pearson"]["p"] > 0.05
    lo, hi = c["pearson"]["ci"]
    assert lo < 0 < hi


def test_autocorrelation_shrinks_effective_n_and_kills_spurious_walk_correlations():
    rng = np.random.default_rng(3)
    hits_naive = hits_adjusted = 0
    for _ in range(40):
        a, b = series(np.cumsum(rng.normal(size=150))), series(np.cumsum(rng.normal(size=150)))
        c = C.correlate(a, b)
        assert c["n_eff"] < 0.25 * c["n"]
        naive_p = C.p_from_r(c["pearson"]["r"], c["n"])
        hits_naive += naive_p < 0.05
        hits_adjusted += c["pearson"]["p"] < 0.05
    # Independent random walks look "significant" most of the time with naive n; far less with n_eff.
    assert hits_naive > 20 and hits_adjusted < hits_naive / 2


def test_trend_adjusted_correlation_removes_a_shared_trend():
    rng = np.random.default_rng(4)
    t = np.arange(150)
    a = series(0.05 * t + rng.normal(size=150))
    b = series(0.05 * t + rng.normal(size=150))
    raw = C.correlate(a, b)["pearson"]["r"]
    adj = C.trend_adjusted(a, b)
    assert raw > 0.6 and abs(adj["r"]) < 0.25


def test_benjamini_hochberg_matches_hand_calculation():
    q = C.bh_adjust([0.01, 0.04, 0.03, 0.5, float("nan")])
    assert q[:4] == pytest.approx([0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.5])
    assert np.isnan(q[4])


def test_missing_values_are_dropped_pairwise_and_short_overlaps_refused():
    x = series([1, 2, np.nan, 4, 5, 6, 7, 8])
    y = series([2, np.nan, 3, 5, 4, 7, 8, 9])
    c = C.correlate(x, y)
    assert c["n"] == 6 and c["pearson"]["r"] > 0.9
    tiny = C.correlate(series([1, 2, 3]), series([3, 2, 1]))
    assert tiny["pearson"] is None and "too few" in tiny["reason"]
    const = C.correlate(series([1.0] * 10), series(range(10)))
    assert const["pearson"] is None


def test_rolling_and_cross_correlation_shapes():
    rng = np.random.default_rng(5)
    x, y = series(rng.normal(size=60)), series(rng.normal(size=60))
    roll = C.rolling(x, y, 14)
    assert roll and all(-1 <= p["r"] <= 1 for p in roll)
    cc = C.cross_correlation(x, y, 3)
    assert [r["lag_days"] for r in cc] == [-3, -2, -1, 0, 1, 2, 3]


def test_strength_words():
    assert [C.strength(v) for v in (0.05, -0.2, 0.4, -0.8, float("nan"))] == ["negligible", "weak", "moderate", "strong", "undefined"]
