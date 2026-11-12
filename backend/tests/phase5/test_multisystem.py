"""Multisystem engine: statuses from actual inputs, cross-system patterns, habitat context."""

from __future__ import annotations

import json
import re

from app.medical.multisystem import CONFIG_PATH, MultisystemConfig, feature

CFG = MultisystemConfig.load()


def test_feature_status_bands_and_informational_inputs():
    assert feature("x", "X", 1, "", z=1.9, category="simulated", source="t", cfg=CFG)["status"] == "within_baseline"
    assert feature("x", "X", 1, "", z=-2.1, category="simulated", source="t", cfg=CFG)["status"] == "deviation"
    f = feature("x", "X", 1, "", z=3.5, category="simulated", source="t", cfg=CFG)
    assert f["status"] == "marked_deviation" and f["direction"] == "above"
    assert feature("x", "X", None, "", category="simulated", source="t", cfg=CFG)["status"] == "insufficient_data"
    assert feature("x", "X", 2, "", informational=True, category="simulated", source="t", cfg=CFG)["status"] == "info"
    assert feature("x", "X", "yes", "", flag=True, category="simulated", source="t", cfg=CFG)["status"] == "deviation"


def test_config_is_documented_as_non_clinical():
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert "NOT clinical thresholds" in raw["_comment"]
    assert set(raw["systems"]) == {"cardiovascular", "respiratory", "thermoregulation", "sleep_circadian",
                                   "activity_recovery", "radiation"}


async def test_quiet_crew_member_has_no_vital_sign_deviation(p5):
    await p5.tick(60)
    a = (await p5.client.get("/api/multisystem/AST-01")).json()
    assert [s["key"] for s in a["systems"]] == list(CFG.systems)
    for key in ("respiratory", "thermoregulation"):
        s = next(x for x in a["systems"] if x["key"] == key)
        assert s["status"] in ("within_baseline", "insufficient_data")
    assert "not clinical thresholds" in a["config"]["note"]
    assert "Not a diagnosis" in a["disclaimer"]


async def test_desaturation_is_explained_from_its_actual_inputs(p5):
    c = p5.client
    r = await c.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                     "intensity": 1.3, "duration_seconds": 900})
    assert r.status_code == 201
    await p5.tick(300)
    a = (await c.get("/api/multisystem/AST-02")).json()
    resp = next(s for s in a["systems"] if s["key"] == "respiratory")
    spo2 = next(f for f in resp["features"] if f["key"] == "spo2")
    assert resp["status"] == "marked_deviation" and spo2["z"] < -3 and spo2["direction"] == "below"
    assert spo2["category"] == "simulated" and "personal baseline" in spo2["reference_label"]
    # Every number quoted in the explanation comes from a listed input.
    for f in resp["features"]:
        if f["status"] in ("deviation", "marked_deviation"):
            assert str(f["value"]) in resp["explanation"] and str(f["reference"]) in resp["explanation"]
    numbers = set(re.findall(r"-?\d+(?:\.\d+)?", resp["explanation"]))
    allowed = {str(v) for f in resp["features"] for v in (f["value"], f["reference"], abs(f["z"] or 0))}
    allowed |= {f"{abs(f['z']):.1f}" for f in resp["features"] if f["z"] is not None}
    assert numbers <= allowed | {"2", "3"}
    keys = {p["key"] for p in a["patterns"]}
    assert "cardiorespiratory" in keys
    assert all("not establish a cause" in p["note"] for p in a["patterns"])
    crew = (await c.get("/api/multisystem")).json()
    row = next(x for x in crew["crew"] if x["astronaut_id"] == "AST-02")
    assert row["statuses"]["respiratory"] == "marked_deviation"


async def test_habitat_anomaly_adds_simulated_cabin_inputs(p5):
    c = p5.client
    r = await c.post("/api/emergency/runs", json={"scenario": "environmental_anomaly", "severity": "severe",
                                                  "duration_seconds": 900})
    assert r.status_code == 201
    await p5.tick(240)
    a = (await c.get("/api/multisystem/AST-03")).json()
    resp = next(s for s in a["systems"] if s["key"] == "respiratory")
    co2 = next(f for f in resp["features"] if f["key"] == "habitat_ppco2")
    assert co2["category"] == "simulated" and co2["value"] > co2["reference"] and co2["status"] == "marked_deviation"
    assert a["habitat"]["note"].startswith("Simulated cabin atmosphere")
    thermo = next(s for s in a["systems"] if s["key"] == "thermoregulation")
    assert any(f["key"] == "habitat_temperature" for f in thermo["features"])


async def test_nasa_indicators_are_context_and_never_change_crew_status(p5):
    from datetime import timedelta

    from app.db.models import SpaceWeatherEventRow

    async with p5.app.state.session_factory() as s:
        s.add(SpaceWeatherEventRow(
            source_id="donki", event_type="FLR", external_id="test-flare", category="indicator",
            start_time=p5.clock.now - timedelta(hours=2), classification="X1.0", scale="R3", severity=3,
            magnitude=1e-4, magnitude_unit="W/m2", instruments=[], raw={}, endpoint="test",
            retrieved_at=p5.clock.now, link=None))
        await s.commit()
    await p5.tick(30)
    a = (await p5.client.get("/api/multisystem/AST-01")).json()
    rad = next(s for s in a["systems"] if s["key"] == "radiation")
    nasa = next(f for f in rad["features"] if f["key"] == "nasa_space_weather")
    assert nasa["status"] == "info" and nasa["category"] == "indicator" and nasa["value"] == 1
    # Whatever the radiation status is, only simulated crew inputs can make it deviate.
    scored = [f for f in rad["features"] if f["status"] in ("deviation", "marked_deviation")]
    assert all(f["category"] == "simulated" for f in scored), scored
