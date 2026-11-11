"""Synthetic single-lead ECG.

Each beat is a sum of Gaussian waves (P, Q, R, S, T), an approach similar in spirit to the
McSharry et al. (2003) dynamical ECG model but simplified for streaming. Beat timing follows
the simulated heart rate with respiratory sinus arrhythmia; the irregular-rhythm scenario
switches to randomised RR intervals without P waves plus occasional premature wide beats.

The waveform is for visual demonstration and rhythm-feature testing only. It is not
physiologically complete and must never be used for diagnosis.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

# (offset from R peak in s at RR = 1 s, amplitude mV, width s)
SINUS_WAVES = (
    (-0.200, 0.12, 0.025),  # P
    (-0.035, -0.10, 0.010),  # Q
    (0.000, 1.10, 0.011),  # R
    (0.035, -0.22, 0.010),  # S
    (0.260, 0.28, 0.045),  # T
)
NO_P_WAVES = SINUS_WAVES[1:]
PREMATURE_WAVES = (
    (0.000, 1.35, 0.028),
    (0.060, -0.55, 0.032),
    (0.300, -0.32, 0.060),
)


@dataclass
class Beat:
    t_r: float
    rr: float
    kind: str  # "sinus" | "irregular" | "premature"


class EcgGenerator:
    def __init__(self, sample_rate_hz: int, rng: np.random.Generator, hrv_sdnn_ms: float) -> None:
        self.fs = sample_rate_hz
        self.rng = rng
        self.hrv_sdnn_s = hrv_sdnn_ms / 1000.0
        self.beats: list[Beat] = []
        self.t_next: float | None = None
        self.rr_history: deque[float] = deque(maxlen=16)
        self._pending_compensatory = False
        self._wander_phase = float(rng.uniform(0, 2 * math.pi))

    # -- beat scheduling -------------------------------------------------------------
    def _next_rr(self, t: float, heart_rate: float, irregular: bool, resp_hz: float) -> tuple[float, str]:
        mean_rr = 60.0 / max(30.0, heart_rate)
        if irregular:
            if self._pending_compensatory:
                self._pending_compensatory = False
                return mean_rr * 1.45, "irregular"
            if self.rng.random() < 0.08:
                self._pending_compensatory = True
                return mean_rr * 0.58, "premature"
            return mean_rr * float(self.rng.uniform(0.62, 1.38)), "irregular"
        self._pending_compensatory = False
        rsa = 1 + 0.03 * math.sin(2 * math.pi * resp_hz * t)
        jitter = float(self.rng.normal(0, 0.4 * self.hrv_sdnn_s * mean_rr))
        return min(2.0, max(0.28, mean_rr * rsa + jitter)), "sinus"

    def _schedule(
        self, start: float, until: float, heart_rate: float, irregular: bool, resp_hz: float
    ) -> None:
        if self.t_next is None or self.t_next < start - 2.0:
            # First chunk, or resuming after a long pause: restart the beat train.
            self.t_next = start - 1.0 + float(self.rng.uniform(0, 0.8))
        while self.t_next < until:
            rr, kind = self._next_rr(self.t_next, heart_rate, irregular, resp_hz)
            self.beats.append(Beat(self.t_next, rr, kind))
            self.rr_history.append(rr)
            self.t_next += rr

    # -- rendering -------------------------------------------------------------------
    def render(
        self,
        t0: float,
        duration: float,
        heart_rate: float,
        irregular: bool,
        respiratory_rate: float,
    ) -> list[float]:
        """Return ``duration * fs`` samples (mV) starting at POSIX time ``t0``."""
        resp_hz = respiratory_rate / 60.0
        self._schedule(t0, t0 + duration + 1.0, heart_rate, irregular, resp_hz)
        self.beats = [b for b in self.beats if b.t_r > t0 - 1.5]

        n = int(round(duration * self.fs))
        ts = t0 + np.arange(n) / self.fs
        signal = np.zeros(n)
        for beat in self.beats:
            if beat.t_r < t0 - 1.0 or beat.t_r > t0 + duration + 1.0:
                continue
            if beat.kind == "premature":
                waves = PREMATURE_WAVES
            elif beat.kind == "irregular":
                waves = NO_P_WAVES
            else:
                waves = SINUS_WAVES
            qt_scale = math.sqrt(max(0.3, beat.rr))
            for offset, amp, width in waves:
                # P and T positions stretch with RR (Bazett-like); QRS stays fixed.
                centre = beat.t_r + (offset * qt_scale if abs(offset) > 0.1 else offset)
                signal += amp * np.exp(-((ts - centre) ** 2) / (2 * width * width))

        signal += 0.045 * np.sin(2 * math.pi * resp_hz * ts + self._wander_phase)
        if irregular:
            signal += 0.03 * np.sin(2 * math.pi * 6.3 * ts) * self.rng.uniform(0.6, 1.0)
        signal += self.rng.normal(0, 0.012, n)
        return [round(float(v), 3) for v in signal]

    # -- rhythm features ---------------------------------------------------------------
    def rhythm_features(self) -> tuple[float, float]:
        """(RMSSD in ms, irregularity index = mean |ΔRR| / mean RR) over recent beats."""
        rr = np.array(self.rr_history, dtype=float)
        if rr.size < 4:
            return 0.0, 0.0
        diffs = np.diff(rr)
        rmssd = float(np.sqrt(np.mean(diffs**2)) * 1000)
        irregularity = float(np.mean(np.abs(diffs)) / np.mean(rr))
        return rmssd, irregularity


IRREGULARITY_THRESHOLD = 0.12


def classify_rhythm(irregularity: float) -> str:
    return "irregular" if irregularity >= IRREGULARITY_THRESHOLD else "regular"
