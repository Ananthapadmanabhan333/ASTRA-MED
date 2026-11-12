"""Incident reports: sections, integrity, review workflow, permissions and PDF export."""

from __future__ import annotations

import re
import zlib

from sqlalchemy import update

from app.db.models import IncidentReportRow
from app.reports.pdf import PdfDocument, clean, wrap

SECTIONS = ("mission", "astronaut", "timestamp", "measurements", "baseline_comparison", "environment",
            "anomaly_results", "model_explanation", "data_quality")


def pdf_text(data: bytes) -> bytes:
    return b"".join(zlib.decompress(m.group(1)) for m in re.finditer(rb"stream\n(.*?)\nendstream", data, re.S))


def assert_valid_pdf(data: bytes) -> int:
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    assert data[xref:xref + 4] == b"xref"
    offsets = [int(x) for x in re.findall(rb"(\d{10}) 00000 n", data)]
    for i, off in enumerate(offsets, start=1):
        assert data[off:off + len(f"{i} 0 obj")] == f"{i} 0 obj".encode()
    return int(re.search(rb"/Count (\d+)", data).group(1))


def test_pdf_writer_wraps_paginates_and_transliterates():
    doc = PdfDocument("t", "footer")
    for i in range(200):
        doc.paragraph(f"Line {i}: SpO₂ ≥ 90 % - (parentheses) and back\\slash " * 3)
    pages = assert_valid_pdf(doc.render())
    assert pages > 3
    assert clean("SpO₂ ≥ 90") == "SpO2 >= 90"
    assert all(len(line) < 120 for line in wrap("word " * 300, 10, 400))


async def _alert(p5) -> str:
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(200)
    items = (await p5.client.get("/api/decision-support/queue")).json()["items"]
    return next(i["alert_id"] for i in items if i["title"] == "Oxygen desaturation")


async def test_report_from_alert_has_every_section_and_is_intact(p5):
    alert_id = await _alert(p5)
    r = await p5.client.post("/api/reports", json={"alert_id": alert_id})
    assert r.status_code == 201
    rep = r.json()
    assert rep["review_status"] == "draft" and rep["integrity"] == "intact" and rep["data_source"] == "simulated"
    for s in SECTIONS:
        assert rep["content"][s], s
    assert rep["content"]["astronaut"]["fictional"] is True
    assert rep["content"]["label"].startswith("SIMULATED DATA")
    assert rep["content"]["measurements"]["trigger_value"] is not None
    assert rep["review_history"][0]["to"] == "draft"
    lst = (await p5.client.get("/api/reports", params={"astronaut_id": "AST-02"})).json()
    assert [x["id"] for x in lst] == [rep["id"]] and "content" not in lst[0]


async def test_report_without_alert_and_validation(p5):
    r = await p5.client.post("/api/reports", json={"astronaut_id": "AST-04", "title": "Routine check"})
    assert r.status_code == 201 and r.json()["content"]["baseline_comparison"]["features"]
    assert (await p5.client.post("/api/reports", json={})).status_code == 422
    assert (await p5.client.post("/api/reports", json={"alert_id": "nope"})).status_code == 404


async def test_tampering_is_detected(p5):
    rid = (await p5.client.post("/api/reports", json={"astronaut_id": "AST-01"})).json()["id"]
    async with p5.app.state.session_factory() as s:
        row = await s.get(IncidentReportRow, rid)
        content = dict(row.content)
        content["summary"] = "edited outside the API"
        await s.execute(update(IncidentReportRow).where(IncidentReportRow.id == rid).values(content=content))
        await s.commit()
    assert (await p5.client.get(f"/api/reports/{rid}")).json()["integrity"] == "modified"


async def test_review_transitions(p5):
    rid = (await p5.client.post("/api/reports", json={"astronaut_id": "AST-01"})).json()["id"]
    url = f"/api/reports/{rid}/review"
    assert (await p5.client.post(url, json={"status": "closed"})).status_code == 409
    for to in ("pending_review", "under_review"):
        assert (await p5.client.post(url, json={"status": to})).status_code == 200
    assert (await p5.client.post(url, json={"status": "reviewed"})).status_code == 409  # note required
    done = await p5.client.post(url, json={"status": "reviewed", "note": "Reviewed simulated data."})
    assert done.status_code == 200
    history = done.json()["review_history"]
    assert [h["to"] for h in history] == ["draft", "pending_review", "under_review", "reviewed"]
    assert history[-1]["note"] == "Reviewed simulated data."


async def test_pdf_export_contains_every_section(p5):
    alert_id = await _alert(p5)
    rid = (await p5.client.post("/api/reports", json={"alert_id": alert_id})).json()["id"]
    r = await p5.client.get(f"/api/reports/{rid}/pdf", params={"download": True})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert "content-security-policy" not in r.headers
    assert assert_valid_pdf(r.content) >= 2
    text = pdf_text(r.content)
    for heading in ("1. Mission information", "2. Astronaut", "3. Timestamp", "4. Measurements",
                    "5. Baseline comparison", "6. Environmental conditions", "7. Anomaly-detection results",
                    "8. Model explanation", "9. Data-quality limitations", "10. Review status"):
        assert heading.encode() in text, heading
    assert b"SIMULATED DATA" in text and b"Lukas Brandt" in text
