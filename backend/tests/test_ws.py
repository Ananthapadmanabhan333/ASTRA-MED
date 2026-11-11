from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app


@pytest.fixture
def live_client(settings):
    settings.simulator_enabled = True
    settings.tick_seconds = 0.2
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def test_websocket_sends_hello_then_live_vitals(live_client):
    with live_client.websocket_connect("/ws/health-monitoring") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["astronaut_ids"] == ["AST-01", "AST-02", "AST-03", "AST-04"]
        assert hello["data_source"] == "simulated"

        msg = ws.receive_json()
        while msg["type"] != "vitals":
            msg = ws.receive_json()
        assert len(msg["readings"]) == 4
        assert all(r["data_source"] == "simulated" for r in msg["readings"])
        assert {e["astronaut_id"] for e in msg["ecg"]} == set(hello["astronaut_ids"])
        assert all(len(e["values_mv"]) > 0 for e in msg["ecg"])


def test_websocket_ping_pong(live_client):
    with live_client.websocket_connect("/ws/health-monitoring") as ws:
        ws.receive_json()
        ws.send_text("not json")  # ignored, connection stays open
        ws.send_json({"action": "ping"})
        for _ in range(50):
            msg = ws.receive_json()
            if msg["type"] == "pong":
                break
        assert msg["type"] == "pong"


def test_websocket_rejects_unknown_origin(live_client):
    with pytest.raises(WebSocketDisconnect):
        with live_client.websocket_connect(
            "/ws/health-monitoring", headers={"origin": "https://evil.example"}
        ) as ws:
            ws.receive_json()


def test_operator_scenario_is_broadcast(live_client):
    with live_client.websocket_connect("/ws/health-monitoring") as ws:
        ws.receive_json()
        r = live_client.post(
            "/api/simulation/events", json={"scenario": "bradycardia", "astronaut_id": "AST-02"}
        )
        assert r.status_code == 201
        for _ in range(100):
            msg = ws.receive_json()
            if msg["type"] == "simulation":
                break
        assert msg["event"] == "started"
        assert msg["scenario"]["astronaut_id"] == "AST-02"
