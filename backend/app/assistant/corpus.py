"""The assistant's knowledge sources, split into citable passages.

1. ASTRA-MED documentation (docs/*.md): describes how the software and its models behave.
2. NASA open data already ingested in phase 4: DONKI notification texts and OSDR study metadata.
3. Approved reference documents placed in backend/knowledge/ and listed in its manifest with
   ``"approved": true`` (e.g. NASA Human Research Program documents). None ship with the repository:
   adding one is a deliberate, reviewed step, so the assistant can never cite a reference that is not
   actually present.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OsdrStudyRow, SpaceNotificationRow

REPO = Path(__file__).resolve().parents[3]
DOCS_DIR = REPO / "docs"
KNOWLEDGE_DIR = REPO / "backend" / "knowledge"
MAX_WORDS = 170
MAX_NOTIFICATIONS = 400

SOURCE_TYPES: dict[str, dict[str, str]] = {
    "astra_docs": {"label": "ASTRA-MED documentation", "knowledge": "project documentation",
                   "description": "How ASTRA-MED and its models work. Describes software, not human physiology."},
    "nasa_donki": {"label": "NASA DONKI notification", "knowledge": "real NASA public data",
                   "description": "Space-weather notification text published by NASA (CCMC/M2M)."},
    "nasa_osdr": {"label": "NASA OSDR study", "knowledge": "real NASA public data",
                  "description": "Study metadata from NASA's Open Science Data Repository."},
    "reference": {"label": "Approved reference", "knowledge": "approved reference document",
                  "description": "A reference document approved for use and listed in backend/knowledge/manifest.json."},
}


@dataclass
class Passage:
    id: str
    source_type: str
    title: str
    section: str | None
    text: str
    url: str | None = None
    path: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        # The section heading is repeated so passages under a matching heading rank first.
        return f"{self.title} {self.section or ''} {self.section or ''} {self.text}"


def _clean_md(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # code blocks are not prose
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*\|.*$", " ", text, flags=re.M)  # tables do not read as quotable prose
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def _chunks(text: str, max_words: int = MAX_WORDS) -> list[str]:
    """Sentence-aligned chunks; the last sentence of a chunk opens the next one for context."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    out: list[str] = []
    cur: list[str] = []
    for s in sentences:
        n = len(s.split())
        if cur and sum(len(c.split()) for c in cur) + n > max_words:
            out.append(" ".join(cur))
            last = cur[-1]
            cur = [last] if len(last.split()) <= 40 else []
        cur.append(s)
    if cur and (sum(len(c.split()) for c in cur) > 8 or not out):
        out.append(" ".join(cur))
    return out


def doc_passages(docs_dir: Path = DOCS_DIR) -> list[Passage]:
    out: list[Passage] = []
    for path in sorted([*docs_dir.glob("*.md"), *docs_dir.glob("reports/*.md")]):
        raw = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", raw, re.M)
        doc_title = title_match.group(1).strip() if title_match else path.stem
        parts = re.split(r"^(#{2,3}\s+.+)$", raw, flags=re.M)
        section = None
        for part in parts:
            if re.match(r"^#{2,3}\s+", part):
                section = part.lstrip("#").strip()
                continue
            body = _clean_md(part)
            if len(body.split()) < 12:
                continue
            for i, chunk in enumerate(_chunks(body)):
                rel = f"docs/{path.relative_to(docs_dir).as_posix()}"
                out.append(Passage(f"doc:{rel}#{section or 'intro'}:{i}", "astra_docs", doc_title, section, chunk,
                                   path=rel))
    return out


async def nasa_passages(session: AsyncSession) -> list[Passage]:
    out: list[Passage] = []
    notes = (await session.scalars(select(SpaceNotificationRow).order_by(SpaceNotificationRow.issue_time.desc())
                                   .limit(MAX_NOTIFICATIONS))).all()
    for n in notes:
        body = re.sub(r"\s+", " ", n.body or "").strip()
        body = re.sub(r"##+", " ", body)
        for i, chunk in enumerate(_chunks(body)[:3]):
            out.append(Passage(f"donki:{n.message_id}:{i}", "nasa_donki",
                               f"DONKI {n.message_type} notification {n.message_id}",
                               n.issue_time.strftime("%Y-%m-%d %H:%M UTC"), chunk, url=n.url,
                               meta={"issue_time": n.issue_time.isoformat(), "retrieved_at": n.retrieved_at.isoformat()}))
    studies = (await session.scalars(select(OsdrStudyRow))).all()
    for s in studies:
        text = " ".join(x for x in (s.title, s.description or "", f"Organism: {s.organism}." if s.organism else "",
                                    f"Mission: {s.mission_name}." if s.mission_name else "",
                                    f"Assay: {s.assay_type}." if s.assay_type else "") if x)
        for i, chunk in enumerate(_chunks(re.sub(r"\s+", " ", text))[:2]):
            out.append(Passage(f"osdr:{s.accession}:{i}", "nasa_osdr", f"OSDR {s.accession}: {s.title}"[:200],
                               s.mission_name, chunk, url=s.link,
                               meta={"accession": s.accession, "retrieved_at": s.retrieved_at.isoformat()}))
    return out


def reference_passages(knowledge_dir: Path = KNOWLEDGE_DIR) -> tuple[list[Passage], list[dict[str, Any]]]:
    """Approved reference documents. Returns (passages, manifest entries with their status)."""
    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        return [], []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: list[Passage] = []
    entries = []
    for entry in manifest.get("documents", []):
        path = knowledge_dir / entry.get("file", "")
        ok = bool(entry.get("approved")) and path.is_file() and path.suffix in (".md", ".txt")
        entries.append({**{k: entry.get(k) for k in ("title", "publisher", "url", "license", "approved", "approved_by")},
                        "loaded": ok})
        if not ok:
            continue
        body = _clean_md(path.read_text(encoding="utf-8"))
        for i, chunk in enumerate(_chunks(body)):
            out.append(Passage(f"ref:{path.name}:{i}", "reference", entry["title"], entry.get("publisher"), chunk,
                               url=entry.get("url"), meta={"license": entry.get("license")}))
    return out, entries
