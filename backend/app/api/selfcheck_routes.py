"""Crew self-check endpoints (phase 8): the astronaut's own health check-in."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.errors import ApiError
from app.schemas.common import ERROR_RESPONSES
from app.schemas.selfcheck import SelfCheckSummary, SelfReport, SelfReportCreate
from app.security.deps import CurrentUser, require
from app.selfcheck.service import SelfCheckService

router = APIRouter(prefix="/api/crew", tags=["crew self-check"], responses=ERROR_RESPONSES)


class EmptyReportError(ApiError):
    status_code = 422
    code = "validation_error"


def get_service(request: Request) -> SelfCheckService:
    return request.app.state.selfcheck


Service = Annotated[SelfCheckService, Depends(get_service)]


@router.get("/{astronaut_id}/self-check", response_model=SelfCheckSummary)
async def self_check(astronaut_id: str, service: Service) -> SelfCheckSummary:
    """The crew member's self-check: hand-entered glucose, mood and symptoms with plain-language status,
    check-in prompts (due / done / overdue) and recent entries. Orientation and process guidance only."""
    return SelfCheckSummary.model_validate(await service.summary(astronaut_id))


@router.post("/{astronaut_id}/self-check", response_model=SelfReport, status_code=201,
             dependencies=[require("selfcheck:write")])
async def add_self_report(astronaut_id: str, body: SelfReportCreate, service: Service,
                          principal: CurrentUser) -> SelfReport:
    """Record a self-check entry (any combination of glucose, mood, symptoms and a note)."""
    if not body.has_content():
        raise EmptyReportError("Record at least one of glucose, mood, symptoms or a note.")
    if body.glucose_mg_dl is not None and body.glucose_context is None:
        raise EmptyReportError("Say whether the glucose value was fasting, after a meal or random.")
    return SelfReport.model_validate(await service.add(astronaut_id, body, principal.username))
