/**
 * Demo mode: which of the twelve guided steps are satisfied, judged only from backend responses.
 *
 * Every value a step shows is copied from an API response (sandbox state, stored run, sandbox
 * alerts, AI analysis, frame, NASA space-weather summary, assistant answer, incident report).
 * Nothing is estimated, interpolated or generated here; a step whose evidence is missing says so.
 */

import type {
  AssistantAnswer,
  MissionAlert,
  SimFrame,
  SimRun,
  SimState,
  WeatherSummary,
} from "@/lib/api/types";

// ------------------------------------------------------------- analysis shape ----

/** One crew member's entry in `analyses` (POST /analyze and the stored run), as sandbox.py builds it. */
export interface CrewAnalysis {
  available: boolean;
  reason?: string;
  sim_time?: string;
  model_version?: string;
  risk?: {
    risk_score: number;
    category: string;
    category_label: string;
    health_score?: number;
    warnings?: { title: string; detail?: string; source?: string; points?: number }[];
    confidence?: { score?: number; level: string; basis?: string[] };
    what_changed?: string;
    anomaly?: { available: boolean; score?: number | null; votes?: number; n_detectors?: number; kind?: string | null };
    contributors?: {
      signal: string;
      label: string;
      share: number;
      value?: number | null;
      unit?: string;
      baseline?: number | null;
      z?: number | null;
      direction?: string | null;
    }[];
  };
  detections?: {
    start: string;
    end?: string;
    kind: string | null;
    peak_score: number;
    signals: string[];
    votes?: number;
    duration_minutes?: number;
  }[];
  flagged_windows?: number;
  windows?: number;
  forecast?:
    | {
        signal: string;
        label: string;
        unit: string;
        horizons: { horizon_h: number; value: number; lower: number; upper: number; crossing: string | null }[];
      }[]
    | null;
  forecast_error?: string | null;
  limitations?: string[];
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** The per-crew entries of an `analyses` object (keys starting with "_" are bookkeeping, e.g. `_last`). */
export function parseAnalyses(analyses: unknown): Record<string, CrewAnalysis> {
  if (!isRecord(analyses)) return {};
  const out: Record<string, CrewAnalysis> = {};
  for (const [k, v] of Object.entries(analyses)) {
    if (k.startsWith("_") || !isRecord(v) || typeof v.available !== "boolean") continue;
    out[k] = v as unknown as CrewAnalysis;
  }
  return out;
}

/** The newer of two analyses by their simulation time (either may be missing). */
export function pickAnalysis(a: CrewAnalysis | null | undefined, b: CrewAnalysis | null | undefined): CrewAnalysis | null {
  if (!a) return b ?? null;
  if (!b) return a;
  const ta = a.sim_time ? Date.parse(a.sim_time) : -Infinity;
  const tb = b.sim_time ? Date.parse(b.sim_time) : -Infinity;
  return tb >= ta ? b : a;
}

/** Per crew member, the newer of the stored analysis and the one an on-request /analyze call returned. */
export function mergeAnalyses(
  stored: Record<string, CrewAnalysis>,
  fresh: Record<string, CrewAnalysis>,
): Record<string, CrewAnalysis> {
  const out: Record<string, CrewAnalysis> = {};
  for (const k of new Set([...Object.keys(stored), ...Object.keys(fresh)])) {
    const v = pickAnalysis(stored[k], fresh[k]);
    if (v) out[k] = v;
  }
  return out;
}

// ---------------------------------------------------------------- helpers ----

/** "T+HH:MM:SS" between the run start and an instant (both ISO strings). */
export function tPlus(start: string, at: string): string {
  const s = Math.max(0, Math.round((Date.parse(at) - Date.parse(start)) / 1000));
  const p = (n: number) => String(n).padStart(2, "0");
  return `T+${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

const num = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d);

const words = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ");

const statNumber = (stats: unknown, key: string): number | null => {
  if (!isRecord(stats)) return null;
  const v = stats[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
};

/**
 * The crew member the demo follows by default: the target of the run's first scripted crew-specific
 * injection (from the stored run config), otherwise the first crew member of the run.
 */
export function defaultFocus(run: Pick<SimRun, "config"> | null | undefined, crew: string[]): string | null {
  const script = isRecord(run?.config) && Array.isArray(run.config.script) ? run.config.script : [];
  for (const step of script) {
    if (isRecord(step) && typeof step.astronaut_id === "string" && crew.includes(step.astronaut_id)) return step.astronaut_id;
  }
  return crew[0] ?? null;
}

/** The alert the demo reviews: highest priority (lowest number), then earliest, preferring the focus crew member. */
export function pickFocusAlert(alerts: MissionAlert[] | null | undefined, focusId: string | null): MissionAlert | null {
  if (!alerts?.length) return null;
  const order = (a: MissionAlert, b: MissionAlert) => a.priority - b.priority || Date.parse(a.created_at) - Date.parse(b.created_at);
  const mine = alerts.filter((a) => focusId && a.astronaut_id === focusId).sort(order);
  if (mine.length) return mine[0];
  const withCrew = alerts.filter((a) => a.astronaut_id).sort(order);
  return withCrew[0] ?? [...alerts].sort(order)[0];
}

/** Forecast values per signal at the 6 h horizon when present, otherwise at the furthest horizon. */
export function forecastHighlights(forecast: CrewAnalysis["forecast"], limit = 3) {
  const out: { label: string; unit: string; horizon_h: number; value: number; lower: number; upper: number }[] = [];
  for (const s of forecast ?? []) {
    if (!s.horizons?.length) continue;
    const h = s.horizons.find((x) => x.horizon_h === 6) ?? s.horizons[s.horizons.length - 1];
    out.push({ label: s.label, unit: s.unit, horizon_h: h.horizon_h, value: h.value, lower: h.lower, upper: h.upper });
    if (out.length >= limit) break;
  }
  return out;
}

/** Statements that carry at least one citation. */
export function citedStatements(answer: AssistantAnswer | null | undefined) {
  return (answer?.statements ?? []).filter((s) => s.citations.length > 0);
}

/** Space-weather freshness modes in which stored NASA records are being served. */
const NASA_SERVED = new Set(["live", "cached", "offline-fallback"]);

// ------------------------------------------------------------------- steps ----

export type StepStatus = "done" | "waiting" | "action" | "locked" | "blocked" | "unavailable";

export interface Evidence {
  label: string;
  value: string;
}

export interface StepResult {
  id: number;
  title: string;
  status: StepStatus;
  /** What was observed, or what the step is waiting for. */
  summary: string;
  evidence: Evidence[];
  href?: string;
  hrefLabel?: string;
}

export const STEP_TITLES = [
  "Mission control initializes the astronaut profile",
  "Physiological data begins streaming",
  "Personalized baseline is established",
  "Monitoring engine detects deviations",
  "AI engine identifies an unusual pattern",
  "Forecasting models estimate future trends",
  "Space environment data is retrieved",
  "Digital twin updates",
  "Medical assistant explains available evidence",
  "Mission control receives a prioritized alert",
  "The operator reviews the incident",
  "A structured incident report is generated",
] as const;

/** Fields shared by IncidentReport and ReportSummary. */
export interface ReportLike {
  id: string;
  title: string;
  integrity: "intact" | "modified";
  content_sha256: string;
  review_status_label: string;
  source_kind: string;
  simulation_id?: string | null;
  created_at: string;
}

export interface DemoPermissions {
  control: boolean;
  manageAlerts: boolean;
  writeReports: boolean;
  assistant: boolean;
}

export interface DemoInputs {
  /** The sandbox state of the run the demo follows; null when no run is followed. */
  state: SimState | null;
  /** The stored run (GET /api/mission-sim/runs/{id}). */
  run?: SimRun | null;
  /** The preset's label from the catalogue, when the run used one. */
  presetLabel?: string | null;
  focusId: string | null;
  /** Display names by crew id (from the run's latest readings or the crew list). */
  names?: Record<string, string>;
  /** Roles by crew id (from GET /api/astronauts), optional. */
  roles?: Record<string, string>;
  /** The newest analysis of the focus crew member. */
  analysis: CrewAnalysis | null;
  /** Every crew member's newest analysis, to point at others that were flagged. */
  analyses?: Record<string, CrewAnalysis>;
  /** Sandbox alerts for the run (context=simulation, simulation_id); undefined while loading. */
  alerts?: MissionAlert[];
  alertsError?: string | null;
  /** Frame at the analysis time (GET /frame?at=analysis.sim_time). */
  frame?: SimFrame | null;
  weather?: WeatherSummary | null;
  weatherError?: string | null;
  /** Assistant answer for this run and focus crew member. */
  answer?: AssistantAnswer | null;
  /** Sandbox incident report for this run. */
  report?: ReportLike | null;
  perms: DemoPermissions;
}

const LOCKED = "Start the demonstration run (or follow the active one) to begin.";

export function evaluateSteps(i: DemoInputs): StepResult[] {
  const s = i.state && i.state.id && i.state.status !== "idle" ? i.state : null;
  const start = s?.sim_start ?? null;
  const at = (t: string | null | undefined) => (start && t ? tPlus(start, t) : "—");
  const name = (aid: string | null | undefined) => (aid ? i.names?.[aid] ?? aid : "—");
  const focusName = name(i.focusId);
  const a = i.analysis && i.analysis.available ? i.analysis : null;
  const aiPending = !s
    ? LOCKED
    : i.analysis && !i.analysis.available
      ? `AI analysis unavailable for ${focusName}: ${i.analysis.reason ?? "no reason given"}.`
      : "Waiting for the AI analysis: the models run every 15 simulated minutes once 15 minutes of stream exist, or on request.";
  const steps: StepResult[] = [];
  const push = (r: Omit<StepResult, "id" | "title">) =>
    steps.push({ id: steps.length + 1, title: STEP_TITLES[steps.length], ...r });

  // 1 ------------------------------------------------------------ run and crew
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [], href: "/simulation", hrefLabel: "Mission simulation" });
  } else {
    const crew = s.crew.map((c) => (i.roles?.[c] ? `${name(c)} (${c}, ${i.roles[c]})` : `${name(c)} (${c})`));
    push({
      status: "done",
      summary: `Sandbox run ${s.id} started with ${s.crew.length} fictional crew member${s.crew.length === 1 ? "" : "s"}.`,
      evidence: [
        { label: "Run", value: `${s.name ?? "—"} (${s.id})` },
        { label: "Preset", value: s.preset ? (i.presetLabel ? `${i.presetLabel} (${s.preset})` : s.preset) : "custom" },
        ...(i.run && i.run.id === s.id ? [{ label: "Seed", value: String(i.run.seed) }] : []),
        { label: "Crew", value: crew.join("; ") || "—" },
        { label: "Started by", value: s.created_by ?? "—" },
      ],
      href: `/timeline?simulation=${s.id}`,
      hrefLabel: "Sandbox timeline",
    });
  }

  // 2 ------------------------------------------------------------ streaming
  const samples = s ? statNumber(s.stats, "samples") : null;
  const reading = s?.latest.find((r) => r.astronaut_id === i.focusId) ?? null;
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [] });
  } else if (samples && samples > 0) {
    push({
      status: "done",
      summary: `${samples} simulated samples stored for this run.`,
      evidence: [
        { label: "Samples stored", value: String(samples) },
        { label: "Engine step", value: `${num(s.step_seconds, 0)} s simulated` },
        ...(reading
          ? [{ label: `Latest for ${focusName}`, value: `HR ${num(reading.heart_rate, 0)} bpm, SpO₂ ${num(reading.spo2, 1)} %, RR ${num(reading.respiratory_rate, 0)} /min at ${at(reading.ts)}` }]
          : []),
      ],
      href: "/simulation",
      hrefLabel: "Sandbox telemetry",
    });
  } else {
    push({ status: "waiting", summary: "Waiting for the first stored sandbox samples.", evidence: [] });
  }

  // 3 ------------------------------------------------------------ baseline
  if (!s || !a) {
    push({ status: s ? "waiting" : "locked", summary: aiPending, evidence: [] });
  } else {
    const withBaseline = (a.risk?.contributors ?? []).filter((c) => c.baseline !== null && c.baseline !== undefined);
    const notes = (a.limitations ?? []).filter((l) => /baseline/i.test(l));
    push({
      status: "done",
      summary: withBaseline.length
        ? `The AI analysis compared ${focusName}'s sandbox stream with the personal baseline; ${withBaseline.length} signal${withBaseline.length === 1 ? "" : "s"} listed against it.`
        : `The AI analysis returned results for ${focusName} using the personal baseline from stored history; it listed no per-signal baseline values this time.`,
      evidence: [
        { label: "Analysed at", value: at(a.sim_time) },
        { label: "Model version", value: a.model_version ?? "—" },
        ...(withBaseline.length
          ? withBaseline.slice(0, 3).map((c) => ({
              label: c.label,
              value: `${num(c.value, 1)} vs baseline ${num(c.baseline, 1)} ${c.unit ?? ""}${c.z !== null && c.z !== undefined ? ` (z ${num(c.z, 1)})` : ""}`.trim(),
            }))
          : [{ label: "Baseline", value: "from stored history" }]),
        ...notes.slice(0, 2).map((n) => ({ label: "Note", value: n })),
      ],
      href: "/simulation",
      hrefLabel: "AI predictions on the sandbox stream",
    });
  }

  // 4 ------------------------------------------------------------ rule alerts
  const alerts = i.alerts ?? [];
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [] });
  } else if (i.alerts === undefined) {
    push({ status: i.alertsError ? "unavailable" : "waiting", summary: i.alertsError ?? "Loading sandbox alerts.", evidence: [] });
  } else if (alerts.length) {
    const bySource = new Map<string, number>();
    for (const x of alerts) bySource.set(x.source_label, (bySource.get(x.source_label) ?? 0) + 1);
    const first = [...alerts].sort((x, y) => Date.parse(x.created_at) - Date.parse(y.created_at))[0];
    push({
      status: "done",
      summary: `${alerts.length} sandbox alert${alerts.length === 1 ? "" : "s"} raised for this run.`,
      evidence: [
        { label: "By source", value: [...bySource].map(([k, v]) => `${k} ${v}`).join("; ") },
        { label: "First alert", value: `${first.title} (${name(first.astronaut_id)}, ${at(first.created_at)})` },
      ],
      href: `/alerts?alert=${first.id}`,
      hrefLabel: "Alert centre (choose Simulation sandbox)",
    });
  } else {
    const next = isRecord(s.next_injection) ? s.next_injection : null;
    push({
      status: "waiting",
      summary: "No sandbox alert yet.",
      evidence: next
        ? [{ label: "Next scripted event", value: `${String(next.t_plus ?? "")} ${words(String(next.injection ?? ""))}`.trim() }]
        : [],
    });
  }

  // 5 ------------------------------------------------------------ AI pattern
  if (!s || !a) {
    push({ status: s ? "waiting" : "locked", summary: aiPending, evidence: [] });
  } else {
    const dets = a.detections ?? [];
    const flagged = a.flagged_windows ?? 0;
    const others = Object.entries(i.analyses ?? {})
      .filter(([k, v]) => k !== i.focusId && v.available && ((v.flagged_windows ?? 0) > 0 || (v.detections?.length ?? 0) > 0))
      .map(([k, v]) => `${name(k)} (${v.flagged_windows ?? 0} windows)`);
    if (dets.length > 0 || flagged > 0) {
      const d = dets[0];
      push({
        status: "done",
        summary: `Experimental AI output: ${flagged} of ${a.windows ?? "—"} windows flagged for ${focusName}, ${dets.length} detection${dets.length === 1 ? "" : "s"}.`,
        evidence: [
          { label: "Flagged windows", value: `${flagged} of ${a.windows ?? "—"}` },
          { label: "Detections", value: String(dets.length) },
          ...(d
            ? [{
                label: "First detection",
                value: `${words(d.kind) || "pattern"} at ${at(d.start)}, peak ${num(d.peak_score, 2)}x threshold${d.signals.length ? `, ${d.signals.slice(0, 3).map(words).join(", ")}` : ""}`,
              }]
            : []),
        ],
        href: "/simulation",
        hrefLabel: "AI predictions on the sandbox stream",
      });
    } else {
      push({
        status: "waiting",
        summary: `Latest analysis (${at(a.sim_time)}) flagged 0 of ${a.windows ?? "—"} windows for ${focusName}.`,
        evidence: others.length ? [{ label: "Flagged for other crew", value: others.join("; ") }] : [],
      });
    }
  }

  // 6 ------------------------------------------------------------ forecast
  const fc = a ? forecastHighlights(a.forecast) : [];
  if (!s || !a) {
    push({ status: s ? "waiting" : "locked", summary: aiPending, evidence: [] });
  } else if (fc.length) {
    push({
      status: "done",
      summary: `Forecast with prediction intervals for ${focusName} (experimental).`,
      evidence: fc.map((f) => ({
        label: `${f.label} +${f.horizon_h} h`,
        value: `${num(f.value, 1)} ${f.unit} (${num(f.lower, 1)} to ${num(f.upper, 1)})`,
      })),
      href: "/simulation",
      hrefLabel: "AI predictions on the sandbox stream",
    });
  } else {
    push({ status: "waiting", summary: a.forecast_error ?? "The latest analysis returned no forecast.", evidence: [] });
  }

  // 7 ------------------------------------------------------------ NASA space weather
  const w = i.weather;
  if (!w) {
    push({
      status: i.weatherError ? "unavailable" : "waiting",
      summary: i.weatherError ?? "Loading the NASA DONKI space-weather summary.",
      evidence: [],
      href: "/space/weather",
      hrefLabel: "Space weather",
    });
  } else {
    const total = Object.values(w.counts).reduce((x, y) => x + y, 0);
    const served = NASA_SERVED.has(w.freshness.mode);
    push({
      status: served ? "done" : w.freshness.mode === "unavailable" ? "unavailable" : "waiting",
      summary: served
        ? `Real NASA DONKI data, context only: ${total} event${total === 1 ? "" : "s"} in the last ${w.window_days} days. Not linked to the simulated crew.`
        : w.freshness.message,
      evidence: served
        ? [
            { label: "Events by type", value: Object.entries(w.counts).map(([k, v]) => `${words(k)} ${v}`).join("; ") || "none" },
            ...(w.strongest_flare ? [{ label: "Strongest flare", value: w.strongest_flare.classification ?? w.strongest_flare.severity_label }] : []),
            { label: "Freshness", value: `${w.freshness.mode}: ${w.freshness.message}` },
          ]
        : [],
      href: "/space/weather",
      hrefLabel: "Space weather",
    });
  }

  // 8 ------------------------------------------------------------ sandbox twin snapshot
  const rawReading = i.frame?.crew.find((c) => c.astronaut_id === i.focusId)?.reading;
  const fr = isRecord(rawReading) ? rawReading : null;
  const fv = (k: string) => (typeof fr?.[k] === "number" ? (fr[k] as number) : null);
  if (!s || !a) {
    push({ status: s ? "waiting" : "locked", summary: s ? "The sandbox twin snapshot is built once the AI analysis has run." : LOCKED, evidence: [] });
  } else if (!i.frame || !fr || !a.risk) {
    push({
      status: "waiting",
      summary: !a.risk ? "The latest analysis has no risk assessment." : "Loading the run frame at the analysis time.",
      evidence: [],
    });
  } else {
    push({
      status: "done",
      summary: `Sandbox twin snapshot for ${focusName} at ${i.frame.t_plus}. Separate from the operational Digital twin page, which tracks the live crew stream and was not changed by this run.`,
      evidence: [
        { label: "Vitals", value: `HR ${num(fv("heart_rate"), 0)} bpm, SpO₂ ${num(fv("spo2"), 1)} %, RR ${num(fv("respiratory_rate"), 0)} /min, ${num(fv("temperature_c"), 1)} °C, BP ${num(fv("systolic"), 0)}/${num(fv("diastolic"), 0)}` },
        { label: "Activity", value: `${words(String(fr.activity_state ?? "—"))}${fr.scenario ? `, test scenario ${words(String(fr.scenario))}` : ""}` },
        { label: "Risk (experimental)", value: `${num(a.risk.risk_score, 0)}/100 ${a.risk.category_label}${a.risk.confidence ? `, confidence ${a.risk.confidence.level}` : ""}` },
        { label: "Alerts so far", value: String(i.frame.alerts.length) },
      ],
      href: "/simulation",
      hrefLabel: "Mission playback",
    });
  }

  // 9 ------------------------------------------------------------ assistant
  const cited = citedStatements(i.answer);
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [], href: "/assistant", hrefLabel: "Medical assistant" });
  } else if (i.answer && cited.length) {
    push({
      status: "done",
      summary: `${cited.length} of ${i.answer.statements.length} statements cite a source (${i.answer.sources.length} source${i.answer.sources.length === 1 ? "" : "s"}).`,
      evidence: cited.slice(0, 3).map((st) => ({ label: `Cites ${st.citations.join(", ")}`, value: st.text })),
      href: "/assistant",
      hrefLabel: "Full conversation in the assistant",
    });
  } else if (!i.perms.assistant) {
    push({ status: "blocked", summary: "Asking the assistant needs the assistant:use permission, which your role does not include.", evidence: [] });
  } else {
    push({
      status: "action",
      summary: i.answer
        ? "The answer contained no cited statements; ask again or open the assistant."
        : `Ask the prepared question about ${focusName}.`,
      evidence: [],
      href: "/assistant",
      hrefLabel: "Medical assistant",
    });
  }

  // 10 ----------------------------------------------------------- prioritized alert
  const focusAlert = pickFocusAlert(i.alerts, i.focusId);
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [] });
  } else if (!focusAlert) {
    push({ status: i.alerts === undefined && i.alertsError ? "unavailable" : "waiting", summary: "Waiting for a sandbox alert in the alert centre.", evidence: [] });
  } else {
    const higher = alerts.filter((x) => x.priority < focusAlert.priority).length;
    push({
      status: "done",
      summary: `P${focusAlert.priority} ${focusAlert.priority_label}: ${focusAlert.title}`,
      evidence: [
        { label: "Priority", value: `P${focusAlert.priority} ${focusAlert.priority_label}${higher ? ` (${higher} alert${higher === 1 ? "" : "s"} ranked higher)` : " (highest in this run)"}` },
        { label: "Severity", value: focusAlert.severity },
        { label: "Classification", value: focusAlert.classification_label },
        { label: "Crew member", value: name(focusAlert.astronaut_id) },
        { label: "Status", value: focusAlert.status },
      ],
      href: `/alerts?alert=${focusAlert.id}`,
      hrefLabel: "Alert centre (choose Simulation sandbox)",
    });
  }

  // 11 ----------------------------------------------------------- operator review
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [] });
  } else if (!focusAlert) {
    push({ status: "locked", summary: "Waits for a sandbox alert to review.", evidence: [] });
  } else if (focusAlert.acknowledged_at || focusAlert.resolved_at) {
    push({
      status: "done",
      summary: focusAlert.acknowledged_at
        ? `Acknowledged by ${focusAlert.acknowledged_by ?? "—"}.`
        : `Resolved by ${focusAlert.resolved_by ?? "—"}.`,
      evidence: [
        ...(focusAlert.acknowledged_at ? [{ label: "Acknowledged", value: `${focusAlert.acknowledged_by ?? "—"} at ${at(focusAlert.acknowledged_at)}` }] : []),
        ...(focusAlert.ack_note ? [{ label: "Note", value: focusAlert.ack_note }] : []),
        ...(focusAlert.resolved_at ? [{ label: "Resolved", value: `${focusAlert.resolved_by ?? "—"} at ${at(focusAlert.resolved_at)}` }] : []),
        { label: "Status", value: focusAlert.status },
      ],
      href: `/alerts?alert=${focusAlert.id}`,
      hrefLabel: "Alert lifecycle",
    });
  } else if (!i.perms.manageAlerts) {
    push({ status: "blocked", summary: "Acknowledging needs the alerts:manage permission, which your role does not include.", evidence: [] });
  } else {
    push({ status: "action", summary: `Acknowledge ${focusAlert.title}.`, evidence: [], href: `/alerts?alert=${focusAlert.id}`, hrefLabel: "Open in the alert centre" });
  }

  // 12 ----------------------------------------------------------- incident report
  if (!s) {
    push({ status: "locked", summary: LOCKED, evidence: [], href: "/reports", hrefLabel: "Reports" });
  } else if (i.report) {
    push({
      status: "done",
      summary: `Sandbox incident report ${i.report.id} created (${i.report.review_status_label}).`,
      evidence: [
        { label: "Report", value: `${i.report.title} (${i.report.id})` },
        { label: "Integrity", value: `${i.report.integrity}, SHA-256 ${i.report.content_sha256.slice(0, 12)}…` },
        { label: "Review status", value: i.report.review_status_label },
      ],
      href: `/reports?report=${i.report.id}`,
      hrefLabel: "Open in reports",
    });
  } else if (!i.perms.writeReports) {
    push({ status: "blocked", summary: "Generating a report needs the reports:write permission, which your role does not include.", evidence: [] });
  } else if (!focusAlert && !i.focusId) {
    push({ status: "locked", summary: "Waits for a crew member or sandbox alert to report on.", evidence: [] });
  } else {
    push({
      status: "action",
      summary: focusAlert ? `Generate a sandbox incident report from ${focusAlert.title}.` : `Generate a sandbox incident report for ${focusName}.`,
      evidence: [],
      href: "/reports",
      hrefLabel: "Reports",
    });
  }

  return steps;
}
