"""End-to-end mission workflow (Module 10) against a real app, stored history and a trained model.

1 start a simulated mission         2 generate physiological data   3 send measurements to the backend
4 run anomaly detection             5 generate predictive analysis  6 retrieve NASA environmental information
7 correlate relevant mission events 8 generate an alert             9 display it in mission control
10 open the astronaut digital twin  11 generate an incident report

Plus the operations path: a live-stream anomaly reaches the alert centre, the AI sweep and crew monitoring.
"""

from __future__ import annotations

from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.models import SpaceWeatherEventRow
from app.main import create_app
from app.simulator.scenarios import Scenario

from .conftest import P6, p6_settings


@pytest_asyncio.fixture
async def e2e(tmp_path, clock, trained_artifacts):
    settings = p6_settings(tmp_path, backfill_days=2, ai_artifacts_dir=str(trained_artifacts))
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=300) as client:
            yield P6(app, client, clock)


async def test_full_mission_workflow(e2e):
    c, st = e2e.client, e2e.state
    assert (await c.get("/api/ai/status")).json()["loaded"] is True

    # 6 (set-up): a real-format NASA DONKI record in the store, as the background sync would write it.
    now = e2e.clock.now
    async with st.session_factory() as s:
        s.add(SpaceWeatherEventRow(
            source_id="donki", event_type="SEP", external_id="e2e-sep", category="indicator",
            start_time=now - timedelta(hours=2), classification="SEP (>10 MeV)", instruments=[], linked_ids=[],
            notification_ids=[], model_derived=False, retrieved_at=now, endpoint="test", raw={}))
        await s.commit()

    # 1 Start a simulated mission.
    r = await c.post("/api/mission-sim/runs", json={"preset": "desaturation_emergency", "speed": 30})
    assert r.status_code == 201, r.text
    rid, crew = r.json()["id"], r.json()["crew"]
    target = crew[0]  # the preset desaturates the first crew member at T+6 min
    sb = st.sandbox
    run = sb.run

    # 2 Generate astronaut physiological data (sandbox clock, 30 simulated minutes).
    await sb.advance(run, 30 * 60)
    state = (await c.get("/api/mission-sim/state")).json()
    assert state["t_plus"] == "T+00:30:00" and {x["astronaut_id"] for x in state["latest"]} == set(crew)
    assert state["stats"]["samples"] > 2 * 170

    # 3 Send measurements to the backend (external telemetry for the second crew member).
    t = run.sim_now
    batch = [{"astronaut_id": crew[1], "ts": (t - timedelta(seconds=50 - 10 * i)).isoformat(), "heart_rate": 150,
              "spo2": 97} for i in range(6)]
    ingest = (await c.post(f"/api/mission-sim/runs/{rid}/telemetry", json={"readings": batch})).json()
    assert ingest["accepted"] == 6 and ingest["alerts_opened"] >= 1

    # 4 Run anomaly detection and 5 predictive analysis over the stream.
    r = await c.post(f"/api/mission-sim/runs/{rid}/analyze")
    assert r.status_code == 200, r.text
    analysis = r.json()
    a = analysis[target]
    assert a["available"] is True and a["windows"] >= 5
    assert a["risk"]["category"] in ("normal", "low_concern", "moderate_concern", "high_concern")
    assert a["forecast"] and {s["signal"] for s in a["forecast"]} >= {"heart_rate", "spo2"}
    assert all(h["lower"] <= h["value"] <= h["upper"] for s in a["forecast"] for h in s["horizons"])
    assert a["flagged_windows"] >= 1  # the injected desaturation is unusual for this crew member

    # 6 Retrieve NASA environmental information (scan into the event store; dashboard section).
    scan = await st.orchestrator.space_scan()
    assert scan["detail"]["new_events"] == 1

    # 8 An alert was generated; 7 it is correlated with the injected scenario and nearby real NASA events.
    alerts = (await c.get("/api/alert-center", params={"context": "simulation", "simulation_id": rid})).json()
    rule = next(x for x in alerts if x["source"] == "physiological_monitoring" and x["astronaut_id"] == target)
    assert rule["priority"] <= 2 and rule["classification"] == "rule_detection"
    corr = rule["correlations"]
    assert corr["injected_scenarios"][0]["scenario"] == "desaturation"
    assert any(e["kind"] == "SEP" for e in corr["space_weather"]["events"])
    assert "not evidence of a causal link" in corr["method"]
    ai_alerts = [x for x in alerts if x["classification"] == "experimental_ai"]
    assert all(x["severity"] != "critical" and x["priority"] >= 3 for x in ai_alerts)

    # 9 Display it in mission control.
    o = (await c.get("/api/mission-control/overview")).json()
    assert o["simulation"]["id"] == rid and o["simulation"]["open_alerts"] >= 1
    assert o["alerts"]["data"]["simulation_summary"]["unresolved"] >= 1
    assert o["space_weather"]["available"] and o["space_weather"]["data"]["counts"]["SEP"] >= 1
    events = (await c.get("/api/events", params={"context": "simulation", "simulation_id": rid, "limit": 500})).json()
    kinds = {e["kind"] for e in events}
    assert {"simulation_started", "injection_health", "alert_opened", "telemetry_ingested"} <= kinds

    # 10 Open the astronaut digital twin.
    twin = await c.get(f"/api/twin/{target}")
    assert twin.status_code == 200 and twin.json()["astronaut"]["id"] == target

    # 11 Generate an incident report.
    rep = await c.post(f"/api/mission-sim/runs/{rid}/report", json={"alert_id": rule["id"]})
    assert rep.status_code == 201, rep.text
    report = rep.json()
    assert report["integrity"] == "intact" and report["source_kind"] == "simulation"
    assert report["content"]["anomaly_results"]["ai_output"]["available"] is True
    assert report["content"]["environment"]["simulated_test_scenario"]
    assert (await c.get(f"/api/reports/{report['id']}/pdf")).content[:4] == b"%PDF"
    await e2e.drain()
    rep_events = (await c.get("/api/events", params={"context": "simulation", "simulation_id": rid,
                                                     "category": "medical_incident"})).json()
    assert rep_events and rep_events[0]["ref_id"] == report["id"]

    # Playback of the whole run.
    pb = (await c.get(f"/api/mission-sim/runs/{rid}/playback")).json()
    assert pb["simulation"]["analyses"][target]["available"] is True


async def test_operations_path_ai_sweep_and_crew_monitoring(e2e):
    c, st = e2e.client, e2e.state
    monitor = e2e.monitor
    monitor.engine.start_scenario(Scenario.TACHYCARDIA, "AST-03", e2e.clock.now, intensity=1.3, duration_s=900)
    await e2e.tick(120)
    await monitor._flush(force=True)
    await e2e.drain()
    out = await st.orchestrator.ai_sweep()
    assert out["state"] == "ok"
    card = next(x for x in (await c.get("/api/crew/monitoring")).json()["crew"] if x["astronaut_id"] == "AST-03")
    assert card["ai"]["available"] is True and card["ai"]["risk_score"] is not None
    assert card["deviations"]["available"] and any((s["z"] or 0) > 2 for s in card["deviations"]["signals"])
    assert card["open_alerts"] and card["status"] != "nominal"
    o = (await c.get("/api/mission-control/overview")).json()
    assert o["ai"]["data"]["model_loaded"] and any(x["astronaut_id"] == "AST-03" and x["risk_score"] is not None
                                                   for x in o["ai"]["data"]["crew"])
    ana = (await c.get("/api/analytics/summary")).json()
    assert ana["model_performance"]["available"] is True
    assert ana["model_performance"]["anomaly"]["detectors"][0]["name"] == "ensemble"
    assert sum(r["rule_total"] for r in ana["anomalies"]) >= 1
    for fmt, kind in (("csv", "text/csv"), ("json", "application/json"), ("md", "text/markdown")):
        r = await c.get("/api/analytics/export", params={"format": fmt})
        assert r.status_code == 200 and r.headers["content-type"].startswith(kind)
        assert "attachment" in r.headers["content-disposition"]
