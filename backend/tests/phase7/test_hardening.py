"""Phase 7 audit fixes: access control, sign-in, probes, production profile, migrations, retention."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.db.migrations import SchemaNotMigratedError, alembic_config
from app.db.models import AuditLogRow, VitalSampleRow
from app.db.retention import prune_once
from app.main import create_app
from app.mission.events import EventInput
from app.reports.pdf import text_width, wrap
from app.services.hub import ConnectionHub


async def _report_event(app) -> str:
    row, _ = await app.state.mission_events.publish(EventInput(
        source="incident_reports", kind="report_created", category="medical_incident", severity="advisory",
        title="Incident report created: confidential title", occurred_at=utcnow(), astronaut_id="AST-01",
        ref_type="incident_report", ref_id="IR-test", payload={"report_id": "IR-test"},
    ))
    return row.id


# --------------------------------------------------------------- incident report events ----
async def test_incident_report_events_hidden_without_reports_read(secure):
    event_id = await _report_event(secure.app)
    async with secure.signed_in("analyst") as c:  # health:read but no reports:read
        listed = (await c.get("/api/events", params={"source": "incident_reports"})).json()
        assert listed == []
        assert (await c.get(f"/api/events/{event_id}")).status_code == 404
        counts = (await c.get("/api/events/counts")).json()
        assert "incident_reports" not in counts["by_source"]
        lanes = (await c.get("/api/events/timeline")).json()
        assert all(e["source"] != "incident_reports" for lane in lanes["lanes"] for e in lane["items"])
        overview = (await c.get("/api/mission-control/overview")).json()
        assert "confidential" not in str(overview)
    async with secure.signed_in("flight_surgeon") as c:  # has reports:read
        listed = (await c.get("/api/events", params={"source": "incident_reports"})).json()
        assert [e["id"] for e in listed] == [event_id]
        assert (await c.get(f"/api/events/{event_id}")).status_code == 200


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


async def test_hub_sends_restricted_messages_only_to_permitted_sockets():
    hub = ConnectionHub()
    analyst, surgeon, untracked = _FakeSocket(), _FakeSocket(), _FakeSocket()
    hub.add(analyst, frozenset({"health:read"}))
    hub.add(surgeon, frozenset({"health:read", "reports:read"}))
    hub.add(untracked)  # authentication disabled: no permission set recorded
    await hub.broadcast("report", requires="reports:read")
    await hub.broadcast("vitals")
    assert analyst.sent == ["vitals"]
    assert surgeon.sent == ["report", "vitals"]
    assert untracked.sent == ["report", "vitals"]


# ----------------------------------------------------------------------- permissions ----
async def test_admin_can_reload_models_but_not_read_health_data(secure):
    async with secure.signed_in("admin") as c:
        r = await c.post("/api/ai/models/reload")
        assert r.status_code == 200, r.text
        assert (await c.get("/api/ai/status")).status_code == 403  # still no crew/AI data access
    async with secure.signed_in("analyst") as c:
        assert (await c.post("/api/ai/models/reload")).status_code == 403


async def test_consistency_repair_needs_system_maintain(secure):
    async with secure.signed_in("flight_surgeon") as c:
        assert (await c.post("/api/system/consistency/repair")).status_code == 403
    async with secure.signed_in("analyst") as c:
        assert (await c.post("/api/system/consistency/repair")).status_code == 403
    for role in ("mission_operator", "admin"):
        async with secure.signed_in(role) as c:
            assert (await c.post("/api/system/consistency/repair")).status_code == 200


async def test_locked_account_gets_the_same_answer_as_a_wrong_password(secure):
    username, password = secure.users["analyst"]
    async with secure.client() as c:
        wrong = None
        for _ in range(5):
            wrong = await c.post("/api/auth/login", json={"username": username, "password": password + "x"})
        assert wrong.status_code == 401
        locked = await c.post("/api/auth/login", json={"username": username, "password": password})
        unknown = await c.post("/api/auth/login", json={"username": "nobody-here", "password": password})
    assert locked.status_code == unknown.status_code == 401
    assert locked.json() == wrong.json() == unknown.json()  # nothing distinguishes the three cases


async def test_phase6_crew_reads_are_audited(secure):
    async with secure.signed_in("analyst") as c:
        assert (await c.get("/api/crew/monitoring")).status_code == 200
        assert (await c.get("/api/alert-center")).status_code == 200
    async with secure.app.state.session_factory() as s:
        actions = set((await s.scalars(select(AuditLogRow.action))).all())
    assert any("/api/crew/monitoring" in a for a in actions)
    assert any("/api/alert-center" in a for a in actions)


# ------------------------------------------------------------------------- probes ----
async def test_liveness_and_readiness_probes(secure):
    async with secure.client() as c:  # no sign-in needed, no data returned
        assert (await c.get("/livez")).json() == {"status": "alive"}
        ready = await c.get("/readyz")
        assert ready.status_code == 200 and ready.json() == {"status": "ready"}
    secure.app.state.ready = False
    async with secure.client() as c:
        assert (await c.get("/readyz")).status_code == 503
    secure.app.state.ready = True


# ------------------------------------------------------------------ production profile ----
def test_production_profile_refuses_unsafe_settings():
    with pytest.raises(RuntimeError) as exc:
        create_app(Settings(environment="production", auth_enabled=True))
    msg = str(exc.value)
    assert "COOKIE_SECURE" in msg and "PostgreSQL" in msg and "SCHEMA_MODE" in msg
    ok = Settings(environment="production", auth_enabled=True, auth_cookie_secure=True, db_schema_mode="migrate",
                  database_url="postgres://u:p@db.example:5432/astra", cors_origins="https://app.example.org")
    assert ok.production_problems() == []
    assert ok.database_url == "postgresql+asyncpg://u:p@db.example:5432/astra"
    app = create_app(ok)  # builds (not started: there is no database here)
    assert app.docs_url is None and app.openapi_url is None  # API docs off in production by default


def test_docs_stay_on_in_development():
    assert create_app(Settings()).docs_url == "/docs"


# ---------------------------------------------------------------------- migrations ----
async def test_migrate_mode_refuses_an_unmigrated_database_then_starts_after_upgrade(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'm.db').as_posix()}"
    settings = Settings(database_url=url, db_schema_mode="migrate", auth_enabled=False, simulator_enabled=False,
                        backfill_days=0, space_sync_enabled=False, mission_orchestrator_enabled=False,
                        log_level="WARNING")
    app = create_app(settings)
    with pytest.raises(SchemaNotMigratedError):
        async with app.router.lifespan_context(app):
            pass

    cfg = alembic_config()
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    await asyncio.to_thread(command.upgrade, cfg, "head")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert app.state.ready


# ----------------------------------------------------------------------- retention ----
async def test_retention_removes_only_rows_older_than_the_window(api):
    _, monitor = api
    app_settings = monitor.settings
    factory = monitor.session_factory
    now = utcnow()
    async with factory() as s:
        for age_days in (1, app_settings.history_retention_days + 2):
            s.add(VitalSampleRow(astronaut_id="AST-01", ts=now - timedelta(days=age_days), heart_rate=60.0, spo2=98.0,
                                 systolic=118.0, diastolic=76.0, temperature_c=36.7, respiratory_rate=14.0,
                                 activity_state="work", activity_met=1.5, rhythm="sinus"))
        await s.commit()
    removed = await prune_once(app_settings, factory)
    assert removed["vital_samples"] >= 1
    async with factory() as s:
        oldest = await s.scalar(select(func.min(VitalSampleRow.ts)))
    assert oldest >= now - timedelta(days=app_settings.history_retention_days)


# ----------------------------------------------------------------------- PDF layout ----
def test_long_tokens_wrap_in_linear_time_and_fit_the_width():
    import time

    started = time.perf_counter()
    lines = wrap("x" * 20_000 + " tail", 9, 120)
    assert time.perf_counter() - started < 0.5  # the old character-by-character search took seconds
    assert all(text_width(line, 9) <= 120 for line in lines)
    assert "".join(line.replace(" ", "") for line in lines) == "x" * 20_000 + "tail"  # nothing lost


# ------------------------------------------------------------- history in the database ----
async def test_sql_buckets_match_python_bucketing(api):
    from app.repositories import vitals as vitals_repo
    from app.services import history as history_service

    _, monitor = api
    now = utcnow()
    start, end = now - timedelta(hours=24), now
    async with monitor.session_factory() as s:
        for resolution in (300, 1800, 3600):
            rows = await vitals_repo.fetch_range(s, "AST-02", start, end, history_service.HISTORY_COLUMNS)
            py = history_service.bucket_rows(rows, start, resolution, len(history_service.HISTORY_COLUMNS))
            sql = await vitals_repo.bucket_means(s, "AST-02", start, end, resolution, history_service.HISTORY_COLUMNS)
            assert len(py) == len(sql) > 0
            for (t1, v1, c1), (t2, v2, c2) in zip(py, sql):
                assert t1 == t2 and c1 == c2
                assert v1 == pytest.approx(v2, rel=1e-9, abs=1e-9)


async def test_request_ids_from_clients_are_sanitised(api):
    client, _ = api
    ok = await client.get("/livez", headers={"X-Request-ID": "trace-123.abc"})
    assert ok.headers["X-Request-ID"] == "trace-123.abc"
    hostile = "bad id; <script>alert(1)</script>"
    bad = await client.get("/livez", headers={"X-Request-ID": hostile})
    assert bad.headers["X-Request-ID"] != hostile and len(bad.headers["X-Request-ID"]) == 12
