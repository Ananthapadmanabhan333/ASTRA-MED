"""Event orchestration (timestamps, priority, de-duplication) and the unified alert centre lifecycle."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import AlertRow, MissionAlertActionRow, MissionAlertRow, SpaceWeatherEventRow
from app.mission.alerts import AlertSpec
from app.mission.events import EventInput
from app.mission.taxonomy import priority_for
from app.simulator.scenarios import Scenario


def test_priority_model_caps_experimental_ai_and_nasa_indicators():
    assert priority_for("critical", "rule_detection", astronaut_specific=True) == (1, 95.0)
    level, score = priority_for("critical", "experimental_ai", astronaut_specific=True)
    assert level == 3 and score <= 59  # AI output is never above P3
    assert priority_for("caution", "environmental_indicator")[0] == 2
    assert priority_for("critical", "environmental_indicator")[0] == 2  # an indicator is never P1
    assert priority_for("info", "rule_detection")[0] == 4


async def test_events_are_normalised_prioritised_and_deduplicated(p6):
    events = p6.state.mission_events
    now = p6.clock.now
    base = dict(source="physiological_monitoring", kind="test_event", category="crew_physiology",
                severity="advisory", title="Test", occurred_at=now, astronaut_id="AST-01")
    first, created = await events.publish(EventInput(**base, ref_type="rule_alert", ref_id="a1"))
    assert created and first.priority == 3 and first.occurrences == 1
    again, created = await events.publish(EventInput(**{**base, "severity": "caution"}, ref_type="rule_alert", ref_id="a1"))
    assert not created and again.id == first.id
    assert again.occurrences == 2 and again.severity == "caution" and again.priority == 2  # merged and escalated

    # Windowed de-duplication for events without a source record.
    a, c1 = await events.publish(EventInput(**base, dedupe_key="k"))
    b, c2 = await events.publish(EventInput(**base, dedupe_key="k"))
    assert c1 and not c2 and a.id == b.id
    p6.clock.advance(p6.state.settings.mission_event_dedupe_minutes * 60 + 5)
    c, c3 = await events.publish(EventInput(**{**base, "occurred_at": p6.clock.now}, dedupe_key="k"))
    assert c3 and c.id != a.id

    # Timestamp synchronisation: a future operations timestamp is clamped and the skew recorded.
    future, _ = await events.publish(EventInput(**{**base, "occurred_at": p6.clock.now + timedelta(minutes=10)},
                                                ref_type="t", ref_id="future"))
    assert future.occurred_at == future.received_at and future.clock_skew_s >= 590
    # ...but the sandbox clock may legitimately run ahead of the wall clock.
    sim, _ = await events.publish(EventInput(**{**base, "occurred_at": p6.clock.now + timedelta(hours=3)},
                                             context="simulation", simulation_id="s1", ref_type="t", ref_id="sim"))
    assert sim.clock_skew_s is None and sim.occurred_at > sim.received_at

    r = await p6.client.get("/api/events", params={"hours": 2})
    assert r.status_code == 200
    rows = r.json()
    assert all(e["context"] == "operations" for e in rows)
    assert any(e["occurrences"] == 2 for e in rows)


async def test_experimental_ai_alert_is_never_critical(p6):
    row, created = await p6.state.alert_center.raise_alert(AlertSpec(
        source="anomaly_detection", source_ref="x", category="ai_prediction", classification="experimental_ai",
        severity="critical", title="AI", occurred_at=p6.clock.now, astronaut_id="AST-02", confidence=0.4,
        confidence_level="low"))
    assert created and row.severity == "caution" and row.priority == 3
    detail = (await p6.client.get(f"/api/alert-center/{row.id}")).json()
    assert detail["experimental"] is True
    assert "not a confirmed medical emergency" in detail["classification_note"]
    assert detail["actions"][0]["action"] == "created"


async def _open_desaturation(p6, seconds: int = 90):
    monitor = p6.monitor
    monitor.engine.start_scenario(Scenario.DESATURATION, "AST-02", p6.clock.now, intensity=1.4, duration_s=600)
    await p6.tick(seconds)
    await p6.drain()
    async with p6.state.session_factory() as s:
        return (await s.scalars(select(AlertRow).where(AlertRow.astronaut_id == "AST-02"))).first()


async def test_rule_alert_is_mirrored_correlated_and_lifecycle_stays_in_sync(p6):
    rule = await _open_desaturation(p6)
    assert rule is not None
    center = p6.state.alert_center
    mirror = await center.find_by_ref("physiological_monitoring", rule.id)
    assert mirror is not None and mirror.status == "open" and mirror.classification == "rule_detection"
    assert mirror.correlations["injected_scenarios"][0]["scenario"] == "desaturation"
    assert mirror.event_id

    # Acknowledge in the alert centre: the phase 2 alert follows.
    r = await p6.client.post(f"/api/alert-center/{mirror.id}/acknowledge", json={"note": "Crew contacted"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"
    await p6.drain()
    assert (await p6.client.get(f"/api/alerts/{rule.id}")).json()["status"] == "acknowledged"
    assert (await p6.client.post(f"/api/alert-center/{mirror.id}/acknowledge", json={})).status_code == 409

    # Resolution needs notes.
    assert (await p6.client.post(f"/api/alert-center/{mirror.id}/resolve", json={})).status_code == 409
    r = await p6.client.post(f"/api/alert-center/{mirror.id}/resolve", json={"note": "SpO2 recovered on O2"})
    assert r.status_code == 200 and r.json()["resolution_notes"] == "SpO2 recovered on O2"
    await p6.drain()
    assert (await p6.client.get(f"/api/alerts/{rule.id}")).json()["status"] == "resolved"

    detail = (await p6.client.get(f"/api/alert-center/{mirror.id}")).json()
    actions = [a["action"] for a in detail["actions"]]
    assert actions[0] == "created" and "acknowledged" in actions and actions[-1] == "resolved"
    assert actions.count("acknowledged") == 1 and actions.count("resolved") == 1  # no duplicate trail entries
    ack = next(a for a in detail["actions"] if a["action"] == "acknowledged")
    assert ack["actor"] == "auth-disabled" and ack["note"] == "Crew contacted"


async def test_legacy_alert_route_is_attributed_in_the_alert_centre(p6):
    rule = await _open_desaturation(p6)
    r = await p6.client.post(f"/api/alerts/{rule.id}/acknowledge", json={"note": "via phase 2 page"})
    assert r.status_code == 200 and r.json()["status"] == "acknowledged"
    await p6.drain()
    mirror = await p6.state.alert_center.find_by_ref("physiological_monitoring", rule.id)
    assert mirror.status == "acknowledged" and mirror.acknowledged_by == "auth-disabled"
    async with p6.state.session_factory() as s:
        n = await s.scalar(select(func.count()).select_from(MissionAlertActionRow).where(
            MissionAlertActionRow.alert_id == mirror.id, MissionAlertActionRow.action == "acknowledged"))
    assert n == 1


async def test_alert_centre_lists_unresolved_first_and_summarises(p6):
    await _open_desaturation(p6)
    await p6.state.alert_center.raise_alert(AlertSpec(
        source="anomaly_detection", source_ref="y", category="ai_prediction", classification="experimental_ai",
        severity="advisory", title="AI pattern", occurred_at=p6.clock.now, astronaut_id="AST-01"))
    rows = (await p6.client.get("/api/alert-center")).json()
    assert rows and rows[0]["status"] != "resolved"
    assert [r["priority"] for r in rows if r["status"] == "open"] == sorted(r["priority"] for r in rows if r["status"] == "open")
    summary = (await p6.client.get("/api/alert-center/summary")).json()
    assert summary["unresolved"] >= 2 and summary["experimental_open"] == 1
    only_ai = (await p6.client.get("/api/alert-center", params={"classification": "experimental_ai"})).json()
    assert {r["source"] for r in only_ai} == {"anomaly_detection"}


async def test_environment_collector_opens_and_clears_habitat_alert(p6):
    monitor = p6.monitor
    s = monitor.engine.start_scenario(Scenario.HABITAT_ATMOSPHERE, None, p6.clock.now, intensity=1.2, duration_s=600)
    await p6.tick(5)
    await p6.drain()
    orch = p6.state.orchestrator
    p6.clock.advance(300)
    await orch.environment_check(p6.clock.now)
    rows = (await p6.client.get("/api/alert-center", params={"source": "environment_monitoring"})).json()
    assert rows and rows[0]["classification"] == "simulated_environment" and rows[0]["category"] == "environment"
    p6.clock.now = s.ends_at + timedelta(seconds=30)
    await orch.environment_check(p6.clock.now)
    row = await p6.state.alert_center.find_by_ref("environment_monitoring", rows[0]["source_ref"])
    assert row.condition_cleared_at is not None and row.status == "open"  # an operator still closes it
    events = (await p6.client.get("/api/events", params={"category": "environment", "hours": 2})).json()
    assert {"environment_anomaly", "environment_nominal"} <= {e["kind"] for e in events}


async def test_space_scan_turns_donki_events_into_events_and_alerts_once(p6):
    now = p6.clock.now
    async with p6.state.session_factory() as s:
        s.add(SpaceWeatherEventRow(
            source_id="donki", event_type="SEP", external_id="2026-11-13T01:00:00-SEP-001", category="indicator",
            start_time=now - timedelta(hours=3), severity=None, classification="SEP (>10 MeV)", instruments=[],
            linked_ids=[], notification_ids=[], model_derived=False, retrieved_at=now, endpoint="test", raw={}))
        s.add(SpaceWeatherEventRow(
            source_id="donki", event_type="FLR", external_id="old-flare", category="indicator",
            start_time=now - timedelta(days=5), severity=3, scale="R3", classification="X1.0", instruments=[],
            linked_ids=[], notification_ids=[], model_derived=False, retrieved_at=now, endpoint="test", raw={}))
        await s.commit()
    orch = p6.state.orchestrator
    out = await orch.space_scan()
    assert out["detail"]["new_events"] == 2 and out["detail"]["new_alerts"] == 1  # the old flare is history only
    again = await orch.space_scan()
    assert again["detail"]["scanned"] == 0
    rows = (await p6.client.get("/api/alert-center", params={"source": "space_weather"})).json()
    assert len(rows) == 1 and rows[0]["data_origin"] == "nasa" and rows[0]["priority"] >= 2
    assert rows[0]["classification"] == "environmental_indicator"
    ev = (await p6.client.get("/api/events", params={"source": "space_weather", "hours": 24 * 7})).json()
    assert {e["data_origin"] for e in ev} == {"nasa"}


async def test_timeline_filters_by_astronaut_category_and_range(p6):
    await _open_desaturation(p6)
    t = (await p6.client.get("/api/events/timeline", params={"astronaut_id": "AST-02", "hours": 2})).json()
    lanes = {lane["key"]: lane for lane in t["lanes"]}
    assert lanes["crew_physiology"]["items"]
    assert all(i["astronaut_id"] in ("AST-02", None) for lane in t["lanes"] for i in lane["items"])
    only = (await p6.client.get("/api/events/timeline", params={"category": ["simulation"], "hours": 2})).json()
    assert [lane["key"] for lane in only["lanes"]] == ["simulation"]
    assert (await p6.client.get("/api/events/timeline", params={"category": ["nope"]})).status_code == 404
    empty = (await p6.client.get("/api/events/timeline", params={
        "start": (p6.clock.now - timedelta(days=10)).isoformat(),
        "end": (p6.clock.now - timedelta(days=9)).isoformat()})).json()
    assert sum(len(lane["items"]) for lane in empty["lanes"]) == 0


async def test_consistency_check_detects_and_repairs_a_missing_mirror(p6):
    rule = await _open_desaturation(p6)
    async with p6.state.session_factory() as s:
        row = (await s.scalars(select(MissionAlertRow).where(MissionAlertRow.source_ref == rule.id))).first()
        await s.delete(row)
        await s.commit()
    report = (await p6.client.get("/api/system/consistency")).json()
    mirror = next(c for c in report["checks"] if c["key"] == "rule_alert_mirror")
    assert mirror["found"] >= 1 and mirror["status"] == "warning"
    fixed = (await p6.client.post("/api/system/consistency/repair")).json()
    assert next(c for c in fixed["checks"] if c["key"] == "rule_alert_mirror")["status"] == "repaired"
    assert await p6.state.alert_center.find_by_ref("physiological_monitoring", rule.id) is not None
    assert next(c for c in fixed["checks"] if c["key"] == "report_integrity")["status"] == "ok"


async def test_system_status_reports_every_component(p6):
    r = (await p6.client.get("/api/system/status")).json()
    keys = {c["key"] for c in r["components"]}
    assert {"api", "database", "simulator", "websocket", "ai", "orchestrator", "nasa_donki", "twin", "sandbox"} <= keys
    assert next(c for c in r["components"] if c["key"] == "database")["status"] == "ok"
    assert next(c for c in r["components"] if c["key"] == "simulator")["status"] == "disabled"
    assert r["orchestrator"]["running"] is True


async def test_mission_control_overview_and_crew_monitoring(p6):
    await _open_desaturation(p6)
    o = (await p6.client.get("/api/mission-control/overview")).json()
    for section in ("crew", "health_monitoring", "alerts", "ai", "space_weather", "environment", "radiation_timeline",
                    "incidents"):
        assert section in o
    assert o["crew"]["available"] and o["crew"]["data"]["total"] == 4
    assert o["alerts"]["data"]["summary"]["unresolved"] >= 1
    assert o["environment"]["data"]["habitat"]["ppco2_mmhg"]["unit"] == "mmHg"
    assert o["connectivity"] and o["simulation"]["status"] == "idle"
    c = (await p6.client.get("/api/crew/monitoring")).json()
    card = next(x for x in c["crew"] if x["astronaut_id"] == "AST-02")
    assert card["status"] in ("caution", "critical") and card["open_rule_alerts"] and card["open_alerts"]
    assert card["deviations"]["available"] and any(s["signal"] == "spo2" for s in card["deviations"]["signals"])
    assert card["ai"]["available"] is False  # no AI sweep ran in this test
