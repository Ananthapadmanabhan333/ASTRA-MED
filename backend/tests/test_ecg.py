from __future__ import annotations

import numpy as np
import pytest

from app.simulator.ecg import EcgGenerator, classify_rhythm


def r_peaks(signal: list[float], fs: int) -> int:
    x = np.array(signal)
    above = x > 0.6
    # Count rising edges through the R-wave threshold, at least 200 ms apart.
    edges = np.flatnonzero(above[1:] & ~above[:-1])
    if edges.size == 0:
        return 0
    keep = [edges[0]]
    for e in edges[1:]:
        if e - keep[-1] > 0.2 * fs:
            keep.append(e)
    return len(keep)


def render(gen: EcgGenerator, seconds: int, hr: float, irregular=False, fs=250):
    out: list[float] = []
    t0 = 1_800_000_000.0
    for i in range(seconds):
        out += gen.render(t0 + i, 1.0, hr, irregular, 14)
    return out


@pytest.mark.parametrize("hr", [50, 72, 110, 150])
def test_beat_rate_matches_heart_rate(hr):
    fs = 250
    gen = EcgGenerator(fs, np.random.default_rng(1), hrv_sdnn_ms=45)
    signal = render(gen, 60, hr, fs=fs)
    assert len(signal) == 60 * fs
    assert abs(r_peaks(signal, fs) - hr) <= max(3, 0.05 * hr)


def test_chunks_are_contiguous_without_gaps():
    gen = EcgGenerator(125, np.random.default_rng(2), hrv_sdnn_ms=45)
    signal = render(gen, 10, 70, fs=125)
    # No flat-line second anywhere: every second contains an R wave.
    for s in range(1, 10):
        assert max(signal[s * 125 : (s + 1) * 125]) > 0.6


def test_regular_rhythm_classified_regular():
    gen = EcgGenerator(125, np.random.default_rng(3), hrv_sdnn_ms=60)
    render(gen, 30, 64, fs=125)
    _, irregularity = gen.rhythm_features()
    assert classify_rhythm(irregularity) == "regular"


def test_irregular_rhythm_classified_irregular():
    gen = EcgGenerator(125, np.random.default_rng(4), hrv_sdnn_ms=60)
    render(gen, 30, 80, irregular=True, fs=125)
    rmssd, irregularity = gen.rhythm_features()
    assert classify_rhythm(irregularity) == "irregular"
    assert rmssd > 100


def test_amplitudes_are_plausible_millivolts():
    gen = EcgGenerator(125, np.random.default_rng(5), hrv_sdnn_ms=45)
    signal = render(gen, 10, 70, fs=125)
    assert 0.8 < max(signal) < 1.6
    assert -0.6 < min(signal) < 0
