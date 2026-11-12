"""Severity classification for space-weather events, using published scales only where the
DONKI record contains the quantity the scale is defined on.

* Solar flares -> NOAA radio blackout scale (R1-R5), defined on GOES 1-8 Å peak X-ray flux:
  R1 >= M1 (1e-5 W/m2), R2 >= M5, R3 >= X1 (1e-4), R4 >= X10, R5 >= X20.
* Geomagnetic storms -> NOAA geomagnetic storm scale (G1-G5) from the maximum Kp:
  G1 Kp 5, G2 Kp 6, G3 Kp 7, G4 Kp 8 (incl. 9-), G5 Kp 9 (thirds: "n-" counts as n).
* CMEs -> SWPC CME Analysis Tool speed classes recorded in DONKI (S < 500, C 500-999,
  O 1000-1999, R 2000-2999, ER >= 3000 km/s). This is a speed class, not an impact scale.
* SEP and radiation-belt events carry no flux in DONKI, so they stay unclassified.

``severity`` is 1-5 for classified events (scale level or speed class) and None otherwise.
"""

from __future__ import annotations

import math
import re

FLARE_BASE = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}
_FLARE = re.compile(r"^\s*([ABCMX])\s*(\d+(?:\.\d+)?)?\s*$", re.IGNORECASE)

R_THRESHOLDS = [(2e-3, 5), (1e-3, 4), (1e-4, 3), (5e-5, 2), (1e-5, 1)]
CME_TYPES = {"S": 1, "C": 2, "O": 3, "R": 4, "ER": 5}
CME_TYPE_TEXT = {
    "S": "S (common, < 500 km/s)",
    "C": "C (common, 500-999 km/s)",
    "O": "O (occasional, 1000-1999 km/s)",
    "R": "R (rare, 2000-2999 km/s)",
    "ER": "ER (extremely rare, >= 3000 km/s)",
}
SEVERITY_WORDS = {1: "minor", 2: "moderate", 3: "strong", 4: "severe", 5: "extreme"}


def flare_flux(class_type: str | None) -> float | None:
    """Peak X-ray flux in W/m2 from a GOES class such as 'M1.7' or 'X10'."""
    if not class_type:
        return None
    m = _FLARE.match(class_type)
    if not m:
        return None
    letter, number = m.group(1).upper(), m.group(2)
    return FLARE_BASE[letter] * (float(number) if number else 1.0)


def radio_blackout_level(flux: float | None) -> int | None:
    if flux is None:
        return None
    for threshold, level in R_THRESHOLDS:
        if flux >= threshold * 0.9999:
            return level
    return 0  # below R1 (C-class or weaker)


# Kp is reported in thirds (8- = 7.67, 8 = 8.0, 8+ = 8.33). We count "n-" as reaching n, and
# keep 9- (8.67) at G4 because NOAA defines G4 as "Kp = 8, including 9-".
G_THRESHOLDS = [(9.0, 5), (7.67, 4), (6.67, 3), (5.67, 2), (4.67, 1)]


def storm_level(max_kp: float | None) -> int | None:
    if max_kp is None or math.isnan(max_kp):
        return None
    for kp, level in G_THRESHOLDS:
        if max_kp >= kp - 0.005:
            return level
    return 0


def cme_level(cme_type: str | None, speed: float | None) -> tuple[str | None, int | None]:
    t = (cme_type or "").upper() or None
    if t is None and speed is not None:
        t = "S" if speed < 500 else "C" if speed < 1000 else "O" if speed < 2000 else "R" if speed < 3000 else "ER"
    return t, CME_TYPES.get(t or "")


def describe(event_type: str, level: int | None) -> str:
    if level is None:
        return "unclassified"
    if level == 0:
        return "below scale"
    word = SEVERITY_WORDS.get(level, "")
    prefix = {"FLR": "R", "GST": "G"}.get(event_type)
    return f"{prefix}{level} ({word})" if prefix else f"class {level} ({word})"
