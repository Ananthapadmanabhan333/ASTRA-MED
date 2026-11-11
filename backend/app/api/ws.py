"""``/ws/health-monitoring``: live vitals, ECG segments, alert and scenario events.

On connect the server sends ``hello`` (current state), then a ``vitals`` message every tick.
Clients may send ``{"action": "ping"}`` and receive ``pong``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.timeutil import utcnow
from app.schemas.ws import WsClientMessage, WsPong
from app.services.monitoring import MonitoringService

logger = logging.getLogger("astra.ws")
router = APIRouter()


def _origin_allowed(ws: WebSocket, allowed: list[str]) -> bool:
    origin = ws.headers.get("origin")
    return origin is None or "*" in allowed or origin in allowed


@router.websocket("/ws/health-monitoring")
async def health_monitoring(ws: WebSocket) -> None:
    monitor: MonitoringService = ws.app.state.monitor
    if not _origin_allowed(ws, monitor.settings.cors_origin_list):
        logger.warning("rejected websocket from origin %s", ws.headers.get("origin"))
        await ws.close(code=1008)
        return

    await ws.accept()
    await ws.send_text(monitor.hello().model_dump_json())
    monitor.hub.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = WsClientMessage.model_validate_json(raw)
            except ValidationError:
                continue  # ignore malformed client messages
            if msg.action == "ping":
                await monitor.hub.send(ws, WsPong(server_time=utcnow()).model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        monitor.hub.remove(ws)
