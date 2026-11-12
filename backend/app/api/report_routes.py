"""Structured incident reports with review status and PDF export (phase 5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.reports.render import render_report
from app.reports.service import ReportService, report_view
from app.schemas.common import ERROR_RESPONSES
from app.schemas.reports import IncidentReport, ReportCreate, ReportSummary, ReviewStatus, ReviewUpdate
from app.security.audit import client_ip
from app.security.deps import CurrentUser, get_audit, require
from app.security.rbac import Principal

router = APIRouter(prefix="/api/reports", tags=["incident reports"], responses=ERROR_RESPONSES)


def get_reports(request: Request) -> ReportService:
    return request.app.state.reports


Reports = Annotated[ReportService, Depends(get_reports)]


@router.post("", response_model=IncidentReport, status_code=201)
async def create_report(body: ReportCreate, reports: Reports,
                        principal: Annotated[Principal, require("reports:write")]) -> IncidentReport:
    """Freeze the current decision-support data for an alert, a run or a time into a draft report."""
    row = await reports.create(principal, alert_id=body.alert_id, run_id=body.run_id, astronaut_id=body.astronaut_id,
                               occurred_at=body.occurred_at, title=body.title, summary=body.summary)
    return IncidentReport.model_validate(report_view(row))


@router.get("", response_model=list[ReportSummary])
async def list_reports(
    reports: Reports, astronaut_id: str | None = None, status: ReviewStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReportSummary]:
    return [ReportSummary.model_validate(report_view(r, include_content=False))
            for r in await reports.list(astronaut_id, status, limit)]


@router.get("/{report_id}", response_model=IncidentReport)
async def get_report(report_id: str, reports: Reports) -> IncidentReport:
    return IncidentReport.model_validate(report_view(await reports.get(report_id)))


@router.post("/{report_id}/review", response_model=IncidentReport)
async def review_report(report_id: str, body: ReviewUpdate, reports: Reports, principal: CurrentUser) -> IncidentReport:
    """Move the review status. Sign-off states (under review, reviewed, closed) need reports:review."""
    row = await reports.review(report_id, principal, body.status, body.note)
    return IncidentReport.model_validate(report_view(row))


@router.get("/{report_id}/pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}, "description": "PDF export"}})
async def report_pdf(report_id: str, reports: Reports, request: Request, principal: CurrentUser,
                     download: bool = False) -> Response:
    """The report as a PDF (inline by default; ``download=true`` for an attachment)."""
    view = report_view(await reports.get(report_id))
    pdf = render_report(view)
    await get_audit(request).record("report_exported", principal=principal, resource_type="report",
                                    resource_id=report_id, ip=client_ip(request), detail={"format": "pdf"})
    disposition = "attachment" if download else "inline"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="astra-med-incident-{report_id}.pdf"'})
