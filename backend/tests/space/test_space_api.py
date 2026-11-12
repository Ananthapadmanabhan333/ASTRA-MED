"""API integration tests for the space module against a fake NASA service (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.space.service import SpaceDataService

from .conftest import fixture

SECRET = "TESTKEY-must-never-leak-123"


def _settings(tmp_path, **kw) -> Settings:
    base = dict(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'space.db').as_posix()}",
        simulator_enabled=False, random_events_per_hour=0, backfill_days=3, backfill_interval_minutes=5,
        ai_enabled=False, log_level="WARNING", nasa_api_key=SECRET, donki_backfill_days=40,
        space_request_spacing_s=0,
    )
    base.update(kw)
    return Settings(**base)


@pytest_asyncio.fixture
async def space_api(tmp_path, fake_nasa, no_sleep):
    settings = _settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await app.state.space.stop()  # replace the real client with one wired to the fake NASA service
        app.state.space = SpaceDataService(settings, app.state.session_factory,
                                           transport=httpx.MockTransport(fake_nasa), sleep=no_sleep)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60) as client:
            yield client, app, fake_nasa
        await app.state.space.stop()


def _is_utc(ts: str) -> bool:
    return ts.endswith("Z") or ts.endswith("+00:00")


async def test_sync_records_provenance_and_failover_without_leaking_the_key(space_api):
    client, _, fake = space_api
    r = await client.post("/api/space/sync", json={"source": "donki"})
    assert r.status_code == 200, r.text
    flr = r.json()["summary"]["FLR"]
    assert flr["received"] == 4 and flr["new"] == 4 and flr["invalid"] == 0

    again = (await client.post("/api/space/sync", json={"source": "donki"})).json()["summary"]["FLR"]
    assert again["new"] == 0 and again["duplicates"] == 4  # duplicate detection

    events = (await client.get("/api/space/weather/events", params={"start": "2000-01-01T00:00:00Z"})).json()
    assert events["total"] > 0 and events["freshness"]["mode"] in ("live", "cached")
    for e in events["events"]:
        assert e["category"] in ("indicator", "model") and e["endpoint"] == "ccmc" and e["source"]
        assert _is_utc(e["start_time"]) and _is_utc(e["retrieved_at"])

    first = events["events"][0]
    detail = (await client.get(f"/api/space/weather/events/{first['id']}")).json()
    original = next(rec for f in ("donki_FLR.json", "donki_CME.json", "donki_GST.json", "donki_SEP.json",
                                  "donki_RBE.json", "donki_IPS.json", "donki_HSS.json", "donki_WSA.json")
                    for rec in fixture(f) if detail["raw"] == rec)
    assert original  # the stored raw record is byte-for-byte the NASA record

    sources = (await client.get("/api/space/sources")).json()
    donki = next(s for s in sources["sources"] if s["id"] == "donki")
    by_name = {e["name"]: e for e in donki["endpoints"]}
    assert by_name["api.nasa.gov"]["available"] is False and "404" in by_name["api.nasa.gov"]["reason"]
    assert by_name["api.nasa.gov"]["rate_limit_limit"] == 10
    assert by_name["ccmc"]["available"] is True
    assert donki["health"]["status"] == "degraded" and donki["records"] > 0
    assert donki["license"] and donki["citation"] and donki["caveats"]
    assert donki["quality"]["duplicates"] >= 4 and donki["quality"]["sync_runs"] > 0
    assert sources["api_key_configured"] is True

    # The key was sent to the NASA gateway, but appears in no response.
    assert any(SECRET in str(req.url) for req in fake.requests if req.url.host == "api.nasa.gov")
    for path in ("/api/space/sources", "/api/space/weather/summary", "/api/space/weather/events", "/openapi.json"):
        assert SECRET not in (await client.get(path)).text, path


async def test_newer_donki_version_replaces_the_stored_record(space_api):
    client, _, fake = space_api
    await client.post("/api/space/sync", json={"source": "donki"})
    revised = [dict(rec, versionId=rec.get("versionId", 1) + 1, classType="X1.2") if i == 0 else rec
               for i, rec in enumerate(fixture("donki_FLR.json"))]
    fake.overrides["/DONKI/WS/get/FLR"] = lambda req: httpx.Response(200, json=revised)
    summary = (await client.post("/api/space/sync", json={"source": "donki"})).json()["summary"]["FLR"]
    assert summary["updated"] == 1 and summary["new"] == 0
    events = (await client.get("/api/space/weather/events", params={"types": "FLR", "start": "2000-01-01T00:00:00Z"})).json()
    upgraded = next(e for e in events["events"] if e["classification"].startswith("X1.2"))
    assert upgraded["scale"] == "R3" and upgraded["version"] == revised[0]["versionId"]


async def test_offline_fallback_keeps_serving_stored_data(space_api):
    client, _, fake = space_api
    await client.post("/api/space/sync", json={"source": "donki"})
    before = (await client.get("/api/space/weather/summary", params={"days": 365})).json()
    fake.down = {"api.nasa.gov", "ccmc.gsfc.nasa.gov"}
    r = await client.post("/api/space/sync", json={"source": "donki"})
    assert r.status_code == 200 and r.json()["summary"]["FLR"]["errors"]
    after = (await client.get("/api/space/weather/summary", params={"days": 365})).json()
    assert after["counts"] == before["counts"]  # stored data still served
    assert after["freshness"]["mode"] == "offline-fallback" and "unreachable" in after["freshness"]["message"]
    sources = (await client.get("/api/space/sources")).json()
    donki = next(s for s in sources["sources"] if s["id"] == "donki")
    assert donki["health"]["status"] == "offline" and donki["quality"]["failed_runs"] > 0
    assert any(run["status"] == "failed" for run in donki["recent_runs"])


async def test_unreachable_nasa_with_an_empty_store_is_reported_not_faked(space_api):
    client, _, fake = space_api
    fake.down = {"api.nasa.gov", "ccmc.gsfc.nasa.gov", "visualization.osdr.nasa.gov", "osdr.nasa.gov"}
    await client.post("/api/space/sync", json={"source": "donki"})
    summary = (await client.get("/api/space/weather/summary")).json()
    assert summary["freshness"]["mode"] == "unavailable" and sum(summary["counts"].values()) == 0
    assert (await client.get("/api/space/weather/events")).json()["events"] == []
    assert (await client.get("/api/space/iss/missions")).json() == []


async def test_eda_ingestion_quality_and_historical_labelling(space_api):
    client, _, _ = space_api
    r = await client.post("/api/space/sync", json={"source": "eda", "missions": ["RR-1"]})
    assert r.status_code == 200, r.text
    await client.post("/api/space/sync", json={"source": "osdr"})
    missions = (await client.get("/api/space/iss/missions")).json()
    rr1 = next(m for m in missions if m["name"] == "RR-1")
    assert rr1["has_telemetry"] and rr1["has_radiation"] and rr1["start_time"].startswith("2014-09")

    detail = (await client.get("/api/space/iss/missions/RR-1", params={"resolution": "1h"})).json()
    series = {(s["quantity"], s["platform"]): s for s in detail["series"]}
    temp = series[("temperature_c", "iss")]
    assert temp["unit"] == "°C" and temp["category"] == "measured" and temp["resolution"] == "1h"
    assert temp["quality"]["out_of_range"] == 1 and temp["quality"]["duplicates"] == 1
    assert max(p["value"] for p in temp["points"]) < 45
    dose = series[("dose_total_mgy_day", "iss")]
    assert dose["unit"] == "mGy/day" and sum(p["approximate"] for p in dose["points"]) == 5
    assert any("not current ISS telemetry" in c for c in detail["caveats"])
    assert any(s["accession"] for s in detail["studies"])  # OSDR studies linked through "RR-1"
    coarse = (await client.get("/api/space/iss/missions/RR-1", params={"resolution": "1d"})).json()
    ctemp = next(s for s in coarse["series"] if s["quantity"] == "temperature_c" and s["platform"] == "iss")
    assert ctemp["resolution"] == "1d" and len(ctemp["points"]) < len(temp["points"])


async def test_radiation_categories_are_separate_and_never_converted(space_api):
    client, _, _ = space_api
    await client.post("/api/space/sync", json={"source": "donki"})
    await client.post("/api/space/sync", json={"source": "eda", "missions": ["RR-1"]})
    rad = (await client.get("/api/space/radiation", params={"days": 30})).json()
    assert rad["measured"]["category"] == "measured" and rad["measured"]["unit"] == "mGy/day"
    assert rad["estimate"]["category"] == "estimate" and rad["estimate"]["unit"] == "mSv/day"
    assert rad["simulated"]["category"] == "simulated" and rad["simulated"]["unit"] == "mSv/day"
    assert rad["indicators"]["category"] == "indicator"
    assert not any("dose" in k or "msv" in k.lower() or "mgy" in k.lower() for k in rad["indicators"])
    m = rad["measured"]["missions"][0]
    assert m["mission"] == "RR-1" and m["approximate_days"] == 5 and 0.1 < m["mean_total_mgy_day"] < 1
    day = rad["timeline"][0]
    assert set(day) == {"day", "estimate_msv", "simulated_crew_mean_msv", "simulated_spe", "indicator_events"}
    assert all("not a dose" in a["note"] for a in rad["alerts"])
    assert any("never converted" in rule for rule in rad["rules"])


async def test_timeline_is_utc_ordered_and_nearby_offsets_are_exact(space_api):
    client, app, _ = space_api
    await client.post("/api/space/sync", json={"source": "donki"})
    end = datetime.now(UTC)
    t = (await client.get("/api/space/timeline", params={"astronaut_id": "AST-01", "start": (end - timedelta(days=30)).isoformat(),
                                                         "end": end.isoformat()})).json()
    assert t["mode"] == "mission" and {lane["key"] for lane in t["lanes"]} >= {"space_weather", "crew_alerts", "ai"}
    for lane in t["lanes"]:
        stamps = [i["ts"] for i in lane["items"]]
        assert all(_is_utc(s) for s in stamps) and stamps == sorted(stamps), lane["key"]
    assert t["series"] and t["series"][0]["category"] == "simulated"
    assert any("not influenced" in n for n in t["notes"])

    swx = next(lane for lane in t["lanes"] if lane["key"] == "space_weather")["items"][0]
    event_ts = datetime.fromisoformat(swx["ts"].replace("Z", "+00:00"))
    probe = (event_ts - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    near = (await client.get("/api/space/timeline/nearby", params={"ts": probe, "window_hours": 6})).json()
    hit = next(e for e in near["events"] if e["id"] == swx["id"])
    assert hit["offset_hours"] == 2.0 and "not evidence of a causal link" in near["note"]

    await client.post("/api/space/sync", json={"source": "eda", "missions": ["RR-1"]})
    iss = (await client.get("/api/space/timeline", params={"mode": "iss", "mission": "RR-1"})).json()
    assert iss["mode"] == "iss" and any(s["category"] == "measured" for s in iss["series"])
    assert (await client.get("/api/space/timeline", params={"mode": "iss"})).status_code == 400


async def test_correlation_endpoints_report_provenance_and_valid_json(space_api):
    client, _, _ = space_api
    await client.post("/api/space/sync", json={"source": "donki"})
    await client.post("/api/space/sync", json={"source": "eda", "missions": ["RR-1"]})
    catalogue = (await client.get("/api/space/correlation/series")).json()
    ids = {s["id"] for s in catalogue}
    assert {"swx:flare_count", "crew:AST-01:hr_mean", "iss:RR-1:dose_gcr_mgy_day"} <= ids

    r = await client.post("/api/space/correlation/analyze", json={
        "x": "iss:RR-1:dose_gcr_mgy_day", "y": "iss:RR-1:dose_saa_mgy_day", "start": "2014-09-20", "end": "2014-11-01"})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ok" and body["n"] > 20
    assert body["pearson"]["ci"][0] <= body["pearson"]["r"] <= body["pearson"]["ci"][1]
    assert "Correlation does not establish causation." in body["interpretation"]
    assert any("Benjamini-Hochberg" in w for w in body["warnings"])
    assert "NaN" not in r.text and "Infinity" not in r.text

    today = datetime.now(UTC).date()
    mixed = (await client.post("/api/space/correlation/analyze", json={
        "x": "swx:cme_count", "y": "crew:AST-01:hr_mean", "start": str(today - timedelta(days=30)), "end": str(today)})).json()
    assert any("coincidental by construction" in w for w in mixed["warnings"])

    mat = await client.post("/api/space/correlation/matrix", json={
        "series": ["iss:RR-1:dose_gcr_mgy_day", "iss:RR-1:dose_saa_mgy_day", "iss:RR-1:temperature_c"],
        "start": "2014-09-20", "end": "2014-11-01"})
    assert mat.status_code == 200 and len(mat.json()["cells"]) == 9 and "NaN" not in mat.text
    assert (await client.post("/api/space/correlation/analyze", json={
        "x": "nope", "y": "swx:sep", "start": "2026-01-01", "end": "2026-02-01"})).status_code == 404
    assert (await client.post("/api/space/correlation/analyze", json={
        "x": "swx:sep", "y": "swx:rbe", "start": "2026-02-01", "end": "2026-01-01"})).status_code == 400


async def test_operator_sync_is_gated(tmp_path, fake_nasa, no_sleep):
    app = create_app(_settings(tmp_path, simulation_control_enabled=False, space_sync_enabled=False))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/space/sync", json={"source": "donki"})
            assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
            assert (await client.get("/api/space/sources")).json()["sync_enabled"] is False


async def test_module_can_be_disabled(tmp_path):
    app = create_app(_settings(tmp_path, space_enabled=False))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/space/sources")
            assert r.status_code == 503 and json.loads(r.text)["error"]["code"] == "space_disabled"
            assert (await client.get("/api/system/health")).status_code == 200  # phases 1-2 unaffected
