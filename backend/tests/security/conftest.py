from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app

ROLES = ("flight_surgeon", "mission_operator", "analyst", "admin")


@pytest.fixture
def secure_settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'secure.db').as_posix()}",
        auth_enabled=True,
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=0,
        space_sync_enabled=False,
        log_level="WARNING",
        auth_login_attempts_per_minute=60,
    )


def make_password() -> str:
    return "Tp-" + secrets.token_urlsafe(18)


class SecureApp:
    def __init__(self, app, users: dict[str, tuple[str, str]]) -> None:
        self.app = app
        self.users = users  # role -> (username, password), generated per test run

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.app, client=("10.0.0.7", 5000)), base_url="http://test")

    @asynccontextmanager
    async def signed_in(self, role: str):
        username, password = self.users[role]
        async with self.client() as c:
            r = await c.post("/api/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
            yield c


@pytest_asyncio.fixture
async def secure(secure_settings):
    app = create_app(secure_settings)
    async with app.router.lifespan_context(app):
        users = {}
        for role in ROLES:
            username, password = f"test-{role.replace('_', '-')}", make_password()
            await app.state.auth.create_user(username, role.replace("_", " ").title(), role, password)
            users[role] = (username, password)
        yield SecureApp(app, users)
