from __future__ import annotations

from datetime import timedelta

from app.services.history import bucket_rows, resolution_for
from app.services.mission import earth_distance_au
from tests.conftest import T0


def test_resolution_respects_point_budget_and_floor():
    assert resolution_for("1h", 360) == 10
    assert resolution_for("7d", 360) == 1680
    assert resolution_for("1h", 1000) == 5  # never finer than the 5 s storage cadence


def test_bucket_rows_averages_and_counts():
    rows = [(T0 + timedelta(seconds=s), float(s)) for s in range(0, 60, 5)]
    buckets = bucket_rows(rows, T0, 30, 1)
    assert [c for _, _, c in buckets] == [6, 6]
    assert buckets[0][1][0] == sum(range(0, 30, 5)) / 6
    assert buckets[0][0] == T0 + timedelta(seconds=15)  # bucket midpoint


def test_bucket_rows_skips_empty_buckets():
    rows = [(T0, 1.0), (T0 + timedelta(seconds=300), 3.0)]
    assert len(bucket_rows(rows, T0, 60, 1)) == 2


def test_earth_distance_grows_over_transit():
    assert earth_distance_au(0) < earth_distance_au(100) < earth_distance_au(240)
    assert earth_distance_au(500) == earth_distance_au(240)
