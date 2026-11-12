"""Labelled synthetic dataset for training and evaluating the AI models.

Built on the ASTRA-MED simulator (same physiology, schedules and crew) with known ground truth:

* sudden events: the simulator's test scenarios (tachycardia-like, bradycardia-like,
  desaturation, elevated temperature, abnormal respiratory rate, irregular rhythm), lasting
  25-150 minutes, at full or *subtle* intensity;
* gradual events: slow drifts that ramp over 6-24 hours, hold 2-8 hours, then recover;
* slow physiological variability (two AR(1) processes, ~3 h and ~24 h), so the series are not
  trivially periodic and forecasting is a real task;
* data defects that are *not* anomalies: random missing values, sensor dropouts, and
  physiologically implausible artefact spikes.

Everything is driven by one seed, so the dataset is reproducible bit for bit. It is synthetic:
models that do well here have learned the simulator, not human physiology.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from app.ai.signals import SIGNALS
from app.simulator.engine import SimulationEngine
from app.simulator.profiles import CREW, AstronautProfile
from app.simulator.scenarios import ActiveScenario, Scenario
from app.simulator.seeding import rng_for

SUDDEN_TYPES: tuple[Scenario, ...] = (
    Scenario.TACHYCARDIA,
    Scenario.BRADYCARDIA,
    Scenario.DESATURATION,
    Scenario.ELEVATED_TEMPERATURE,
    Scenario.ABNORMAL_RESPIRATORY_RATE,
    Scenario.IRREGULAR_RHYTHM,
)

# Full-intensity effect of each gradual drift (added on top of normal physiology).
GRADUAL_TYPES: dict[str, dict[str, float]] = {
    "gradual_hr_rise": {"heart_rate": 18.0, "respiratory_rate": 2.5, "temperature_c": 0.35},
    "gradual_desaturation": {"spo2": -4.5, "respiratory_rate": 3.5, "heart_rate": 7.0},
    "gradual_temperature_rise": {"temperature_c": 1.1, "heart_rate": 11.0, "respiratory_rate": 2.0},
    "gradual_bp_rise": {"systolic": 20.0, "diastolic": 11.0, "heart_rate": 4.0},
}

# (fast AR sigma, slow AR sigma) per signal: stationary standard deviations.
SLOW_VARIABILITY: dict[str, tuple[float, float]] = {
    "heart_rate": (2.5, 1.5),
    "spo2": (0.25, 0.15),
    "systolic": (3.0, 2.0),
    "diastolic": (2.0, 1.2),
    "temperature_c": (0.07, 0.05),
    "respiratory_rate": (0.5, 0.3),
}

ARTEFACT_VALUES: dict[str, tuple[float, ...]] = {
    "heart_rate": (0.0, 245.0),
    "spo2": (35.0,),
    "temperature_c": (29.5, 44.0),
    "respiratory_rate": (0.0, 75.0),
}


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = 7
    days: int = 120
    start: str = "2026-01-05"
    interval_minutes: int = 5
    crew: tuple[str, ...] = tuple(p.id for p in CREW)
    sudden_events_per_day: float = 0.5
    gradual_events_per_week: float = 0.7
    subtle_fraction: float = 0.45
    missing_rate: float = 0.02
    dropouts_per_week: float = 0.7
    artefact_rate: float = 0.0008
    slow_variability: bool = True
    label_level: float = 0.3  # an event window is "anomalous" once its effect reaches 30%

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:12]


@dataclass
class Event:
    id: str
    astronaut_id: str
    type: str
    kind: str  # "sudden" | "gradual"
    start: datetime
    end: datetime
    intensity: float
    subtle: bool
    ramp_hours: float = 0.0
    hold_hours: float = 0.0
    effects: dict[str, float] = field(default_factory=dict)

    def level(self, ts: np.ndarray) -> np.ndarray:
        """Effect level 0..intensity at each timestamp (seconds since epoch)."""
        t0, t1 = self.start.timestamp(), self.end.timestamp()
        if self.kind == "sudden":
            scenario = ActiveScenario(self.id, Scenario(self.type), self.astronaut_id, 1.0,
                                      self.start, self.end, "random")
            env = np.zeros(len(ts))
            inside = np.flatnonzero((ts >= t0) & (ts < t1))
            env[inside] = [scenario.envelope(datetime.fromtimestamp(ts[i], tz=UTC)) for i in inside]
            return env * self.intensity
        ramp = self.ramp_hours * 3600
        hold_end = t0 + ramp + self.hold_hours * 3600
        env = np.where(ts < t0, 0.0, np.where(ts < t0 + ramp, (ts - t0) / ramp, 1.0))
        recovery = np.clip(1 - (ts - hold_end) / max(1.0, t1 - hold_end), 0, 1)
        env = np.where(ts >= hold_end, recovery, env)
        env = np.where(ts >= t1, 0.0, env)
        return env * self.intensity

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        return d


def _events(cfg: SyntheticConfig, profile: AstronautProfile, start: datetime, end: datetime) -> list[Event]:
    rng = rng_for(cfg.seed, "dataset-events", profile.id)
    span_days = (end - start).total_seconds() / 86400
    events: list[Event] = []
    for i in range(rng.poisson(cfg.sudden_events_per_day * span_days)):
        kind = SUDDEN_TYPES[int(rng.integers(len(SUDDEN_TYPES)))]
        subtle = bool(rng.random() < cfg.subtle_fraction)
        begins = start + timedelta(seconds=float(rng.uniform(0, span_days * 86400)))
        events.append(Event(
            id=f"{profile.id}-s{i}", astronaut_id=profile.id, type=kind.value, kind="sudden",
            start=begins, end=begins + timedelta(minutes=float(rng.uniform(25, 150))),
            intensity=float(rng.uniform(0.35, 0.6) if subtle else rng.uniform(0.75, 1.2)), subtle=subtle,
        ))
    for i in range(rng.poisson(cfg.gradual_events_per_week * span_days / 7)):
        kind = list(GRADUAL_TYPES)[int(rng.integers(len(GRADUAL_TYPES)))]
        subtle = bool(rng.random() < cfg.subtle_fraction)
        ramp, hold = float(rng.uniform(6, 24)), float(rng.uniform(2, 8))
        begins = start + timedelta(seconds=float(rng.uniform(0, max(1, span_days - 2) * 86400)))
        events.append(Event(
            id=f"{profile.id}-g{i}", astronaut_id=profile.id, type=kind, kind="gradual",
            start=begins, end=begins + timedelta(hours=ramp + hold + 3),
            intensity=float(rng.uniform(0.4, 0.65) if subtle else rng.uniform(0.8, 1.15)), subtle=subtle,
            ramp_hours=ramp, hold_hours=hold, effects=GRADUAL_TYPES[kind],
        ))
    return sorted(events, key=lambda e: e.start)


def _ar1(n: int, sigma: float, tau_steps: float, rng: np.random.Generator) -> np.ndarray:
    phi = np.exp(-1.0 / tau_steps)
    noise = rng.normal(0, sigma * np.sqrt(1 - phi * phi), n)
    out = np.empty(n)
    out[0] = rng.normal(0, sigma)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + noise[i]
    return out


def generate(cfg: SyntheticConfig | None = None) -> tuple[pd.DataFrame, list[Event]]:
    """Return (samples, events). Samples: one row per astronaut per interval, long format."""
    cfg = cfg or SyntheticConfig()
    start = datetime.fromisoformat(cfg.start).replace(tzinfo=UTC)
    end = start + timedelta(days=cfg.days)
    interval = timedelta(minutes=cfg.interval_minutes)
    engine = SimulationEngine(CREW, seed=cfg.seed, random_events_per_hour=0)
    frames, all_events = [], []

    for profile in CREW:
        if profile.id not in cfg.crew:
            continue
        events = _events(cfg, profile, start, end)
        all_events += events
        sudden = [
            ActiveScenario(e.id, Scenario(e.type), profile.id, e.intensity, e.start, e.end, "random")
            for e in events if e.kind == "sudden"
        ]
        rows = list(engine.history(profile, start, end, interval, sudden))
        df = pd.DataFrame(
            {
                "ts": [r.ts for r in rows],
                **{s: [getattr(r, s) for r in rows] for s in SIGNALS},
                "activity_state": [r.activity_state for r in rows],
                "activity_met": [r.activity_met for r in rows],
            }
        )
        ts_sec = np.array([t.timestamp() for t in df["ts"]])
        rng = rng_for(cfg.seed, "dataset-noise", profile.id)

        if cfg.slow_variability:
            steps_per_hour = 60 / cfg.interval_minutes
            for s, (fast, slow) in SLOW_VARIABILITY.items():
                df[s] += _ar1(len(df), fast, 3 * steps_per_hour, rng) + _ar1(len(df), slow, 24 * steps_per_hour, rng)

        level = np.zeros(len(df))
        event_id = np.full(len(df), None, dtype=object)
        event_type = np.full(len(df), None, dtype=object)
        event_kind = np.full(len(df), None, dtype=object)
        for e in events:
            lv = e.level(ts_sec)
            if e.kind == "gradual":
                for s, delta in e.effects.items():
                    df[s] += delta * lv
            stronger = lv > level
            level = np.where(stronger, lv, level)
            event_id = np.where(stronger & (lv > 0), e.id, event_id)
            event_type = np.where(stronger & (lv > 0), e.type, event_type)
            event_kind = np.where(stronger & (lv > 0), e.kind, event_kind)

        df["temperature_c"] = df["temperature_c"].round(2)
        for s in ("heart_rate", "spo2", "respiratory_rate"):
            df[s] = df[s].round(1)
        df["spo2"] = df["spo2"].clip(upper=100.0)
        df[["systolic", "diastolic"]] = df[["systolic", "diastolic"]].round(0)

        df["event_level"] = level
        df["event_id"], df["event_type"], df["event_kind"] = event_id, event_type, event_kind
        df["label"] = level >= cfg.label_level

        # Data defects (not anomalies).
        for s in SIGNALS:
            df.loc[rng.random(len(df)) < cfg.missing_rate, s] = np.nan
        steps_per_minute = 1 / cfg.interval_minutes
        for _ in range(rng.poisson(cfg.dropouts_per_week * cfg.days / 7)):
            i0 = int(rng.integers(len(df)))
            length = int(rng.uniform(30, 180) * steps_per_minute)
            df.loc[i0:i0 + length, list(SIGNALS)] = np.nan
        artefact = rng.random(len(df)) < cfg.artefact_rate
        for i in np.flatnonzero(artefact):
            s = list(ARTEFACT_VALUES)[int(rng.integers(len(ARTEFACT_VALUES)))]
            df.loc[i, s] = float(rng.choice(ARTEFACT_VALUES[s]))
        df["artefact"] = artefact

        df.insert(0, "astronaut_id", profile.id)
        frames.append(df)

    data = pd.concat(frames, ignore_index=True)
    data["ts"] = pd.to_datetime(data["ts"], utc=True)
    data["data_source"] = "simulated"
    return data, all_events


@dataclass(frozen=True)
class Split:
    train_end: pd.Timestamp
    val_end: pd.Timestamp
    end: pd.Timestamp

    def name(self, ts: pd.Series | pd.DatetimeIndex) -> np.ndarray:
        ts = pd.DatetimeIndex(ts)
        return np.where(ts < self.train_end, "train", np.where(ts < self.val_end, "val", "test"))

    def to_dict(self) -> dict[str, str]:
        return {"train_end": self.train_end.isoformat(), "val_end": self.val_end.isoformat(), "end": self.end.isoformat()}


def chronological_split(cfg: SyntheticConfig, train_frac: float = 0.6, val_frac: float = 0.2) -> Split:
    """Day-aligned chronological boundaries shared by every crew member (no shuffling)."""
    start = pd.Timestamp(cfg.start, tz="UTC")
    train_days = round(cfg.days * train_frac)
    val_days = round(cfg.days * val_frac)
    return Split(
        train_end=start + pd.Timedelta(days=train_days),
        val_end=start + pd.Timedelta(days=train_days + val_days),
        end=start + pd.Timedelta(days=cfg.days),
    )
