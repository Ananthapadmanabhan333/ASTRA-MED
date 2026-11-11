"""Time-range queries with server-side downsampling into fixed buckets."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.schemas.health import HistoryPoint

RANGE_SECONDS: dict[str, int] = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
MIN_RESOLUTION_S = 5
HISTORY_COLUMNS = (
    "heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate", "activity_met",
)


def window(range_key: str, now: datetime) -> tuple[datetime, datetime]:
    return now - timedelta(seconds=RANGE_SECONDS[range_key]), now


def resolution_for(range_key: str, max_points: int) -> int:
    return max(MIN_RESOLUTION_S, math.ceil(RANGE_SECONDS[range_key] / max_points))


def bucket_rows(
    rows: Sequence[tuple], start: datetime, resolution_s: int, n_values: int
) -> list[tuple[datetime, list[float], int]]:
    """Average rows ``(ts, v1, v2, ...)`` into buckets; returns (bucket_ts, means, count)."""
    sums: dict[int, list[float]] = {}
    counts: dict[int, int] = {}
    base = start.timestamp()
    for row in rows:
        idx = int((row[0].timestamp() - base) // resolution_s)
        acc = sums.setdefault(idx, [0.0] * n_values)
        for i in range(n_values):
            acc[i] += float(row[i + 1])
        counts[idx] = counts.get(idx, 0) + 1
    out = []
    for idx in sorted(sums):
        c = counts[idx]
        ts = start + timedelta(seconds=idx * resolution_s + resolution_s / 2)
        out.append((ts, [v / c for v in sums[idx]], c))
    return out


def history_points(rows: Sequence[tuple], start: datetime, resolution_s: int) -> list[HistoryPoint]:
    points = []
    for ts, means, count in bucket_rows(rows, start, resolution_s, len(HISTORY_COLUMNS)):
        values = dict(zip(HISTORY_COLUMNS, means))
        points.append(
            HistoryPoint(
                ts=ts,
                **{k: round(v, 2) for k, v in values.items()},
                samples=count,
            )
        )
    return points
