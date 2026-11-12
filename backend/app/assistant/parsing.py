"""Light-weight question understanding: tasks, crew member, signal and time window."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.simulator.profiles import AstronautProfile

TASKS: dict[str, re.Pattern[str]] = {
    "incident_report": re.compile(r"incident report|(generate|write|draft|create|prepare) (an? )?(incident )?report", re.I),
    "environment": re.compile(r"space weather|solar|flare|\bcme\b|coronal|geomagnetic|storm|\bsep\b|radiation|"
                              r"\bdose\b|dosimet|\biss\b|donki|cosmic|particle|environment|cabin|habitat|co2|co₂", re.I),
    "anomaly": re.compile(r"anomal|why|alert|flag|unusual|deviat|abnormal|spike|drop", re.I),
    "trend": re.compile(r"trend|over (the )?(last|past)|summar|longitudinal|chang|stage|week|month|lately|recent", re.I),
    "history": re.compile(r"histor|since (launch|departure|mission start|the start)|so far|whole mission|entire mission", re.I),
    "records": re.compile(r"\b(show|list|find|retrieve|get|which|records?|reports?|last night|sleep)\b", re.I),
    "measurement": re.compile(r"what (is|are|does)|meaning|\bmean\b|explain|define|how (is|are) .* (measured|computed|calculated)|"
                              r"how does|normal|baseline", re.I),
    "status": re.compile(r"\b(how is|how are|status|current|now|right now|latest|today|doing)\b", re.I),
}

METRICS: dict[str, tuple[str, ...]] = {
    "heart_rate": ("heart rate", "heart-rate", "pulse", r"\bhr\b", "bpm"),
    "spo2": ("spo2", "spo₂", "oxygen saturation", "saturation", r"\bo2\b", "desaturation"),
    "systolic": ("systolic", "blood pressure", r"\bbp\b"),
    "diastolic": ("diastolic",),
    "temperature_c": ("temperature", r"\btemp\b", "fever", "thermo"),
    "respiratory_rate": ("respiratory rate", "breathing", "respiration", "breaths", r"\brr\b"),
    "hrv_rmssd_ms": ("hrv", "variability", "rmssd"),
    "sleep": ("sleep", "slept", "night", "circadian"),
    "dose": ("dose", "radiation", "dosimet", "msv", "mgy"),
}


@dataclass
class Parsed:
    tasks: list[str] = field(default_factory=list)
    astronaut_ids: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    hours: int | None = None
    alert_id: str | None = None
    crew_wide: bool = False


def parse(question: str, crew: dict[str, AstronautProfile]) -> Parsed:
    q = question.lower()
    p = Parsed()
    p.tasks = [k for k, rx in TASKS.items() if rx.search(question)] or ["data_question"]
    for aid, prof in crew.items():
        first, last = prof.name.lower().split()[0], prof.name.lower().split()[-1]
        if aid.lower() in q or re.search(rf"\b({re.escape(first)}|{re.escape(last)})\b", q) or \
                re.search(rf"\b{re.escape(prof.role.lower())}\b", q):
            p.astronaut_ids.append(aid)
    p.crew_wide = bool(re.search(r"\b(crew|everyone|all astronauts|all crew|team)\b", q))
    for metric, words in METRICS.items():
        if any(re.search(w if w.startswith(r"\b") else re.escape(w), q) for w in words):
            p.metrics.append(metric)
    m = re.search(r"(?:last|past)\s+(\d+)\s*(hours?|h\b|days?|d\b|weeks?)", q)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        p.hours = n * (168 if unit.startswith("w") else 24 if unit.startswith("d") else 1)
    elif re.search(r"\b(this|last|past) week\b", q):
        p.hours = 168
    elif re.search(r"\b(today|last 24|past day)\b", q):
        p.hours = 24
    elif re.search(r"\b(yesterday|last night)\b", q):
        p.hours = 48
    elif re.search(r"\b(this|last|past) month\b", q):
        p.hours = 720
    a = re.search(r"\b[0-9a-f]{16}\b", q)
    if a:
        p.alert_id = a.group(0)
    return p
