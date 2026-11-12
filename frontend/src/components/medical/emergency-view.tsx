"use client";

import { BrainCircuit, ClipboardPlus, FlaskConical, Play, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { EmptyState, LoadingState, QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { useAstronauts } from "@/lib/api/hooks";
import {
  useAnalyzeRun,
  useCancelRun,
  useCreateReport,
  useEmergencyRuns,
  useEmergencyScenarios,
  useRunTimeline,
  useStartRun,
} from "@/lib/api/medical-hooks";
import type { EmergencyAnalysis, EmergencyKey, EmergencyRun, Severity, SeverityLevel, SystemStatus } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { duration, fmt, utcDayTime, utcTime } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import { CrewPicker, SystemStatusPill, useParamState } from "./common";

const SIGNALS: Record<string, { label: string; unit: string; decimals: number }> = {
  heart_rate: { label: "Heart rate", unit: "bpm", decimals: 0 },
  spo2: { label: "SpO₂", unit: "%", decimals: 1 },
  respiratory_rate: { label: "Respiratory rate", unit: "br/min", decimals: 0 },
  temperature_c: { label: "Temperature", unit: "°C", decimals: 2 },
  systolic: { label: "Systolic", unit: "mmHg", decimals: 0 },
};

function Launcher({ onStarted }: { onStarted: (id: string) => void }) {
  const scenarios = useEmergencyScenarios();
  const crew = useAstronauts();
  const start = useStartRun();
  const canRun = useCan("simulation:control");
  const [key, setKey] = useState<EmergencyKey>("hr_elevation");
  const [astronaut, setAstronaut] = useState<string | null>(null);
  const [severity, setSeverity] = useState<SeverityLevel>("moderate");
  const [minutes, setMinutes] = useState<number | null>(null);
  const [nights, setNights] = useState(3);
  const spec = scenarios.data?.find((s) => s.key === key);
  const target = astronaut ?? crew.data?.[0]?.id ?? null;
  const durationS = minutes != null ? Math.round(minutes * 60) : spec?.default_duration_s ?? 300;

  return (
    <Panel raised title="Configure a simulated scenario" description="Select, set severity and duration, then run. Every run is a labelled software test.">
      <QueryView query={scenarios}>
        {(list) => (
          <div className="space-y-4">
            <div role="radiogroup" aria-label="Scenario" className="grid gap-2 sm:grid-cols-2">
              {list.map((s) => (
                <button key={s.key} type="button" role="radio" aria-checked={key === s.key} onClick={() => { setKey(s.key); setMinutes(null); }}
                  className={cn("rounded-md border p-2.5 text-left", key === s.key ? "border-telemetry bg-telemetry/5" : "border-bulkhead/70 hover:border-bulkhead")}>
                  <span className="flex items-center gap-2 text-sm font-medium">{s.label}{s.crew_wide && <span className="rounded border border-bulkhead px-1 text-[10px] text-ink-3">whole crew</span>}</span>
                  <span className="mt-0.5 block text-xs text-ink-2">{s.description}</span>
                </button>
              ))}
            </div>
            {spec && !spec.crew_wide && <CrewPicker value={target} onChange={(v) => setAstronaut(v)} />}
            <div className="flex flex-wrap items-end gap-4">
              <fieldset>
                <legend className="mb-1 text-xs text-ink-3">Severity</legend>
                <div className="flex gap-1">
                  {spec?.severities.map((s) => (
                    <button key={s.key} type="button" aria-pressed={severity === s.key} onClick={() => setSeverity(s.key)}
                      className={cn("rounded-md border px-2.5 py-1 text-sm capitalize", severity === s.key ? "border-telemetry text-foreground" : "border-bulkhead text-ink-2")}>
                      {s.key} <span className="text-xs text-ink-3">×{s.intensity}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
              <label className="text-sm">
                <span className="mb-1 block text-xs text-ink-3">Duration (minutes)</span>
                <input type="number" min={0.5} max={60} step={0.5} value={minutes ?? (spec?.default_duration_s ?? 300) / 60}
                  onChange={(e) => setMinutes(Number(e.target.value))} className="h-8 w-24 rounded-md border border-input bg-abyss px-2" />
              </label>
              {spec?.overlay === "sleep" && (
                <label className="text-sm">
                  <span className="mb-1 block text-xs text-ink-3">Nights in overlay</span>
                  <input type="number" min={1} max={7} value={nights} onChange={(e) => setNights(Number(e.target.value))} className="h-8 w-20 rounded-md border border-input bg-abyss px-2" />
                </label>
              )}
              <Button size="lg" disabled={!canRun || start.isPending || !spec || durationS < 30 || durationS > 3600}
                onClick={() => start.mutate(
                  { scenario: key, astronaut_id: spec?.crew_wide ? null : target, severity, duration_seconds: durationS, nights },
                  { onSuccess: (r) => { toast.success(`${r.label} started (simulated)`); onStarted(r.id); }, onError: (e) => toast.error(e.message) },
                )}>
                <Play aria-hidden /> Run simulation
              </Button>
            </div>
            {!canRun && <p className="text-xs text-caution">Your role can watch runs but not start them (needs simulation:control).</p>}
            {spec && <p className="text-xs text-ink-3">Watch: {spec.observe.join(", ")}. Components: {spec.components.map((c) => `${c.scenario} ×${c.factor}`).join(" + ")}.</p>}
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

function RunList({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const runs = useEmergencyRuns();
  const now = useNow(1000);
  return (
    <Panel title="Runs, last 72 h">
      <QueryView query={runs} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No runs yet">Start a scenario to rehearse the monitoring and review workflow.</EmptyState>}>
        {(list) => (
          <ul className="max-h-80 space-y-1.5 overflow-auto">
            {list.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onSelect(r.id)} aria-pressed={selected === r.id}
                  className={cn("w-full rounded-md border px-3 py-2 text-left text-sm", selected === r.id ? "border-telemetry bg-telemetry/5" : "border-bulkhead/70")}>
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{r.label}</span>
                    <span className={cn("rounded px-1.5 text-[11px]", r.status === "running" ? "bg-caution/15 text-caution" : "bg-bulkhead/60 text-ink-2")}>{r.status}</span>
                  </span>
                  <span className="block text-xs text-ink-2">
                    {r.astronaut_id ?? "whole crew"} · {r.severity} · {utcDayTime(r.started_at)} UTC
                    {r.status === "running" && now && ` · ${duration(Math.max(0, (Date.parse(r.ends_at) - now) / 1000))} left`}
                    {r.analyses.length > 0 && ` · ${r.analyses.length} analysis`}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Panel>
  );
}

function AnalysisView({ a }: { a: EmergencyAnalysis }) {
  return (
    <div className="space-y-3 rounded-md border border-bulkhead/70 p-3">
      <p className="text-xs text-ink-3">AI analysis {utcDayTime(a.ts)} UTC by {a.requested_by} · run {a.run_status} · {a.note}</p>
      {a.crew.map((c) => {
        const crew = c as { astronaut_id: string; name: string; summary: string; systems: Record<string, SystemStatus>; patterns: { label: string }[];
          alerts: { id: string; title: string; severity: string; escalation: string }[]; escalation: { level: string; label: string };
          anomaly: { available: boolean; flagged_windows?: number; windows?: number; peak?: { ensemble_score: number; votes: number } | null; reason?: string };
          risk: { category_label?: string; risk_score?: number } };
        return (
          <div key={crew.astronaut_id} className="space-y-1.5">
            <p className="text-sm font-medium">{crew.name}: {crew.summary}</p>
            <div className="flex flex-wrap gap-1.5">{Object.entries(crew.systems).map(([k, v]) => <span key={k} className="flex items-center gap-1 text-xs text-ink-2">{k.replace("_", " ")} <SystemStatusPill status={v} compact /></span>)}</div>
            <p className="text-xs text-ink-2">
              Anomaly ensemble: {crew.anomaly.available ? `${crew.anomaly.flagged_windows} of ${crew.anomaly.windows} windows flagged${crew.anomaly.peak ? `, peak ${fmt(crew.anomaly.peak.ensemble_score, 2)}×` : ""}` : crew.anomaly.reason}
              {crew.risk?.category_label && ` · risk rules: ${crew.risk.category_label} (${fmt(crew.risk.risk_score, 0)})`}
            </p>
            {crew.patterns.length > 0 && <p className="text-xs text-caution">Patterns: {crew.patterns.map((p) => p.label).join("; ")}</p>}
            {crew.alerts.length > 0 && (
              <ul className="space-y-0.5">{crew.alerts.map((al) => <li key={al.id} className="flex flex-wrap items-center gap-2 text-xs"><StatusPill status={al.severity as Severity} /> {al.title} <span className="text-ink-3">{al.escalation}</span></li>)}</ul>
            )}
            <p className={cn("text-xs font-medium", crew.escalation.level === "immediate" ? "text-critical" : "text-ink-2")}>{crew.escalation.label}</p>
          </div>
        );
      })}
    </div>
  );
}

function RunDetail({ run }: { run: EmergencyRun }) {
  const [aidSel, setAid] = useState<string | null>(null);
  const aid = run.astronaut_id ?? aidSel;
  const live = run.status === "running";
  const tl = useRunTimeline(run.id, aid, live);
  const [signal, setSignal] = useState("heart_rate");
  const cancel = useCancelRun();
  const analyze = useAnalyzeRun();
  const create = useCreateReport();
  const canRun = useCan("simulation:control");
  const canReport = useCan("reports:write");
  const canAnalyze = canRun || canReport;
  const router = useRouter();
  const meta = SIGNALS[signal];

  return (
    <div className="space-y-4">
      <p className="flex items-start gap-2 rounded-md border border-dashed border-caution/50 bg-caution/5 px-3 py-2 text-sm text-ink-2">
        <FlaskConical className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden /> {run.label_simulated}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {live && canRun && <Button size="sm" variant="destructive" disabled={cancel.isPending} onClick={() => cancel.mutate(run.id, { onError: (e) => toast.error(e.message) })}><Square aria-hidden /> Cancel run</Button>}
        {canAnalyze && <Button size="sm" disabled={analyze.isPending} onClick={() => analyze.mutate(run.id, { onSuccess: () => toast.success("AI analysis stored on the run"), onError: (e) => toast.error(e.message) })}><BrainCircuit aria-hidden /> {analyze.isPending ? "Analysing" : "Run AI analysis"}</Button>}
        {canReport && run.astronaut_id && (
          <Button size="sm" variant="outline" disabled={create.isPending} onClick={() => create.mutate({ run_id: run.id }, {
            onSuccess: (r) => { toast.success("Draft incident report created"); router.push(`/reports?report=${r.id}`); }, onError: (e) => toast.error(e.message) })}>
            <ClipboardPlus aria-hidden /> Create incident report
          </Button>
        )}
        <span className="text-xs text-ink-3">{run.components.map((c) => `${c.label} ×${c.intensity}`).join(" + ")}</span>
      </div>
      {!run.astronaut_id && <CrewPicker value={aid} onChange={setAid} label="Crew member to observe" />}
      {!aid ? <p className="text-sm text-ink-2">Choose a crew member to observe.</p> : (
        <QueryView query={tl} loading={<LoadingState rows={4} />}>
          {(t) => {
            const data: ChartRow[] = t.vitals.map((v) => ({ t: Date.parse(String(v.ts)), v: (v[signal] as number | null) ?? null }));
            const events = t.events;
            return (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-1">
                  {Object.entries(SIGNALS).map(([k, s]) => (
                    <button key={k} type="button" aria-pressed={signal === k} onClick={() => setSignal(k)}
                      className={cn("rounded-md border px-2 py-0.5 text-xs", signal === k ? "border-telemetry text-foreground" : "border-bulkhead text-ink-2")}>{s.label}</button>
                  ))}
                  {live && <span className="ml-auto text-xs text-caution">live · refreshes every 5 s</span>}
                </div>
                {data.length > 1 ? (
                  <TrendChart data={data} series={[{ key: "v", label: meta.label, color: "var(--telemetry)" }]} unit={meta.unit} decimals={meta.decimals} height={200}
                    ariaLabel={`${meta.label} during the simulated run`} />
                ) : <p className="text-sm text-ink-2">Waiting for stored samples…</p>}
                {t.environment.length > 0 && (() => {
                  const keys = Object.keys(t.environment[0]).filter((k) => k !== "ts");
                  const key = keys.includes("ppco2_mmhg") ? "ppco2_mmhg" : "dose_rate_msv_day";
                  const rows: ChartRow[] = t.environment.map((e) => ({ t: Date.parse(String(e.ts)), v: (e[key] as number) ?? null }));
                  return <TrendChart data={rows} series={[{ key: "v", label: key === "ppco2_mmhg" ? "Cabin CO₂ (simulated)" : "Habitat dose rate (simulated)", color: "var(--caution)" }]}
                    unit={key === "ppco2_mmhg" ? "mmHg" : "mSv/day"} decimals={2} height={140} ariaLabel="Simulated environment during the run" />;
                })()}
                <ol className="space-y-1 text-sm">
                  {events.map((e, i) => (
                    <li key={i} className="flex gap-3"><span className="w-16 shrink-0 text-xs tabular-nums text-ink-3">{utcTime(e.ts)}</span>
                      <span className={cn(e.kind === "alert_opened" && (e.severity === "critical" ? "text-critical" : "text-caution"))}>{e.label}{e.severity ? ` (${e.severity})` : ""}</span></li>
                  ))}
                </ol>
                {t.overlay && (t.overlay as { type?: string }).type === "sleep" && (
                  <table className="w-full text-left text-xs tabular-nums">
                    <caption className="mb-1 text-left text-ink-2">Sleep what-if overlay (stored records unchanged)</caption>
                    <thead className="text-ink-3"><tr><th className="py-1 font-medium">Night</th><th className="py-1 font-medium">Stored</th><th className="py-1 font-medium">Overlay</th></tr></thead>
                    <tbody>
                      {Object.entries((t.overlay as { nights: Record<string, { duration_hours: number; efficiency_pct: number; original_duration_hours: number; original_efficiency_pct: number }> }).nights).map(([n, v]) => (
                        <tr key={n} className="border-t border-bulkhead/50"><td className="py-1">{n}</td><td className="py-1">{fmt(v.original_duration_hours, 1)} h · {fmt(v.original_efficiency_pct, 0)}%</td><td className="py-1 text-caution">{fmt(v.duration_hours, 1)} h · {fmt(v.efficiency_pct, 0)}%</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          }}
        </QueryView>
      )}
      {[...run.analyses].reverse().map((a) => <AnalysisView key={String(a.id)} a={a as unknown as EmergencyAnalysis} />)}
    </div>
  );
}

export function EmergencyView() {
  const [runId, setRun] = useParamState("run");
  const runs = useEmergencyRuns();
  const run = runs.data?.find((r) => r.id === runId) ?? null;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-3"><Launcher onStarted={(id) => setRun(id)} /></div>
        <div className="min-w-0 xl:col-span-2"><RunList selected={runId} onSelect={setRun} /></div>
      </div>
      <Panel title={run ? `${run.label}${run.astronaut_id ? ` · ${run.astronaut_id}` : " · whole crew"}` : "Run"} description="Observe vitals, trigger AI analysis, inspect alerts and review the run timeline.">
        {run ? <RunDetail run={run} /> : <EmptyState title="No run selected">Start a run or pick one from the list.</EmptyState>}
      </Panel>
    </div>
  );
}
