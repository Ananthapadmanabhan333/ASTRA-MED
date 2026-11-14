"""Inference performance monitoring and runtime library fingerprints.

``InferenceStats`` keeps a bounded window of recent timings per operation (detection, each
forecaster, risk, ...) so the API can report latency percentiles and error counts without any
external tooling. Memory use is constant: each operation keeps at most ``window`` samples.

``library_versions`` records the numerical libraries a model version was trained with. Pickled
scikit-learn models are only guaranteed to load correctly with the version that wrote them, so the
service compares the training fingerprint with the running one and reports any mismatch.
"""

from __future__ import annotations

import importlib.metadata
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

TRACKED_LIBRARIES = ("numpy", "pandas", "scikit-learn", "scipy", "xgboost", "torch", "joblib")
# Alternative distribution names that install the same import package.
_DISTRIBUTIONS = {"xgboost": ("xgboost", "xgboost-cpu")}


def library_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in TRACKED_LIBRARIES:
        out[name] = None
        for dist in _DISTRIBUTIONS.get(name, (name,)):
            try:
                out[name] = importlib.metadata.version(dist)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    return out


def version_mismatches(trained: dict[str, str | None] | None, running: dict[str, str | None]) -> dict[str, dict]:
    """Libraries whose major.minor differs between training and serving (patch releases are ignored)."""
    if not trained:
        return {}

    def minor(v: str | None) -> str | None:
        if not v:
            return v
        base = v.split("+", 1)[0]
        return ".".join(base.split(".")[:2])

    return {
        name: {"trained": trained.get(name), "running": running.get(name)}
        for name in TRACKED_LIBRARIES
        if trained.get(name) and minor(trained.get(name)) != minor(running.get(name))
    }


def process_memory_mb() -> float | None:
    try:
        import psutil
    except ImportError:  # optional dependency
        return None
    return round(psutil.Process().memory_info().rss / 2**20, 1)


class InferenceStats:
    def __init__(self, window: int = 200) -> None:
        self.window = window
        self._lock = threading.Lock()
        self._samples: dict[str, deque[float]] = {}
        self._count: dict[str, int] = {}
        self._errors: dict[str, int] = {}
        self._last_error: dict[str, str] = {}

    def record(self, op: str, ms: float, error: BaseException | None = None) -> None:
        with self._lock:
            self._samples.setdefault(op, deque(maxlen=self.window)).append(ms)
            self._count[op] = self._count.get(op, 0) + 1
            if error is not None:
                self._errors[op] = self._errors.get(op, 0) + 1
                self._last_error[op] = f"{type(error).__name__}: {error}"[:300]

    @contextmanager
    def measure(self, op: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        except BaseException as exc:
            self.record(op, (time.perf_counter() - start) * 1000, exc)
            raise
        self.record(op, (time.perf_counter() - start) * 1000)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = {op: (sorted(s), s[-1]) for op, s in self._samples.items() if s}
            counts, errors, last = dict(self._count), dict(self._errors), dict(self._last_error)
        ops = {}
        for op, (s, latest) in sorted(items.items()):
            ops[op] = {
                "count": counts.get(op, 0),
                "errors": errors.get(op, 0),
                "last_error": last.get(op),
                "window": len(s),
                "last_ms": round(latest, 1),
                "p50_ms": round(_pct(s, 0.50), 1),
                "p95_ms": round(_pct(s, 0.95), 1),
                "max_ms": round(s[-1], 1),
            }
        return {"operations": ops, "process_memory_mb": process_memory_mb()}


def _pct(sorted_values: list[float], p: float) -> float:
    k = (len(sorted_values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)
