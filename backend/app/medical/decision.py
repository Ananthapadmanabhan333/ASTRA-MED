"""Explainable decision-support packet for an alert.

Eight parts, each built from stored data or model outputs, never from invented clinical content:
observation, measurements, baseline comparison, environmental context, AI output, confidence and
uncertainty, data quality, and the recommended medical *review workflow* (process steps from
``review_workflow.json``; no diagnoses, treatments or clinical thresholds).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.detection.evaluator import AlertRecord
from app.detection.rules import THRESHOLD_RULES
from app.medical import DECISION_SUPPORT_DISCLAIMER
from app.repositories import vitals as vitals_repo
from app.security.rbac import ROLE_LABELS, Role
from app.services.monitoring import MonitoringService
from app.simulator.habitat import habitat_at
from app.simulator.scenarios import SCENARIOS, Scenario
from app.space.timeline import nearby_events
from app.twin import summary as S
from app.twin.stages import stage_for

logger = logging.getLogger("astra.decision")
WORKFLOW_PATH = Path(__file__).with_name("review_workflow.json")
SIGNIFICANT = ("caution", "critical")
SERIES_METRICS = ("heart_rate", "spo2", "respiratory_rate", "temperature_c", "systolic", "diastolic")
BEFORE = timedelta(minutes=30)
AFTER = timedelta(minutes=15)
LIMIT_NOTE = ("Prototype alert limit from app/detection/rules.py, chosen to exercise the software. "
              "It is not a clinical criterion.")


def load_workflow() -> dict[str, Any]:
    raw = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    return raw


def _scenario_label(key: str | None) -> str | None:
    if not key:
        return None
    try:
        return SCENARIOS[Scenario(key)].label
    except ValueError:
        return key


def _series(rows: list[tuple], cols: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    df = S.frame(rows, ("ts", *cols))
    if df.empty:
        return [], {"samples": 0, "interval_s": None, "largest_gap_s": None}
    interval = S.sample_interval_s(df)
    gaps = df["ts"].diff().dt.total_seconds().dropna()
    per_min = df.set_index("ts")[list(cols)].apply(pd.to_numeric, errors="coerce").resample("1min").mean()
    points = [{"ts": ts.to_pydatetime(), **{c: (None if pd.isna(v) else round(float(v), 2)) for c, v in row.items()}}
              for ts, row in per_min.iterrows()]
    return points, {"samples": int(len(df)), "interval_s": None if interval is None else round(interval, 1),
                    "largest_gap_s": None if gaps.empty else round(float(gaps.max()), 1)}


def escalation_for(severity: str, multisystem: dict[str, Any] | None, workflow: dict[str, Any]) -> dict[str, Any]:
    level_key = severity if severity in workflow["escalation"] else "advisory"
    reasons = [f"Alert severity: {severity}."]
    if workflow.get("escalate_on_patterns") and multisystem:
        patterns = multisystem.get("patterns") or []
        marked = [s["label"] for s in multisystem.get("systems", []) if s["status"] == "marked_deviation"]
        if patterns:
            reasons.append("Concurrent deviations across systems: " + "; ".join(p["label"] for p in patterns) + ".")
        if len(marked) >= 2:
            reasons.append("Marked deviations in " + ", ".join(marked) + ".")
        if (patterns or len(marked) >= 2) and level_key != "critical":
            level_key = "critical"
    esc = workflow["escalation"][level_key]
    return {**esc, "severity_basis": level_key, "reasons": reasons,
            "requires_medical_review": level_key in ("critical", "caution")}


async def packet(session: AsyncSession, monitor: MonitoringService, ai, multisystem_engine, record: AlertRecord,
                 now: datetime, include_multisystem: bool = True) -> dict[str, Any]:
    aid = record.astronaut_id
    profile = monitor.engine.profiles.get(aid)
    workflow = load_workflow()
    opened = record.opened_at
    end = min(now, opened + AFTER)
    notes: list[str] = []

    # 1. Observation
    scenario_label = _scenario_label(record.scenario)
    sentence = (f"{record.title} for {profile.name if profile else aid}: {record.message}")
    observation = {
        "alert_id": record.id, "astronaut_id": aid, "name": profile.name if profile else aid,
        "title": record.title, "message": record.message, "severity": record.severity, "status": record.status,
        "category": record.category, "metric": record.metric, "direction": record.direction,
        "opened_at": opened, "updated_at": record.updated_at, "summary": sentence,
        "simulated_test_scenario": scenario_label, "data_category": "simulated",
    }

    # 2. Measurements
    rows = await vitals_repo.fetch_range(session, aid, opened - BEFORE, end, columns=SERIES_METRICS)
    points, sample_stats = _series(rows, SERIES_METRICS)
    rule = next((r for r in THRESHOLD_RULES if r.key == record.rule_key), None)
    measurements = {
        "metric": record.metric, "label": S.LABELS.get(record.metric, record.metric), "unit": record.unit,
        "trigger_value": record.trigger_value, "peak_value": record.peak_value,
        "alert_limit": record.threshold_value, "alert_limit_note": LIMIT_NOTE if record.threshold_value is not None else None,
        "limits": None if rule is None else {"caution": rule.caution, "critical": rule.critical},
        "window": {"start": opened - BEFORE, "end": end}, "series": points, "series_resolution_s": 60,
        "data_category": "simulated",
    }

    # 3. Baseline comparison and 5. AI output (both from the Phase 3 alert explanation)
    explanation = None
    try:
        explanation = await ai.explain_alert(record.id) if ai is not None else None
    except ApiError as exc:
        notes.append(f"Baseline comparison unavailable: {exc.message}")
    except Exception:  # a failing model explanation must not take the rest of the packet down
        logger.exception("alert explanation failed for %s", record.id)
        notes.append("The model explanation failed for this alert; see the server log.")
    if explanation:
        ex = explanation["explanation"]
        baseline = {
            "available": True, "contributors": ex["contributors"], "significance": ex["significance"],
            "method": "Personal baseline by activity and time of day (Phase 3), 5-minute window containing the alert.",
            "data_category": "derived",
        }
        ctx = explanation.get("anomaly_context") or []
        peak = max(ctx, key=lambda c: c["ensemble_score"], default=None)
        ai_output = {
            "available": True, "model_version": explanation.get("model_version"), "rule": explanation["rule"],
            "kind": ex["kind"], "what_changed": ex["what_changed"],
            "anomaly_peak": None if peak is None else {"ts": peak["ts"], "ensemble_score": peak["ensemble_score"],
                                                       "votes": peak["votes"], "flagged": peak["flagged"]},
            "flagged_windows": sum(1 for c in ctx if c["flagged"]), "windows": len(ctx),
            "data_category": "model",
            "note": "Model output on simulated data; it describes how unusual the pattern is, not its cause.",
        }
    else:
        baseline = {"available": False, "contributors": [], "significance": None, "method": None, "data_category": "derived"}
        ai_output = {"available": False, "model_version": None, "rule": None, "kind": None, "what_changed": None,
                     "anomaly_peak": None, "flagged_windows": 0, "windows": 0, "data_category": "model",
                     "note": "No model explanation could be produced for this alert."}

    # 4. Environmental context
    activity_state = record.activity_state
    habitat_then = habitat_at(opened, [s for s in monitor.engine.scenarios.values()
                                       if s.started_at <= opened <= s.effective_end])
    try:
        space = await nearby_events(session, opened, 24)
    except Exception:  # space tables may be empty or disabled
        space = {"events": [], "note": "NASA space-weather data unavailable."}
    mission_day = (opened.date() - monitor.settings.mission_start_date).days
    environment = {
        "activity_state": activity_state, "mission_day": mission_day, "mission_stage": stage_for(mission_day).label,
        "simulated_test_scenario": scenario_label,
        "scenario_note": ("This alert occurred while a simulated test scenario was running; the deviation was "
                          "injected by the simulator.") if scenario_label else None,
        "habitat": habitat_then if habitat_then and habitat_then.get("anomaly_scenario_id") else None,
        "space_weather": {"events": space["events"][:8], "window_hours": 24, "note": space.get("note"),
                          "data_category": "indicator"},
    }

    # 6. Confidence and uncertainty
    conf = (explanation or {}).get("explanation", {}).get("confidence") or {"score": None, "level": "low",
                                                                             "basis": ["no model explanation"]}
    limitations = (explanation or {}).get("explanation", {}).get("limitations", [])
    uncertainty = {
        "confidence": conf,
        "meaning": "Confidence describes agreement between models and data completeness, not diagnostic certainty.",
        "sources": [
            "Models were trained and calibrated on simulated data only.",
            *limitations,
        ],
    }

    # 7. Data quality
    window_s = (end - (opened - BEFORE)).total_seconds()
    interval = sample_stats["interval_s"]
    completeness = None if not interval else round(min(1.0, sample_stats["samples"] * interval / window_s), 3)
    latest = monitor.latest_reading(aid)
    data_quality = {
        **sample_stats, "window_seconds": round(window_s), "completeness": completeness,
        "latest_reading_age_s": None if latest is None else round((now - latest.ts).total_seconds(), 1),
        "notes": notes + ([] if completeness is None or completeness >= 0.8 else
                          [f"Only {completeness:.0%} of the expected samples are stored around this alert."]),
    }

    # 8. Review workflow
    ms = None
    if include_multisystem and multisystem_engine is not None:
        try:
            ms = await multisystem_engine.assess(session, aid, now)
        except ApiError:
            ms = None
    esc = escalation_for(record.severity, ms, workflow)
    steps = [{"key": st["key"], "label": st["label"], "role": st["role"],
              "role_label": ROLE_LABELS.get(Role(st["role"]), st["role"])}
             for st in workflow["steps"] if esc["severity_basis"] in st["severities"]]
    review = {
        "escalation": esc, "steps": steps, "alert_status": record.status,
        "acknowledged_at": record.acknowledged_at, "resolved_at": record.resolved_at,
        "source": "app/medical/review_workflow.json",
        "note": "Process steps only. Clinical decisions follow the mission's approved medical procedures.",
    }
    return {
        "alert_id": record.id, "generated_at": now, "observation": observation, "measurements": measurements,
        "baseline_comparison": baseline, "environmental_context": environment, "ai_output": ai_output,
        "confidence_uncertainty": uncertainty, "data_quality": data_quality, "review_workflow": review,
        "concurrent_patterns": (ms or {}).get("patterns", []),
        "disclaimer": DECISION_SUPPORT_DISCLAIMER, "data_source": "simulated",
    }
