from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.timeutil import utcnow
from app.main import create_app


async def tick(monitor, seconds: int):
    t = utcnow()
    for i in range(seconds):
        await monitor.tick(t + timedelta(seconds=i + 1))


async def test_system_health(api):
    client, _ = api
    r = await client.get("/api/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert r.headers["x-request-id"]


async def test_astronaut_roster_is_simulated_and_complete(api):
    client, monitor = api
    await tick(monitor, 2)
    r = await client.get("/api/astronauts")
    crew = r.json()
    assert [a["id"] for a in crew] == ["AST-01", "AST-02", "AST-03", "AST-04"]
    assert all(a["data_source"] == "simulated" for a in crew)
    assert all(a["latest"]["data_source"] == "simulated" for a in crew)
    assert {a["status"] for a in crew} <= {"nominal", "advisory", "caution", "critical"}


async def test_unknown_astronaut_uses_error_envelope(api):
    client, _ = api
    for path in ("/api/astronauts/AST-99", "/api/health/AST-99", "/api/health/AST-99/history"):
        r = await client.get(path)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


async def test_invalid_query_is_rejected(api):
    client, _ = api
    r = await client.get("/api/health/AST-01/history", params={"range": "2y"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_snapshot_contains_all_monitored_domains(api):
    client, monitor = api
    await tick(monitor, 3)
    body = (await client.get("/api/health/AST-02")).json()
    latest = body["latest"]
    for field in ("heart_rate", "spo2", "systolic", "diastolic", "temperature_c", "respiratory_rate"):
        assert isinstance(latest[field], float)
    assert body["sleep"]["last_night_hours"] > 3
    assert body["activity"]["exercise_target_minutes"] == 90
    assert body["radiation"]["career_dose_msv"] > body["radiation"]["mission_dose_msv"]


async def test_history_is_downsampled_within_range(api):
    client, _ = api
    r = await client.get("/api/health/AST-01/history", params={"range": "24h", "max_points": 60})
    body = r.json()
    assert r.status_code == 200
    assert 0 < len(body["points"]) <= 60
    assert body["resolution_seconds"] == 1440
    stamps = [p["ts"] for p in body["points"]]
    assert stamps == sorted(stamps)


async def test_compare_returns_series_per_crew_member(api):
    client, _ = api
    body = (await client.get("/api/health/compare", params={"metric": "spo2", "range": "24h"})).json()
    assert len(body["series"]) == 4
    assert all(s["points"] for s in body["series"])


async def test_mission_status_and_radiation(api):
    client, _ = api
    mission = (await client.get("/api/mission/status")).json()
    assert mission["crew_count"] == 4 and mission["mission_day"] >= 0
    assert mission["one_way_light_delay_s"] > 0
    rad = (await client.get("/api/radiation", params={"days": 7})).json()
    assert rad["reference_career_limit_msv"] == 600
    assert all(0 < c["career_limit_pct"] < 100 for c in rad["crew"])


async def test_scenario_to_alert_to_resolution_flow(api):
    client, monitor = api
    r = await client.post(
        "/api/simulation/events",
        json={"scenario": "desaturation", "astronaut_id": "AST-03", "duration_seconds": 300},
    )
    assert r.status_code == 201
    event = r.json()
    assert event["active"] and event["triggered_by"] == "operator"

    dup = await client.post("/api/simulation/events", json={"scenario": "tachycardia", "astronaut_id": "AST-03"})
    assert dup.status_code == 409

    await tick(monitor, 80)
    alerts = (await client.get("/api/alerts", params={"status": "active", "astronaut_id": "AST-03"})).json()
    spo2_alerts = [a for a in alerts if a["metric"] == "spo2"]
    assert spo2_alerts, alerts
    alert = spo2_alerts[0]
    assert alert["severity"] == "critical"
    assert alert["scenario"] == "desaturation"

    snap = (await client.get("/api/health/AST-03")).json()
    assert snap["status"] == "critical"

    ack = await client.post(f"/api/alerts/{alert['id']}/acknowledge", json={"note": "Crew contacted"})
    assert ack.status_code == 200 and ack.json()["status"] == "acknowledged"
    again = await client.post(f"/api/alerts/{alert['id']}/acknowledge")
    assert again.status_code == 409

    cancel = await client.delete(f"/api/simulation/events/{event['id']}")
    assert cancel.status_code == 200 and cancel.json()["cancelled_at"]

    res = await client.post(f"/api/alerts/{alert['id']}/resolve", json={"note": "Sensor re-seated"})
    body = res.json()
    assert body["status"] == "resolved" and body["operator_note"] == "Sensor re-seated"
    assert monitor.evaluator.find(alert["id"]) is None


async def test_scenario_validation(api):
    client, _ = api
    missing = await client.post("/api/simulation/events", json={"scenario": "tachycardia"})
    assert missing.status_code == 409
    unknown = await client.post("/api/simulation/events", json={"scenario": "tachycardia", "astronaut_id": "AST-99"})
    assert unknown.status_code == 404
    bad = await client.post("/api/simulation/events", json={"scenario": "alien", "astronaut_id": "AST-01"})
    assert bad.status_code == 422
    too_hot = await client.post(
        "/api/simulation/events", json={"scenario": "tachycardia", "astronaut_id": "AST-01", "intensity": 5}
    )
    assert too_hot.status_code == 422


async def test_crew_wide_scenario_and_listing(api):
    client, _ = api
    r = await client.post("/api/simulation/events", json={"scenario": "solar_particle_event"})
    assert r.status_code == 201 and r.json()["astronaut_id"] is None
    events = (await client.get("/api/simulation/events")).json()
    assert any(e["scenario"] == "solar_particle_event" and e["active"] for e in events)
    scenarios = (await client.get("/api/simulation/scenarios")).json()
    assert {s["key"] for s in scenarios} >= {"tachycardia", "bradycardia", "desaturation"}


async def test_thresholds_match_detection_rules(api):
    client, _ = api
    rules = (await client.get("/api/monitoring/thresholds")).json()
    hr_high = next(r for r in rules if r["key"] == "heart_rate:high")
    assert (hr_high["caution"], hr_high["critical"]) == (120, 140)
    assert hr_high["overrides"]["exercise"] == [172, 188]


async def test_insights_cite_evidence(api):
    client, _ = api
    insights = (await client.get("/api/insights")).json()
    assert insights, "fixture history should produce at least one insight"
    for i in insights:
        assert i["method"] == "rule-based" and i["evidence"]


@pytest.mark.parametrize("control_enabled", [False])
async def test_simulation_control_can_be_disabled(settings, control_enabled):
    settings.simulation_control_enabled = control_enabled
    from httpx import ASGITransport, AsyncClient

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post("/api/simulation/events", json={"scenario": "tachycardia", "astronaut_id": "AST-01"})
            assert r.status_code == 403


def test_openapi_documents_rest_and_websocket_contracts(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for p in ("/api/astronauts", "/api/health/{astronaut_id}", "/api/health/{astronaut_id}/history",
              "/api/mission/status", "/api/alerts"):
        assert p in paths
    for name in ("WsHello", "WsVitals", "WsAlert", "WsSimulation", "EcgSegment"):
        assert name in schema["components"]["schemas"]
