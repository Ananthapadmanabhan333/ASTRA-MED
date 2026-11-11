from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from app.detection.baseline import BaselineDetector
from app.detection.evaluator import AlertEvaluator
from app.detection.rules import THRESHOLD_RULES
from app.simulator.engine import VitalReading
from tests.conftest import T0

NORMAL = VitalReading(
    astronaut_id="AST-01",
    ts=T0,
    heart_rate=64,
    spo2=98,
    systolic=118,
    diastolic=76,
    temperature_c=36.8,
    respiratory_rate=14,
    activity_state="work",
    activity_met=1.7,
    rhythm="regular",
    hrv_rmssd_ms=40,
    scenario=None,
)


def feed(evaluator: AlertEvaluator, n: int, start: int = 0, **values):
    changes = []
    for i in range(start, start + n):
        reading = replace(NORMAL, ts=T0 + timedelta(seconds=i), **values)
        changes += evaluator.process(reading)
    return changes


def test_rule_limits_are_activity_aware():
    hr_high = next(r for r in THRESHOLD_RULES if r.key == "heart_rate:high")
    assert hr_high.breach(130, "work") == ("caution", 120)
    assert hr_high.breach(130, "exercise") is None
    assert hr_high.breach(150, "rest") == ("critical", 140)
    spo2 = next(r for r in THRESHOLD_RULES if r.key == "spo2:low")
    assert spo2.breach(93, "sleep") == ("caution", 94)
    assert spo2.breach(89, "work") == ("critical", 90)


def test_transient_spike_does_not_open_alert():
    ev = AlertEvaluator(persist_samples=5)
    assert feed(ev, 4, heart_rate=130) == []
    assert feed(ev, 3, start=4) == []
    assert ev.open_alerts() == []


def test_sustained_breach_opens_then_escalates():
    ev = AlertEvaluator(persist_samples=5)
    opened = feed(ev, 5, heart_rate=128)
    assert [c.kind for c in opened] == ["opened"]
    alert = opened[0].alert
    assert (alert.severity, alert.status, alert.metric) == ("caution", "active", "heart_rate")

    escalated = feed(ev, 3, start=5, heart_rate=146)
    assert [c.kind for c in escalated] == ["escalated"]
    assert alert.severity == "critical"
    assert alert.peak_value == 146


def test_escalation_reactivates_acknowledged_alert():
    ev = AlertEvaluator(persist_samples=3)
    alert = feed(ev, 3, spo2=93)[0].alert
    alert.status = "acknowledged"
    feed(ev, 1, start=3, spo2=88)
    assert (alert.status, alert.severity) == ("active", "critical")


def test_recovery_clears_condition_but_keeps_alert_open():
    ev = AlertEvaluator(persist_samples=3, clear_samples=5)
    alert = feed(ev, 3, temperature_c=38.0)[0].alert
    cleared = feed(ev, 5, start=3)
    assert [c.kind for c in cleared] == ["cleared"]
    assert alert.condition_cleared_at is not None
    assert alert.is_open  # an operator still has to resolve it

    recurred = feed(ev, 1, start=8, temperature_c=38.1)
    assert [c.kind for c in recurred] == ["recurred"]
    assert alert.condition_cleared_at is None


def test_release_allows_a_fresh_alert():
    ev = AlertEvaluator(persist_samples=3)
    first = feed(ev, 3, respiratory_rate=27)[0].alert
    ev.release(first.id)
    assert ev.open_alerts() == []
    second = feed(ev, 3, start=3, respiratory_rate=27)
    assert second and second[0].alert.id != first.id


def test_irregular_rhythm_opens_rhythm_alert():
    ev = AlertEvaluator(persist_samples=3)
    changes = feed(ev, 3, rhythm="irregular", hrv_rmssd_ms=240)
    assert changes[0].alert.category == "rhythm"
    assert changes[0].alert.severity == "caution"


def test_dirty_alerts_are_reported_once():
    ev = AlertEvaluator(persist_samples=2)
    feed(ev, 2, heart_rate=125)
    assert len(ev.pop_dirty()) == 1
    assert ev.pop_dirty() == []


def test_baseline_detector_flags_deviation_inside_fixed_limits():
    expected = {"heart_rate": 64.0, "respiratory_rate": 14.0, "spo2": 98.0}
    detector = BaselineDetector(lambda *_: expected)
    ev = AlertEvaluator(detector, persist_samples=5, baseline_persist_samples=10)
    assert feed(ev, 50) == []  # learning on normal data
    # 100 bpm is under the 120 bpm threshold but far above this person's baseline.
    changes = feed(ev, 10, start=50, heart_rate=100)
    assert [(c.kind, c.alert.category, c.alert.severity) for c in changes] == [
        ("opened", "baseline", "advisory")
    ]
    assert "above" in changes[0].alert.message


def test_baseline_advisory_suppressed_while_threshold_alert_open():
    expected = {"heart_rate": 64.0, "respiratory_rate": 14.0, "spo2": 98.0}
    ev = AlertEvaluator(BaselineDetector(lambda *_: expected), persist_samples=3, baseline_persist_samples=3)
    changes = feed(ev, 10, heart_rate=135)
    categories = {c.alert.category for c in changes}
    assert categories == {"threshold"}
