from __future__ import annotations

from datetime import timedelta
from statistics import mean

import pytest

from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW, CREW_BY_ID
from app.simulator.scenarios import Scenario
from app.simulator.schedule import EXERCISE, SLEEP, activity_at, exercise_plan, night_plan
from tests.conftest import T0


def run(engine: SimulationEngine, seconds: int, start=T0):
    t = start
    results = []
    for _ in range(seconds):
        t += timedelta(seconds=1)
        results.append(engine.step(t))
    return results


def series(results, astronaut_id: str, metric: str) -> list[float]:
    return [
        next(r for r in res.readings if r.astronaut_id == astronaut_id).value(metric) for res in results
    ]


def test_same_seed_reproduces_identical_data():
    a = SimulationEngine(CREW, seed=11, random_events_per_hour=0)
    b = SimulationEngine(CREW, seed=11, random_events_per_hour=0)
    ra, rb = run(a, 30), run(b, 30)
    assert [r.readings for r in ra] == [r.readings for r in rb]
    assert [c.values_mv for c in ra[-1].ecg] == [c.values_mv for c in rb[-1].ecg]


def test_every_reading_is_labelled_and_covers_whole_crew(engine):
    res = run(engine, 3)[-1]
    assert {r.astronaut_id for r in res.readings} == {p.id for p in CREW}
    assert all(r.ts == res.ts for r in res.readings)


@pytest.mark.parametrize(
    ("metric", "lo", "hi"),
    [
        ("heart_rate", 45, 100),
        ("spo2", 95, 100),
        ("systolic", 95, 140),
        ("diastolic", 55, 95),
        ("temperature_c", 36.0, 37.6),
        ("respiratory_rate", 9, 22),
    ],
)
def test_normal_variation_stays_in_physiological_range(engine, metric, lo, hi):
    results = run(engine, 600)
    for profile in CREW:
        values = series(results, profile.id, metric)
        assert lo <= min(values) and max(values) <= hi, (profile.id, min(values), max(values))


def test_values_vary_but_are_not_white_noise(engine):
    hr = series(run(engine, 300), "AST-01", "heart_rate")
    steps = [abs(b - a) for a, b in zip(hr, hr[1:])]
    assert max(hr) - min(hr) > 1.0  # it moves
    assert mean(steps) < 1.5  # but smoothly, like a real trend


def test_sleep_lowers_and_exercise_raises_heart_rate():
    profile = CREW_BY_ID["AST-01"]
    seed = 7
    night = night_plan(profile, T0.date(), seed)
    ex = exercise_plan(profile, T0.date(), seed)
    asleep_at = night.start + timedelta(hours=2)
    exercising_at = ex.start + timedelta(minutes=30)
    assert activity_at(profile, asleep_at, seed)[0] == SLEEP
    assert activity_at(profile, exercising_at, seed)[0] == EXERCISE

    def avg_hr(at):
        e = SimulationEngine([profile], seed=seed, random_events_per_hour=0)
        return mean(series(run(e, 120, at), profile.id, "heart_rate")[60:])

    awake = avg_hr(T0)
    assert avg_hr(asleep_at) < awake - 4
    assert avg_hr(exercising_at) > awake + 30


@pytest.mark.parametrize(
    ("scenario", "metric", "direction", "min_change"),
    [
        (Scenario.TACHYCARDIA, "heart_rate", 1, 45),
        (Scenario.BRADYCARDIA, "heart_rate", -1, 15),
        (Scenario.DESATURATION, "spo2", -1, 7),
        (Scenario.ELEVATED_TEMPERATURE, "temperature_c", 1, 1.2),
        (Scenario.ABNORMAL_RESPIRATORY_RATE, "respiratory_rate", 1, 12),
    ],
)
def test_scenarios_move_the_expected_signal(engine, scenario, metric, direction, min_change):
    baseline = mean(series(run(engine, 30), "AST-03", metric))
    start = T0 + timedelta(seconds=30)
    active = engine.start_scenario(scenario, "AST-03", start, duration_s=600)
    plateau = series(run(engine, 200, start), "AST-03", metric)[-30:]
    assert direction * (mean(plateau) - baseline) >= min_change
    # Other crew members are unaffected and readings carry the scenario label.
    last = engine.step(start + timedelta(seconds=201))
    labelled = {r.astronaut_id: r.scenario for r in last.readings}
    assert labelled["AST-03"] == scenario.value
    assert labelled["AST-01"] is None
    assert active.id in engine.scenarios


def test_irregular_rhythm_is_detected_from_ecg_intervals(engine):
    engine.start_scenario(Scenario.IRREGULAR_RHYTHM, "AST-02", T0, duration_s=600)
    results = run(engine, 120)
    reading = next(r for r in results[-1].readings if r.astronaut_id == "AST-02")
    others = [r for r in results[-1].readings if r.astronaut_id != "AST-02"]
    assert reading.rhythm == "irregular"
    assert all(r.rhythm == "regular" for r in others)


def test_solar_particle_event_is_crew_wide_and_raises_dose(engine):
    quiet = run(engine, 5)[-1].dose_msv
    start = T0 + timedelta(seconds=5)
    spe = engine.start_scenario(Scenario.SOLAR_PARTICLE_EVENT, "AST-01", start, duration_s=600)
    assert spe.astronaut_id is None  # crew-wide regardless of the requested target
    storm = run(engine, 120, start)[-1].dose_msv
    for aid in quiet:
        assert storm[aid] > 10 * quiet[aid]


def test_scenario_ends_and_is_reported_once(engine):
    active = engine.start_scenario(Scenario.TACHYCARDIA, "AST-01", T0, duration_s=30)
    results = run(engine, 40)
    ended = [s.id for r in results for s in r.ended]
    assert ended == [active.id]
    assert active.id not in engine.scenarios


def test_cancelled_scenario_fades_out_quickly(engine):
    engine.start_scenario(Scenario.TACHYCARDIA, "AST-01", T0, duration_s=900)
    run(engine, 150)
    sid = next(iter(engine.scenarios))
    cancel_at = T0 + timedelta(seconds=150)
    assert engine.cancel_scenario(sid, cancel_at) is not None
    after = series(run(engine, 60, cancel_at), "AST-01", "heart_rate")
    assert mean(after[-10:]) < 100
    assert engine.cancel_scenario(sid, cancel_at) is None  # already gone


def test_random_scenarios_fire_at_configured_rate():
    engine = SimulationEngine(CREW, seed=3, random_events_per_hour=3600)  # ~1 per second
    results = run(engine, 20)
    assert any(r.started for r in results)
    assert all(s.triggered_by == "random" for r in results for s in r.started)


def test_history_backfill_is_deterministic_and_spaced(engine):
    profile = CREW_BY_ID["AST-04"]
    start, end = T0 - timedelta(hours=6), T0
    scenarios = engine.historical_scenarios(start, end)
    a = list(engine.history(profile, start, end, timedelta(minutes=5), scenarios))
    b = list(engine.history(profile, start, end, timedelta(minutes=5), scenarios))
    assert a == b
    assert len(a) == 72
    assert all((y.ts - x.ts) == timedelta(minutes=5) for x, y in zip(a, a[1:]))
