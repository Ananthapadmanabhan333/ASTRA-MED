"""Answers questions from retrieved passages and structured data, citing every statement.

Default mode ("extractive") runs offline: it gathers facts from ASTRA-MED's own services (each one a
citable record) and quotes the best-matching sentences of retrieved passages. Optional "claude" mode
sends the same records and passages, as citation-enabled documents, to the Anthropic API and keeps
only what Claude cites. Both modes pass through the same safety layer.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistant import ASSISTANT_DISCLAIMER
from app.assistant.corpus import (
    DOCS_DIR,
    KNOWLEDGE_DIR,
    SOURCE_TYPES,
    Passage,
    doc_passages,
    nasa_passages,
    reference_passages,
)
from app.assistant.parsing import Parsed, parse
from app.assistant.retrieval import Hit, PassageIndex, stem
from app.assistant.safety import EMERGENCY, ESCALATION_TEXT, SafetyResult, screen
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.timeutil import utcnow
from app.db.models import AstronautRow, EmergencyRunRow, IncidentReportRow, OsdrStudyRow, SpaceNotificationRow
from app.detection.rules import THRESHOLD_RULES
from app.medical.decision import SIGNIFICANT, packet
from app.repositories import alerts as alerts_repo
from app.security.rbac import Principal
from app.services.monitoring import MonitoringService
from app.space.intel import weather_summary
from app.twin import summary as S
from app.twin import views as twin_views
from app.twin.service import TwinService

logger = logging.getLogger("astra.assistant")

KIND_LABELS = {
    "data": "Simulated data record",
    "derived": "Statistic computed from simulated data",
    "model": "Experimental model output (not clinically validated)",
    "nasa": "Real NASA public data",
    "documentation": "ASTRA-MED documentation (how the system works)",
    "reference": "Approved reference document",
    "safety": "Safety notice",
    "configured": "ASTRA-MED configuration (prototype setting, not a clinical criterion)",
}
MEDICAL_KNOWLEDGE = re.compile(r"\b(normal range|healthy|safe|dangerous|risk of|cause[sd]?|effects? of|health effect|"
                               r"symptom|clinical|physiolog\w*|why does .* (rise|fall|drop|increase))\b", re.I)
STOP = set("the a an of to in on for and or is are was were be been with what why how does do did this that it "
           "its from by at as about me show tell give please can you i we our their his her".split())
INDEX_TTL_S = 3600.0
QUOTE_MIN = 0.10  # passages below this are not quoted
DATA_QUOTE_MIN = 0.20  # stricter when the question is about crew data rather than documentation
KNOWLEDGE_TASKS = {"measurement", "environment", "history"}


@dataclass
class Source:
    id: str
    kind: str
    title: str
    detail: str | None = None
    excerpt: str | None = None
    url: str | None = None
    path: str | None = None
    link: str | None = None  # route in the ASTRA-MED frontend
    score: float | None = None
    source_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "kind_label": KIND_LABELS[self.kind]}


@dataclass
class Draft:
    statements: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    escalation: list[str] = field(default_factory=list)

    def record(self, text: str, kind: str, title: str, *, link: str | None = None, detail: str | None = None) -> str:
        sid = f"D{sum(1 for s in self.sources if s.id.startswith('D')) + 1}"
        self.sources.append(Source(sid, kind, title, detail=detail, excerpt=text, link=link))
        self.statements.append({"text": text, "citations": [sid], "kind": kind})
        return sid

    def passage(self, hit: Hit, excerpt: str) -> str:
        p = hit.passage
        sid = f"S{sum(1 for s in self.sources if s.id.startswith('S')) + 1}"
        kind = {"astra_docs": "documentation", "reference": "reference"}.get(p.source_type, "nasa")
        self.sources.append(Source(sid, kind, p.title, detail=p.section, excerpt=excerpt, url=p.url, path=p.path,
                                   score=hit.score, source_type=p.source_type))
        return sid


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s) > 20]


def _tokens(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9₂]+", text.lower()) if w not in STOP and len(w) > 2}


def best_excerpt(passage: Passage, question: str, max_sentences: int = 2) -> str:
    """Best-matching run of consecutive sentences, quoted verbatim from the passage."""
    q = _tokens(question)
    sents = _sentences(passage.text)
    if not sents:
        return passage.text[:400]
    best = max(range(len(sents)), key=lambda i: (len(q & _tokens(" ".join(sents[i:i + max_sentences]))), -i))
    excerpt = sents[best]
    for nxt in sents[best + 1: best + max_sentences]:
        if len(excerpt) + len(nxt) > 600:
            break
        excerpt = f"{excerpt} {nxt}"
    return excerpt


def _fmt(v: Any, unit: str = "") -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        v = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v} {unit}".strip()


class AssistantService:
    def __init__(self, settings: Settings, factory: async_sessionmaker[AsyncSession], monitor: MonitoringService,
                 ai, twin: TwinService, multisystem) -> None:
        self.settings = settings
        self.factory = factory
        self.monitor = monitor
        self.ai = ai
        self.twin = twin
        self.multisystem = multisystem
        self._index: PassageIndex | None = None
        self._index_key: tuple | None = None
        self.references: list[dict[str, Any]] = []

    # ------------------------------------------------------------------- corpus ----
    async def index(self, session: AsyncSession) -> PassageIndex:
        n_notes = await session.scalar(select(func.count()).select_from(SpaceNotificationRow)) or 0
        n_studies = await session.scalar(select(func.count()).select_from(OsdrStudyRow)) or 0
        key = (n_notes, n_studies)
        stale = self._index is None or time.time() - self._index.built_at > INDEX_TTL_S
        if stale or key != self._index_key:
            s = self.settings
            refs, self.references = reference_passages(Path(s.assistant_knowledge_dir) if s.assistant_knowledge_dir else KNOWLEDGE_DIR)
            docs = doc_passages(Path(s.assistant_docs_dir) if s.assistant_docs_dir else DOCS_DIR)
            passages = [*docs, *await nasa_passages(session), *refs]
            self._index = PassageIndex(passages)
            self._index_key = key
            logger.info("assistant index built: %d passages", len(passages))
        return self._index

    def mode(self) -> dict[str, Any]:
        requested = self.settings.assistant_mode.strip().lower()
        if requested != "claude":
            return {"mode": "extractive", "requested": requested, "available": True, "reason": None}
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return {"mode": "extractive", "requested": "claude", "available": False,
                    "reason": "The optional 'anthropic' package is not installed."}
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {"mode": "extractive", "requested": "claude", "available": False,
                    "reason": "ANTHROPIC_API_KEY is not set in the backend environment."}
        return {"mode": "claude", "requested": "claude", "available": True, "reason": None,
                "model": self.settings.assistant_model}

    async def status(self) -> dict[str, Any]:
        async with self.factory() as session:
            idx = await self.index(session)
        counts: dict[str, int] = {}
        for p in idx.passages:
            counts[p.source_type] = counts.get(p.source_type, 0) + 1
        return {
            "mode": self.mode(), "passages": len(idx.passages), "by_source": counts,
            "source_types": [{"key": k, **v, "passages": counts.get(k, 0)} for k, v in SOURCE_TYPES.items()],
            "references": self.references, "built_at": idx.built_at,
            "reference_note": None if counts.get("reference") else (
                "No approved reference documents are installed (backend/knowledge/manifest.json). The assistant "
                "therefore cannot cite aerospace-medicine literature and says so when a question needs it."),
            "disclaimer": ASSISTANT_DISCLAIMER,
        }

    # ---------------------------------------------------------------------- ask ----
    async def ask(self, question: str, principal: Principal, context_astronaut: str | None = None) -> dict[str, Any]:
        now = utcnow()
        question = question.strip()
        crew = self.monitor.engine.profiles
        parsed = parse(question, crew)
        if not parsed.astronaut_ids and context_astronaut in crew:
            parsed.astronaut_ids = [context_astronaut]
        safety = screen(question)
        draft = Draft()
        async with self.factory() as session:
            await self._collect(session, draft, parsed, principal, question, now)
            idx = await self.index(session)
        names = {w.lower() for prof in crew.values() for w in prof.name.split()}
        words = [w for w in question.split() if w.strip("?.,!'").lower() not in names]
        query = " ".join([*words, *(S.LABELS.get(m, m) for m in parsed.metrics)])
        types = None if "environment" in parsed.tasks else ("astra_docs", "reference")
        hits = idx.search(query, k=self.settings.assistant_max_passages, source_types=types)
        if not hits and types:
            hits = idx.search(query, k=self.settings.assistant_max_passages)
        self._missing(draft, parsed, hits, question)
        mode = self.mode()
        result_mode = "extractive"
        model_note = None
        if mode["mode"] == "claude":
            try:
                await self._claude(draft, hits, question, safety)
                result_mode = "claude"
            except Exception as exc:  # any API/SDK failure falls back to the offline answer
                logger.warning("claude mode failed, falling back to extractive: %s", exc.__class__.__name__)
                model_note = f"Claude mode failed ({exc.__class__.__name__}); showing the offline answer."
                self._extractive(draft, hits, question, parsed.tasks)
        else:
            self._extractive(draft, hits, question, parsed.tasks)
        if mode["requested"] == "claude" and not mode["available"]:
            model_note = f"Claude mode is configured but unavailable: {mode['reason']} Showing the offline answer."
        return self._finish(draft, safety, parsed, question, now, result_mode, model_note)

    # ---------------------------------------------------------------- collecting ----
    async def _collect(self, session: AsyncSession, d: Draft, p: Parsed, principal: Principal, question: str, now) -> None:
        crew = self.monitor.engine.profiles
        targets = p.astronaut_ids or (list(crew) if p.crew_wide else [])
        hours = p.hours or 24
        tasks = set(p.tasks)
        knowledge_only = bool(MEDICAL_KNOWLEDGE.search(question)) and not p.astronaut_ids and not p.crew_wide
        if not targets and not knowledge_only \
                and tasks & {"status", "data_question", "anomaly", "records", "trend", "history"} \
                and not tasks & {"measurement", "environment"}:
            targets = list(crew)
            d.missing.append("No crew member was named, so this covers the whole crew. Name one (e.g. AST-02 or "
                             "a first name) for detail.")
        detailed = len(targets) == 1
        for m in p.metrics:
            rules = [r for r in THRESHOLD_RULES if r.metric == m]
            if rules and (knowledge_only or "measurement" in tasks):
                d.record("ASTRA-MED prototype alert limits for " + S.LABELS.get(m, m).lower() + ": " + "; ".join(
                    f"{r.title}: caution {r.caution:g}, critical {r.critical:g} {r.unit}" for r in rules)
                    + ". These exercise the software and are not clinical criteria.", "configured",
                    f"Alert rules ({m})", link="/alerts", detail="app/detection/rules.py")

        for aid in targets:
            name = crew[aid].name
            if tasks & {"status", "data_question", "measurement", "anomaly"}:
                await self._status(session, d, aid, name, p, now, detailed)
            if detailed and (tasks & {"trend", "history"} or p.hours and p.hours >= 72):
                await self._trends(d, aid, name, p, max(7, (p.hours or 720) // 24) if "history" not in tasks else None)
            if "sleep" in p.metrics and detailed:
                await self._sleep(d, aid, name)
            if tasks & {"anomaly", "incident_report"} or p.alert_id:
                await self._alerts(session, d, aid, name, hours if p.hours else 72, principal, explain=detailed, now=now,
                                   alert_id=p.alert_id, report="incident_report" in tasks)
            elif "records" in tasks:
                await self._alerts(session, d, aid, name, hours if p.hours else 72, principal, explain=False, now=now)
            if "records" in tasks and re.search(r"report", question, re.I):
                await self._reports(session, d, aid, name, principal)
            if "dose" in p.metrics or ("environment" in tasks and detailed):
                await self._dose(d, aid, name)
        if "environment" in tasks:
            await self._space(session, d, now, max(1, (p.hours or 720) // 24))
        if re.search(r"emergency|simulat\w* run|test scenario", question, re.I):
            runs = (await session.scalars(select(EmergencyRunRow).order_by(EmergencyRunRow.started_at.desc()).limit(5))).all()
            for r in runs:
                d.record(f"Simulated emergency run '{r.label}' ({r.severity}) started {r.started_at:%Y-%m-%d %H:%M} UTC"
                         f"{' for ' + crew[r.astronaut_id].name if r.astronaut_id else ' (whole crew)'}.",
                         "data", f"Emergency run {r.id}", link=f"/emergency?run={r.id}")

    async def _status(self, session, d: Draft, aid: str, name: str, p: Parsed, now, detailed: bool) -> None:
        reading = self.monitor.latest_reading(aid)
        metrics = [m for m in p.metrics if m in S.METRICS] or (list(S.METRICS[:6]) if detailed else ["heart_rate", "spo2"])
        if reading is not None:
            parts = [f"{S.LABELS[m]} {_fmt(getattr(reading, m), S.UNITS[m])}" for m in metrics if getattr(reading, m) is not None]
            d.record(f"Latest simulated reading for {name} ({reading.ts:%H:%M:%S} UTC, {reading.activity_state}): "
                     + ", ".join(parts) + ".", "data", f"Latest reading, {aid}", link=f"/crew/{aid}")
        try:
            ms = await self.multisystem.assess(session, aid, now)
        except ApiError:
            ms = None
        if ms:
            d.record(f"Multisystem assessment for {name}: {ms['summary']}", "derived", f"Multisystem assessment, {aid}",
                     link=f"/medical?astronaut={aid}")
            for s in ms["systems"]:
                if s["status"] in ("deviation", "marked_deviation") and (detailed or s["status"] == "marked_deviation"):
                    d.record(f"{s['label']} ({name}): {s['explanation']}", "derived", f"{s['label']} system, {aid}",
                             link=f"/medical?astronaut={aid}")
            for pat in ms["patterns"]:
                d.record(f"Cross-system pattern for {name}: {pat['label']}. This is co-occurrence, not a cause.",
                         "derived", f"Pattern {pat['key']}, {aid}", link=f"/medical?astronaut={aid}")
            if ms.get("ai") and detailed:
                ai = ms["ai"]
                d.record(f"Phase 3 risk rules for {name}: {ai['category_label']} (score {ai['risk_score']:.0f}/100, "
                         f"confidence {ai['confidence']['level']}).", "model", f"AI risk assessment, {aid}",
                         link=f"/intelligence?astronaut={aid}")
            marked = [s["label"] for s in ms["systems"] if s["status"] == "marked_deviation"]
            if ms["patterns"] or len(marked) >= 2:
                d.escalation.append(f"{name}: concurrent or marked deviations ({', '.join(marked) or ms['patterns'][0]['label']}).")
        if detailed and set(p.metrics) & set(S.METRICS):
            try:
                await self.twin.ensure(aid)
                async with self.factory() as s2:
                    row = await s2.get(AstronautRow, aid)
                    prof = await twin_views.profile(self.twin, self.ai, s2, row, self.monitor, now)
                for c in prof["resting_comparison"]:
                    if c["metric"] in p.metrics:
                        d.record(f"{c['label']} for {name} at rest (awake, no test scenario): last 24 h "
                                 f"{_fmt(c['last_24h']['value'], c['unit'])}, last 7 days {_fmt(c['last_7d']['value'], c['unit'])}, "
                                 f"early mission {_fmt(c['early_mission']['value'], c['unit'])}; configured simulator value "
                                 f"{_fmt(c['configured']['value'], c['unit'])}.", "derived", f"Twin resting comparison, {aid}",
                                 link=f"/twin?astronaut={aid}")
            except ApiError:
                pass

    async def _trends(self, d: Draft, aid: str, name: str, p: Parsed, days: int | None) -> None:
        metrics = [m for m in p.metrics if m in S.METRICS] or ["heart_rate"]
        first = utcnow().date() - timedelta(days=days - 1) if days else None
        await self.twin.ensure(aid)
        rows = await self.twin.days(aid, first)
        for m in metrics[:3]:
            t = twin_views.trend(rows, m, "awake_rest_mean")
            fit = t["trend"]
            vals = [x["value"] for x in t["points"] if x["value"] is not None]
            if not vals:
                d.missing.append(f"No daily {S.LABELS[m].lower()} values for {name} in that period.")
                continue
            span = f"{t['points'][0]['day']} to {t['points'][-1]['day']}"
            text = (f"{S.LABELS[m]} at rest for {name}, {span}: daily mean {min(vals):.1f}–{max(vals):.1f} {S.UNITS[m]}")
            if fit:
                text += (f"; trend {fit['slope_per_30d']:+.2f} {S.UNITS[m]} per 30 days (95% CI {fit['ci95'][0]:+.2f} to "
                         f"{fit['ci95'][1]:+.2f}), {fit['direction']}")
            regenerated = sum(1 for x in t["points"] if x["basis"] == "regenerated")
            if regenerated:
                text += f"; {regenerated} of {len(t['points'])} days are regenerated by the simulator (pruned samples)"
            d.record(text + ".", "derived", f"Twin trend {m}, {aid}", link=f"/twin?astronaut={aid}")

    async def _sleep(self, d: Draft, aid: str, name: str) -> None:
        rows = [r for r in await self.twin.days(aid, utcnow().date() - timedelta(days=8)) if r.sleep]
        for r in rows[-3:]:
            s = r.sleep
            d.record(f"{name}, night of {r.day}: {s['duration_hours']:.1f} h asleep, efficiency {s['efficiency_pct']:.0f}% "
                     f"({'stored' if s['basis'] == 'stored' else 'regenerated'} simulated record).", "data",
                     f"Sleep record {r.day}, {aid}", link=f"/sleep?astronaut={aid}")
        ov = self.multisystem.overlays(aid) if self.multisystem.overlays else None
        if ov:
            d.record(f"A sleep-disruption test run is active for {name}; its what-if overlay shortens "
                     f"{len(ov['nights'])} recent nights (stored records are unchanged).", "data",
                     f"Sleep overlay, {aid}", link="/emergency")

    async def _dose(self, d: Draft, aid: str, name: str) -> None:
        rows = await self.twin.days(aid)
        total = sum((r.radiation or {}).get("dose_msv", 0.0) for r in rows)
        last = next((r for r in reversed(rows) if r.radiation), None)
        if last:
            d.record(f"Simulated crew dose for {name}: {total:.1f} mSv since mission start; {last.radiation['dose_msv']:.2f} mSv "
                     f"on {last.day}. Simulated values, never combined with real NASA dosimetry.", "data",
                     f"Simulated dosimetry, {aid}", link="/radiation")

    async def _alerts(self, session, d: Draft, aid: str, name: str, hours: int, principal: Principal, *, explain: bool,
                      now, alert_id: str | None = None, report: bool = False) -> None:
        rows = await alerts_repo.list_alerts(session, astronaut_id=aid, since=now - timedelta(hours=hours), limit=50)
        if alert_id:
            one = await alerts_repo.get(session, alert_id)
            rows = [one] if one and one.astronaut_id == aid else rows
        if not rows:
            d.record(f"No alerts for {name} in the last {hours} h.", "data", f"Alert log, {aid}", link=f"/alerts?astronaut={aid}")
            return
        counts: dict[str, int] = {}
        for r in rows:
            counts[r.severity] = counts.get(r.severity, 0) + 1
        d.record(f"{name}: {len(rows)} alert(s) in the last {hours} h ("
                 + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) + "). Most recent: "
                 + "; ".join(f"{r.title} ({r.severity}, {r.status}, {r.opened_at:%m-%d %H:%M} UTC)" for r in rows[:3]) + ".",
                 "data", f"Alert log, {aid}", link=f"/alerts?astronaut={aid}")
        if any(r.severity == "critical" and r.status != "resolved" for r in rows):
            d.escalation.append(f"{name} has an unresolved critical alert.")
        target = next((r for r in rows if r.id == alert_id), None) or next(
            (r for r in rows if r.severity in SIGNIFICANT), rows[0])
        if explain:
            rec = self.monitor.evaluator.find(target.id) or alerts_repo.row_to_record(target)
            pk = await packet(session, self.monitor, self.ai, self.multisystem, rec, now, include_multisystem=False)
            obs = pk["observation"]
            d.record(f"Alert '{obs['title']}' ({obs['severity']}) for {name}: {obs['message']}", "data",
                     f"Alert {target.id}", link=f"/medical?alert={target.id}")
            if obs["simulated_test_scenario"]:
                d.record(f"A simulated test scenario ('{obs['simulated_test_scenario']}') was running when this alert opened; "
                         "the deviation was injected by the simulator.", "data", f"Scenario log, alert {target.id}",
                         link=f"/medical?alert={target.id}")
            contrib = pk["baseline_comparison"].get("contributors") or []
            if contrib:
                d.record("Against the personal baseline: " + "; ".join(
                    f"{c['label']} {_fmt(c.get('value'), c.get('unit', ''))} vs {_fmt(c.get('baseline'), c.get('unit', ''))}"
                    f" (z {c['z']:+.1f})" for c in contrib[:3] if c.get("z") is not None) + ".", "derived",
                         f"Baseline comparison, alert {target.id}", link=f"/medical?alert={target.id}")
            ai = pk["ai_output"]
            if ai.get("available"):
                peak = ai.get("anomaly_peak") or {}
                d.record(f"Anomaly models classified the pattern as '{(ai.get('kind') or '').replace('_', ' ')}'"
                         + (f"; peak ensemble score {peak.get('ensemble_score')}× threshold with {peak.get('votes')} detectors"
                            if peak else "") + f" (model {ai.get('model_version')}).", "model",
                         f"Anomaly ensemble, alert {target.id}", link=f"/medical?alert={target.id}")
            esc = pk["review_workflow"]["escalation"]
            d.record(f"Review workflow: {esc['label']} ({esc['who']}).", "data", f"Review workflow, alert {target.id}",
                     link=f"/medical?alert={target.id}")
        if report:
            if principal.can("reports:write"):
                d.actions.append({"type": "create_report", "alert_id": target.id,
                                  "label": f"Create a draft incident report for '{target.title}'"})
            else:
                d.missing.append("Your role cannot create incident reports (needs reports:write).")

    async def _reports(self, session, d: Draft, aid: str, name: str, principal: Principal) -> None:
        if not principal.can("reports:read"):
            d.missing.append("Your role cannot read incident reports.")
            return
        rows = (await session.scalars(select(IncidentReportRow).where(IncidentReportRow.astronaut_id == aid)
                                      .order_by(IncidentReportRow.created_at.desc()).limit(5))).all()
        if not rows:
            d.record(f"No incident reports for {name}.", "data", f"Reports, {aid}", link="/reports")
        for r in rows:
            d.record(f"Incident report '{r.title}' for {name}, {r.occurred_at:%Y-%m-%d %H:%M} UTC, status {r.review_status}.",
                     "data", f"Report {r.id}", link=f"/reports?report={r.id}")

    async def _space(self, session, d: Draft, now, days: int) -> None:
        days = min(days, 90)
        ws = await weather_summary(session, now, days)
        counts = ws["counts"]
        if not any(counts.values()):
            d.missing.append("No NASA DONKI events are stored for that period (synchronisation may not have run).")
            return
        fl = ws["strongest_flare"]
        text = (f"NASA DONKI, last {days} days: {counts.get('FLR', 0)} flares, {counts.get('CME', 0)} CMEs, "
                f"{counts.get('SEP', 0)} SEP events, {counts.get('GST', 0)} geomagnetic storms")
        if fl is not None:
            text += f"; strongest flare {fl.classification} at {fl.start_time:%Y-%m-%d %H:%M} UTC"
        d.record(text + ". These are environmental indicators, not crew doses.", "nasa", f"DONKI summary, {days} days",
                 link="/space/weather")

    # ----------------------------------------------------------------- composing ----
    def _missing(self, d: Draft, p: Parsed, hits: list[Hit], question: str) -> None:
        if MEDICAL_KNOWLEDGE.search(question) and not any(h.passage.source_type == "reference" for h in hits):
            d.missing.append("This needs aerospace-medicine reference material, and no approved reference documents "
                             "are installed (backend/knowledge/manifest.json). I can't cite medical literature for it.")
        if not any(h.score >= QUOTE_MIN for h in hits) and (set(p.tasks) & KNOWLEDGE_TASKS or not d.statements):
            d.missing.append("No documentation or NASA passage matched the question closely enough to cite.")
        if EMERGENCY.search(question):
            d.missing.append("ASTRA-MED holds no symptom reports or examinations; the simulated measurements can "
                             "neither confirm nor rule out what was described.")
        if "hrv_rmssd_ms" in p.metrics:
            d.missing.append("HRV (RMSSD) exists only for live samples with ECG; backfilled history has none.")

    def _extractive(self, d: Draft, hits: list[Hit], question: str, tasks: list[str]) -> None:
        knowledge = bool(set(tasks) & KNOWLEDGE_TASKS) or not d.statements
        floor, limit = (QUOTE_MIN, 3) if knowledge else (DATA_QUOTE_MIN, 1)
        for h in [h for h in hits if h.score >= floor][:limit]:
            excerpt = best_excerpt(h.passage, question)
            sid = d.passage(h, excerpt)
            label = SOURCE_TYPES[h.passage.source_type]["label"]
            where = f"{h.passage.title}" + (f", {h.passage.section}" if h.passage.section else "")
            d.statements.append({"text": f"{label} ({where}): “{excerpt}”", "citations": [sid],
                                 "kind": {"astra_docs": "documentation", "reference": "reference"}.get(h.passage.source_type, "nasa")})

    async def _claude(self, d: Draft, hits: list[Hit], question: str, safety: SafetyResult) -> None:
        import anthropic

        records = [s for s in d.sources if s.id.startswith("D")]
        passage_sources = [d.passage(h, h.passage.text) for h in hits]
        all_sources = records + [s for s in d.sources if s.id in passage_sources]
        documents = [{
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": s.excerpt or ""},
            "title": f"[{s.id}] {KIND_LABELS[s.kind]}: {s.title}"[:250],
            "citations": {"enabled": True},
        } for s in all_sources]
        system = (
            "You are the ASTRA-MED medical data assistant for a research prototype. All crew data is simulated and "
            "crew members are fictional. Answer only from the provided documents and cite them. Each document title "
            "says what it is: simulated data record, statistic, experimental model output, real NASA data, or "
            "ASTRA-MED documentation. Keep those apart and say which is which. Never diagnose, never name a medical "
            "condition, never recommend treatment, medication or doses. If the documents do not answer the question, "
            "say what information is missing. Be concise."
        )
        if safety.declined:
            system += " The user asked for a diagnosis or treatment: decline that part and explain only the data."
        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=self.settings.assistant_model, max_tokens=2000, thinking={"type": "adaptive"}, system=system,
            messages=[{"role": "user", "content": [*documents, {"type": "text", "text": question}]}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model refused")
        statements = []
        for block in response.content:
            if block.type != "text":
                continue
            cites = []
            for c in getattr(block, "citations", None) or []:
                i = getattr(c, "document_index", None)
                if i is not None and 0 <= i < len(all_sources):
                    cites.append(all_sources[i].id)
            text = block.text.strip()
            if text:
                kinds = {next(s.kind for s in all_sources if s.id == c) for c in cites}
                statements.append({"text": text, "citations": sorted(set(cites)),
                                   "kind": kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "uncited")})
        cited = {c for s in statements for c in s["citations"]}
        d.statements = statements
        d.sources = [s for s in d.sources if s.id in cited]

    def _finish(self, d: Draft, safety: SafetyResult, p: Parsed, question: str, now, mode: str,
                model_note: str | None) -> dict[str, Any]:
        statements = []
        for text in safety.declined:
            statements.append({"text": text, "citations": [], "kind": "safety"})
        statements += d.statements
        reasons = [*safety.escalation_reasons, *d.escalation]
        escalation = {"required": bool(reasons), "reasons": reasons,
                      "message": ESCALATION_TEXT if reasons else None, "who": "Flight surgeon on duty" if reasons else None}
        if reasons:
            statements.append({"text": ESCALATION_TEXT, "citations": [], "kind": "safety"})
        answer = "\n".join(
            f"{s['text']}" + (" " + " ".join(f"[{c}]" for c in s["citations"]) if s["citations"] else "") for s in statements)
        if not d.statements and not safety.declined:
            answer = "I could not find data or documentation that answers this question."
        return {
            "question": question, "generated_at": now, "mode": mode, "model_note": model_note,
            "answer": answer, "statements": statements, "sources": [s.to_dict() for s in d.sources],
            "missing_information": list(dict.fromkeys(d.missing)), "declined": safety.declined,
            "escalation": escalation, "actions": d.actions,
            "understood": {"tasks": p.tasks, "astronaut_ids": p.astronaut_ids, "metrics": p.metrics, "hours": p.hours},
            "knowledge_types": [{"key": k, "label": v} for k, v in KIND_LABELS.items()],
            "disclaimer": ASSISTANT_DISCLAIMER, "data_source": "simulated",
        }
