"""Digital twin: daily summaries, data consistency, regeneration and live updates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select

from app.db.models import TwinDailyRow, VitalSampleRow
from app.twin import summary as S
from app.twin.service import day_bounds
from app.twin.stages import STAGES, stage_for


def test_summary_excludes_exercise_and_scenarios_from_resting_means():
    ts = [datetime(2026, 7, 1, tzinfo=UTC) + timedelta(minutes=5 * i) for i in range(6)]
    rows = [
        (ts[0], 60, "rest", None), (ts[1], 62, "work", None), (ts[2], 140, "exercise", None),
        (ts[3], 110, "rest", "tachycardia"), (ts[4], 50, "sleep", None), (ts[5], 52, "sleep", None),
    ]
    df = S.frame(rows, ("ts", "heart_rate", "activity_state", "scenario"))
    m = S.summarize_metrics(df)["heart_rate"]
    assert m["awake_rest_mean"] == 61.0 and m["awake_rest_n"] == 2
    assert m["sleep_mean"] == 51.0 and m["n"] == 6 and m["max"] == 140
    cov = S.coverage(df, S.sample_interval_s(df), 30 * 60)
    assert cov["interval_s"] == 300 and cov["completeness"] == 1.0


def test_trend_recovers_a_known_slope_and_reports_flat_series():
    rng = np.random.default_rng(3)
    days = list(range(90))
    fit = S.series_trend(days, [60 + 0.1 * d + rng.normal(0, 0.3) for d in days])
    assert fit["direction"] == "rising" and fit["ci95"][0] < 3.0 < fit["ci95"][1]
    noise = S.series_trend(days, list(60 + rng.normal(0, 0.3, 90)))
    assert noise["direction"] == "no clear trend" and noise["n_eff"] <= 90
    assert S.series_trend([1, 2, 3], [1, 2, 3]) is None  # too few days


def test_stage_boundaries():
    assert stage_for(0).key == "launch_adaptation" and stage_for(14).key == "launch_adaptation"
    assert stage_for(15).key == "early_transit" and stage_for(400).key == "arrival"
    assert all(a.last_day + 1 == b.first_day for a, b in zip(STAGES, STAGES[1:]))


async def test_twin_covers_every_mission_day_with_labelled_basis(p5):
    twin, settings = p5.app.state.twin, p5.app.state.settings
    rows = await twin.days("AST-01")
    expected = (p5.clock.now.date() - settings.mission_start_date).days + 1
    assert len(rows) == expected
    assert {r.basis for r in rows} == {"stored", "regenerated"}
    assert rows[0].basis == "regenerated" and rows[-1].basis == "stored" and not rows[-1].complete
    assert all(r.complete for r in rows[:-1])
    assert all(r.stage == stage_for(r.mission_day).key for r in rows)


async def test_stored_day_summary_matches_the_stored_samples(p5):
    twin = p5.app.state.twin
    row = next(r for r in await twin.days("AST-02") if r.basis == "stored" and r.complete)
    start, end = day_bounds(row.day)
    async with p5.app.state.session_factory() as s:
        n, mean = (await s.execute(select(func.count(), func.avg(VitalSampleRow.heart_rate)).where(
            VitalSampleRow.astronaut_id == "AST-02", VitalSampleRow.ts >= start, VitalSampleRow.ts < end))).one()
    assert row.metrics["heart_rate"]["n"] == n == row.coverage["samples"]
    assert abs(row.metrics["heart_rate"]["mean"] - mean) < 0.06


async def test_regenerated_days_are_deterministic(p5):
    twin = p5.app.state.twin
    first = (await twin.days("AST-03"))[0]
    async with p5.app.state.session_factory() as s:
        again = await twin.compute_day(s, "AST-03", first.day, p5.clock.now)
    assert again["basis"] == "regenerated"
    assert again["metrics"] == first.metrics and again["sleep"] == first.sleep


async def test_twin_updates_as_new_measurements_arrive(p5):
    twin = p5.app.state.twin
    before = (await twin.days("AST-04"))[-1]
    await p5.tick(30)
    p5.monitor.settings.persist_every_ticks = 1
    await p5.tick(5)
    await twin.refresh(full=False, now=p5.clock.now)
    after = (await twin.days("AST-04"))[-1]
    assert after.day == before.day and after.coverage["samples"] > before.coverage["samples"]
    assert after.computed_at > before.computed_at


async def test_twin_api_profile_timeline_trends_and_stages(p5):
    c = p5.client
    prof = (await c.get("/api/twin/AST-01")).json()
    assert prof["data_source"] == "simulated" and "not reproduce the complete biological state" in prof["disclaimer"]
    assert {x["key"] for x in prof["categories"]} >= {"simulated", "regenerated", "derived", "model"}
    hr = next(x for x in prof["resting_comparison"] if x["metric"] == "heart_rate")
    assert hr["configured"]["category"] == "configured" and hr["early_mission"]["value"] is not None
    assert prof["coverage"]["days_regenerated"] > 0 and prof["coverage"]["days_stored"] >= 2
    tl = (await c.get("/api/twin/AST-01/timeline", params={"days": 5})).json()
    assert len(tl["days"]) == 5 and all(d["category"] in ("simulated", "regenerated") for d in tl["days"])
    tr = (await c.get("/api/twin/AST-01/trends", params={"metric": "dose_msv"})).json()
    assert tr["cumulative"][-1]["value"] >= tr["points"][0]["value"]
    st = (await c.get("/api/twin/AST-01/stages")).json()
    assert [s["key"] for s in st["stages"]] == ["launch_adaptation", "early_transit"]
    assert "vs_first_stage" in st["stages"][1]["metrics"]["heart_rate"]
    assert any("adaptation" in n for n in st["notes"])
    assert (await c.get("/api/twin/AST-99")).status_code == 404
    assert (await c.get("/api/twin/AST-01/trends", params={"metric": "nonsense"})).status_code == 422


async def test_twin_rows_are_unique_per_day(p5):
    await p5.app.state.twin.refresh(full=True)
    async with p5.app.state.session_factory() as s:
        dupes = (await s.execute(select(TwinDailyRow.astronaut_id, TwinDailyRow.day, func.count())
                                 .group_by(TwinDailyRow.astronaut_id, TwinDailyRow.day)
                                 .having(func.count() > 1))).all()
    assert dupes == []


async def test_mission_overview_aggregates_and_filters(p5):
    await p5.client.post("/api/simulation/events", json={"scenario": "desaturation", "astronaut_id": "AST-02",
                                                         "intensity": 1.3, "duration_seconds": 900})
    await p5.tick(200)
    ov = (await p5.client.get("/api/overview", params={"period": "7d"})).json()
    assert len(ov["crew"]) == 4 and len(ov["alert_history"]) == 8
    ast2 = next(c for c in ov["crew"] if c["astronaut_id"] == "AST-02")
    assert ast2["alerts_in_period"].get("critical", 0) >= 1 and ast2["systems"]["respiratory"] == "marked_deviation"
    kinds = {s["kind"] for s in ov["summary"]["statements"]}
    assert {"derived", "data", "nasa"} <= kinds
    total = sum(d["critical"] + d["caution"] + d["advisory"] for d in ov["alert_history"])
    assert any(f"{total} alert(s)" in s["text"] for s in ov["summary"]["statements"])
    one = (await p5.client.get("/api/overview", params={"period": "24h", "astronaut_id": "AST-02"})).json()
    assert [c["astronaut_id"] for c in one["crew"]] == ["AST-02"]
    assert all(a["astronaut_id"] == "AST-02" for a in one["active_alerts"])
    assert (await p5.client.get("/api/overview", params={"astronaut_id": "AST-99"})).status_code == 404
