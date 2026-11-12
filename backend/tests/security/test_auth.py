"""Authentication, sessions, CSRF, RBAC and audit logging, with authentication switched on."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.models import AuditLogRow, AuthSessionRow, UserRow
from app.main import create_app
from app.security import passwords
from app.security.rbac import PERMISSIONS, ROLE_PERMISSIONS, Role
from app.security.service import LoginThrottle

from .conftest import make_password


async def audit_rows(app, action: str | None = None) -> list[AuditLogRow]:
    async with app.state.session_factory() as s:
        stmt = select(AuditLogRow).order_by(AuditLogRow.id)
        if action:
            stmt = stmt.where(AuditLogRow.action == action)
        return list((await s.execute(stmt)).scalars())


# ----------------------------------------------------------------- passwords -------
def test_scrypt_hash_round_trip_and_format():
    pw = make_password()
    h = passwords.hash_password(pw)
    assert h.startswith("scrypt$32768$8$3$") and pw not in h
    assert passwords.verify_password(pw, h)
    assert not passwords.verify_password(pw + "x", h)
    assert passwords.hash_password(pw) != h  # salted
    assert not passwords.verify_password(pw, "garbage") and not passwords.verify_password(pw, "md5$abc")
    assert not passwords.needs_rehash(h) and passwords.needs_rehash("scrypt$16384$8$1$a$b")


def test_password_policy():
    assert passwords.policy_problems("short")
    assert passwords.policy_problems("aaaaaaaaaaaaaaaa")  # repetitive
    assert passwords.policy_problems("operator-2026-secret", "operator")
    assert passwords.policy_problems(make_password(), "alice") == []


def test_every_role_permission_is_defined_and_admin_has_no_health_access():
    assert {r.value for r in Role} == {"flight_surgeon", "mission_operator", "analyst", "admin"}
    assert all(p in PERMISSIONS for perms in ROLE_PERMISSIONS.values() for p in perms)
    assert "health:read" not in ROLE_PERMISSIONS[Role.ADMIN]
    assert "reports:review" in ROLE_PERMISSIONS[Role.FLIGHT_SURGEON]
    assert ROLE_PERMISSIONS[Role.ANALYST] == {"health:read", "space:read", "assistant:use"}


def test_login_throttle_window():
    t = LoginThrottle(per_minute=3)
    for i in range(3):
        t.check("ip", now=100.0 + i)
    with pytest.raises(Exception) as exc:
        t.check("ip", now=103.0)
    assert exc.value.status_code == 429 and exc.value.retry_after_s >= 1
    t.check("ip", now=161.0)  # oldest attempt left the window


def test_production_refuses_disabled_auth_and_wildcard_cors(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(Settings(environment="production", auth_enabled=False))
    with pytest.raises(RuntimeError):
        create_app(Settings(cors_origins="*", auth_enabled=True))


# ------------------------------------------------------------------ sign-in -------
async def test_unauthenticated_requests_are_rejected_except_liveness(secure):
    async with secure.client() as c:
        assert (await c.get("/api/system/health")).status_code == 200
        for path in ("/api/astronauts", "/api/alerts", "/api/space/sources", "/api/ai/status", "/api/auth/me",
                     "/api/admin/audit"):
            r = await c.get(path)
            assert r.status_code == 401, path
            assert r.json()["error"]["code"] == "unauthenticated"
            assert r.headers["www-authenticate"].startswith("Bearer")


async def test_login_sets_strict_httponly_cookie_and_returns_csrf(secure):
    username, password = secure.users["flight_surgeon"]
    async with secure.client() as c:
        r = await c.post("/api/auth/login", json={"username": username.upper(), "password": password})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["role"] == "flight_surgeon" and body["method"] == "session"
        assert body["csrf_token"] and "reports:review" in body["permissions"]
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
        assert password not in r.text
        me = (await c.get("/api/auth/me")).json()
        assert me["user"]["username"] == username and me["csrf_token"] == body["csrf_token"]
        token = c.cookies["astra_session"]
    async with secure.app.state.session_factory() as s:
        sessions = list((await s.execute(select(AuthSessionRow))).scalars())
        assert len(sessions) == 1 and len(sessions[0].token_hash) == 64
        assert sessions[0].token_hash != token and token not in str(sessions[0].__dict__)
    logins = await audit_rows(secure.app, "login")
    assert logins and logins[-1].username == username and logins[-1].ip == "10.0.0.7"


async def test_wrong_password_is_generic_and_audited(secure):
    username, _ = secure.users["analyst"]
    async with secure.client() as c:
        bad = await c.post("/api/auth/login", json={"username": username, "password": "wrong-password-123"})
        unknown = await c.post("/api/auth/login", json={"username": "nobody", "password": "wrong-password-123"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"] == "Invalid username or password."
    assert bad.json()["error"]["details"] is None
    failed = await audit_rows(secure.app, "login_failed")
    assert [f.username for f in failed] == [username, "nobody"]
    assert all(f.outcome == "denied" and "wrong-password" not in str(f.detail) for f in failed)


async def test_account_locks_after_repeated_failures(secure):
    username, password = secure.users["mission_operator"]
    limit = secure.app.state.settings.auth_max_failed_logins
    async with secure.client() as c:
        for _ in range(limit):
            assert (await c.post("/api/auth/login", json={"username": username, "password": "nope-nope-nope"})).status_code == 401
        locked = await c.post("/api/auth/login", json={"username": username, "password": password})
        assert locked.status_code == 401  # correct password, but locked
    async with secure.app.state.session_factory() as s:
        user = (await s.execute(select(UserRow).where(UserRow.username == username))).scalar_one()
        assert user.locked_until is not None
    reasons = [r.detail.get("reason") for r in await audit_rows(secure.app, "login_failed")]
    assert reasons[-1] == "locked"


async def test_login_rate_limit_per_client(secure):
    secure.app.state.auth.throttle.per_minute = 3
    async with secure.client() as c:
        codes = [(await c.post("/api/auth/login", json={"username": "x", "password": "y" * 12})).status_code
                 for _ in range(4)]
        assert codes == [401, 401, 401, 429]
        r = await c.post("/api/auth/login", json={"username": "x", "password": "y" * 12})
        assert int(r.headers["retry-after"]) >= 1


async def test_logout_revokes_the_session(secure):
    async with secure.signed_in("analyst") as c:
        token = c.cookies["astra_session"]
        assert (await c.get("/api/auth/me")).status_code == 200
        assert (await c.post("/api/auth/logout")).status_code == 204
        assert "astra_session" not in c.cookies  # cookie cleared
    async with secure.client() as replay:
        r = await replay.get("/api/auth/me", headers={"Cookie": f"astra_session={token}"})
        assert r.status_code == 401 and r.json()["error"]["details"]["reason"] == "session_expired"
    assert await audit_rows(secure.app, "logout")


async def test_idle_and_expired_sessions_are_refused(secure):
    async with secure.signed_in("analyst") as c:
        assert (await c.get("/api/astronauts")).status_code == 200
        async with secure.app.state.session_factory() as s:
            await s.execute(update(AuthSessionRow).values(last_seen_at=utcnow() - timedelta(minutes=61)))
            await s.commit()
        r = await c.get("/api/astronauts")
        assert r.status_code == 401 and r.json()["error"]["details"]["reason"] == "session_expired"


# --------------------------------------------------------------------- CSRF -------
async def test_cookie_writes_need_the_csrf_token(secure):
    async with secure.signed_in("mission_operator") as c:
        csrf = c.headers.pop("X-CSRF-Token")
        r = await c.post("/api/alerts/does-not-exist/acknowledge", json={})
        assert r.status_code == 403 and r.json()["error"]["details"]["reason"] == "csrf"
        r = await c.post("/api/alerts/does-not-exist/acknowledge", json={}, headers={"X-CSRF-Token": "forged"})
        assert r.status_code == 403
        r = await c.post("/api/alerts/does-not-exist/acknowledge", json={}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 404  # passed authentication, CSRF and permission checks
    assert await audit_rows(secure.app, "csrf_rejected")


async def test_bearer_tokens_work_without_csrf(secure):
    username, password = secure.users["mission_operator"]
    async with secure.client() as c:
        r = await c.post("/api/auth/token", json={"username": username, "password": password})
        assert r.status_code == 200 and "set-cookie" not in r.headers
        token = r.json()["access_token"]
    async with secure.client() as c:
        h = {"Authorization": f"Bearer {token}"}
        me = (await c.get("/api/auth/me", headers=h)).json()
        assert me["method"] == "bearer" and me["csrf_token"] is None
        r = await c.post("/api/alerts/does-not-exist/acknowledge", json={}, headers=h)
        assert r.status_code == 404
        assert (await c.get("/api/auth/me", headers={"Authorization": "Bearer forged"})).status_code == 401


# --------------------------------------------------------------------- RBAC -------
@pytest.mark.parametrize(
    ("role", "method", "path", "expected"),
    [
        ("admin", "GET", "/api/astronauts", 403),  # separation of duties: no health records
        ("admin", "GET", "/api/admin/audit", 200),
        ("admin", "GET", "/api/admin/users", 200),
        ("admin", "GET", "/api/space/sources", 200),
        ("analyst", "GET", "/api/astronauts", 200),
        ("analyst", "GET", "/api/admin/audit", 403),
        ("analyst", "POST", "/api/alerts/x/acknowledge", 403),
        ("analyst", "POST", "/api/simulation/events", 403),
        ("flight_surgeon", "POST", "/api/simulation/events", 403),
        ("flight_surgeon", "POST", "/api/alerts/x/resolve", 404),
        ("mission_operator", "POST", "/api/ai/models/reload", 403),
        ("mission_operator", "GET", "/api/admin/users", 403),
    ],
)
async def test_role_permission_matrix(secure, role, method, path, expected):
    async with secure.signed_in(role) as c:
        body = {"scenario": "tachycardia", "astronaut_id": "AST-01"} if path.endswith("events") else {}
        r = await c.request(method, path, json=body if method == "POST" else None)
        assert r.status_code == expected, r.text
        if expected == 403:
            assert r.json()["error"]["details"]["reason"] == "permission"


async def test_denials_are_audited_with_the_missing_permission(secure):
    async with secure.signed_in("admin") as c:
        for _ in range(3):  # a polling client repeating the same denied request
            assert (await c.get("/api/health/AST-01")).status_code == 403
        await c.get("/api/health/AST-02")
    denied = await audit_rows(secure.app, "access_denied")
    assert [d.resource_id for d in denied] == ["GET /api/health/AST-01", "GET /api/health/AST-02"]
    assert denied[-1].detail == {"missing": ["health:read"]} and denied[-1].role == "admin"


async def test_admin_user_management_and_role_change_revokes_sessions(secure):
    async with secure.signed_in("admin") as admin:
        weak = await admin.post("/api/admin/users", json={
            "username": "new.user", "display_name": "New", "role": "analyst", "password": "short"})
        assert weak.status_code == 409 and weak.json()["error"]["details"]["problems"]
        pw = make_password()
        r = await admin.post("/api/admin/users", json={
            "username": "new.user", "display_name": "New", "role": "analyst", "password": pw})
        assert r.status_code == 201
        uid = r.json()["id"]
        bad_role = await admin.post("/api/admin/users", json={
            "username": "x.user", "display_name": "X", "role": "superuser", "password": make_password()})
        assert bad_role.status_code == 422
        async with secure.client() as user:
            await user.post("/api/auth/login", json={"username": "new.user", "password": pw})
            assert (await user.get("/api/auth/me")).status_code == 200
            assert (await admin.patch(f"/api/admin/users/{uid}", json={"role": "flight_surgeon"})).status_code == 200
            assert (await user.get("/api/auth/me")).status_code == 401  # must sign in again
        me_id = (await admin.get("/api/auth/me")).json()["user"]["id"]
        assert (await admin.patch(f"/api/admin/users/{me_id}", json={"active": False})).status_code == 409
    actions = [r.action for r in await audit_rows(secure.app)]
    assert "user_created" in actions and "user_updated" in actions


async def test_password_change_signs_out_other_sessions(secure):
    username, password = secure.users["analyst"]
    async with secure.signed_in("analyst") as first, secure.signed_in("analyst") as second:
        new = make_password()
        r = await first.post("/api/auth/password", json={"current_password": "wrong-one-123", "new_password": new})
        assert r.status_code == 401
        r = await first.post("/api/auth/password", json={"current_password": password, "new_password": new})
        assert r.status_code == 204
        assert (await first.get("/api/auth/me")).status_code == 200
        assert (await second.get("/api/auth/me")).status_code == 401


# -------------------------------------------------------------------- audit -------
async def test_health_record_views_are_audited_once_per_window(secure):
    async with secure.signed_in("flight_surgeon") as c:
        for _ in range(3):
            assert (await c.get("/api/health/AST-02")).status_code == 200
        await c.get("/api/health/AST-03")
    views = [r for r in await audit_rows(secure.app) if r.action == "view /api/health/{astronaut_id}"]
    assert [(v.resource_type, v.resource_id) for v in views] == [("astronaut", "AST-02"), ("astronaut", "AST-03")]
    assert all(v.username == "test-flight-surgeon" and v.outcome == "success" for v in views)


async def test_audit_log_endpoint_filters_and_holds_no_values(secure):
    async with secure.signed_in("mission_operator") as c:
        await c.get("/api/health/AST-01")
    async with secure.signed_in("admin") as admin:
        rows = (await admin.get("/api/admin/audit", params={"username": "test-mission-operator"})).json()
        assert rows and all(r["username"] == "test-mission-operator" for r in rows)
        assert {r["action"] for r in rows} >= {"login", "view /api/health/{astronaut_id}"}
        text = str(rows)
        assert "heart_rate" not in text and "spo2" not in text


# ------------------------------------------------------------------ headers -------
async def test_security_headers(secure):
    async with secure.signed_in("analyst") as c:
        r = await c.get("/api/astronauts")
    h = r.headers
    assert h["cache-control"] == "no-store" and h["x-frame-options"] == "DENY"
    assert h["content-security-policy"].startswith("default-src 'none'")
    assert h["referrer-policy"] == "no-referrer" and h["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" not in h  # only when served over HTTPS


async def test_cors_allows_credentials_only_for_listed_origins(secure):
    async with secure.client() as c:
        ok = await c.options("/api/auth/me", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-csrf-token,content-type"})
        bad = await c.options("/api/auth/me", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-credentials"] == "true"
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


# ---------------------------------------------------------------- websocket -------
def test_websocket_requires_a_session_with_health_access(secure_settings):
    app = create_app(secure_settings)
    with TestClient(app) as client:
        pw = make_password()
        admin_pw = make_password()
        client.portal.call(app.state.auth.create_user, "ws.surgeon", "WS", "flight_surgeon", pw)
        client.portal.call(app.state.auth.create_user, "ws.admin", "WS", "admin", admin_pw)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/health-monitoring") as ws:
                ws.receive_json()
        assert exc.value.code == 1008
        assert client.post("/api/auth/login", json={"username": "ws.admin", "password": admin_pw}).status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/health-monitoring") as ws:
                ws.receive_json()
        client.cookies.clear()
        assert client.post("/api/auth/login", json={"username": "ws.surgeon", "password": pw}).status_code == 200
        with client.websocket_connect("/ws/health-monitoring") as ws:
            assert ws.receive_json()["type"] == "hello"


def test_http_client_request_urls_are_not_logged_at_info():
    import logging

    from app.core.logging import configure_logging

    configure_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
