"""Deterministic random streams so a given seed always reproduces the same crew history."""

from __future__ import annotations

import hashlib

import numpy as np


def rng_for(seed: int, *keys: object) -> np.random.Generator:
    digest = hashlib.sha256(":".join([str(seed), *map(str, keys)]).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))
