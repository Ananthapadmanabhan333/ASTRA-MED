"""Six-system health assessment built from actual inputs.

For each system the engine lists the inputs it used (value, reference, z against the crew member's
own baseline, data category and source), derives a status from configurable statistical bands,
attaches the Phase 3 model outputs that concern the system, and writes an explanation only from
those inputs. Cross-system patterns are co-deviations of systems listed in the config; they describe
co-occurrence, never a cause.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.signals import SIGNALS
from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.db.models import SpaceWeatherEventRow
from app.medical import DECISION_SUPPORT_DISCLAIMER
from app.repositories import vitals as vitals_repo
from app.services.monitoring import MonitoringService
from app.simulator.habitat import habitat_at
from app.simulator.schedule import sleep_window_at
from app.twin import summary as S
from app.twin.service import TwinService

CONFIG_PATH = Path(__file__).with_name("multisystem_config.json")
ALERT_SYSTEM = {
    "heart_rate": "cardiovascular", "systolic": "cardiovascular", "diastolic": "cardiovascular",
    "rhythm": "cardiovascular", "spo2": "respiratory", "respiratory_rate": "respiratory",
    "temperature_c": "thermoregulation",
}
SIGNAL_SYSTEM = {"heart_rate": "cardiovascular", "systolic": "cardiovascular", "diastolic": "cardiovascular",
                 "spo2": "respiratory", "respiratory_rate": "respiratory", "temperature_c": "thermoregulation"}
STATUS_RANK = {"insufficient_data": -1, "info": -1, "within_baseline": 0, "deviation": 1, "marked_deviation": 2}
CACHE_S = 15.0
CURRENT_WINDOW = timedelta(minutes=5)


@dataclass(frozen=True)
class MultisystemConfig:
    z_deviation: float
    z_marked: float
    sleep_reference_nights: int
    recovery_reference_days: int
    space_weather_lookback_hours: int
    exercise_shortfall_fraction: float
    systems: dict[str, dict[str, Any]]
    patterns: list[dict[str, Any]]

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> MultisystemConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("_comment", None)
        return cls(**raw)


def feature(key: str, label: str, value: float | None, unit: str, *, reference: float | None = None,
            z: float | None = None, category: str, source: str, reference_label: str | None = None,
            flag: bool | None = None, note: str | None = None, informational: bool = False,
            cfg: MultisystemConfig) -> dict[str, Any]:
    """One assessed input. Status comes from a rule flag, else from |z| bands; otherwise it is
    informational (shown, not scored) or insufficient (missing a value or a reference)."""
    if flag is not None:
        status = "deviation" if flag else "within_baseline"
    elif z is not None and not math.isnan(z):
        az = abs(z)
        status = "marked_deviation" if az >= cfg.z_marked else "deviation" if az >= cfg.z_deviation else "within_baseline"
    else:
        status = "info" if informational and value is not None else "insufficient_data"
    return {
        "key": key, "label": label, "value": value, "unit": unit, "reference": reference,
        "reference_label": reference_label, "z": None if z is None or math.isnan(z) else round(float(z), 2),
        "direction": None if z is None or math.isnan(z) or abs(z) < cfg.z_deviation else ("above" if z > 0 else "below"),
        "status": status, "category": category, "source": source, "note": note,
    }


def _z(value: float | None, ref: list[float]) -> tuple[float | None, float | None]:
    vals = [v for v in ref if v is not None]
    if value is None or len(vals) < 5:
        return None, (float(np.mean(vals)) if vals else None)
    mean, sd = float(np.mean(vals)), float(np.std(vals, ddof=1))
    if sd <= 1e-9:
        return 0.0, mean
    return (value - mean) / sd, mean


def describe(f: dict[str, Any]) -> str:
    unit = f" {f['unit']}" if f["unit"] else ""
    if f["z"] is not None and f["reference"] is not None:
        return (f"{f['label']} {f['value']}{unit} is {abs(f['z']):.1f} SD {'above' if f['z'] > 0 else 'below'} "
                f"{f['reference_label'] or 'the reference'} ({f['reference']}{unit}).")
    if f["note"]:
        return f"{f['label']}: {f['note']}"
    return f"{f['label']} {f['value']}{unit}."


class MultisystemEngine:
    def __init__(self, monitor: MonitoringService, ai, twin: TwinService, overlays=None,
                 config: MultisystemConfig | None = None) -> None:
        self.monitor = monitor
        self.ai = ai
        self.twin = twin
        self.overlays = overlays  # callable(astronaut_id) -> dict | None, from the emergency simulator
        self.cfg = config or MultisystemConfig.load()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def assess(self, session: AsyncSession, aid: str, now: datetime | None = None, use_cache: bool = True) -> dict[str, Any]:
        hit = self._cache.get(aid)
        if use_cache and hit and time.monotonic() - hit[0] < CACHE_S:
            return hit[1]
        result = await self._assess(session, aid, now or utcnow())
        self._cache[aid] = (time.monotonic(), result)
        return result

    async def _assess(self, session: AsyncSession, aid: str, now: datetime) -> dict[str, Any]:
        cfg = self.cfg
        profile = self.monitor.engine.profiles[aid]
        reading = self.monitor.latest_reading(aid)
        if reading is None:
            reading = await vitals_repo.latest(session, aid)
        quality_notes: list[str] = []

        # "Current" = mean of the stored samples in the 5 minutes up to the latest reading, which is the
        # resolution the Phase 3 personal baseline was fitted at (single 1 Hz readings are noisier).
        baseline: dict[str, dict[str, Any]] = {}
        risk: dict[str, Any] | None = None
        ref_time = getattr(reading, "ts", None) or now
        recent = await vitals_repo.fetch_range(session, aid, ref_time - CURRENT_WINDOW, ref_time,
                                               columns=(*SIGNALS, "activity_state"))
        if self.ai is not None:
            try:
                pb = (await self.ai.baseline(aid)).baseline
                if recent:
                    states = [r[-1] for r in recent if r[-1]]
                    state = max(dict.fromkeys(states), key=states.count) if states else "work"  # ties: earliest
                    for i, sig in enumerate(SIGNALS, start=1):
                        vals = [r[i] for r in recent if r[i] is not None]
                        if not vals:
                            continue
                        value = float(np.mean(vals))
                        ref = pb.reference(sig, state, pd.Timestamp(ref_time))
                        baseline[sig] = {"value": S._r(sig, value), "expected": round(ref.center, 2) if ref.comparable else None,
                                         "z": ref.z_or_none(value), "state": state, "reference_level": ref.basis,
                                         "n": len(vals)}
                else:
                    quality_notes.append("No stored samples in the last 5 minutes.")
            except ApiError as exc:
                quality_notes.append(f"Personal baseline unavailable: {exc.message}")
            try:
                risk = await self.ai.risk(aid)
            except ApiError as exc:
                quality_notes.append(f"AI risk assessment unavailable: {exc.message}")

        days = await self.twin.days(aid, now.date() - timedelta(days=max(cfg.sleep_reference_nights, 30) + 1))
        complete = [d for d in days if d.complete]
        overlay = self.overlays(aid) if self.overlays else None
        scenarios = self.monitor.active_scenarios(now)
        habitat = habitat_at(now, scenarios)
        habitat_active = habitat["anomaly_scenario_id"] is not None

        def vital(sig: str) -> dict[str, Any]:
            cur = baseline.get(sig)
            value = getattr(reading, sig, None) if reading is not None else None
            if cur:
                ref_label = f"personal baseline for '{cur['state']}' ({cur['reference_level']} reference)"
                return feature(sig, S.LABELS[sig], cur["value"], S.UNITS[sig], reference=cur.get("expected"),
                               z=cur.get("z"), category="simulated",
                               source=f"5-minute mean of {cur['n']} samples vs Phase 3 personal baseline",
                               reference_label=ref_label if cur.get("expected") is not None else None,
                               note=None if cur.get("expected") is not None else "No baseline yet for the current activity.",
                               cfg=cfg)
            return feature(sig, S.LABELS[sig], value, S.UNITS[sig], category="simulated", source="Latest reading",
                           note="No personal baseline comparison available.", cfg=cfg)

        systems: dict[str, list[dict[str, Any]]] = {k: [] for k in cfg.systems}
        for sig in ("heart_rate", "systolic", "diastolic"):
            systems["cardiovascular"].append(vital(sig))
        rhythm = getattr(reading, "rhythm", None) if reading is not None else None
        systems["cardiovascular"].append(feature(
            "rhythm", "Rhythm (synthetic ECG)", rhythm, "", flag=None if rhythm is None else rhythm == "irregular",
            category="simulated", source="Live rhythm classification",
            note=None if rhythm is None else f"classified {rhythm}", cfg=cfg))
        hrv = getattr(reading, "hrv_rmssd_ms", None) if reading is not None else None
        rows = await vitals_repo.fetch_range(session, aid, now - timedelta(hours=24), now, columns=("hrv_rmssd_ms",))
        hrv_ref = [r[1] for r in rows if r[1] is not None]
        hz, hmean = _z(hrv, hrv_ref)
        systems["cardiovascular"].append(feature(
            "hrv_rmssd_ms", S.LABELS["hrv_rmssd_ms"], hrv, "ms", reference=None if hmean is None else round(hmean, 1),
            z=hz, category="simulated", source="Live RMSSD vs stored samples of the last 24 h",
            reference_label="its 24-hour mean", note=None if hrv is not None else "Needs live ECG samples.", cfg=cfg))

        systems["respiratory"] += [vital("spo2"), vital("respiratory_rate")]
        systems["thermoregulation"].append(vital("temperature_c"))
        if habitat_active:
            p = habitat["parameters"]
            systems["respiratory"].append(feature(
                "habitat_ppco2", p["ppco2_mmhg"]["label"], p["ppco2_mmhg"]["value"], "mmHg",
                reference=p["ppco2_mmhg"]["nominal"], z=p["ppco2_mmhg"]["deviation_sigma"], category="simulated",
                source="Simulated habitat atmosphere", reference_label="the simulated nominal level", cfg=cfg))
            systems["thermoregulation"].append(feature(
                "habitat_temperature", p["cabin_temperature_c"]["label"], p["cabin_temperature_c"]["value"], "°C",
                reference=p["cabin_temperature_c"]["nominal"], z=p["cabin_temperature_c"]["deviation_sigma"],
                category="simulated", source="Simulated habitat atmosphere", reference_label="the simulated nominal level",
                cfg=cfg))

        # Sleep and circadian (from the twin; an emergency-simulator overlay replaces recent nights).
        nights = [(d.day, d.sleep) for d in complete if d.sleep]
        overlay_nights = (overlay or {}).get("nights") or {}
        if overlay_nights:
            nights = [(day, overlay_nights.get(day.isoformat(), s)) for day, s in nights]
        sleep_cat = "simulated"
        if nights:
            last_day, last = nights[-1]
            prev = [s for _, s in nights[-1 - cfg.sleep_reference_nights:-1]]
            from_overlay = last_day.isoformat() in overlay_nights
            src = "Emergency-simulator overlay (simulated what-if)" if from_overlay else "Twin: last completed night"
            dz, dmean = _z(last["duration_hours"], [s["duration_hours"] for s in prev])
            ez, emean = _z(last["efficiency_pct"], [s["efficiency_pct"] for s in prev])
            systems["sleep_circadian"].append(feature(
                "sleep_duration", "Sleep duration", round(last["duration_hours"], 2), "h",
                reference=None if dmean is None else round(dmean, 2), z=dz, category=sleep_cat, source=src,
                reference_label=f"the previous {len(prev)} nights", cfg=cfg))
            systems["sleep_circadian"].append(feature(
                "sleep_efficiency", "Sleep efficiency", round(last["efficiency_pct"], 1), "%",
                reference=None if emean is None else round(emean, 1), z=ez, category=sleep_cat, source=src,
                reference_label=f"the previous {len(prev)} nights", cfg=cfg))
            week = [s["duration_hours"] for _, s in nights[-7:]]
            debt = round(sum(profile.sleep_target_hours - h for h in week), 2)
            systems["sleep_circadian"].append(feature(
                "sleep_debt_7d", "Sleep debt, last 7 nights", debt, "h", reference=round(profile.sleep_target_hours, 1),
                category="derived", source="Twin sleep records vs configured sleep target",
                reference_label="the configured nightly target",
                note=f"{debt:+.1f} h against a {profile.sleep_target_hours:g} h nightly target over {len(week)} nights",
                informational=True, cfg=cfg))
        else:
            quality_notes.append("No completed nights in the twin yet.")
        in_window = sleep_window_at(profile, now, self.monitor.engine.seed)
        state = getattr(reading, "activity_state", None) if reading is not None else None
        disrupted = bool(in_window and state is not None and state != "sleep")
        disruption_active = any(s.scenario.value == "sleep_disruption" and s.affects(aid) for s in scenarios)
        systems["sleep_circadian"].append(feature(
            "awake_in_sleep_window", "Awake during scheduled sleep", "yes" if (disrupted or disruption_active) else "no",
            "", flag=bool(disrupted or disruption_active), category="simulated", source="Schedule vs activity state",
            note=("a sleep-disruption test scenario is running" if disruption_active else
                  "inside the scheduled sleep window" if in_window else "outside the scheduled sleep window"), cfg=cfg))

        # Activity and recovery.
        if complete:
            y = complete[-1]
            ex = (y.activity or {}).get("exercise_minutes")
            systems["activity_recovery"].append(feature(
                "exercise_minutes", f"Exercise on {y.day.isoformat()}", ex, "min",
                reference=float(profile.exercise_minutes), category="derived", source="Twin activity summary",
                reference_label="the planned session",
                flag=None if ex is None else ex < cfg.exercise_shortfall_fraction * profile.exercise_minutes,
                note=None if ex is None else f"{ex} of {profile.exercise_minutes} planned minutes", cfg=cfg))
            ref_days = complete[-1 - cfg.recovery_reference_days:-1]
            rhr = (y.metrics.get("heart_rate") or {}).get("sleep_mean")
            rz, rmean = _z(rhr, [(d.metrics.get("heart_rate") or {}).get("sleep_mean") for d in ref_days])
            systems["activity_recovery"].append(feature(
                "resting_heart_rate", "Sleeping heart rate (last complete day)", rhr, "bpm",
                reference=None if rmean is None else round(rmean, 1), z=rz, category="derived",
                source="Twin daily sleep-state mean", reference_label=f"the previous {len(ref_days)} days", cfg=cfg))
        met = getattr(reading, "activity_met", None) if reading is not None else None
        systems["activity_recovery"].append(feature(
            "activity_met", "Current activity", met, "MET", category="simulated", source="Latest reading",
            note=f"{state or 'unknown'} at {met} MET" if met is not None else None, informational=True, cfg=cfg))

        # Radiation exposure indicators.
        # Complete days only: today's dose is still accumulating and would look low.
        doses = [(d.day, (d.radiation or {}).get("dose_msv")) for d in complete if d.radiation]
        if doses:
            today_dose = doses[-1][1]
            ref = [v for _, v in doses[:-1]][-30:]
            dz, dmean = _z(today_dose, ref)
            systems["radiation"].append(feature(
                "daily_dose", f"Simulated dose on {doses[-1][0].isoformat()}", round(today_dose, 4), "mSv",
                reference=None if dmean is None else round(dmean, 4), z=dz, category="simulated",
                source="Simulated crew dosimetry", reference_label="the previous 30 days", cfg=cfg))
            spe = [d.day.isoformat() for d in days[-3:] if (d.radiation or {}).get("solar_particle_event")]
            systems["radiation"].append(feature(
                "spe_recent", "Simulated solar particle event, last 3 days", "yes" if spe else "no", "",
                flag=bool(spe), category="simulated", source="Simulated crew dosimetry",
                note=("on " + ", ".join(spe)) if spe else "none", cfg=cfg))
        dose_mult = max([1.0] + [1 + (s.spec.dose_rate_multiplier - 1) * s.envelope(now) for s in scenarios])
        systems["radiation"].append(feature(
            "habitat_dose_rate", "Habitat dose-rate multiplier (simulated)", round(dose_mult, 2), "×",
            flag=dose_mult > 1.5, category="simulated", source="Simulator scenario state",
            note="a simulated solar particle event is running" if dose_mult > 1.5 else "background only", cfg=cfg))
        since = now - timedelta(hours=cfg.space_weather_lookback_hours)
        events = (await session.execute(select(SpaceWeatherEventRow.event_type, SpaceWeatherEventRow.scale,
                                                SpaceWeatherEventRow.severity, SpaceWeatherEventRow.start_time)
                                         .where(SpaceWeatherEventRow.start_time >= since,
                                                SpaceWeatherEventRow.event_type.in_(("FLR", "SEP", "GST", "CME"))))).all()
        notable = [e for e in events if e.event_type == "SEP" or (e.severity or 0) >= 1]
        systems["radiation"].append(feature(
            "nasa_space_weather", f"NASA DONKI events, last {cfg.space_weather_lookback_hours} h", len(notable), "events",
            informational=True, category="indicator", source="NASA DONKI (real data, context only)",
            note=(", ".join(sorted({f"{e.event_type}{' ' + e.scale if e.scale else ''}" for e in notable}))
                  if notable else f"{len(events)} event(s), none at or above scale level 1 and no SEP"), cfg=cfg))

        # ----------------------------------------------------------------- per system
        open_alerts = self.monitor.open_alerts_for(aid)
        out_systems = []
        statuses: dict[str, str] = {}
        flags: dict[str, bool] = {}
        for key, meta in cfg.systems.items():
            feats = systems[key]
            for f in feats:
                flags[f["key"]] = f["status"] in ("deviation", "marked_deviation")
            # Real NASA indicators never change a crew member's status; they only feed the
            # co-occurrence pattern with simulated dose.
            flags["nasa_space_weather"] = bool(notable)
            scored = [f for f in feats if f["status"] not in ("insufficient_data", "info")]
            status = max((f["status"] for f in scored), key=lambda s: STATUS_RANK[s]) if scored else "insufficient_data"
            alerts = [{"id": a.id, "title": a.title, "severity": a.severity, "metric": a.metric}
                      for a in open_alerts if ALERT_SYSTEM.get(a.metric) == key]
            ai_items = []
            if risk:
                sys_signals = {s for s, k in SIGNAL_SYSTEM.items() if k == key}
                for w in risk.get("warnings", []):
                    if sys_signals & set(w.get("signals") or []):
                        ai_items.append({"source": w["source"], "title": w["title"], "detail": w["detail"],
                                         "concern": w.get("concern"), "category": "model" if w["source"] in ("anomaly", "trend") else "derived"})
            deviating = [f for f in feats if f["status"] in ("deviation", "marked_deviation")]
            if deviating:
                explanation = " ".join(describe(f) for f in deviating)
            elif scored:
                explanation = (f"All {len(scored)} assessed inputs are within ±{cfg.z_deviation:g} SD of their reference "
                               "or show no flagged condition.")
            else:
                explanation = "Not enough data to assess this system."
            missing = [f["label"] for f in feats if f["status"] == "insufficient_data"]
            out_systems.append({
                "key": key, "label": meta["label"], "description": meta["description"], "status": status,
                "features": feats, "open_alerts": alerts, "ai_outputs": ai_items, "explanation": explanation,
                "data_quality": {"inputs": len(feats), "assessed": len(scored), "missing": missing},
            })
            statuses[key] = status

        patterns = []
        for p in cfg.patterns:
            sys_ok = all(STATUS_RANK[statuses.get(s, "insufficient_data")] >= 1 for s in p["systems"])
            req_ok = all(flags.get(r, False) for r in p.get("requires", []))
            if sys_ok and req_ok and (len(p["systems"]) > 1 or p.get("requires")):
                evidence = [describe(f) for s in out_systems if s["key"] in p["systems"]
                            for f in s["features"] if f["status"] in ("deviation", "marked_deviation")
                            and (not p.get("requires") or f["key"] in p["requires"])]
                patterns.append({"key": p["key"], "label": p["label"], "systems": p["systems"],
                                 "evidence": evidence, "review": p["review"],
                                 "note": "Co-occurrence of deviations; it does not establish a cause."})

        reading_ts = getattr(reading, "ts", None) if reading is not None else None
        age_s = (now - reading_ts).total_seconds() if reading_ts else None
        if age_s is not None and age_s > 120:
            quality_notes.append(f"Latest reading is {age_s / 60:.0f} min old.")
        deviating_systems = [s["label"] for s in out_systems if STATUS_RANK[s["status"]] >= 1]
        summary = (f"{len(deviating_systems)} of {len(out_systems)} systems show deviations: {', '.join(deviating_systems)}."
                   if deviating_systems else "No system shows a deviation from this crew member's baseline.")
        return {
            "astronaut_id": aid, "name": profile.name, "generated_at": now, "reading_ts": reading_ts,
            "summary": summary, "systems": out_systems, "patterns": patterns,
            "ai": None if risk is None else {"risk_score": risk["risk_score"], "category": risk["category"],
                                             "category_label": risk["category_label"],
                                             "model_version": risk.get("model_version"),
                                             "anomaly": risk.get("anomaly"),
                                             "confidence": risk["explanation"]["confidence"]},
            "habitat": habitat if habitat_active else None,
            "overlay": overlay,
            "config": {"z_deviation": cfg.z_deviation, "z_marked": cfg.z_marked,
                       "source": "app/medical/multisystem_config.json",
                       "note": "Statistical bands relative to this crew member's own baseline; not clinical thresholds."},
            "data_quality": {"notes": quality_notes, "reading_age_s": None if age_s is None else round(age_s, 1)},
            "disclaimer": DECISION_SUPPORT_DISCLAIMER,
        }
