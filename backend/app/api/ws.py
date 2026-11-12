"""``/ws/health-monitoring``: live vitals, ECG segments, alert and scenario events.

On connect the server sends ``hello`` (current state), then a ``vitals`` message every tick.
Clients may send ``{"action": "ping"}`` and receive ``pong``.

The handshake must come from an allowed Origin and carry a valid session (the browser sends the
session cookie automatically; other clients send ``Authorization: Bearer``) whose role grants
``health:read``. Otherwise the server closes with 1008 (policy violation) before accepting.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.timeutil import utcnow
from app.schemas.ws import WsClientMessage, WsPong
from app.security.audit import client_ip
from app.security.deps import authenticate, get_audit
from app.services.monitoring import MonitoringService

logger = logging.getLogger("astra.ws")
router = APIRouter()

REVALIDATE_EVERY_S = 60.0  # a revoked or expired session stops streaming within this time


async def _revalidate(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(REVALIDATE_EVERY_S)
        principal = await authenticate(ws)
        if principal is None or not principal.can("health:read"):
            logger.info("closing websocket: session no longer valid")
            await ws.close(code=1008)
            return


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
    principal = await authenticate(ws)
    if principal is None or not principal.can("health:read"):
        await get_audit(ws).record(
            "ws_rejected", principal=principal, outcome="denied", resource_type="stream",
            resource_id="health-monitoring", ip=client_ip(ws),
            detail={"reason": "not_signed_in" if principal is None else "permission"},
        )
        await ws.close(code=1008)
        return
    audit = get_audit(ws)
    if audit.first_read(principal.user_id, "/ws/health-monitoring", ""):
        await audit.record("view /ws/health-monitoring", principal=principal, resource_type="stream",
                           resource_id="health-monitoring", ip=client_ip(ws))

    await ws.accept()
    await ws.send_text(monitor.hello().model_dump_json())
    monitor.hub.add(ws)
    watchdog = asyncio.create_task(_revalidate(ws)) if principal.method != "disabled" else None
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
    except RuntimeError:
        pass  # closed by the revalidation watchdog
    finally:
        monitor.hub.remove(ws)
        if watchdog is not None:
            watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await watchdog
