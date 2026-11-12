"""Timestamp parsing for NASA sources. Everything is returned as aware UTC datetimes."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

# DONKI: 2026-11-11T21:06Z; EDA: 2014-09-20T03:59:00Z; OSDR: epoch seconds as text.
_ISO_MINUTE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")


class TimestampError(ValueError):
    pass


def parse_utc(value: object) -> datetime:
    """Parse a NASA timestamp. Naive values are UTC (DONKI and EDA document UTC)."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if not isinstance(value, str) or not value.strip():
        raise TimestampError(f"not a timestamp: {value!r}")
    text = value.strip()
    if _ISO_MINUTE.match(text):
        text = text[:-1] + ":00+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise TimestampError(f"unrecognised timestamp: {value!r}") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def parse_utc_optional(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    return parse_utc(value)


def parse_epoch(value: object) -> datetime | None:
    """OSDR release dates are epoch seconds, sometimes as text with a decimal part."""
    if value in (None, ""):
        return None
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not 0 < seconds < 4e9:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def day_param(d: date | datetime) -> str:
    return (d.date() if isinstance(d, datetime) else d).isoformat()
