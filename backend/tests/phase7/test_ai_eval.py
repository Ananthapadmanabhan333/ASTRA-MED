"""Phase 7 evaluation metrics, experiment tracking and AI serving (lazy loading, pinning, monitoring)."""

from __future__ import annotations

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.ai.experiments.tracking import build_index, render_index
from app.ai.metrics import RATIO_SCALE_SIGNALS, classification, regression
from app.ai.monitoring import InferenceStats, library_versions, version_mismatches
from app.ai.registry import ModelRegistry
from app.ai.service import LazyModels, ModelBundle
from app.core.config import Settings
from app.main import create_app


def test_classification_reports_false_negative_rate_and_specificity():
    y = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
    scores = np.array([0.9, 0.8, 0.2, 0.1, 0.95, 0.1, 0.1, 0.1, 0.1, 0.1])
    m = classification(y, scores, threshold=0.5)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (2, 2, 1, 5)
    assert m["false_negative_rate"] == pytest.approx(0.5) == pytest.approx(1 - m["recall"])
    assert m["false_alarm_rate"] == pytest.approx(1 / 6, abs=1e-4)
    assert m["specificity"] == pytest.approx(5 / 6, abs=1e-4)


def test_mape_only_on_ratio_scale_signals():
    assert "temperature_c" not in RATIO_SCALE_SIGNALS and "heart_rate" in RATIO_SCALE_SIGNALS
    y, pred = np.array([60.0, 80.0, 100.0]), np.array([66.0, 76.0, 100.0])
    with_mape = regression(y, pred, mape=True)
    assert with_mape["mape_pct"] == pytest.approx((10 + 5 + 0) / 3, abs=1e-3)
    assert "mape_pct" not in regression(y, pred)


def test_inference_stats_percentiles_and_errors():
    stats = InferenceStats(window=5)
    for ms in (10, 20, 30, 40, 50, 60):  # window keeps the last five
        stats.record("forecast:xgboost", ms)
    with pytest.raises(ValueError), stats.measure("risk_assessment"):
        raise ValueError("boom")
    snap = stats.snapshot()["operations"]
    assert snap["forecast:xgboost"]["count"] == 6 and snap["forecast:xgboost"]["window"] == 5
    assert snap["forecast:xgboost"]["p50_ms"] == 40 and snap["forecast:xgboost"]["max_ms"] == 60
    assert snap["risk_assessment"]["errors"] == 1 and "boom" in snap["risk_assessment"]["last_error"]


def test_library_mismatch_ignores_patch_releases():
    running = library_versions()
    assert running["numpy"]
    trained = dict(running, numpy="1.0.0")
    assert set(version_mismatches(trained, running)) == {"numpy"}
    if running.get("scikit-learn"):
        major, minor, *_ = running["scikit-learn"].split(".")
        patched = dict(running, **{"scikit-learn": f"{major}.{minor}.999"})
        assert version_mismatches(patched, running) == {}
    assert version_mismatches(None, running) == {}


def test_lazy_models_load_on_first_use_only():
    calls = []

    def loader(name):
        def build():
            calls.append(name)
            return f"model-{name}"
        return build

    models = LazyModels({n: loader(n) for n in ("xgboost", "lstm", "gru")}, eager=["xgboost"])
    assert calls == ["xgboost"] and list(models) == ["xgboost", "lstm", "gru"] and "lstm" in models
    assert models.loaded() == ["xgboost"]
    assert models["lstm"] == "model-lstm" and models["lstm"] == "model-lstm"
    assert calls == ["xgboost", "lstm"]
    with pytest.raises(KeyError):
        models["tcn"]


def test_bundle_refuses_an_unregistered_pinned_version(trained_artifacts):
    with pytest.raises(FileNotFoundError):
        ModelBundle.load(trained_artifacts, "v00000000-000000-deadbeef")
    latest = ModelRegistry(trained_artifacts).latest()
    bundle = ModelBundle.load(trained_artifacts, latest)
    assert bundle.version == latest and bundle.forecasters.loaded() == [bundle.serving]


def test_experiment_index_lists_versions_with_library_versions(trained_artifacts):
    rows = build_index(trained_artifacts)
    assert rows and rows[-1]["latest"] and rows[-1]["libraries"]["numpy"]
    assert rows[-1]["ensemble_fnr"] is not None
    assert "Experiment index" in render_index(rows)


@pytest_asyncio.fixture
async def ai_app(tmp_path, trained_artifacts):
    settings = Settings(database_url=f"sqlite+aiosqlite:///{(tmp_path / 'ai7.db').as_posix()}",
                        simulator_enabled=False, random_events_per_hour=0, backfill_days=2,
                        backfill_interval_minutes=5, ai_artifacts_dir=str(trained_artifacts), ai_cache_seconds=0,
                        space_sync_enabled=False, mission_orchestrator_enabled=False, log_level="WARNING",
                        ai_model_version=ModelRegistry(trained_artifacts).latest())
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", timeout=120) as c:
            yield c, app


async def test_status_reports_pinning_lazy_models_and_inference_timings(ai_app):
    c, app = ai_app
    status = (await c.get("/api/ai/status")).json()
    assert status["pinned_version"] == status["model_version"]
    assert status["forecasters_loaded"] == [status["serving_forecaster"]]
    assert status["library_mismatch"] == {}
    r = await c.get("/api/ai/astronaut/AST-01/forecast", params={"model": "climatology"})
    assert r.status_code == 200
    r = await c.post("/api/ai/anomaly-detection", json={"astronaut_id": "AST-01"})
    assert r.status_code == 200
    status = (await c.get("/api/ai/status")).json()
    ops = status["inference"]["operations"]
    assert ops["anomaly_detection"]["count"] == 1 and ops["forecast:climatology"]["count"] == 1
    assert "climatology" in status["forecasters_loaded"]


async def test_batched_attribution_matches_row_by_row(ai_app):
    _, app = ai_app
    ai = app.state.ai
    bundle = await ai.require_bundle()
    entry = await ai.baseline("AST-01")
    from datetime import timedelta

    from app.core.timeutil import utcnow

    now = utcnow()
    windows = await ai.windows("AST-01", now - timedelta(hours=12), now)
    a = ai._analyse(bundle, entry.baseline, windows, list(bundle.detectors))
    rows = [len(windows) - 3, len(windows) - 10, len(windows) - 40]
    batch = ai._contributions(a, bundle, rows)
    for i in rows:
        a.contrib.clear()
        single = ai._contributions(a, bundle, [i])[i]
        np.testing.assert_allclose(batch[i], single, rtol=1e-5, atol=1e-7)


def test_planned_state_is_independent_of_string_hashing():
    """Regression: max(set(...)) picked tied states by hash order, so forecasts changed per process."""
    import subprocess
    import sys

    code = ("import pandas as pd; from app.ai.timeline import planned_steps; "
            "idx = pd.date_range('2026-11-09', periods=96, freq='30min', tz='UTC'); "
            "print(','.join(planned_steps('AST-01', idx, 2026)['state']))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={**__import__('os').environ, "PYTHONHASHSEED": seed}).stdout
            for seed in ("1", "2", "3", "4")}
    assert len(outs) == 1
