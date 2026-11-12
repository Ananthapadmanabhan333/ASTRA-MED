"""Audit log: who signed in, who viewed which health records, and who changed what.

Entries hold identifiers (user, route, resource id, outcome), never measurement values, so the log
itself does not become a second copy of the health record. Repeated reads of the same resource by
the same user are recorded once per ``audit_read_dedupe_seconds`` (dashboards poll).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.timeutil import utcnow
from app.db.models import AuditLogRow
from app.security.rbac import Principal

logger = logging.getLogger("astra.audit")

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Route templates whose successful GETs count as viewing a health record.
SENSITIVE_READ_PREFIXES = (
    "/api/health/", "/api/alerts", "/api/insights", "/api/radiation", "/api/ai/", "/api/twin",
    "/api/multisystem", "/api/decision-support", "/api/reports", "/api/emergency", "/api/overview",
    "/api/assistant", "/api/astronauts/",
)
SKIP_PREFIXES = ("/api/auth/",)  # the auth routes write their own, more specific entries

RESOURCE_PARAMS = ("astronaut_id", "alert_id", "report_id", "run_id", "event_id", "user_id")


def client_ip(request: Any) -> str | None:
    client = getattr(request, "client", None)
    return client.host if client else None


def resource_from_path(template: str, params: dict[str, Any]) -> tuple[str | None, str | None]:
    for name in RESOURCE_PARAMS:
        if name in params:
            return name.removesuffix("_id"), str(params[name])
    parts = [p for p in template.split("/") if p and not p.startswith("{")]
    return (parts[1] if len(parts) > 1 else None), None


def outcome_for(status: int) -> str:
    if status < 400:
        return "success"
    if status in (401, 403):
        return "denied"
    return "failure"


class AuditLog:
    def __init__(self, factory: async_sessionmaker[AsyncSession], read_dedupe_s: int = 300) -> None:
        self.factory = factory
        self.read_dedupe_s = read_dedupe_s
        self._recent_reads: dict[tuple[str, str, str], float] = {}

    async def record(
        self,
        action: str,
        *,
        principal: Principal | None = None,
        username: str | None = None,
        outcome: str = "success",
        resource_type: str | None = None,
        resource_id: str | None = None,
        status_code: int | None = None,
        ip: str | None = None,
        request_id: str | None = None,
        detail: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> None:
        row = AuditLogRow(
            ts=ts or utcnow(),
            user_id=principal.user_id if principal else None,
            username=(principal.username if principal else username),
            role=principal.role if principal else None,
            action=action[:64],
            resource_type=resource_type and resource_type[:48],
            resource_id=resource_id and resource_id[:128],
            outcome=outcome,
            status_code=status_code,
            ip=ip and ip[:64],
            request_id=request_id and request_id[:32],
            detail=detail or {},
        )
        try:
            async with self.factory() as session:
                session.add(row)
                await session.commit()
        except Exception:  # pragma: no cover - storage failure must be loud but not crash the request
            logger.exception("could not write audit entry %s", action)

    def first_read(self, user_id: str, route: str, resource: str, now: float | None = None,
                   window_s: float | None = None) -> bool:
        """True if this event should be recorded (not seen within the dedupe window)."""
        now = time.monotonic() if now is None else now
        window = self.read_dedupe_s if window_s is None else window_s
        key = (user_id, route, resource)
        last = self._recent_reads.get(key)
        if last is not None and now - last < window:
            return False
        self._recent_reads[key] = now
        if len(self._recent_reads) > 20_000:  # keep memory bounded
            cutoff = now - self.read_dedupe_s
            self._recent_reads = {k: v for k, v in self._recent_reads.items() if v >= cutoff}
        return True

    async def list(
        self,
        *,
        username: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        resource_type: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[AuditLogRow]:
        stmt = select(AuditLogRow).order_by(AuditLogRow.ts.desc(), AuditLogRow.id.desc()).limit(limit)
        if username:
            stmt = stmt.where(AuditLogRow.username == username)
        if action:
            stmt = stmt.where(AuditLogRow.action.contains(action))
        if outcome:
            stmt = stmt.where(AuditLogRow.outcome == outcome)
        if resource_type:
            stmt = stmt.where(AuditLogRow.resource_type == resource_type)
        if since:
            stmt = stmt.where(AuditLogRow.ts >= since)
        async with self.factory() as session:
            return list((await session.execute(stmt)).scalars())
