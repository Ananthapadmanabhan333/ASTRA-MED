"""Access control on the phase 5 endpoints (authentication switched on)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AuditLogRow


@pytest.mark.parametrize(
    ("role", "method", "path", "body", "expected"),
    [
        ("admin", "GET", "/api/twin/AST-01", None, 403),
        ("admin", "GET", "/api/multisystem", None, 403),
        ("admin", "POST", "/api/assistant/ask", {"question": "How is AST-01?"}, 403),
        ("admin", "GET", "/api/reports", None, 403),
        ("analyst", "GET", "/api/reports", None, 403),
        ("analyst", "POST", "/api/reports", {"astronaut_id": "AST-01"}, 403),
        ("analyst", "POST", "/api/emergency/runs", {"scenario": "hr_elevation", "astronaut_id": "AST-01"}, 403),
        ("analyst", "GET", "/api/decision-support/queue", None, 200),
        ("analyst", "POST", "/api/assistant/ask", {"question": "What is the personal baseline?"}, 200),
        ("flight_surgeon", "POST", "/api/emergency/runs", {"scenario": "hr_elevation", "astronaut_id": "AST-01"}, 403),
        ("flight_surgeon", "GET", "/api/reports", None, 200),
        ("mission_operator", "POST", "/api/emergency/runs",
         {"scenario": "hr_elevation", "astronaut_id": "AST-01", "duration_seconds": 30}, 201),
    ],
)
async def test_phase5_permission_matrix(secure, role, method, path, body, expected):
    async with secure.signed_in(role) as c:
        r = await c.request(method, path, json=body)
        assert r.status_code == expected, r.text


async def test_only_reviewers_can_sign_off_reports(secure):
    async with secure.signed_in("mission_operator") as op:
        rep = await op.post("/api/reports", json={"astronaut_id": "AST-02", "title": "Access test"})
        assert rep.status_code == 201
        rid = rep.json()["id"]
        assert (await op.post(f"/api/reports/{rid}/review", json={"status": "pending_review"})).status_code == 200
        denied = await op.post(f"/api/reports/{rid}/review", json={"status": "under_review"})
        assert denied.status_code == 403 and denied.json()["error"]["details"]["required"] == ["reports:review"]
    async with secure.signed_in("flight_surgeon") as fs:
        assert (await fs.post(f"/api/reports/{rid}/review", json={"status": "under_review"})).status_code == 200
        ok = await fs.post(f"/api/reports/{rid}/review", json={"status": "reviewed", "note": "Reviewed."})
        assert ok.status_code == 200 and ok.json()["review_history"][-1]["role"] == "flight_surgeon"
        pdf = await fs.get(f"/api/reports/{rid}/pdf")
        assert pdf.status_code == 200
    async with secure.app.state.session_factory() as s:
        actions = [r.action for r in (await s.scalars(select(AuditLogRow))).all()]
    assert "report_exported" in actions and "POST /api/reports/{report_id}/review" in actions


async def test_assistant_queries_are_audited_without_their_text(secure):
    question = "How is Priya doing right now?"
    async with secure.signed_in("analyst") as c:
        assert (await c.post("/api/assistant/ask", json={"question": question})).status_code == 200
    async with secure.app.state.session_factory() as s:
        row = (await s.scalars(select(AuditLogRow).where(AuditLogRow.action == "assistant_query"))).one()
    assert row.username == "test-analyst" and len(row.detail["question_sha256"]) == 16
    assert question not in str(row.detail) and "Priya" not in str(row.detail)
