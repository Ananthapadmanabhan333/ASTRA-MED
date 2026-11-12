"""Environmental Data App (EDA) adapter: ISS cabin telemetry and radiation dosimetry.

Validation and quality checks run on the raw records before anything is aggregated:
plausibility ranges, duplicate timestamps, missing values, gaps relative to the median sampling
interval, and (for dosimetry) that GCR + SAA matches the reported total. Telemetry is stored as
hourly mean/min/max; dosimetry stays daily, as published.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from app.space.timeparse import TimestampError, parse_utc

# quantity key -> (EDA field stem, unit, plausible range). Ranges are generous physical bounds
# for an ISS module, used only to reject corrupt values.
TELEMETRY: dict[str, tuple[str, str, tuple[float, float]]] = {
    "temperature_c": ("temperature", "°C", (5.0, 45.0)),
    "humidity_pct": ("humidity", "%", (0.0, 100.0)),
    "co2_ppm": ("co2", "ppm", (0.0, 20000.0)),
}
DOSIMETRY: dict[str, tuple[str, str, tuple[float, float]]] = {
    "dose_gcr_mgy_day": ("gcr", "mGy/day", (0.0, 5.0)),
    "dose_saa_mgy_day": ("saa", "mGy/day", (0.0, 5.0)),
    "dose_total_mgy_day": ("total", "mGy/day", (0.0, 10.0)),
}
QUANTITY_LABELS = {
    "temperature_c": "Cabin temperature",
    "humidity_pct": "Relative humidity",
    "co2_ppm": "CO₂ concentration",
    "dose_gcr_mgy_day": "GCR absorbed dose rate",
    "dose_saa_mgy_day": "SAA absorbed dose rate",
    "dose_total_mgy_day": "Total absorbed dose rate",
}
PLATFORMS = ("iss", "ground")
TRANSFER_MILESTONE = "transfer"  # e.g. "Transfer to ISS"
EMPTY_LABELS = {"", "NA", "N/A", "NONE", "NULL"}  # EDA placeholders, not milestones


@dataclass
class SeriesQuality:
    quantity: str
    platform: str
    unit: str
    raw_rows: int = 0  # rows in the response carrying this field
    raw_points: int = 0  # distinct timestamps
    valid: int = 0
    missing: int = 0  # timestamps where no row has a usable value
    out_of_range: int = 0  # timestamps with an implausible value (excluded)
    duplicates: int = 0  # extra rows at an already-seen timestamp, merged
    conflicts: int = 0  # merged timestamps whose values disagree (median kept)
    first: datetime | None = None
    last: datetime | None = None
    median_interval_min: float | None = None
    gaps: int = 0
    longest_gap_hours: float = 0.0
    approximate_points: int = 0
    consistency_failures: int = 0

    @property
    def completeness(self) -> float:
        return self.valid / self.raw_points if self.raw_points else 0.0

    def as_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["first"] = self.first.isoformat() if self.first else None
        d["last"] = self.last.isoformat() if self.last else None
        d["completeness"] = round(self.completeness, 4)
        return d


def normalise_missions(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("EDA missions response is not a list")
    out = []
    for r in records:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        out.append({
            "name": str(r["name"])[:32],
            "title": str(r.get("title") or r["name"])[:255],
            "description": (str(r["description"]).strip() if r.get("description") else None),
            "link": (str(r["link"])[:255] if r.get("link") else None),
        })
    return out


def _milestones(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    out, seen = [], set()
    for r in records:
        label = r.get("milestones")
        if not label or str(label).strip().upper() in EMPTY_LABELS:
            continue
        try:
            ts = parse_utc(r.get("time"))
        except TimestampError:
            continue
        key = (ts, str(label))
        if key in seen:
            continue
        seen.add(key)
        out.append({"time": ts.isoformat(), "label": str(label)})
    return sorted(out, key=lambda m: m["time"])


def _gap_stats(times: list[datetime], q: SeriesQuality) -> None:
    if len(times) < 2:
        return
    deltas = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:]) if b > a]
    if not deltas:
        return
    med = median(deltas)
    q.median_interval_min = round(med, 2)
    big = [d for d in deltas if d > 3 * med]
    q.gaps = len(big)
    q.longest_gap_hours = round(max(big) / 60, 2) if big else 0.0


def _parse_points(records: list[dict[str, Any]], field_name: str, rng: tuple[float, float],
                  q: SeriesQuality) -> dict[datetime, float]:
    """One value per timestamp. Some EDA responses split a timestamp across two rows (one with all
    fields, one with only some); rows are merged per timestamp before any check, so a field that
    is null in one row but present in the other is not counted as missing."""
    per_ts: dict[datetime, list[float]] = {}
    for r in records:
        if not isinstance(r, dict) or field_name not in r:
            continue
        q.raw_rows += 1
        try:
            ts = parse_utc(r.get("time"))
        except TimestampError:
            continue
        vals = per_ts.setdefault(ts, [])
        v = r.get(field_name)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(fv):
            continue
        vals.append(fv)
    q.raw_points = len(per_ts)
    q.duplicates = q.raw_rows - q.raw_points
    values: dict[datetime, float] = {}
    for ts, vals in per_ts.items():
        if not vals:
            q.missing += 1
            continue
        good = [v for v in vals if rng[0] <= v <= rng[1]]
        if len(good) < len(vals):
            q.out_of_range += 1
        if not good:
            continue
        if max(good) - min(good) > 1e-9:
            q.conflicts += 1
        values[ts] = float(median(good))
    times = sorted(values)
    q.valid = len(values)
    if times:
        q.first, q.last = times[0], times[-1]
    _gap_stats(times, q)
    return values


def normalise_telemetry(records: Any) -> tuple[list[dict[str, Any]], list[SeriesQuality], list[dict[str, str]]]:
    """Hourly aggregates for every telemetry quantity and platform present in the response."""
    if not isinstance(records, list):
        raise ValueError("EDA telemetry response is not a list")
    rows: list[dict[str, Any]] = []
    qualities: list[SeriesQuality] = []
    for quantity, (stem, unit, rng) in TELEMETRY.items():
        for platform in PLATFORMS:
            field_name = f"{stem}_{platform}"
            q = SeriesQuality(quantity, platform, unit)
            values = _parse_points(records, field_name, rng, q)
            if q.raw_points == 0:
                continue
            qualities.append(q)
            buckets: dict[datetime, list[float]] = defaultdict(list)
            for ts, v in values.items():
                buckets[ts.replace(minute=0, second=0, microsecond=0)].append(v)
            for hour, vs in sorted(buckets.items()):
                rows.append({
                    "quantity": quantity, "platform": platform, "ts": hour, "resolution": "1h",
                    "value": round(sum(vs) / len(vs), 4), "min_value": min(vs), "max_value": max(vs),
                    "n": len(vs), "unit": unit, "approximate": False, "category": "measured",
                })
    return rows, qualities, _milestones(records)


def normalise_radiation(records: Any) -> tuple[list[dict[str, Any]], list[SeriesQuality], list[dict[str, str]]]:
    """Daily dosimetry. Days before the 'Transfer to ISS' milestone are flagged approximate:
    EDA states launch-vehicle doses are approximated from US Lab averages."""
    if not isinstance(records, list):
        raise ValueError("EDA radiation response is not a list")
    milestones = _milestones(records)
    transfer = next((parse_utc(m["time"]) for m in milestones if TRANSFER_MILESTONE in m["label"].strip().lower()), None)
    rows: list[dict[str, Any]] = []
    qualities: list[SeriesQuality] = []
    parsed: dict[str, dict[datetime, float]] = {}
    for quantity, (stem, unit, rng) in DOSIMETRY.items():
        q = SeriesQuality(quantity, "iss", unit)
        values = _parse_points(records, stem, rng, q)
        if q.raw_points == 0:
            continue
        parsed[quantity] = values
        qualities.append(q)
    gcr, saa, tot = (parsed.get(k, {}) for k in DOSIMETRY)
    inconsistent = {ts for ts in tot if ts in gcr and ts in saa and abs(gcr[ts] + saa[ts] - tot[ts]) > 0.002}
    for q in qualities:
        if q.quantity == "dose_total_mgy_day":
            q.consistency_failures = len(inconsistent)
    for quantity, values in parsed.items():
        q = next(x for x in qualities if x.quantity == quantity)
        for ts, v in sorted(values.items()):
            # A daily value starting before the transfer includes launch-vehicle time (approximated
            # by EDA), so the transfer day itself is flagged too.
            approx = transfer is not None and ts <= transfer
            if approx:
                q.approximate_points += 1
            rows.append({
                "quantity": quantity, "platform": "iss", "ts": ts, "resolution": "1d", "value": v,
                "min_value": None, "max_value": None, "n": 1, "unit": DOSIMETRY[quantity][1],
                "approximate": approx, "category": "measured",
            })
    return rows, qualities, milestones


def mission_window(rows: list[dict[str, Any]]) -> tuple[datetime | None, datetime | None]:
    times = [r["ts"] for r in rows]
    return (min(times), max(times)) if times else (None, None)
