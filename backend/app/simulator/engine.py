"""Simulation engine: advances every crew member's physiology one tick at a time.

The engine is pure Python with no I/O. The monitoring service drives it, persists what it
produces and broadcasts it. Every reading it emits is synthetic.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import numpy as np

from app.simulator.ecg import EcgGenerator, classify_rhythm
from app.simulator.physiology import (
    LAG_SECONDS,
    METRICS,
    NOISE_SIGMA,
    clamp_metric,
    target_vitals,
)
from app.simulator.profiles import AstronautProfile
from app.simulator.radiation import dose_rate_msv_per_second
from app.simulator.scenarios import SCENARIOS, ActiveScenario, Scenario
from app.simulator.schedule import activity_at
from app.simulator.seeding import rng_for

NOISE_TAU_S = 25.0

RANDOM_SCENARIO_WEIGHTS: dict[Scenario, float] = {
    Scenario.TACHYCARDIA: 0.22,
    Scenario.BRADYCARDIA: 0.12,
    Scenario.DESATURATION: 0.2,
    Scenario.ELEVATED_TEMPERATURE: 0.1,
    Scenario.ABNORMAL_RESPIRATORY_RATE: 0.14,
    Scenario.IRREGULAR_RHYTHM: 0.17,
    Scenario.SOLAR_PARTICLE_EVENT: 0.05,
}


@dataclass
class VitalReading:
    astronaut_id: str
    ts: datetime
    heart_rate: float
    spo2: float
    systolic: float
    diastolic: float
    temperature_c: float
    respiratory_rate: float
    activity_state: str
    activity_met: float
    rhythm: str
    hrv_rmssd_ms: float | None
    scenario: str | None

    def value(self, metric: str) -> float:
        return float(getattr(self, metric))


@dataclass
class EcgChunk:
    astronaut_id: str
    start: datetime
    sample_rate_hz: int
    values_mv: list[float]


@dataclass
class TickResult:
    ts: datetime
    readings: list[VitalReading]
    ecg: list[EcgChunk]
    started: list[ActiveScenario] = field(default_factory=list)
    ended: list[ActiveScenario] = field(default_factory=list)
    dose_msv: dict[str, float] = field(default_factory=dict)


@dataclass
class _LiveState:
    current: dict[str, float]
    noise: dict[str, float]
    ecg: EcgGenerator
    ecg_cursor: float | None = None


def _round(metric: str, value: float) -> float:
    if metric in ("systolic", "diastolic"):
        return float(round(value))
    if metric == "temperature_c":
        return round(value, 2)
    return round(value, 1)


class SimulationEngine:
    def __init__(
        self,
        profiles: Sequence[AstronautProfile],
        *,
        seed: int,
        ecg_sample_rate_hz: int = 125,
        random_events_per_hour: float = 6.0,
        default_tick_seconds: float = 1.0,
    ) -> None:
        self.profiles: dict[str, AstronautProfile] = {p.id: p for p in profiles}
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.ecg_fs = ecg_sample_rate_hz
        self.random_events_per_hour = random_events_per_hour
        self.default_tick_seconds = default_tick_seconds
        self.scenarios: dict[str, ActiveScenario] = {}
        self.last_tick: datetime | None = None
        self._live: dict[str, _LiveState] = {}

    # ------------------------------------------------------------------ scenarios ----
    def start_scenario(
        self,
        scenario: Scenario,
        astronaut_id: str | None,
        now: datetime,
        *,
        intensity: float = 1.0,
        duration_s: int | None = None,
        triggered_by: str = "operator",
    ) -> ActiveScenario:
        spec = SCENARIOS[scenario]
        if spec.crew_wide:
            astronaut_id = None
        elif astronaut_id not in self.profiles:
            raise KeyError(astronaut_id)
        active = ActiveScenario(
            id=uuid4().hex[:12],
            scenario=scenario,
            astronaut_id=astronaut_id,
            intensity=intensity,
            started_at=now,
            ends_at=now + timedelta(seconds=duration_s or spec.default_duration_s),
            triggered_by=triggered_by,
        )
        self.scenarios[active.id] = active
        return active

    def cancel_scenario(self, scenario_id: str, now: datetime) -> ActiveScenario | None:
        active = self.scenarios.get(scenario_id)
        if active is None or not active.is_active(now) or active.cancelled_at is not None:
            return None
        active.cancelled_at = now
        return active

    def active_scenarios(self, now: datetime) -> list[ActiveScenario]:
        return [s for s in self.scenarios.values() if s.is_active(now)]

    def _effects(
        self, astronaut_id: str, t: datetime, scenarios: Sequence[ActiveScenario]
    ) -> tuple[dict[str, float], bool, float, str | None]:
        deltas: dict[str, float] = {}
        irregular = False
        dose_multiplier = 1.0
        label: str | None = None
        for s in scenarios:
            if not s.affects(astronaut_id):
                continue
            level = s.envelope(t)
            if level <= 0:
                continue
            spec = s.spec
            for metric, delta in spec.effects.items():
                deltas[metric] = deltas.get(metric, 0.0) + delta * s.intensity * level
            if spec.irregular_rhythm and level > 0.35:
                irregular = True
            dose_multiplier = max(dose_multiplier, 1 + (spec.dose_rate_multiplier - 1) * level)
            label = label or s.scenario.value
        return deltas, irregular, dose_multiplier, label

    def _maybe_random_scenario(self, now: datetime, dt: float) -> list[ActiveScenario]:
        if self.random_events_per_hour <= 0:
            return []
        if self.rng.random() >= self.random_events_per_hour * dt / 3600:
            return []
        busy = {s.astronaut_id for s in self.active_scenarios(now)}
        if None in busy:
            return []
        free = [pid for pid in self.profiles if pid not in busy]
        if not free:
            return []
        keys = list(RANDOM_SCENARIO_WEIGHTS)
        weights = np.array([RANDOM_SCENARIO_WEIGHTS[k] for k in keys])
        scenario = keys[int(self.rng.choice(len(keys), p=weights / weights.sum()))]
        if SCENARIOS[scenario].crew_wide and busy:
            return []
        astronaut_id = free[int(self.rng.integers(len(free)))]
        base = SCENARIOS[scenario].default_duration_s
        return [
            self.start_scenario(
                scenario,
                astronaut_id,
                now,
                intensity=float(self.rng.uniform(0.8, 1.15)),
                duration_s=int(base * self.rng.uniform(0.7, 1.4)),
                triggered_by="random",
            )
        ]

    # ------------------------------------------------------------------- live ticks ----
    def _init_live(self, profile: AstronautProfile, now: datetime) -> _LiveState:
        state, met = activity_at(profile, now, self.seed)
        target = target_vitals(profile, now, state, met)
        return _LiveState(
            current=dict(target),
            noise={m: 0.0 for m in METRICS},
            ecg=EcgGenerator(
                self.ecg_fs, rng_for(self.seed, "ecg", profile.id), profile.baseline.hrv_sdnn_ms
            ),
        )

    def step(self, now: datetime) -> TickResult:
        dt = (
            (now - self.last_tick).total_seconds()
            if self.last_tick is not None
            else self.default_tick_seconds
        )
        dt = min(10.0, max(0.05, dt))
        started = self._maybe_random_scenario(now, dt)
        active = self.active_scenarios(now)

        result = TickResult(ts=now, readings=[], ecg=[], started=started)
        for profile in self.profiles.values():
            reading, chunk, dose = self._step_one(profile, now, dt, active)
            result.readings.append(reading)
            if chunk is not None:
                result.ecg.append(chunk)
            result.dose_msv[profile.id] = dose

        for s in list(self.scenarios.values()):
            if not s.is_active(now):
                result.ended.append(s)
                del self.scenarios[s.id]
        self.last_tick = now
        return result

    def _step_one(
        self,
        profile: AstronautProfile,
        now: datetime,
        dt: float,
        active: Sequence[ActiveScenario],
    ) -> tuple[VitalReading, EcgChunk | None, float]:
        live = self._live.get(profile.id)
        if live is None:
            live = self._live[profile.id] = self._init_live(profile, now)

        state, met = activity_at(profile, now, self.seed)
        target = target_vitals(profile, now, state, met)
        deltas, irregular, dose_multiplier, label = self._effects(profile.id, now, active)

        values: dict[str, float] = {}
        for m in METRICS:
            live.current[m] += (target[m] - live.current[m]) * (1 - math.exp(-dt / LAG_SECONDS[m]))
            sigma = NOISE_SIGMA[m]
            live.noise[m] += -live.noise[m] * dt / NOISE_TAU_S + sigma * math.sqrt(
                2 * dt / NOISE_TAU_S
            ) * float(self.rng.normal())
            values[m] = clamp_metric(m, live.current[m] + live.noise[m] + deltas.get(m, 0.0))
        values["diastolic"] = min(values["diastolic"], values["systolic"] - 25)

        # Render ECG contiguously from where the previous chunk ended.
        now_s = now.timestamp()
        if live.ecg_cursor is None or now_s - live.ecg_cursor > 5 or now_s <= live.ecg_cursor:
            live.ecg_cursor = now_s - dt
        n = int(round((now_s - live.ecg_cursor) * self.ecg_fs))
        chunk = None
        if n > 0:
            start = live.ecg_cursor
            samples = live.ecg.render(
                start, n / self.ecg_fs, values["heart_rate"], irregular, values["respiratory_rate"]
            )
            live.ecg_cursor = start + n / self.ecg_fs
            chunk = EcgChunk(
                profile.id, datetime.fromtimestamp(start, tz=UTC), self.ecg_fs, samples
            )
        rmssd, irregularity = live.ecg.rhythm_features()

        reading = VitalReading(
            astronaut_id=profile.id,
            ts=now,
            **{m: _round(m, v) for m, v in values.items()},
            activity_state=state,
            activity_met=round(met, 2),
            rhythm=classify_rhythm(irregularity),
            hrv_rmssd_ms=round(rmssd, 1),
            scenario=label,
        )
        dose = dose_rate_msv_per_second(profile, dose_multiplier) * dt
        return reading, chunk, dose

    # -------------------------------------------------------------------- history ----
    def historical_scenarios(self, start: datetime, end: datetime) -> list[ActiveScenario]:
        """Deterministic past events so a fresh database already has a story to show."""
        events: list[ActiveScenario] = []
        candidates = [s for s in RANDOM_SCENARIO_WEIGHTS if not SCENARIOS[s].crew_wide]
        day: date = start.date()
        while day <= end.date():
            for pid in self.profiles:
                rng = rng_for(self.seed, "history-event", pid, day.isoformat())
                if rng.random() >= 0.4:
                    continue
                scenario = candidates[int(rng.integers(len(candidates)))]
                begins = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(
                    seconds=float(rng.uniform(0, 86400))
                )
                ends = begins + timedelta(seconds=float(rng.uniform(420, 1200)))
                if start <= begins and ends < end:
                    events.append(
                        ActiveScenario(
                            id=f"h-{pid}-{day.isoformat()}",
                            scenario=scenario,
                            astronaut_id=pid,
                            intensity=float(rng.uniform(0.85, 1.15)),
                            started_at=begins,
                            ends_at=ends,
                            triggered_by="random",
                        )
                    )
            day += timedelta(days=1)
        return events

    def reading_at(
        self,
        profile: AstronautProfile,
        t: datetime,
        scenarios: Sequence[ActiveScenario],
        rng: np.random.Generator,
    ) -> VitalReading:
        """Equilibrium reading (no lag) used for backfilled history."""
        state, met = activity_at(profile, t, self.seed)
        target = target_vitals(profile, t, state, met)
        deltas, irregular, _, label = self._effects(profile.id, t, scenarios)
        values = {
            m: clamp_metric(m, target[m] + deltas.get(m, 0.0) + float(rng.normal(0, NOISE_SIGMA[m])))
            for m in METRICS
        }
        values["diastolic"] = min(values["diastolic"], values["systolic"] - 25)
        return VitalReading(
            astronaut_id=profile.id,
            ts=t,
            **{m: _round(m, v) for m, v in values.items()},
            activity_state=state,
            activity_met=round(met, 2),
            rhythm="irregular" if irregular else "regular",
            hrv_rmssd_ms=None,
            scenario=label,
        )

    def history(
        self,
        profile: AstronautProfile,
        start: datetime,
        end: datetime,
        interval: timedelta,
        scenarios: Sequence[ActiveScenario],
    ) -> Iterator[VitalReading]:
        rng = rng_for(self.seed, "history", profile.id, start.isoformat())
        relevant = [s for s in scenarios if s.affects(profile.id)]
        t = start
        while t < end:
            yield self.reading_at(profile, t, relevant, rng)
            t += interval
