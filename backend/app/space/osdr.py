"""OSDR study catalogue adapter. Only metadata is ingested; no study data files are downloaded."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.space.timeparse import parse_epoch

STUDY_URL = "https://osdr.nasa.gov/bio/repo/data/studies/{accession}"

# Topic presets for the explorer: (key, label, OSDR search term).
TOPICS: list[tuple[str, str, str]] = [
    ("radiation", "Radiation-related biological studies", "radiation"),
    ("rodent", "Rodent research", "rodent research"),
    ("spaceflight", "Spaceflight biological experiments", "spaceflight"),
    ("physiology", "Physiological research", "cardiovascular"),
    ("environment", "Environmental monitoring", "environmental monitoring"),
]
TOPIC_KEYS = {k for k, _, _ in TOPICS}
# Lookarounds instead of \b: "_" is a word character, and identifiers look like "RR-1_BSP".
_MISSION_CODE = re.compile(r"(?<![A-Za-z0-9])((?:RR|APEX|VEG)-\d+[A-Z]?(?:-\d)?)(?![0-9])", re.IGNORECASE)
_WS = re.compile(r"\s+")


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        value = "; ".join(str(v) for v in value if v not in (None, ""))
    s = _WS.sub(" ", str(value)).strip()
    return s[:limit] if s else None


def parse_us_date(value: Any) -> datetime | None:
    """OSDR mission dates: MM/DD/YYYY or M/D/YY."""
    text = _text(value, 20)
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def mission_codes(*texts: str | None) -> list[str]:
    codes = []
    for t in texts:
        for m in _MISSION_CODE.findall(t or ""):
            c = m.upper()
            if c not in codes:
                codes.append(c)
    return codes


def normalise_hit(hit: dict[str, Any], topic: str | None) -> dict[str, Any] | None:
    src = hit.get("_source") if isinstance(hit, dict) else None
    if not isinstance(src, dict):
        return None
    accession = _text(src.get("Accession"), 32)
    title = _text(src.get("Study Title"), 2000)
    if not accession or not accession.upper().startswith(("OSD-", "GLDS-")) or not title:
        return None
    mission = src.get("Mission") if isinstance(src.get("Mission"), dict) else {}
    codes = mission_codes(_text(src.get("Project Identifier"), 64), title)
    topics = ([topic] if topic else []) + [f"mission:{c}" for c in codes]
    return {
        "accession": accession,
        "title": title,
        "description": _text(src.get("Study Description"), 4000),
        "organism": _text(src.get("organism"), 255),
        "project_type": _text(src.get("Project Type"), 64),
        "flight_program": _text(src.get("Flight Program"), 128),
        "mission_name": _text(mission.get("Name"), 128),
        "mission_start": parse_us_date(mission.get("Start Date")),
        "mission_end": parse_us_date(mission.get("End Date")),
        "assay_type": _text(src.get("Study Assay Technology Type"), 255),
        "material_type": _text(src.get("Material Type"), 255),
        "platform": _text(src.get("Experiment Platform"), 128),
        "release_date": parse_epoch(src.get("Study Public Release Date")),
        "data_source_accession": _text(src.get("Data Source Accession"), 64),
        "link": STUDY_URL.format(accession=accession),
        "topics": topics,
    }


def normalise_search(payload: Any, topic: str | None) -> tuple[list[dict[str, Any]], int, int]:
    """Returns (studies, total hits reported by OSDR, invalid hits)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), dict):
        raise ValueError("OSDR search response has no 'hits' object")
    hits = payload["hits"].get("hits") or []
    total = payload["hits"].get("total")
    total = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
    out, invalid, seen = [], 0, set()
    for h in hits:
        n = normalise_hit(h, topic)
        if n is None:
            invalid += 1
            continue
        if n["accession"] in seen:
            continue
        seen.add(n["accession"])
        out.append(n)
    return out, total, invalid
