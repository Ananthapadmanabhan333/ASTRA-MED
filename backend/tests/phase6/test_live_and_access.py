"""Live WebSocket delivery of unified events, alerts and sandbox state; role-based access to phase 6."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import p6_settings


@pytest.fixture
def live(tmp_path):
    settings = p6_settings(tmp_path, simulator_enabled=True, tick_seconds=0.2, mission_sim_tick_seconds=0.2)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app


def _until(ws, predicate, limit=400):
    for _ in range(limit):
        msg = ws.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError("expected message not received")


def test_websocket_streams_mission_events_alerts_and_sandbox_state(live):
    client, _ = live
    with client.websocket_connect("/ws/health-monitoring") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-01",
                                                        "intensity": 1.5, "duration_seconds": 600})
        assert r.status_code == 201
        ev = _until(ws, lambda m: m["type"] == "mission_event")
        assert ev["item"]["context"] == "operations" and ev["item"]["kind"] == "scenario_started"

        r = client.post("/api/mission-sim/runs", json={"crew": ["AST-02"], "speed": 60, "duration_minutes": 60})
        assert r.status_code == 201
        state = _until(ws, lambda m: m["type"] == "sim_state" and m["state"]["sim_time"] != m["state"]["sim_start"])
        assert state["state"]["context"] == "simulation" and state["state"]["latest"][0]["astronaut_id"] == "AST-02"

        rid = r.json()["id"]
        client.post(f"/api/mission-sim/runs/{rid}/inject", json={"injection": "desaturation", "astronaut_id": "AST-02",
                                                                 "intensity": 1.5})
        alert = _until(ws, lambda m: m["type"] == "mission_alert" and m["alert"]["context"] == "simulation", limit=2000)
        assert alert["event"] == "opened" and alert["alert"]["title"].startswith("[SIM]")
        client.post(f"/api/mission-sim/runs/{rid}/reset")


async def test_phase6_permissions(secure):
    async with secure.signed_in("analyst") as c:
        assert (await c.get("/api/mission-control/overview")).status_code == 200
        assert (await c.get("/api/alert-center")).status_code == 200
        assert (await c.get("/api/crew/monitoring")).status_code == 200
        assert (await c.post("/api/mission-sim/runs", json={})).status_code == 403
        assert (await c.post("/api/alert-center/AL-x/acknowledge", json={})).status_code == 403
        assert (await c.get("/api/system/status")).status_code == 200
        assert (await c.get("/api/system/consistency")).status_code == 403
    async with secure.signed_in("admin") as c:
        # Separation of duties: no crew health data, but platform health and consistency checks.
        assert (await c.get("/api/mission-control/overview")).status_code == 403
        assert (await c.get("/api/events")).status_code == 403
        assert (await c.get("/api/system/status")).status_code == 200
        assert (await c.get("/api/system/consistency")).status_code == 200
    async with secure.signed_in("mission_operator") as c:
        r = await c.post("/api/mission-sim/runs", json={"crew": ["AST-01"], "duration_minutes": 10})
        assert r.status_code == 201, r.text
        assert (await c.post(f"/api/mission-sim/runs/{r.json()['id']}/reset")).status_code == 200
    async with secure.client() as anon:
        assert (await anon.get("/api/system/status")).status_code == 401
        assert (await anon.get("/api/system/health")).status_code == 200
