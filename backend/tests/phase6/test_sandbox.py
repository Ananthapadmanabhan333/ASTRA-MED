"""Mission simulation sandbox: controls, injections, telemetry ingestion, isolation, playback, reports."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import AlertRow, MissionSimSampleRow, SimulationEventRow, VitalSampleRow


async def _counts(p6):
    async with p6.state.session_factory() as s:
        return (await s.scalar(select(func.count()).select_from(VitalSampleRow)),
                await s.scalar(select(func.count()).select_from(AlertRow)),
                await s.scalar(select(func.count()).select_from(SimulationEventRow)))


async def test_catalogue_lists_presets_and_injections(p6):
    c = (await p6.client.get("/api/mission-sim/catalogue")).json()
    assert {p["key"] for p in c["presets"]} >= {"nominal_transit", "desaturation_emergency", "solar_particle_event"}
    kinds = {i["kind"] for i in c["injections"]}
    assert kinds == {"health", "environment", "space_weather"}
    assert (await p6.client.get("/api/mission-sim/state")).json()["status"] == "idle"


async def test_sandbox_run_is_isolated_controllable_and_replayable(p6):
    before = await _counts(p6)
    r = await p6.client.post("/api/mission-sim/runs", json={"preset": "desaturation_emergency", "speed": 20})
    assert r.status_code == 201, r.text
    state = r.json()
    rid = state["id"]
    assert state["status"] == "running" and len(state["crew"]) == 2 and state["context"] == "simulation"
    assert (await p6.client.post("/api/mission-sim/runs", json={})).status_code == 409  # one active run

    sb = p6.state.sandbox
    run = sb.run
    await sb.advance(run, 10 * 60)  # scripted desaturation fires at T+6 min
    assert run.sim_now == run.sim_start + timedelta(minutes=10)
    assert any(i["injection"] == "desaturation" for i in run.injections)
    await sb.advance(run, 6 * 60)
    alerts = (await p6.client.get("/api/alert-center", params={"context": "simulation", "simulation_id": rid})).json()
    rule = [a for a in alerts if a["source"] == "physiological_monitoring"]
    assert rule and rule[0]["title"].startswith("[SIM]") and rule[0]["data_origin"] == "sandbox"
    assert rule[0]["correlations"]["injected_scenarios"][0]["scenario"] == "desaturation"
    # Operations views never show sandbox alerts.
    ops = (await p6.client.get("/api/alert-center")).json()
    assert not any(a["simulation_id"] == rid for a in ops)

    # Isolation: nothing reached the live crew tables.
    assert await _counts(p6) == before
    async with p6.state.session_factory() as s:
        n = await s.scalar(select(func.count()).select_from(MissionSimSampleRow).where(MissionSimSampleRow.simulation_id == rid))
    assert n > 2 * 90  # two crew, ~16 min at 10 s steps

    # Pause freezes the clock; speed changes; resume continues.
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/pause")).json()["status"] == "paused"
    frozen = run.sim_now
    await sb.advance(run, 600)
    assert run.sim_now == frozen
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/speed", json={"speed": 60})).json()["speed"] == 60
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/resume")).json()["status"] == "running"
    await sb.advance(run, 60)
    assert run.sim_now > frozen

    # Inject a simulated space-weather marker and a crew-wide habitat anomaly now; schedule one later.
    r = await p6.client.post(f"/api/mission-sim/runs/{rid}/inject", json={"injection": "solar_flare"})
    assert r.status_code == 200 and r.json()["status"] == "fired"
    r = await p6.client.post(f"/api/mission-sim/runs/{rid}/inject",
                             json={"injection": "tachycardia", "astronaut_id": run.crew[1], "at_minute": 60})
    assert r.json()["status"] == "scheduled"
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/inject",
                                 json={"injection": "tachycardia"})).status_code == 409  # needs a crew member
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/inject",
                                 json={"injection": "tachycardia", "astronaut_id": "AST-04"})).status_code == 404

    # Playback and frames read the stored run back.
    pb = (await p6.client.get(f"/api/mission-sim/runs/{rid}/playback", params={"max_points": 60})).json()
    assert len(pb["series"]) == 2 and pb["series"][0]["points"] and pb["events"] and pb["alerts"]
    at = (run.sim_start + timedelta(minutes=12)).isoformat()
    frame = (await p6.client.get(f"/api/mission-sim/runs/{rid}/frame", params={"at": at})).json()
    assert frame["t_plus"] == "T+00:12:00" and all(c["reading"] for c in frame["crew"])
    assert any(i["injection"] == "desaturation" for i in frame["active_injections"])

    # Timeline in sandbox context uses the run's clock.
    tl = (await p6.client.get("/api/events/timeline", params={"simulation_id": rid})).json()
    assert tl["context"] == "simulation" and sum(len(lane["items"]) for lane in tl["lanes"]) > 3

    # Reset closes the sandbox alerts and returns to idle; the run stays for playback.
    r = (await p6.client.post(f"/api/mission-sim/runs/{rid}/reset")).json()
    assert r["status"] == "idle"
    left = (await p6.client.get("/api/alert-center", params={"context": "simulation", "simulation_id": rid,
                                                             "status": ["open", "acknowledged"]})).json()
    assert left == []
    runs = (await p6.client.get("/api/mission-sim/runs")).json()
    assert runs[0]["id"] == rid and runs[0]["status"] == "reset"


async def test_external_telemetry_is_validated_and_detected(p6):
    r = await p6.client.post("/api/mission-sim/runs", json={"crew": ["AST-01"], "speed": 10, "duration_minutes": 60})
    rid = r.json()["id"]
    sb = p6.state.sandbox
    run = sb.run
    await sb.advance(run, 120)
    await p6.client.post(f"/api/mission-sim/runs/{rid}/pause")
    t0 = run.sim_now
    readings = [{"astronaut_id": "AST-01", "ts": (t0 - timedelta(seconds=60 - 10 * i)).isoformat(), "spo2": 84.0,
                 "heart_rate": 104} for i in range(6)]
    readings.append({"astronaut_id": "AST-01", "ts": (t0 + timedelta(hours=1)).isoformat(), "spo2": 85.0})  # clock ahead
    readings.append({"astronaut_id": "AST-03", "ts": t0.isoformat(), "spo2": 97.0})  # not in this mission
    r = await p6.client.post(f"/api/mission-sim/runs/{rid}/telemetry", json={"readings": readings})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["accepted"] == 7 and out["rejected"] == 1 and out["alerts_opened"] >= 1
    assert any(i.get("clamped") for i in out["issues"])
    bad = await p6.client.post(f"/api/mission-sim/runs/{rid}/telemetry",
                               json={"readings": [{"astronaut_id": "AST-01", "ts": t0.isoformat(), "spo2": 12}]})
    assert bad.status_code == 422  # physiologically implausible values are rejected by the contract
    async with p6.state.session_factory() as s:
        ext = await s.scalar(select(func.count()).select_from(MissionSimSampleRow).where(
            MissionSimSampleRow.simulation_id == rid, MissionSimSampleRow.source == "external"))
    assert ext == 7
    alerts = (await p6.client.get("/api/alert-center", params={"context": "simulation", "simulation_id": rid})).json()
    spo2 = next(a for a in alerts if a["measurements"].get("metric") == "spo2")
    # Acknowledge and resolve a sandbox alert through the alert centre (delegated to the sandbox evaluator).
    assert (await p6.client.post(f"/api/alert-center/{spo2['id']}/acknowledge", json={})).status_code == 200
    r = await p6.client.post(f"/api/alert-center/{spo2['id']}/resolve", json={"note": "Drill complete"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert run.evaluator.find(spo2["source_ref"]) is None  # released in the sandbox evaluator

    # A sandbox incident report: same sections, sandbox-labelled, intact digest.
    rep = await p6.client.post(f"/api/mission-sim/runs/{rid}/report", json={"alert_id": spo2["id"]})
    assert rep.status_code == 201, rep.text
    report = rep.json()
    assert report["source_kind"] == "simulation" and report["simulation_id"] == rid
    assert report["integrity"] == "intact" and report["title"].startswith("[SIM]")
    assert "SIMULATION SANDBOX" in report["content"]["label"]
    pdf = await p6.client.get(f"/api/reports/{report['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    stop = (await p6.client.post(f"/api/mission-sim/runs/{rid}/stop")).json()
    assert stop["status"] == "completed"
    assert (await p6.client.post(f"/api/mission-sim/runs/{rid}/pause")).status_code == 409


async def test_run_completes_at_planned_length_and_failures_stay_isolated(p6):
    r = await p6.client.post("/api/mission-sim/runs", json={"crew": ["AST-02"], "speed": 30, "duration_minutes": 5})
    rid = r.json()["id"]
    sb = p6.state.sandbox
    run = sb.run
    await sb.advance(run, 10 * 60)
    assert run.status == "completed" and run.sim_now == run.sim_end

    r = await p6.client.post("/api/mission-sim/runs", json={"crew": ["AST-03"], "speed": 5, "duration_minutes": 30})
    run = sb.run

    def boom(*_a, **_k):
        raise RuntimeError("engine fault")

    run.engine.step = boom
    task = run.task
    run.task = None
    task.cancel()
    try:
        await sb.advance(run, 10)
    except RuntimeError:
        await sb._finish(run, "failed", error="RuntimeError: engine fault")
    assert run.status == "failed"
    status = (await p6.client.get("/api/system/status")).json()
    assert next(c for c in status["components"] if c["key"] == "sandbox")["status"] == "degraded"
    assert next(c for c in status["components"] if c["key"] == "database")["status"] == "ok"
    # A new run can start after a failure.
    assert (await p6.client.post("/api/mission-sim/runs", json={"crew": ["AST-01"], "duration_minutes": 10})).status_code == 201
    assert rid
