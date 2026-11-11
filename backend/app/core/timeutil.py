from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    """Return an aware UTC datetime; naive values are treated as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def hours_of_day(dt: datetime) -> float:
    """Fractional hour of the UTC day. Mission time is kept on UTC, as on the ISS."""
    dt = as_utc(dt)
    return dt.hour + dt.minute / 60 + dt.second / 3600 + dt.microsecond / 3.6e9
