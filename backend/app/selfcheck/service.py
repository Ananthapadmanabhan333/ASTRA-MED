"""Crew self-check: the astronaut's own view of their health (phase 8).

The 2026 Space Apps challenge asks for a tool that helps astronauts assess their own health. This
module adds what the monitoring stream cannot measure, entered by hand:

* blood glucose (mg/dL, with whether it was fasting),
* a mood check-in (1 very low to 5 very good),
* symptoms from a fixed list, plus a short note.

It combines them with the automatically monitored indicators into one plain-language status per
indicator, scheduled check-in prompts, and when-to-escalate guidance.

**Not a medical device.** Glucose bands are orientation bands taken from the American Diabetes
Association's criteria for non-pregnant adults (laboratory plasma glucose), not a diagnosis. Mood and
symptom rules are process prompts ("tell the flight surgeon"), not assessments. Nothing here
recommends a treatment.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError
from app.core.timeutil import as_utc, utcnow
from app.db.models import CrewSelfReportRow, SleepSessionRow
from app.simulator.profiles import CREW_BY_ID

GLUCOSE_CONTEXTS = ("fasting", "after_meal", "random")

# Symptom vocabulary. "contact" symptoms are reported to the flight surgeon straight away; the rest
# are recorded for the next medical conference. Process guidance only.
SYMPTOMS: dict[str, dict[str, str]] = {
    "headache": {"label": "Headache", "level": "attention"},
    "nausea": {"label": "Nausea", "level": "attention"},
    "fatigue": {"label": "Unusual fatigue", "level": "attention"},
    "dizziness": {"label": "Dizziness", "level": "attention"},
    "congestion": {"label": "Nasal congestion", "level": "attention"},
    "back_pain": {"label": "Back pain", "level": "attention"},
    "sleep_problems": {"label": "Trouble sleeping", "level": "attention"},
    "vision_change": {"label": "Change in vision", "level": "contact"},
    "chest_pain": {"label": "Chest pain or pressure", "level": "contact"},
    "shortness_of_breath": {"label": "Shortness of breath", "level": "contact"},
}

# How often each hand-entered check is expected (hours) and when it counts as overdue.
CHECK_INTERVAL_H = {"glucose": 24, "mood": 24, "symptoms": 24}
OVERDUE_AFTER_H = 12

GLUCOSE_REFERENCE = (
    "Orientation bands from the American Diabetes Association criteria for non-pregnant adults "
    "(Standards of Care in Diabetes: fasting plasma glucose 100–125 mg/dL and 2-hour values "
    "140–199 mg/dL are above the typical range; ≥126 fasting or ≥200 after a meal are high; below 70 "
    "is level 1 and below 54 level 2 hypoglycaemia). They describe laboratory plasma glucose, not a "
    "diagnosis, and are shown for orientation only."
)

STATUS_RANK = {"no_data": 0, "normal": 1, "attention": 2, "contact": 3}


@dataclass(frozen=True)
class Band:
    status: str  # normal | attention | contact
    label: str
    guidance: str


def glucose_band(value: float, context: str | None) -> Band:
    """ADA-based orientation band for one glucose value (mg/dL)."""
    if value < 54:
        return Band("contact", "Very low (below 54 mg/dL)",
                    "Contact the flight surgeon now and follow the mission's hypoglycaemia procedure.")
    if value < 70:
        return Band("attention", "Low (54–69 mg/dL)",
                    "Re-check soon and tell the crew medical officer; follow the mission's procedure for low glucose.")
    if context == "fasting":
        if value < 100:
            return Band("normal", "In the typical fasting range (70–99 mg/dL)", "No action; keep the daily check.")
        if value < 126:
            return Band("attention", "Above the typical fasting range (100–125 mg/dL)",
                        "Repeat the fasting check tomorrow; mention it at the next medical conference.")
        return Band("contact", "High for a fasting value (126 mg/dL or more)",
                    "Repeat the check and report it to the flight surgeon.")
    if value < 140:
        return Band("normal", "In the typical range after a meal (below 140 mg/dL)", "No action; keep the daily check.")
    if value < 200:
        return Band("attention", "Above the typical range after a meal (140–199 mg/dL)",
                    "Check again fasting tomorrow; mention it at the next medical conference.")
    return Band("contact", "High (200 mg/dL or more)", "Repeat the check and report it to the flight surgeon.")


def mood_assessment(moods: list[tuple[datetime, int]]) -> dict[str, Any]:
    """Latest mood against the person's own previous check-ins (newest first)."""
    if not moods:
        return {"status": "no_data", "label": "No mood check-in yet", "baseline": None, "low_streak": 0,
                "guidance": "Record a mood check-in; it takes a few seconds."}
    latest = moods[0][1]
    previous = [m for _, m in moods[1:15]]
    baseline = statistics.median(previous) if len(previous) >= 5 else None
    streak = 0
    for _, m in moods:
        if m <= 2:
            streak += 1
        else:
            break
    if streak >= 3:
        status, label = "contact", f"Low mood on {streak} check-ins in a row"
        guidance = "Talk to the flight surgeon or the behavioural-health support team. You do not need a reason."
    elif latest <= 2 or (baseline is not None and latest <= baseline - 2):
        status = "attention"
        label = "Lower than usual" if baseline is not None and latest > 2 else "Low today"
        guidance = "Note what is affecting you; if it lasts several days, talk to the flight surgeon."
    else:
        status, label = "normal", "Usual range for you" if baseline is not None else "Recorded"
        guidance = "No action; keep the daily check-in."
    return {"status": status, "label": label, "baseline": baseline, "low_streak": streak, "guidance": guidance,
            "baseline_note": None if baseline is not None else "Your personal range needs at least 6 check-ins."}


def symptom_assessment(symptoms: list[str]) -> dict[str, Any]:
    if not symptoms:
        return {"status": "normal", "label": "No symptoms reported", "items": [], "guidance": "No action."}
    items = [{"key": s, **SYMPTOMS[s]} for s in symptoms if s in SYMPTOMS]
    worst = max((i["level"] for i in items), key=lambda lv: STATUS_RANK[lv], default="attention")
    guidance = ("Report these to the flight surgeon now." if worst == "contact"
                else "Recorded for the next medical conference; report sooner if they get worse.")
    return {"status": worst, "label": ", ".join(i["label"] for i in items), "items": items, "guidance": guidance}


def prompt_status(last: datetime | None, interval_h: float, now: datetime) -> dict[str, Any]:
    if last is None:
        return {"status": "due", "last_at": None, "due_at": None}
    due = last + timedelta(hours=interval_h)
    status = "done" if now < due else "overdue" if now >= due + timedelta(hours=OVERDUE_AFTER_H) else "due"
    return {"status": status, "last_at": last, "due_at": due}


def report_view(row: CrewSelfReportRow) -> dict[str, Any]:
    band = glucose_band(row.glucose_mg_dl, row.glucose_context) if row.glucose_mg_dl is not None else None
    return {
        "id": row.id, "astronaut_id": row.astronaut_id, "recorded_at": row.recorded_at, "created_at": row.created_at,
        "created_by": row.created_by, "glucose_mg_dl": row.glucose_mg_dl, "glucose_context": row.glucose_context,
        "glucose_status": band.status if band else None, "mood": row.mood, "symptoms_checked": bool(row.symptoms_checked),
        "symptoms": list(row.symptoms or []),
        "note": row.note, "data_source": row.data_source,
    }


class SelfCheckService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], monitor) -> None:
        self.factory = factory
        self.monitor = monitor

    @staticmethod
    def _require(astronaut_id: str) -> None:
        if astronaut_id not in CREW_BY_ID:
            raise NotFoundError(f"Unknown crew member {astronaut_id}.")

    async def add(self, astronaut_id: str, body, actor: str) -> dict[str, Any]:
        self._require(astronaut_id)
        now = utcnow()
        recorded = as_utc(body.recorded_at) if body.recorded_at else now
        row = CrewSelfReportRow(
            id=uuid.uuid4().hex[:16], astronaut_id=astronaut_id, recorded_at=min(recorded, now), created_at=now,
            created_by=actor, glucose_mg_dl=body.glucose_mg_dl, glucose_context=body.glucose_context,
            mood=body.mood, symptoms_checked=body.symptoms is not None, symptoms=sorted(set(body.symptoms or [])),
            note=(body.note or None),
        )
        async with self.factory() as session:
            session.add(row)
            await session.commit()
        return report_view(row)

    async def summary(self, astronaut_id: str) -> dict[str, Any]:
        self._require(astronaut_id)
        now = utcnow()
        async with self.factory() as session:
            rows = list((await session.scalars(
                select(CrewSelfReportRow).where(CrewSelfReportRow.astronaut_id == astronaut_id,
                                                CrewSelfReportRow.recorded_at >= now - timedelta(days=60))
                .order_by(CrewSelfReportRow.recorded_at.desc()).limit(200))).all())
            sleep = (await session.scalars(
                select(SleepSessionRow).where(SleepSessionRow.astronaut_id == astronaut_id)
                .order_by(SleepSessionRow.night.desc()).limit(1))).first()

        glucose_rows = [r for r in rows if r.glucose_mg_dl is not None]
        mood_rows = [(r.recorded_at, r.mood) for r in rows if r.mood is not None]
        latest_symptoms = next((r for r in rows if r.symptoms_checked), None)

        indicators: list[dict[str, Any]] = []
        if glucose_rows:
            g = glucose_rows[0]
            band = glucose_band(g.glucose_mg_dl, g.glucose_context)
            indicators.append({"key": "glucose", "label": "Blood glucose", "system": "metabolic",
                               "value": g.glucose_mg_dl, "unit": "mg/dL", "context": g.glucose_context,
                               "at": g.recorded_at, "status": band.status, "status_label": band.label,
                               "guidance": band.guidance, "source": "self_reported", "reference": GLUCOSE_REFERENCE})
        else:
            indicators.append({"key": "glucose", "label": "Blood glucose", "system": "metabolic", "value": None,
                               "unit": "mg/dL", "context": None, "at": None, "status": "no_data",
                               "status_label": "No glucose check recorded", "guidance": "Record a glucose check.",
                               "source": "self_reported", "reference": GLUCOSE_REFERENCE})
        mood = mood_assessment(mood_rows)
        indicators.append({"key": "mood", "label": "Mood", "system": "behavioural",
                           "value": float(mood_rows[0][1]) if mood_rows else None, "unit": "of 5", "context": None,
                           "at": mood_rows[0][0] if mood_rows else None, "status": mood["status"],
                           "status_label": mood["label"], "guidance": mood["guidance"], "source": "self_reported",
                           "reference": (f"Compared with your own median of {mood['baseline']:g} over recent check-ins."
                                         if mood.get("baseline") is not None
                                         else "Your personal range needs at least 6 check-ins.")})
        sym = symptom_assessment(list(latest_symptoms.symptoms) if latest_symptoms else [])
        indicators.append({"key": "symptoms", "label": "Symptoms", "system": "general",
                           "value": float(len(sym["items"])), "unit": "reported",
                           "context": None, "at": latest_symptoms.recorded_at if latest_symptoms else None,
                           "status": sym["status"] if latest_symptoms else "no_data",
                           "status_label": sym["label"] if latest_symptoms else "No symptom check recorded",
                           "guidance": sym["guidance"] if latest_symptoms else "Record a symptom check.",
                           "source": "self_reported", "reference": None})

        reading = self.monitor.latest_reading(astronaut_id) if self.monitor is not None else None
        prompts = [
            {"key": "vitals", "label": "Vital signs", "how": "Measured automatically by the monitoring stream "
             "(heart rate, SpO₂, blood pressure, temperature, respiratory rate).", "automatic": True,
             "status": "done" if reading else "due", "last_at": reading.ts if reading else None, "due_at": None},
            {"key": "sleep", "label": "Sleep log", "how": "Recorded automatically each night.", "automatic": True,
             "status": "done" if sleep else "due", "last_at": sleep.end if sleep else None, "due_at": None,
             "detail": f"{sleep.duration_hours:.1f} h, efficiency {sleep.efficiency_pct:.0f} %" if sleep else None},
            {"key": "glucose", "label": "Blood glucose", "automatic": False,
             "how": "Finger-stick meter; note whether you have eaten in the last 8 hours.",
             **prompt_status(glucose_rows[0].recorded_at if glucose_rows else None, CHECK_INTERVAL_H["glucose"], now)},
            {"key": "mood", "label": "Mood check-in", "automatic": False, "how": "Rate today from 1 to 5.",
             **prompt_status(mood_rows[0][0] if mood_rows else None, CHECK_INTERVAL_H["mood"], now)},
            {"key": "symptoms", "label": "Symptom check", "automatic": False,
             "how": "Tick anything you noticed today, or record that there was nothing.",
             **prompt_status(latest_symptoms.recorded_at if latest_symptoms else None, CHECK_INTERVAL_H["symptoms"], now)},
        ]
        return {
            "astronaut_id": astronaut_id, "name": CREW_BY_ID[astronaut_id].name, "generated_at": now,
            "indicators": indicators, "prompts": prompts,
            "reports": [report_view(r) for r in rows[:60]],
            "symptom_catalogue": [{"key": k, **v} for k, v in SYMPTOMS.items()],
            "notes": [
                "Glucose, mood and symptoms are entered by hand (self-reported). The vital signs are simulated.",
                "Bands and prompts are for orientation and process only: ASTRA-MED is not a medical device and "
                "does not diagnose or recommend treatment.",
            ],
        }
