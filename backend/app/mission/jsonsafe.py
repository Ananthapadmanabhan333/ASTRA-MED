"""Convert values to what a JSON column can store (datetimes as ISO strings, NaN as null)."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from app.core.timeutil import as_utc


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set):
        return [jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return as_utc(obj).isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "isoformat"):  # pandas Timestamp
        return obj.isoformat()
    if hasattr(obj, "item") and not isinstance(obj, str | bytes):  # numpy scalar
        try:
            return jsonable(obj.item())
        except (TypeError, ValueError):
            return str(obj)
    if hasattr(obj, "model_dump"):
        return jsonable(obj.model_dump(mode="json"))
    return obj
