"""DONKI adapter: validate and normalise space-weather records.

Each DONKI type has its own identifier and time fields. ``normalise_event`` maps one raw record
to a flat dictionary for ``space_weather_events``; the raw record is kept unchanged in ``raw``.
Records that fail validation are counted and skipped, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.space import classify
from app.space.timeparse import TimestampError, parse_utc, parse_utc_optional

EVENT_TYPES: dict[str, str] = {
    "FLR": "Solar flare",
    "CME": "Coronal mass ejection",
    "SEP": "Solar energetic particle event",
    "GST": "Geomagnetic storm",
    "RBE": "Radiation belt enhancement",
    "IPS": "Interplanetary shock",
    "HSS": "High-speed solar wind stream",
    "MPC": "Magnetopause crossing",
    "WSA": "WSA-ENLIL solar wind simulation",
}
# DONKI web-service path for each type.
PATHS: dict[str, str] = {
    "FLR": "FLR", "CME": "CME", "SEP": "SEP", "GST": "GST", "RBE": "RBE", "IPS": "IPS",
    "HSS": "HSS", "MPC": "MPC", "WSA": "WSAEnlilSimulations",
}
RADIATION_RELEVANT = ("SEP", "FLR", "RBE", "GST", "CME")
HISTORICAL_TYPES = ("FLR", "CME", "SEP", "GST", "RBE")  # fetched for historical ISS mission windows
_ID_FIELDS = {
    "FLR": ("flrID", "beginTime"), "CME": ("activityID", "startTime"), "SEP": ("sepID", "eventTime"),
    "GST": ("gstID", "startTime"), "RBE": ("rbeID", "eventTime"), "IPS": ("activityID", "eventTime"),
    "HSS": ("hssID", "eventTime"), "MPC": ("mpcID", "eventTime"), "WSA": ("simulationID", "modelCompletionTime"),
}
_WS = re.compile(r"\s+")


class RecordError(ValueError):
    pass


@dataclass
class NormaliseReport:
    received: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates_in_response: int = 0
    errors: list[str] = field(default_factory=list)


def _text(value: Any, limit: int | None = None) -> str | None:
    if value is None:
        return None
    s = _WS.sub(" ", str(value)).strip()
    if not s:
        return None
    return s[:limit] if limit else s


def _instrument_names(record: dict[str, Any]) -> list[str]:
    out = []
    for inst in record.get("instruments") or []:
        name = inst.get("displayName") if isinstance(inst, dict) else inst
        if name:
            out.append(str(name))
    return out


def _ids(items: Any, key: str) -> list[str]:
    return [str(i[key]) for i in (items or []) if isinstance(i, dict) and i.get(key)]


def _best_cme_analysis(record: dict[str, Any]) -> dict[str, Any] | None:
    analyses = [a for a in (record.get("cmeAnalyses") or []) if isinstance(a, dict)]
    if not analyses:
        return None
    return next((a for a in analyses if a.get("isMostAccurate")), analyses[-1])


def normalise_event(event_type: str, record: dict[str, Any]) -> dict[str, Any]:
    if event_type not in _ID_FIELDS:
        raise RecordError(f"unknown DONKI type {event_type}")
    if not isinstance(record, dict):
        raise RecordError("record is not an object")
    id_field, time_field = _ID_FIELDS[event_type]
    external_id = _text(record.get(id_field), 128)
    if not external_id:
        raise RecordError(f"{event_type}: missing {id_field}")
    try:
        start = parse_utc(record.get(time_field))
        submitted = parse_utc_optional(record.get("submissionTime"))
    except TimestampError as exc:
        raise RecordError(f"{event_type} {external_id}: {exc}") from exc

    out: dict[str, Any] = {
        "event_type": event_type,
        "external_id": external_id,
        "category": "model" if event_type == "WSA" else "indicator",
        "start_time": start,
        "peak_time": None,
        "end_time": None,
        "classification": None,
        "scale": None,
        "severity": None,
        "magnitude": None,
        "magnitude_unit": None,
        "location": None,
        "description": _text(record.get("note")),
        "instruments": _instrument_names(record),
        "linked_ids": _ids(record.get("linkedEvents"), "activityID"),
        "notification_ids": _ids(record.get("sentNotifications"), "messageID"),
        "model_derived": False,
        "link": _text(record.get("link"), 255),
        "version": int(record.get("versionId") or 1),
        "submitted_at": submitted,
        "raw": record,
    }

    try:
        if event_type == "FLR":
            out["peak_time"] = parse_utc_optional(record.get("peakTime"))
            out["end_time"] = parse_utc_optional(record.get("endTime"))
            cls = _text(record.get("classType"), 16)
            flux = classify.flare_flux(cls)
            level = classify.radio_blackout_level(flux)
            out.update(classification=f"{cls} flare" if cls else "flare (class not reported)",
                       magnitude=flux, magnitude_unit="W/m²", severity=level,
                       scale=f"R{level}" if level else None, location=_text(record.get("sourceLocation"), 64))
        elif event_type == "CME":
            a = _best_cme_analysis(record) or {}
            speed = a.get("speed")
            speed = float(speed) if isinstance(speed, int | float) else None
            ctype, level = classify.cme_level(a.get("type"), speed)
            half = a.get("halfAngle")
            parts = [f"type {classify.CME_TYPE_TEXT.get(ctype, ctype)}" if ctype else "no speed analysis yet"]
            if half is not None:
                parts.append(f"half-angle {half:g}°")
            out.update(classification="CME " + ", ".join(parts), magnitude=speed, magnitude_unit="km/s",
                       severity=level, location=_text(record.get("sourceLocation"), 64))
        elif event_type == "GST":
            kps = [k for k in (record.get("allKpIndex") or []) if isinstance(k, dict) and k.get("kpIndex") is not None]
            if kps:
                peak = max(kps, key=lambda k: float(k["kpIndex"]))
                max_kp = float(peak["kpIndex"])
                level = classify.storm_level(max_kp)
                out.update(magnitude=max_kp, magnitude_unit="Kp", severity=level,
                           scale=f"G{level}" if level else None,
                           classification=f"Geomagnetic storm, max Kp {max_kp:g}",
                           peak_time=parse_utc_optional(peak.get("observedTime")),
                           end_time=max(parse_utc(k["observedTime"]) for k in kps if k.get("observedTime")))
            else:
                out["classification"] = "Geomagnetic storm (no Kp values reported)"
        elif event_type == "SEP":
            model = any(i.upper().startswith("MODEL") for i in out["instruments"])
            out.update(classification="SEP event (particle flux not reported in DONKI)", model_derived=model)
        elif event_type == "RBE":
            out["classification"] = "Radiation belt electron enhancement"
        elif event_type == "IPS":
            out.update(classification=f"Interplanetary shock at {_text(record.get('location'), 40) or 'unknown location'}",
                       location=_text(record.get("location"), 64))
        elif event_type == "HSS":
            out["classification"] = "High-speed stream"
        elif event_type == "MPC":
            out["classification"] = "Magnetopause crossing"
        elif event_type == "WSA":
            arrival = parse_utc_optional(record.get("estimatedShockArrivalTime"))
            out["end_time"] = arrival
            impacts = record.get("impactList") or []
            targets = sorted({str(i.get("location")) for i in impacts if isinstance(i, dict) and i.get("location")})
            if record.get("isEarthGB"):
                earth = "Earth glancing blow predicted"
            elif arrival:
                earth = "Earth shock arrival predicted"
            elif record.get("isEarthMinorImpact"):
                earth = "minor Earth impact predicted"
            else:
                earth = "no Earth impact predicted"
            out["classification"] = f"Model run: {earth}" + (f"; also reaches {', '.join(targets[:4])}" if targets else "")
            kp = record.get("kp_90")
            if isinstance(kp, int | float):
                out.update(magnitude=float(kp), magnitude_unit="Kp (modelled)")
            out["linked_ids"] = [str(c.get("CMEID")) for c in record.get("cmeInputs") or [] if isinstance(c, dict) and c.get("CMEID")]
    except (TimestampError, TypeError, ValueError, KeyError) as exc:
        raise RecordError(f"{event_type} {external_id}: {exc}") from exc
    # Bounded columns: never let an unusually long NASA string abort a batch.
    for key, limit in (("classification", 1000), ("scale", 8), ("magnitude_unit", 64), ("location", 64), ("link", 255)):
        if isinstance(out.get(key), str):
            out[key] = out[key][:limit]
    return out


def normalise_batch(event_type: str, records: Any) -> tuple[list[dict[str, Any]], NormaliseReport]:
    report = NormaliseReport()
    if not isinstance(records, list):
        report.errors.append(f"{event_type}: response is not a list")
        report.invalid = 1
        return [], report
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        report.received += 1
        try:
            n = normalise_event(event_type, rec)
        except RecordError as exc:
            report.invalid += 1
            if len(report.errors) < 20:
                report.errors.append(str(exc))
            continue
        key = n["external_id"]
        if key in seen:  # same event listed twice: keep the latest version
            report.duplicates_in_response += 1
            if n["version"] < seen[key]["version"]:
                continue
        seen[key] = n
    report.valid = len(seen)
    return list(seen.values()), report


def _notification_summary(body: str) -> str | None:
    """First substantive line of a DONKI notification ('## Summary:' section when present)."""
    m = re.search(r"##\s*Summary:\s*(.+?)(?:\n##|\Z)", body, flags=re.S)
    text = m.group(1) if m else ""
    text = _WS.sub(" ", text).strip()
    return text[:600] or None


def normalise_notification(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise RecordError("notification is not an object")
    mid = _text(record.get("messageID"), 64)
    if not mid:
        raise RecordError("notification without messageID")
    try:
        issued = parse_utc(record.get("messageIssueTime"))
    except TimestampError as exc:
        raise RecordError(f"notification {mid}: {exc}") from exc
    body = str(record.get("messageBody") or "")
    return {
        "message_id": mid,
        "message_type": _text(record.get("messageType"), 32) or "unknown",
        "issue_time": issued,
        "url": _text(record.get("messageURL"), 255),
        "summary": _notification_summary(body),
        "body": body[:20000],
    }


def normalise_notifications(records: Any) -> tuple[list[dict[str, Any]], NormaliseReport]:
    report = NormaliseReport()
    if not isinstance(records, list):
        report.errors.append("notifications: response is not a list")
        report.invalid = 1
        return [], report
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        report.received += 1
        try:
            n = normalise_notification(rec)
        except RecordError as exc:
            report.invalid += 1
            report.errors.append(str(exc))
            continue
        if n["message_id"] in seen:
            report.duplicates_in_response += 1
        seen[n["message_id"]] = n
    report.valid = len(seen)
    return list(seen.values()), report
