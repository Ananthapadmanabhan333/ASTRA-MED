"""Decision-support packets, the review workflow and the emergency scenario simulator."""

from __future__ import annotations

import json
import re

from sqlalchemy import select

from app.db.models import SleepSessionRow
from app.emergency.catalogue import CATALOGUE
from app.medical.decision import WORKFLOW_PATH

CLINICAL_WORDS = re.compile(r"\b(mg|milligram|dose of|administer|medicat\w*|drug|prescri\w*|antibiotic|"
                            r"aspirin|oxygen therapy|intubat\w*|defibrillat\w*|diagnos(e|is) is)\b", re.I)


def test_review_workflow_contains_process_steps_only():
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "NOT clinical protocols" in data["_comment"]
    steps = " ".join(s["label"] for s in data["steps"])
    assert not CLINICAL_WORDS.search(steps)
    assert {s["role"] for s in data["steps"]} <= {"mission_operator", "flight_surgeon"}
    assert data["escalation"]["critical"]["who"] == "Flight surgeon on duty"


async def _desaturation_alert(p5) -> dict:
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(240)
    queue = (await p5.client.get("/api/decision-support/queue")).json()
    return next(i for i in queue["items"] if i["title"] == "Oxygen desaturation")


async def test_packet_has_all_eight_parts_built_from_the_alert(p5):
    item = await _desaturation_alert(p5)
    pk = (await p5.client.get(f"/api/decision-support/alerts/{item['alert_id']}")).json()
    for part in ("observation", "measurements", "baseline_comparison", "environmental_context", "ai_output",
                 "confidence_uncertainty", "data_quality", "review_workflow"):
        assert pk[part], part
    rec = p5.monitor.evaluator.find(item["alert_id"])
    m = pk["measurements"]
    assert m["trigger_value"] == rec.trigger_value and m["alert_limit"] == rec.threshold_value
    assert "not a clinical criterion" in m["alert_limit_note"] and m["series"]
    assert pk["observation"]["simulated_test_scenario"] == "Oxygen desaturation"
    assert "injected by the simulator" in pk["environmental_context"]["scenario_note"]
    assert pk["environmental_context"]["space_weather"]["data_category"] == "indicator"
    assert "not diagnostic certainty" in pk["confidence_uncertainty"]["meaning"]
    esc = pk["review_workflow"]["escalation"]
    assert esc["level"] == "immediate" and esc["requires_medical_review"]
    assert [s["key"] for s in pk["review_workflow"]["steps"]][0] == "notify"
    if pk["baseline_comparison"]["available"]:
        spo2 = next(c for c in pk["baseline_comparison"]["contributors"] if c["signal"] == "spo2")
        assert spo2["z"] < 0 and spo2["baseline"] > spo2["value"]
    assert (await p5.client.get("/api/decision-support/alerts/nope")).status_code == 404


async def test_queue_is_ordered_and_escalates_by_severity(p5):
    await _desaturation_alert(p5)
    items = (await p5.client.get("/api/decision-support/queue", params={"include_advisory": True})).json()["items"]
    ranks = [{"critical": 0, "caution": 1, "advisory": 2}[i["severity"]] for i in items]
    assert ranks == sorted(ranks)
    assert {i["escalation"]["level"] for i in items if i["severity"] == "critical"} == {"immediate"}


async def test_emergency_catalogue_and_labels(p5):
    cat = (await p5.client.get("/api/emergency/scenarios")).json()
    assert {c["key"] for c in cat} == set(CATALOGUE) and len(cat) == 7
    assert {s["key"] for s in cat[0]["severities"]} == {"mild", "moderate", "severe"}


async def test_emergency_run_lifecycle_analysis_and_timeline(p5):
    c = p5.client
    r = await c.post("/api/emergency/runs", json={"scenario": "multiple_deviations", "astronaut_id": "AST-03",
                                                  "severity": "severe", "duration_seconds": 600})
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "running" and len(run["components"]) == 3
    assert run["label_simulated"].startswith("SIMULATED TEST SCENARIO")
    assert {x["scenario"] for x in run["components"]} == {"tachycardia", "desaturation", "elevated_temperature"}
    clash = await c.post("/api/emergency/runs", json={"scenario": "hr_elevation", "astronaut_id": "AST-03"})
    assert clash.status_code == 409
    assert (await c.post("/api/emergency/runs", json={"scenario": "desaturation"})).status_code == 409
    await p5.tick(420)
    an = await c.post(f"/api/emergency/runs/{run['id']}/analyze")
    assert an.status_code == 200
    crew = an.json()["crew"][0]
    assert crew["astronaut_id"] == "AST-03" and crew["alerts"]
    assert sum(1 for v in crew["systems"].values() if v in ("deviation", "marked_deviation")) >= 2
    assert crew["escalation"]["level"] == "immediate"
    if crew["anomaly"].get("available"):
        assert crew["anomaly"]["flagged_windows"] > 0
    tl = (await c.get(f"/api/emergency/runs/{run['id']}/timeline")).json()
    kinds = [e["kind"] for e in tl["events"]]
    assert kinds[0] == "run_started" and "alert_opened" in kinds and "analysis" in kinds
    assert tl["vitals"] and tl["label"].startswith("SIMULATED")
    detail = (await c.get(f"/api/emergency/runs/{run['id']}")).json()
    assert len(detail["analyses"]) == 1
    cancelled = await c.post(f"/api/emergency/runs/{run['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (await c.post(f"/api/emergency/runs/{run['id']}/cancel")).status_code == 409


async def test_sleep_disruption_overlay_leaves_stored_sleep_unchanged(p5):
    async with p5.app.state.session_factory() as s:
        before = {r.night: r.duration_hours for r in (await s.scalars(
            select(SleepSessionRow).where(SleepSessionRow.astronaut_id == "AST-01"))).all()}
    r = await p5.client.post("/api/emergency/runs", json={"scenario": "sleep_disruption", "astronaut_id": "AST-01",
                                                          "severity": "severe", "nights": 3})
    overlay = r.json()["overlay"]
    assert overlay["type"] == "sleep" and len(overlay["nights"]) == 3
    assert all(n["duration_hours"] < n["original_duration_hours"] for n in overlay["nights"].values())
    await p5.tick(120)
    a = (await p5.client.get("/api/multisystem/AST-01")).json()
    sleep = next(s for s in a["systems"] if s["key"] == "sleep_circadian")
    assert sleep["status"] in ("deviation", "marked_deviation")
    assert any("overlay" in f["source"] for f in sleep["features"])
    async with p5.app.state.session_factory() as s:
        after = {r.night: r.duration_hours for r in (await s.scalars(
            select(SleepSessionRow).where(SleepSessionRow.astronaut_id == "AST-01"))).all()}
    assert after == before


async def test_radiation_event_timeline_shows_simulated_dose_rate(p5):
    r = await p5.client.post("/api/emergency/runs", json={"scenario": "radiation_event", "severity": "moderate",
                                                          "duration_seconds": 300})
    assert r.status_code == 201 and r.json()["astronaut_id"] is None
    await p5.tick(150)
    tl = (await p5.client.get(f"/api/emergency/runs/{r.json()['id']}/timeline", params={"astronaut_id": "AST-04"})).json()
    rates = [p["dose_rate_msv_day"] for p in tl["environment"]]
    assert max(rates) > 5 * min(rates)


async def test_baseline_category_alerts_are_explained(p5):
    """Regression: explaining a rhythm/baseline alert (no threshold value) used to raise a TypeError."""
    await _desaturation_alert(p5)
    items = (await p5.client.get("/api/decision-support/queue", params={"include_advisory": True})).json()["items"]
    rec = next(p5.monitor.evaluator.find(i["alert_id"]) for i in items
               if p5.monitor.evaluator.find(i["alert_id"]).category != "threshold")
    pk = await p5.client.get(f"/api/decision-support/alerts/{rec.id}")
    assert pk.status_code == 200
    if pk.json()["ai_output"]["available"]:
        assert pk.json()["ai_output"]["rule"].startswith(("Personal-baseline check", "Rhythm check"))
    assert (await p5.client.get(f"/api/ai/explanations/{rec.id}")).status_code == 200


async def test_unhandled_errors_keep_cors_headers(p5, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(p5.app.state.multisystem, "assess", boom)
    r = await p5.client.get("/api/multisystem/AST-01", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
