"""Safety layer: decline diagnosis and treatment, detect situations that need a human now."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DIAGNOSIS = re.compile(
    r"\b(diagnos\w*|what (disease|condition|illness|disorder)|"
    r"(does|do|did) [\w-]+ have (a|an) (disease|condition|illness|disorder|infection|medical problem)|"
    r"is [\w-]+ (sick|ill|having a)|what'?s wrong with|which (disease|condition)|prognosis|"
    r"heart attack|infection|pneumonia|hypoxia|arrhythmia)\b", re.I)
TREATMENT = re.compile(
    r"\b(prescri\w*|medicat\w*|medicine|drugs?|dosage|\d+\s?mg|milligram|antibiotic\w*|aspirin|ibuprofen|"
    r"paracetamol|acetaminophen|epinephrine|sedat\w*|treat(ment|ed|ing)?|therapy|cure|"
    r"should [\w-]+ (take|be given|receive|get)|what should (i|we) (give|do for)|administer|first aid)\b", re.I)
EMERGENCY = re.compile(
    r"\b(chest pain|unconscious|unresponsive|not breathing|stopped breathing|can'?t breathe|seizure|"
    r"collaps\w*|severe bleeding|bleeding|cardiac arrest|choking|stroke|faint\w*|passed out|emergency)\b", re.I)


@dataclass
class SafetyResult:
    declined: list[str] = field(default_factory=list)
    escalation_reasons: list[str] = field(default_factory=list)

    @property
    def escalate(self) -> bool:
        return bool(self.escalation_reasons)


def screen(question: str) -> SafetyResult:
    result = SafetyResult()
    if DIAGNOSIS.search(question):
        result.declined.append(
            "I can't diagnose or name a medical condition. I can show what the simulated measurements, "
            "baselines and alerts say, and a flight surgeon can interpret them.")
    if TREATMENT.search(question):
        result.declined.append(
            "I can't recommend treatment, medication or doses. Treatment decisions belong to qualified "
            "medical personnel under the mission's medical procedures.")
    if EMERGENCY.search(question):
        result.escalation_reasons.append(
            "The question describes a potentially serious situation. Contact the flight surgeon on duty now; "
            "this assistant cannot assess medical urgency.")
    return result


ESCALATION_TEXT = ("Escalate to qualified medical personnel: notify the flight surgeon on duty. "
                   "This assistant cannot judge medical urgency.")
