"""Accounts and sessions.

Sessions are server-side: the browser holds a random 256-bit token in an HttpOnly cookie and the
database holds only its SHA-256 digest, so sessions can be revoked (logout, password change,
deactivation) and a database dump does not contain usable tokens. Every state-changing request
made with the cookie must also carry the session's CSRF token in ``X-CSRF-Token``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, RateLimitedError, UnauthorizedError
from app.core.timeutil import utcnow
from app.db.models import AuthSessionRow, UserRow
from app.security import passwords
from app.security.rbac import Principal, Role, permissions_for

logger = logging.getLogger("astra.auth")

LAST_SEEN_WRITE_S = 60  # throttle session "last seen" writes
INVALID_LOGIN = "Invalid username or password."


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginThrottle:
    """Sliding-window limit on login attempts per client address (in memory, per process)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise RateLimitedError(
                "Too many sign-in attempts. Wait a minute and try again.",
                retry_after_s=max(1, int(60 - (now - hits[0])) + 1),
            )
        hits.append(now)


@dataclass
class LoginResult:
    token: str
    session: AuthSessionRow
    user: UserRow


class AuthService:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.factory = factory
        self.throttle = LoginThrottle(settings.auth_login_attempts_per_minute)

    # ------------------------------------------------------------------- login ----
    async def login(self, username: str, password: str, ip: str | None, user_agent: str | None) -> LoginResult:
        self.throttle.check(ip or "unknown")
        now = utcnow()
        async with self.factory() as session:
            user = await self._user_by_name(session, username)
            if user is None:
                # Spend the same hashing effort so response time does not reveal valid usernames.
                await asyncio.to_thread(passwords.verify_password, password, passwords.dummy_hash())
                raise UnauthorizedError(INVALID_LOGIN, details={"reason": "invalid_credentials"})
            if user.locked_until is not None and user.locked_until > now:
                # Same message and the same hashing effort as a wrong password, so a lockout cannot
                # be used to confirm that a username exists. The audit log keeps the real reason.
                await asyncio.to_thread(passwords.verify_password, password, passwords.dummy_hash())
                raise UnauthorizedError(INVALID_LOGIN, details={"reason": "locked"})
            ok = await asyncio.to_thread(passwords.verify_password, password, user.password_hash)
            if not ok or not user.active:
                if ok and not user.active:
                    raise UnauthorizedError(INVALID_LOGIN, details={"reason": "inactive"})
                user.failed_logins += 1
                if user.failed_logins >= self.settings.auth_max_failed_logins:
                    user.locked_until = now + timedelta(minutes=self.settings.auth_lockout_minutes)
                    user.failed_logins = 0
                    logger.warning("account %s locked after repeated failed sign-ins", user.username)
                await session.commit()
                raise UnauthorizedError(INVALID_LOGIN, details={"reason": "invalid_credentials"})
            if passwords.needs_rehash(user.password_hash):
                user.password_hash = await asyncio.to_thread(passwords.hash_password, password)
            user.failed_logins = 0
            user.locked_until = None
            user.last_login_at = now
            token = secrets.token_urlsafe(32)
            row = AuthSessionRow(
                id=uuid.uuid4().hex,
                token_hash=token_digest(token),
                user_id=user.id,
                csrf_token=secrets.token_urlsafe(24),
                created_at=now,
                expires_at=now + timedelta(hours=self.settings.auth_session_hours),
                last_seen_at=now,
                ip=(ip or None) and ip[:64],
                user_agent=(user_agent or None) and user_agent[:200],
            )
            session.add(row)
            await session.commit()
            return LoginResult(token, row, user)

    async def resolve(self, token: str, method: str = "session") -> Principal | None:
        """Principal for a session token, or None if it is unknown, expired, idle or revoked."""
        now = utcnow()
        async with self.factory() as session:
            found = (
                await session.execute(
                    select(AuthSessionRow, UserRow)
                    .join(UserRow, UserRow.id == AuthSessionRow.user_id)
                    .where(AuthSessionRow.token_hash == token_digest(token))
                )
            ).first()
            if found is None:
                return None
            row, user = found
            idle = timedelta(minutes=self.settings.auth_idle_minutes)
            if row.revoked_at is not None or row.expires_at <= now or row.last_seen_at + idle <= now or not user.active:
                return None
            if (now - row.last_seen_at).total_seconds() >= LAST_SEEN_WRITE_S:
                row.last_seen_at = now
                await session.commit()
            return Principal(
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=user.role,
                permissions=permissions_for(user.role),
                method=method,
                session_id=row.id,
                csrf_token=row.csrf_token,
            )

    async def session_info(self, session_id: str) -> AuthSessionRow | None:
        async with self.factory() as session:
            return await session.get(AuthSessionRow, session_id)

    async def logout(self, session_id: str) -> None:
        async with self.factory() as session:
            await session.execute(
                update(AuthSessionRow)
                .where(AuthSessionRow.id == session_id, AuthSessionRow.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            await session.commit()

    async def revoke_user_sessions(self, session: AsyncSession, user_id: str, keep: str | None = None) -> None:
        stmt = update(AuthSessionRow).where(
            AuthSessionRow.user_id == user_id, AuthSessionRow.revoked_at.is_(None)
        )
        if keep:
            stmt = stmt.where(AuthSessionRow.id != keep)
        await session.execute(stmt.values(revoked_at=utcnow()))

    # ----------------------------------------------------------------- accounts ----
    @staticmethod
    async def _user_by_name(session: AsyncSession, username: str) -> UserRow | None:
        return (
            await session.execute(select(UserRow).where(UserRow.username == username.strip().lower()))
        ).scalar_one_or_none()

    async def list_users(self) -> list[UserRow]:
        async with self.factory() as session:
            return list((await session.execute(select(UserRow).order_by(UserRow.username))).scalars())

    async def create_user(self, username: str, display_name: str, role: str, password: str) -> UserRow:
        username = username.strip().lower()
        Role(role)  # raises ValueError for unknown roles
        problems = passwords.policy_problems(password, username)
        if problems:
            raise ConflictError("The password does not meet the policy.", details={"problems": problems})
        now = utcnow()
        async with self.factory() as session:
            if await self._user_by_name(session, username) is not None:
                raise ConflictError(f"User {username} already exists.")
            user = UserRow(
                id=uuid.uuid4().hex,
                username=username,
                display_name=display_name.strip() or username,
                role=role,
                password_hash=await asyncio.to_thread(passwords.hash_password, password),
                active=True,
                created_at=now,
                password_changed_at=now,
                failed_logins=0,
            )
            session.add(user)
            await session.commit()
            return user

    async def update_user(
        self, user_id: str, *, role: str | None = None, active: bool | None = None,
        display_name: str | None = None, unlock: bool = False,
    ) -> UserRow:
        async with self.factory() as session:
            user = await session.get(UserRow, user_id)
            if user is None:
                raise NotFoundError(f"User {user_id} not found.")
            if role is not None:
                Role(role)
                if role != user.role:
                    user.role = role
                    await self.revoke_user_sessions(session, user.id)  # new permissions on next sign-in
            if active is not None and active != user.active:
                user.active = active
                if not active:
                    await self.revoke_user_sessions(session, user.id)
            if display_name is not None and display_name.strip():
                user.display_name = display_name.strip()
            if unlock:
                user.locked_until = None
                user.failed_logins = 0
            await session.commit()
            return user

    async def change_password(self, user_id: str, current: str, new: str, keep_session: str | None) -> None:
        async with self.factory() as session:
            user = await session.get(UserRow, user_id)
            if user is None:
                raise NotFoundError("User not found.")
            if not await asyncio.to_thread(passwords.verify_password, current, user.password_hash):
                raise UnauthorizedError("The current password is not correct.", details={"reason": "invalid_credentials"})
            problems = passwords.policy_problems(new, user.username)
            if problems:
                raise ConflictError("The password does not meet the policy.", details={"problems": problems})
            user.password_hash = await asyncio.to_thread(passwords.hash_password, new)
            user.password_changed_at = utcnow()
            await self.revoke_user_sessions(session, user.id, keep=keep_session)
            await session.commit()

    async def count_users(self) -> int:
        async with self.factory() as session:
            return len((await session.execute(select(UserRow.id))).all())


def session_expiry(row: AuthSessionRow, idle_minutes: int) -> datetime:
    return min(row.expires_at, row.last_seen_at + timedelta(minutes=idle_minutes))
