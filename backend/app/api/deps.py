from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.monitoring import MonitoringService


def get_monitor(request: Request) -> MonitoringService:
    return request.app.state.monitor


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


Monitor = Annotated[MonitoringService, Depends(get_monitor)]
Session = Annotated[AsyncSession, Depends(get_session)]
