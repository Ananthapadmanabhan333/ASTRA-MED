"""WebSocket fan-out. Slow or dead clients are dropped instead of stalling the tick loop."""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger("astra.ws")


class ConnectionHub:
    def __init__(self, send_timeout_s: float = 2.0) -> None:
        # One lock per socket: broadcasts and direct replies never interleave frames.
        self._clients: dict[WebSocket, asyncio.Lock] = {}
        # Permissions each socket's user holds (None: not tracked, e.g. authentication disabled).
        self._permissions: dict[WebSocket, frozenset[str] | None] = {}
        self.send_timeout_s = send_timeout_s

    @property
    def count(self) -> int:
        return len(self._clients)

    def add(self, ws: WebSocket, permissions: frozenset[str] | None = None) -> None:
        self._clients[ws] = asyncio.Lock()
        self._permissions[ws] = permissions
        logger.info("client connected (%d total)", len(self._clients))

    def remove(self, ws: WebSocket) -> None:
        self._permissions.pop(ws, None)
        if self._clients.pop(ws, None) is not None:
            logger.info("client disconnected (%d total)", len(self._clients))

    async def send(self, ws: WebSocket, text: str) -> None:
        lock = self._clients.get(ws)
        if lock is None:
            await ws.send_text(text)
            return
        async with lock:
            await asyncio.wait_for(ws.send_text(text), self.send_timeout_s)

    async def broadcast(self, text: str, requires: str | None = None) -> None:
        """Send to every client, or only to clients whose user holds ``requires``."""
        if not self._clients:
            return
        clients = [ws for ws in self._clients
                   if requires is None or (perms := self._permissions.get(ws)) is None or requires in perms]
        results = await asyncio.gather(*(self.send(ws, text) for ws in clients), return_exceptions=True)
        for ws, result in zip(clients, results):
            if isinstance(result, BaseException):
                logger.warning("dropping client after send failure: %r", result)
                self.remove(ws)
