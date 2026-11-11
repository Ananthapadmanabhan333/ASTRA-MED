"""Alert lifecycle state machine.

    breach sustained for N samples ──► opened (active)
    worse severity while open ───────► escalated (re-activates an acknowledged alert)
    back within limits for M samples ► cleared (condition_cleared_at set; alert stays open)
    breach returns before resolution ► recurred
    operator resolves ───────────────► released; a new breach opens a new alert

Operators acknowledge and resolve alerts through the API; the evaluator never auto-resolves,
so a flight-surgeon decision is always recorded.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.detection.baseline import BaselineDetector
from app.detection.rules import (
    METRIC_LABELS,
    METRIC_UNITS,
    RHYTHM_RULE_KEY,
    RHYTHM_TITLE,
    SEVERITY_RANK,
    THRESHOLD_RULES,
    ThresholdRule,
)


@dataclass
class AlertRecord:
    id: str
    astronaut_id: str
    rule_key: str
    category: str  # "threshold" | "rhythm" | "baseline"
    metric: str
    direction: str
    severity: str
    status: str  # "active" | "acknowledged" | "resolved"
    title: str
    message: str
    unit: str
    trigger_value: float
    threshold_value: float | None
    peak_value: float
    opened_at: datetime
    updated_at: datetime
    activity_state: str | None = None
    scenario: str | None = None
    condition_cleared_at: datetime | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    operator_note: str | None = None

    @property
    def is_open(self) -> bool:
        return self.status != "resolved"


@dataclass(frozen=True)
class AlertChange:
    kind: str  # "opened" | "escalated" | "cleared" | "recurred"
    alert: AlertRecord


@dataclass
class _Track:
    breach: int = 0
    clear: int = 0
    alert: AlertRecord | None = None


def _fmt(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


class AlertEvaluator:
    def __init__(
        self,
        baseline: BaselineDetector | None = None,
        *,
        rules: Iterable[ThresholdRule] = THRESHOLD_RULES,
        persist_samples: int = 5,
        clear_samples: int = 10,
        baseline_persist_samples: int = 20,
    ) -> None:
        self.baseline = baseline
        self.rules = tuple(rules)
        self.persist_samples = persist_samples
        self.clear_samples = clear_samples
        self.baseline_persist_samples = baseline_persist_samples
        self._tracks: dict[tuple[str, str], _Track] = {}
        self._dirty: set[str] = set()

    # ------------------------------------------------------------------ public API ----
    def process(self, reading) -> list[AlertChange]:
        changes: list[AlertChange] = []
        open_metrics: set[str] = set()

        for rule in self.rules:
            value = reading.value(rule.metric)
            hit = rule.breach(value, reading.activity_state)
            message = None
            if hit:
                severity, threshold = hit
                relation = "above" if rule.direction == "high" else "below"
                message = (
                    f"{METRIC_LABELS[rule.metric]} {_fmt(value)} {rule.unit} is {relation} the "
                    f"{severity} limit of {_fmt(threshold)} {rule.unit} (activity: {reading.activity_state})."
                )
            change = self._advance(
                reading,
                key=rule.key,
                category="threshold",
                metric=rule.metric,
                direction=rule.direction,
                title=rule.title,
                unit=rule.unit,
                value=value,
                hit=hit,
                message=message,
                persist=self.persist_samples,
            )
            if change:
                changes.append(change)
            track = self._tracks.get((reading.astronaut_id, rule.key))
            if track and track.alert:
                open_metrics.add(rule.metric)

        rmssd = reading.hrv_rmssd_ms or 0.0
        rhythm_hit = ("caution", None) if reading.rhythm == "irregular" else None
        change = self._advance(
            reading,
            key=RHYTHM_RULE_KEY,
            category="rhythm",
            metric="hrv_rmssd_ms",
            direction="high",
            title=RHYTHM_TITLE,
            unit="ms",
            value=rmssd,
            hit=rhythm_hit,
            message=(
                f"Beat-to-beat intervals in the synthetic ECG are irregular (RMSSD {_fmt(rmssd)} ms)."
                if rhythm_hit
                else None
            ),
            persist=self.persist_samples,
        )
        if change:
            changes.append(change)

        if self.baseline is not None:
            for dev in self.baseline.evaluate(reading):
                hit = None
                message = None
                direction = "high" if dev.z > 0 else "low"
                if self.baseline.is_anomalous(dev) and dev.metric not in open_metrics:
                    hit = ("advisory", dev.expected)
                    delta = abs(dev.value - dev.expected)
                    relation = "above" if dev.z > 0 else "below"
                    unit = METRIC_UNITS[dev.metric]
                    message = (
                        f"{METRIC_LABELS[dev.metric]} {_fmt(dev.value)} {unit} is {_fmt(delta)} {unit} "
                        f"{relation} this crew member's expected {_fmt(dev.expected)} {unit} for the "
                        f"current activity (z = {dev.z:+.1f})."
                    )
                change = self._advance(
                    reading,
                    key=f"baseline:{dev.metric}",
                    category="baseline",
                    metric=dev.metric,
                    direction=direction,
                    title=f"{METRIC_LABELS[dev.metric]} off personal baseline",
                    unit=METRIC_UNITS[dev.metric],
                    value=dev.value,
                    hit=hit,
                    message=message,
                    persist=self.baseline_persist_samples,
                )
                if change:
                    changes.append(change)
        return changes

    def restore(self, alerts: Iterable[AlertRecord]) -> None:
        for alert in alerts:
            if alert.is_open:
                self._tracks.setdefault((alert.astronaut_id, alert.rule_key), _Track()).alert = alert

    def release(self, alert_id: str) -> None:
        for track in self._tracks.values():
            if track.alert and track.alert.id == alert_id:
                track.alert = None
                track.breach = 0
                track.clear = 0

    def find(self, alert_id: str) -> AlertRecord | None:
        for track in self._tracks.values():
            if track.alert and track.alert.id == alert_id:
                return track.alert
        return None

    def open_alerts(self) -> list[AlertRecord]:
        return [t.alert for t in self._tracks.values() if t.alert]

    def pop_dirty(self) -> list[AlertRecord]:
        out = [a for a in self.open_alerts() if a.id in self._dirty]
        self._dirty.clear()
        return out

    # ------------------------------------------------------------------- internals ----
    def _advance(
        self,
        reading,
        *,
        key: str,
        category: str,
        metric: str,
        direction: str,
        title: str,
        unit: str,
        value: float,
        hit: tuple[str, float | None] | None,
        message: str | None,
        persist: int,
    ) -> AlertChange | None:
        track = self._tracks.setdefault((reading.astronaut_id, key), _Track())
        alert = track.alert
        now: datetime = reading.ts

        if hit is None:
            track.breach = 0
            if alert and alert.condition_cleared_at is None:
                track.clear += 1
                if track.clear >= self.clear_samples:
                    alert.condition_cleared_at = now
                    alert.updated_at = now
                    self._dirty.add(alert.id)
                    return AlertChange("cleared", alert)
            return None

        severity, threshold = hit
        track.breach += 1
        track.clear = 0

        if alert is None:
            if track.breach < persist:
                return None
            alert = AlertRecord(
                id=uuid4().hex[:16],
                astronaut_id=reading.astronaut_id,
                rule_key=key,
                category=category,
                metric=metric,
                direction=direction,
                severity=severity,
                status="active",
                title=title,
                message=message or title,
                unit=unit,
                trigger_value=value,
                threshold_value=threshold,
                peak_value=value,
                opened_at=now,
                updated_at=now,
                activity_state=reading.activity_state,
                scenario=reading.scenario,
            )
            track.alert = alert
            self._dirty.add(alert.id)
            return AlertChange("opened", alert)

        worse = value > alert.peak_value if alert.direction == "high" else value < alert.peak_value
        if worse:
            alert.peak_value = value
            alert.updated_at = now
            self._dirty.add(alert.id)

        if SEVERITY_RANK[severity] > SEVERITY_RANK[alert.severity]:
            alert.severity = severity
            alert.threshold_value = threshold
            alert.message = message or alert.message
            alert.status = "active"
            alert.updated_at = now
            self._dirty.add(alert.id)
            return AlertChange("escalated", alert)

        if alert.condition_cleared_at is not None:
            alert.condition_cleared_at = None
            alert.status = "active"
            alert.updated_at = now
            self._dirty.add(alert.id)
            return AlertChange("recurred", alert)
        return None
