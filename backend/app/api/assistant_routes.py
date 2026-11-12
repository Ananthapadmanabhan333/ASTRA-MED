"""Medical data assistant endpoints (phase 5)."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.assistant.service import AssistantService
from app.schemas.assistant import AskRequest, AssistantAnswer, AssistantStatus
from app.schemas.common import ERROR_RESPONSES
from app.security.audit import client_ip
from app.security.deps import get_audit, require
from app.security.rbac import Principal

router = APIRouter(prefix="/api/assistant", tags=["assistant"], responses=ERROR_RESPONSES)


def get_assistant(request: Request) -> AssistantService:
    return request.app.state.assistant


Assistant = Annotated[AssistantService, Depends(get_assistant)]


@router.get("/status", response_model=AssistantStatus)
async def assistant_status(assistant: Assistant) -> AssistantStatus:
    """Answer mode, indexed sources and the approved reference library."""
    return AssistantStatus.model_validate(await assistant.status())


@router.post("/ask", response_model=AssistantAnswer)
async def ask(body: AskRequest, request: Request, assistant: Assistant,
              principal: Annotated[Principal, require("assistant:use")]) -> AssistantAnswer:
    """Answer a question with a citation for every statement. Declines diagnosis and treatment, lists
    missing information and escalates potentially serious situations. Nothing is stored except an
    audit entry with a hash of the question (not its text)."""
    result = await assistant.ask(body.question, principal, body.astronaut_id)
    await get_audit(request).record(
        "assistant_query", principal=principal, resource_type="assistant", ip=client_ip(request),
        detail={"question_sha256": hashlib.sha256(body.question.encode("utf-8")).hexdigest()[:16],
                "tasks": result["understood"]["tasks"], "astronauts": result["understood"]["astronaut_ids"],
                "mode": result["mode"], "escalated": result["escalation"]["required"],
                "declined": bool(result["declined"])},
    )
    return AssistantAnswer.model_validate(result)
