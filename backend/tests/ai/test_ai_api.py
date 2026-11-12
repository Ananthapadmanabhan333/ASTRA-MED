"""Integration tests for /api/ai/* against a real app, stored history and a small trained model."""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.ai.experiments.config import ExperimentConfig
from app.ai.experiments.runner import run
from app.core.config import Settings
from app.core.timeutil import utcnow
from app.main import create_app
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW, CREW_BY_ID
from app.simulator.scenarios import ActiveScenario, Scenario


@pytest.fixture(scope="session")
def trained_artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("ai-artifacts")
    results = run(ExperimentConfig().quick(), root)
    assert results["version"]
    return root


def _settings(tmp_path, artifacts) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'ai.db').as_posix()}",
        simulator_enabled=False,
        random_events_per_hour=0,
        backfill_days=2,
        backfill_interval_minutes=5,
        ai_artifacts_dir=str(artifacts),
        ai_cache_seconds=0,
        log_level="WARNING",
    )


@pytest_asyncio.fixture
async def ai_api(tmp_path, trained_artifacts):
    app = create_app(_settings(tmp_path, trained_artifacts))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=120) as client:
            yield client, app


async def _tick_scenario(app, scenario: Scenario, astronaut_id: str, seconds: int = 150):
    monitor = app.state.monitor
    start = utcnow() - timedelta(seconds=seconds + 5)
    monitor.engine.start_scenario(scenario, astronaut_id, start, duration_s=seconds + 60, intensity=1.2)
    for i in range(seconds):
        await monitor.tick(start + timedelta(seconds=i + 1))
    await monitor._flush(force=True)


async def test_status_reports_loaded_version(ai_api):
    client, _ = ai_api
    body = (await client.get("/api/ai/status")).json()
    assert body["loaded"] and body["model_version"].startswith("v")
    assert {"statistical", "isolation_forest", "lof", "one_class_svm", "autoencoder"} <= set(body["detectors"])
    assert body["serving_forecaster"] == "xgboost"


async def test_baseline_is_personal_and_compares_current_values(ai_api):
    client, _ = ai_api
    body = (await client.get("/api/ai/astronaut/AST-02/baseline")).json()
    assert body["windows_used"] > 400 and body["data_source"] == "simulated"
    hr = next(s for s in body["signals"] if s["signal"] == "heart_rate")
    assert {"sleep", "work"} <= set(hr["by_state"])
    assert hr["by_state"]["sleep"]["center"] < hr["by_state"]["work"]["center"]
    assert hr["current"]["assessment"] in {"within", "high", "low"}
    assert hr["rolling_24h"]["n"] > 0 and "disclaimer" in body
    assert (await client.get("/api/ai/astronaut/AST-99/baseline")).status_code == 404


async def test_anomaly_detection_on_stored_data(ai_api):
    client, _ = ai_api
    r = await client.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["detectors"]) == 5
    assert 60 <= len(body["timeline"]) <= 73
    point = body["timeline"][-1]
    assert set(point["scores"]) == {d["name"] for d in body["detectors"]}
    assert body["data_quality"]["windows"] == len(body["timeline"])


async def test_anomaly_detection_finds_injected_event_in_supplied_readings(ai_api):
    client, _ = ai_api
    profile = CREW_BY_ID["AST-01"]
    end = utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(hours=3)
    event = ActiveScenario("t", Scenario.DESATURATION, profile.id, 1.3, start + timedelta(hours=1), start + timedelta(hours=2), "operator")
    engine = SimulationEngine(CREW, seed=99, random_events_per_hour=0)
    readings = [
        {"ts": r.ts.isoformat(), "heart_rate": r.heart_rate, "spo2": r.spo2, "systolic": r.systolic,
         "diastolic": r.diastolic, "temperature_c": r.temperature_c, "respiratory_rate": r.respiratory_rate,
         "activity_state": r.activity_state, "activity_met": r.activity_met}
        for r in engine.history(profile, start, end, timedelta(minutes=5), [event])
    ]
    readings[3]["heart_rate"] = None  # missing value
    readings[5]["temperature_c"] = 44.9  # implausible: dropped before analysis
    body = (await client.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01", "readings": readings})).json()
    assert body["source"] == "supplied"
    assert body["data_quality"]["implausible_values_removed"] == 1
    assert body["detections"], "the injected desaturation should be detected"
    det = max(body["detections"], key=lambda d: d["duration_minutes"])
    assert start + timedelta(minutes=50) <= _ts(det["peak_ts"]) <= start + timedelta(hours=2, minutes=10)
    expl = det["explanation"]
    assert "spo2" in [c["signal"] for c in expl["contributors"]][:3]
    assert expl["confidence"]["level"] in {"low", "medium", "high"}
    assert any("simulated" in lim for lim in expl["limitations"])


async def test_anomaly_detection_accepts_explicit_iso_range_like_the_browser(ai_api):
    client, _ = ai_api
    end = utcnow()
    body = {"astronaut_id": "AST-01", "start": (end - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z")}
    r = await client.post("/api/ai/anomaly-detection", json=body)
    assert r.status_code == 200, r.text
    assert 20 <= len(r.json()["timeline"]) <= 25


async def test_anomaly_detection_validation(ai_api):
    client, _ = ai_api
    bad_model = await client.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01", "models": ["magic"]})
    assert bad_model.status_code == 422
    subset = await client.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01", "models": ["lof", "statistical"]})
    assert subset.status_code == 200 and len(subset.json()["detectors"]) == 2
    too_long = await client.post("/api/ai/anomaly-detection", json={
        "astronaut_id": "AST-01", "start": "2026-01-01T00:00:00Z", "end": "2026-03-01T00:00:00Z"})
    assert too_long.status_code == 422


@pytest.mark.parametrize("model", ["xgboost", "lstm", "climatology"])
async def test_forecast_has_intervals_and_horizons(ai_api, model):
    client, _ = ai_api
    r = await client.get("/api/ai/astronaut/AST-03/forecast", params={"model": model})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == model and len(body["series"]) == 4
    for s in body["series"]:
        assert len(s["forecast"]) == 48 and len(s["history"]) == 48
        assert all(p["lower"] <= p["value"] <= p["upper"] for p in s["forecast"])
        assert [h["horizon_h"] for h in s["horizons"]] == [1, 6, 12, 24]
        assert s["explanation"]["kind"] == "forecast"
    hr = next(s for s in body["series"] if s["signal"] == "heart_rate")
    if model == "xgboost":
        assert hr["drivers"] and abs(sum(d["share"] for d in hr["drivers"]) - 1) < 0.1
    assert 40 < hr["forecast"][0]["value"] < 140


async def test_forecast_filters_and_rejects_unknown(ai_api):
    client, _ = ai_api
    only = (await client.get("/api/ai/astronaut/AST-03/forecast", params={"signals": ["spo2"]})).json()
    assert [s["signal"] for s in only["series"]] == ["spo2"]
    assert (await client.get("/api/ai/astronaut/AST-03/forecast", params={"model": "prophet"})).status_code == 422
    assert (await client.get("/api/ai/astronaut/AST-03/forecast", params={"signals": ["systolic"]})).status_code == 422


async def test_risk_rises_during_injected_desaturation(ai_api):
    client, app = ai_api
    calm = (await client.get("/api/ai/astronaut/AST-02/risk-assessment")).json()
    assert calm["category"] in {"normal", "low_concern", "moderate_concern", "high_concern"}
    assert calm["health_score"] == round(100 - calm["risk_score"])
    await _tick_scenario(app, Scenario.DESATURATION, "AST-02")
    hot = (await client.get("/api/ai/astronaut/AST-02/risk-assessment")).json()
    assert hot["risk_score"] > calm["risk_score"]
    assert hot["category"] != "normal"
    assert hot["warnings"] and hot["warnings"][0]["priority"] == 1
    assert "spo2" in {sig for w in hot["warnings"] for sig in w["signals"]}
    assert hot["explanation"]["contributors"][0]["signal"] in {"spo2", "respiratory_rate", "heart_rate"}

    overview = (await client.get("/api/ai/crew-overview")).json()
    assert len(overview["crew"]) == 4
    assert overview["crew"][0]["astronaut_id"] == "AST-02"  # highest concern first


async def test_alert_explanation(ai_api):
    client, app = ai_api
    await _tick_scenario(app, Scenario.TACHYCARDIA, "AST-04")
    alerts = (await client.get("/api/alerts", params={"astronaut_id": "AST-04", "status": "active"})).json()
    hr = next(a for a in alerts if a["metric"] == "heart_rate")
    body = (await client.get(f"/api/ai/explanations/{hr['id']}")).json()
    assert body["alert_id"] == hr["id"] and "Threshold rule heart_rate:high" in body["rule"]
    assert body["explanation"]["contributors"][0]["signal"] == "heart_rate"
    assert body["anomaly_context"]
    assert (await client.get("/api/ai/explanations/nope")).status_code == 404


async def test_model_performance_and_reload(ai_api):
    client, _ = ai_api
    perf = (await client.get("/api/ai/model-performance")).json()
    assert perf["version"].startswith("v") and perf["report_markdown"].startswith("# ASTRA-MED model evaluation")
    assert "ensemble" in perf["anomaly"] and "xgboost" in perf["forecast"]["models"]
    assert any("simulated" in lim.lower() for lim in perf["limitations"])
    reloaded = await client.post("/api/ai/models/reload")
    assert reloaded.status_code == 200 and reloaded.json()["loaded"]


async def test_endpoints_degrade_without_trained_models(tmp_path):
    app = create_app(_settings(tmp_path, tmp_path / "empty-artifacts"))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", timeout=60) as client:
            assert (await client.get("/api/ai/status")).json()["loaded"] is False
            for r in (
                await client.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01"}),
                await client.get("/api/ai/astronaut/AST-01/forecast"),
                await client.get("/api/ai/model-performance"),
            ):
                assert r.status_code == 503 and r.json()["error"]["code"] == "models_unavailable"
            # Baselines and rule-based risk still work without trained models.
            assert (await client.get("/api/ai/astronaut/AST-01/baseline")).status_code == 200
            risk = (await client.get("/api/ai/astronaut/AST-01/risk-assessment")).json()
            assert risk["anomaly"]["available"] is False and risk["model_version"] is None


def _ts(s: str):
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00"))
