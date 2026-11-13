"use client";

import { BrainCircuit, ClipboardList, FastForward, Pause, Play, RotateCcw, Send, Square, Syringe } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { DataCard, Meter, Stat } from "@/components/mc/card";
import { ExperimentalTag, OriginChip, PriorityBadge, SandboxTag, SeverityDot } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { StatusPill } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAstronauts } from "@/lib/api/hooks";
import {
  useAlertCenter,
  useMissionEvents,
  usePlayback,
  useSimAnalyze,
  useSimCatalogue,
  useSimControl,
  useSimFrame,
  useSimInject,
  useSimReport,
  useSimRun,
  useSimRuns,
  useSimSpeed,
  useSimStateQuery,
  useSimTelemetry,
  useStartSim,
} from "@/lib/api/mission-hooks";
import type { SimCatalogue, SimInjectionType, SimPreset, SimRun, SimState } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { crewColor, crewDash } from "@/lib/crew";
import { fmt, utcDayTime, utcTime } from "@/lib/format";
import { useLive } from "@/lib/live/store";
import { cn } from "@/lib/utils";

const SPEEDS = [1, 5, 10, 20, 30, 40, 60, 120];
const onError = (e: unknown) => toast.error(e instanceof Error ? e.message : "The request failed.");

function tPlus(start: string, t: string | number): string {
  const s = Math.max(0, Math.round(((typeof t === "number" ? t : Date.parse(t)) - Date.parse(start)) / 1000));
  return `T+${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** The sandbox state: socket messages while connected, REST every 5 s otherwise. */
function useSimState(): SimState | undefined {
  const live = useLive((s) => s.sim);
  const rest = useSimStateQuery();
  const connection = useLive((s) => s.connection);
  return connection === "live" && live ? live : rest.data ?? live ?? undefined;
}

function SandboxBanner() {
  return (
    <div className="flex items-stretch overflow-hidden rounded-lg border border-sandbox/50 bg-sandbox/8">
      <span className="sandbox-tape w-3 shrink-0 opacity-80" aria-hidden />
      <p className="px-4 py-2.5 text-sm text-ink-1">
        <span className="font-semibold text-sandbox">Simulation sandbox.</span> Runs on its own engine and clock and writes
        only to the sandbox tables: nothing here reaches the live crew stream, the digital twin or the AI baselines.
        Crew members are fictional; the space-weather events you inject here are simulated. Real NASA data is labelled
        <span className="mx-1 inline-block align-middle"><OriginChip origin="nasa" /></span>wherever it appears.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- start a run ----
function StartPanel({ cat }: { cat: SimCatalogue }) {
  const crewQ = useAstronauts();
  const canControl = useCan("simulation:control");
  const start = useStartSim();
  const [presetKey, setPresetKey] = useState<string>(cat.presets[1]?.key ?? cat.presets[0]?.key ?? "");
  const preset = cat.presets.find((p) => p.key === presetKey) ?? null;
  const allCrew = crewQ.data ?? [];
  const [crew, setCrew] = useState<string[]>([]);
  const [speed, setSpeed] = useState<string>("");
  const [minutes, setMinutes] = useState<string>("");
  const chosenCrew = crew.length ? crew : allCrew.slice(0, preset?.crew_size ?? allCrew.length).map((a) => a.id);
  const chosenSpeed = speed || String(preset?.speed ?? 30);
  const chosenMinutes = minutes || String(preset?.duration_minutes ?? 120);

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
      <Panel raised title="Scenario presets" description="Scripted missions: crew, speed, length and injected events at set simulated times.">
        <ul className="grid gap-3 md:grid-cols-2">
          {cat.presets.map((p: SimPreset) => (
            <li key={p.key}>
              <button
                type="button"
                onClick={() => { setPresetKey(p.key); setCrew([]); setSpeed(""); setMinutes(""); }}
                aria-pressed={p.key === presetKey}
                className={cn(
                  "h-full w-full rounded-md border p-3 text-left transition-colors",
                  p.key === presetKey ? "border-sandbox/70 bg-sandbox/8" : "border-bulkhead/70 hover:border-bulkhead hover:bg-sidebar-accent/40",
                )}
              >
                <p className="font-heading text-base font-semibold">{p.label}</p>
                <p className="mt-1 text-sm text-ink-2">{p.description}</p>
                <p className="mt-2 text-xs text-ink-3">
                  {p.crew_size} crew, {p.duration_minutes} min at {p.speed}x
                  {p.script.length ? `, ${p.script.length} scripted event${p.script.length > 1 ? "s" : ""}` : ", no injected events"}
                </p>
                {p.script.length > 0 && (
                  <ol className="mt-1 space-y-0.5 text-xs text-ink-2">
                    {(p.script as { at_minute: number; label: string }[]).map((s, i) => (
                      <li key={i}>T+{String(Math.floor(s.at_minute / 60)).padStart(2, "0")}:{String(s.at_minute % 60).padStart(2, "0")} {s.label}</li>
                    ))}
                  </ol>
                )}
              </button>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Start a simulated mission" className="border-sandbox/40">
        <div className="space-y-4">
          <div className="space-y-1.5">
            <p className="text-xs text-ink-3">Crew</p>
            <ToggleGroup type="multiple" variant="outline" size="sm" value={chosenCrew} onValueChange={(v) => setCrew(v)} className="flex-wrap justify-start">
              {allCrew.map((a) => (
                <ToggleGroupItem key={a.id} value={a.id} aria-label={a.name}>
                  <span className="size-2 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
                  {a.name.split(" ")[0]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-ink-3">Speed</Label>
              <Select value={chosenSpeed} onValueChange={setSpeed}>
                <SelectTrigger aria-label="Simulation speed"><SelectValue /></SelectTrigger>
                <SelectContent>{SPEEDS.filter((s) => s <= cat.max_speed).map((s) => <SelectItem key={s} value={String(s)}>{s}x</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-ink-3">Length</Label>
              <Select value={chosenMinutes} onValueChange={setMinutes}>
                <SelectTrigger aria-label="Mission length"><SelectValue /></SelectTrigger>
                <SelectContent>{[30, 60, 90, 120, 150, 180, 360, 720].map((m) => <SelectItem key={m} value={String(m)}>{m} sim. min</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <p className="text-xs text-ink-3">
            At {chosenSpeed}x, {chosenMinutes} simulated minutes take about {fmt(Number(chosenMinutes) / Number(chosenSpeed), 1)} minutes.
            The AI models analyse the stream every 15 simulated minutes.
          </p>
          {!cat.enabled ? (
            <p className="text-sm text-caution">Mission simulation is disabled on this deployment.</p>
          ) : !canControl ? (
            <p className="text-sm text-ink-2">Starting a simulation needs the mission operator role.</p>
          ) : (
            <Button
              className="w-full"
              disabled={start.isPending || chosenCrew.length === 0}
              onClick={() =>
                start.mutate(
                  { preset: preset?.key ?? null, crew: chosenCrew, speed: Number(chosenSpeed), duration_minutes: Number(chosenMinutes) },
                  { onSuccess: () => toast.success("Simulated mission started"), onError },
                )
              }
            >
              <Play aria-hidden /> Start simulated mission
            </Button>
          )}
        </div>
      </Panel>
    </div>
  );
}

// -------------------------------------------------------------- live controls ----
function ControlBar({ s }: { s: SimState }) {
  const canControl = useCan("simulation:control");
  const control = useSimControl();
  const speed = useSimSpeed();
  const id = s.id!;
  const act = (action: "pause" | "resume" | "stop" | "reset") =>
    control.mutate({ id, action }, { onSuccess: () => toast.success(`Simulation ${action === "stop" ? "stopped" : action === "reset" ? "reset" : action + "d"}`), onError });
  return (
    <DataCard
      sandbox
      title={<span className="flex items-center gap-2">{s.name} <SandboxTag>{s.status}</SandboxTag></span>}
      meta={<span>started by {s.created_by}</span>}
    >
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
        <Stat label="Simulation clock" value={s.t_plus ?? "—"} tone="sandbox" sub={s.sim_time ? `${utcDayTime(s.sim_time)} UTC (sim.)` : undefined} />
        <div className="min-w-48 flex-1">
          <p className="mb-1 flex justify-between text-xs text-ink-3"><span>Progress</span><span>{fmt((s.progress ?? 0) * 100, 0)}% of {s.sim_start && s.sim_end ? Math.round((Date.parse(s.sim_end) - Date.parse(s.sim_start)) / 60000) : "—"} min</span></p>
          <Meter value={(s.progress ?? 0) * 100} tone="sandbox" label="Simulation progress" />
          <p className="mt-1 text-xs text-ink-3">
            {s.next_injection ? `Next scripted event ${String((s.next_injection as { t_plus?: string }).t_plus ?? "")}: ${String((s.next_injection as { injection?: string }).injection ?? "").replace(/_/g, " ")}` : "No scripted events pending"}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Speed</p>
          <Select value={String(s.speed)} onValueChange={(v) => speed.mutate({ id, speed: Number(v) }, { onError })} disabled={!canControl || !s.active}>
            <SelectTrigger className="w-24" aria-label="Simulation speed"><FastForward className="size-3.5" aria-hidden /><SelectValue /></SelectTrigger>
            <SelectContent>{[...new Set([...SPEEDS, s.speed ?? 30])].sort((a, b) => a - b).map((v) => <SelectItem key={v} value={String(v)}>{v}x</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {canControl && (
          <div className="flex flex-wrap gap-2">
            {s.status === "running" && <Button variant="outline" onClick={() => act("pause")} disabled={control.isPending}><Pause aria-hidden /> Pause</Button>}
            {s.status === "paused" && <Button onClick={() => act("resume")} disabled={control.isPending}><Play aria-hidden /> Resume</Button>}
            {s.active && <Button variant="outline" onClick={() => act("stop")} disabled={control.isPending}><Square aria-hidden /> Stop</Button>}
            <Button variant="ghost" onClick={() => act("reset")} disabled={control.isPending} title="Abandon the run, close its sandbox alerts and return to idle">
              <RotateCcw aria-hidden /> Reset
            </Button>
          </div>
        )}
      </div>
      {s.error && <p className="mt-3 text-sm text-critical">{s.error}</p>}
    </DataCard>
  );
}

function LiveTelemetry({ s }: { s: SimState }) {
  const trail = useLive((st) => st.simTrail);
  const rows = (trail.id === s.id ? trail.rows : []) as ChartRow[];
  const series = (prefix: string) => s.latest.map((r) => ({ key: `${prefix}_${r.astronaut_id}`, label: r.name.split(" ")[0], color: crewColor(r.astronaut_id), dash: crewDash(r.astronaut_id) }));
  return (
    <DataCard sandbox title="Sandbox telemetry" meta={<span className="flex items-center gap-2">every step {fmt(s.step_seconds, 0)} s sim. <OriginChip origin="sandbox" /></span>}>
      <ul className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {s.latest.map((r) => (
          <li key={r.astronaut_id} className="rounded-md border border-bulkhead/70 bg-panel-2 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5 font-medium"><span className="size-2 rounded-full" style={{ background: crewColor(r.astronaut_id) }} aria-hidden /><span className="truncate">{r.name}</span></span>
              <StatusPill status={r.status as "nominal"} compact />
            </div>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div><dt className="text-ink-3">HR</dt><dd className="readout text-lg font-semibold text-sandbox">{fmt(r.heart_rate, 0)}</dd></div>
              <div><dt className="text-ink-3">SpO₂</dt><dd className="readout text-lg font-semibold">{fmt(r.spo2, 1)}</dd></div>
              <div><dt className="text-ink-3">Resp.</dt><dd className="readout text-lg font-semibold">{fmt(r.respiratory_rate, 0)}</dd></div>
              <div><dt className="text-ink-3">Temp</dt><dd className="tabular-nums">{fmt(r.temperature_c, 1)} °C</dd></div>
              <div><dt className="text-ink-3">BP</dt><dd className="tabular-nums">{fmt(r.systolic, 0)}/{fmt(r.diastolic, 0)}</dd></div>
              <div><dt className="text-ink-3">Dose</dt><dd className="tabular-nums">{fmt(r.dose_msv * 1000, 1)} µSv</dd></div>
            </dl>
            <p className="mt-1 truncate text-xs text-ink-2">{r.activity_state}{r.scenario ? <span className="text-caution">, {r.scenario.replace(/_/g, " ")}</span> : null}</p>
          </li>
        ))}
      </ul>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-xs text-ink-2">Heart rate (bpm)</p>
          {rows.length > 1 ? <TrendChart data={rows} series={series("hr")} unit="bpm" height={150} endLabels ariaLabel="Sandbox heart rate per crew member" /> : <p className="text-sm text-ink-2">Collecting frames.</p>}
        </div>
        <div>
          <p className="mb-1 text-xs text-ink-2">SpO₂ (%)</p>
          {rows.length > 1 ? <TrendChart data={rows} series={series("spo2")} unit="%" decimals={1} height={150} endLabels ariaLabel="Sandbox SpO2 per crew member" refs={[{ value: 92, label: "caution 92%" }]} /> : null}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 border-t border-bulkhead/50 pt-3 text-sm">
        {Object.entries(s.habitat as Record<string, { label: string; value: number; unit: string; deviation_sigma: number }>).map(([k, p]) => (
          <span key={k} className={cn(Math.abs(p.deviation_sigma) >= 4 && "text-caution")}>
            <span className="text-ink-3">{p.label} </span>{p.value} {p.unit}
          </span>
        ))}
        <span className={cn((s.dose_rate_multiplier ?? 1) > 2 && "text-caution")}><span className="text-ink-3">Dose rate </span>x{fmt(s.dose_rate_multiplier, 1)}</span>
      </div>
      <p className="mt-2 text-xs text-ink-3">Charts show the frames this browser received while the page was open; the full run is in mission playback.</p>
    </DataCard>
  );
}

function InjectPanel({ s, cat }: { s: SimState; cat: SimCatalogue }) {
  const canControl = useCan("simulation:control");
  const inject = useSimInject();
  const [key, setKey] = useState("desaturation");
  const [aid, setAid] = useState<string>(s.crew[0] ?? "");
  const [intensity, setIntensity] = useState(1);
  const [when, setWhen] = useState("now");
  const spec = cat.injections.find((i) => i.key === key) as SimInjectionType | undefined;
  const groups: [string, string][] = [["health", "Health anomalies"], ["environment", "Environmental events"], ["space_weather", "Simulated space weather"]];
  const minuteNow = s.sim_start && s.sim_time ? (Date.parse(s.sim_time) - Date.parse(s.sim_start)) / 60000 : 0;
  return (
    <DataCard sandbox title="Event injection" icon={<Syringe />}>
      {!canControl ? <p className="text-sm text-ink-2">Injecting events needs the mission operator role.</p> : (
        <div className="space-y-3">
          <Select value={key} onValueChange={setKey}>
            <SelectTrigger className="w-full" aria-label="Event to inject"><SelectValue /></SelectTrigger>
            <SelectContent>
              {groups.map(([kind, label]) => (
                <SelectGroup key={kind}>
                  <SelectLabel>{label}</SelectLabel>
                  {cat.injections.filter((i) => i.kind === kind).map((i) => <SelectItem key={i.key} value={i.key}>{i.label}</SelectItem>)}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
          {spec && <p className="text-xs text-ink-2">{spec.description}</p>}
          {spec && !spec.crew_wide && (
            <ToggleGroup type="single" variant="outline" size="sm" value={aid} onValueChange={(v) => v && setAid(v)} aria-label="Crew member" className="flex-wrap justify-start">
              {s.latest.map((r) => <ToggleGroupItem key={r.astronaut_id} value={r.astronaut_id}>{r.name.split(" ")[0]}</ToggleGroupItem>)}
            </ToggleGroup>
          )}
          {spec && !spec.event_only && (
            <div className="space-y-1.5">
              <p className="flex justify-between text-xs text-ink-3"><span>Intensity</span><span className="tabular-nums">{fmt(intensity, 1)}</span></p>
              <Slider value={[intensity]} min={0.3} max={1.5} step={0.1} onValueChange={([v]) => setIntensity(v)} aria-label="Intensity" />
            </div>
          )}
          <ToggleGroup type="single" variant="outline" size="sm" value={when} onValueChange={(v) => v && setWhen(v)} aria-label="When">
            <ToggleGroupItem value="now">Now</ToggleGroupItem>
            <ToggleGroupItem value="10">In 10 min</ToggleGroupItem>
            <ToggleGroupItem value="30">In 30 min</ToggleGroupItem>
          </ToggleGroup>
          <Button
            className="w-full"
            disabled={inject.isPending || !s.active}
            onClick={() =>
              inject.mutate(
                { id: s.id!, body: { injection: key, astronaut_id: spec?.crew_wide ? null : aid, intensity, at_minute: when === "now" ? null : minuteNow + Number(when) } },
                { onSuccess: (r) => toast.success(`${spec?.label ?? "Event"} ${(r as { status?: string }).status === "scheduled" ? "scheduled" : "injected"}`), onError },
              )
            }
          >
            Inject event
          </Button>
        </div>
      )}
    </DataCard>
  );
}

function TelemetryPanel({ s }: { s: SimState }) {
  const canControl = useCan("simulation:control");
  const send = useSimTelemetry();
  const [aid, setAid] = useState(s.crew[0] ?? "");
  const [spo2, setSpo2] = useState("86");
  const [hr, setHr] = useState("108");
  const [count, setCount] = useState("6");
  const [result, setResult] = useState<string | null>(null);
  if (!canControl) return null;
  return (
    <DataCard sandbox title="Send measurements" icon={<Send />}>
      <p className="mb-3 text-xs text-ink-2">
        Sends readings to the backend for this run, ending at the simulation clock, 10 s apart. They go through the same
        validation and rule detection as generated telemetry.
      </p>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-3">
          <ToggleGroup type="single" variant="outline" size="sm" value={aid} onValueChange={(v) => v && setAid(v)} aria-label="Crew member" className="flex-wrap justify-start">
            {s.latest.map((r) => <ToggleGroupItem key={r.astronaut_id} value={r.astronaut_id}>{r.name.split(" ")[0]}</ToggleGroupItem>)}
          </ToggleGroup>
        </div>
        {([["SpO₂ %", spo2, setSpo2], ["Heart rate", hr, setHr], ["Samples", count, setCount]] as const).map(([label, v, set]) => (
          <label key={label} className="space-y-1 text-xs text-ink-3">
            {label}
            <input value={v} onChange={(e) => set(e.target.value)} inputMode="decimal"
              className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm text-foreground tabular-nums" />
          </label>
        ))}
      </div>
      <Button
        className="mt-3 w-full"
        variant="outline"
        disabled={send.isPending || !s.sim_time}
        onClick={() => {
          const end = Date.parse(s.sim_time!);
          const n = Math.max(1, Math.min(60, Number(count) || 1));
          const readings = Array.from({ length: n }, (_, i) => ({
            astronaut_id: aid, ts: new Date(end - (n - 1 - i) * 10_000).toISOString(),
            spo2: Number(spo2), heart_rate: Number(hr),
          }));
          send.mutate({ id: s.id!, readings }, {
            onSuccess: (r) => {
              setResult(`${r.accepted} accepted, ${r.rejected} rejected, ${r.alerts_opened} alert(s) opened.${r.issues.length ? ` ${r.issues.map((x) => String((x as { issue: string }).issue)).join("; ")}` : ""}`);
              toast.success(`${r.accepted} measurements ingested`);
            },
            onError: (e) => { setResult(e instanceof Error ? e.message : "Rejected"); onError(e); },
          });
        }}
      >
        <Send aria-hidden /> Send to backend
      </Button>
      {result && <p className="mt-2 text-xs text-ink-2" role="status">{result}</p>}
    </DataCard>
  );
}

interface CrewAnalysis {
  available: boolean;
  reason?: string;
  sim_time?: string;
  model_version?: string;
  risk?: { risk_score: number; category: string; category_label: string; warnings: { title: string }[]; confidence: { level: string } };
  detections?: { start: string; kind: string; peak_score: number; signals: string[] }[];
  flagged_windows?: number;
  windows?: number;
  forecast?: { signal: string; label: string; unit: string; horizons: { horizon_h: number; value: number; lower: number; upper: number; crossing: string | null }[] }[] | null;
  forecast_error?: string | null;
}

function AiPanel({ s }: { s: SimState }) {
  const run = useSimRun(s.id ?? null, true);
  const analyze = useSimAnalyze();
  const canControl = useCan("simulation:control");
  const analyses = (run.data?.analyses ?? {}) as Record<string, CrewAnalysis>;
  const crew = s.latest;
  return (
    <DataCard sandbox title="AI predictions on the sandbox stream" icon={<BrainCircuit />}
      meta={<span className="flex items-center gap-2">{s.ai_status && <span>{s.ai_status}</span>}<ExperimentalTag /></span>}
      actions={canControl ? (
        <Button size="sm" variant="outline" disabled={analyze.isPending || !s.id}
          onClick={() => analyze.mutate(s.id!, { onSuccess: () => toast.success("AI analysis complete"), onError })}>
          {analyze.isPending ? "Analysing" : "Run AI analysis now"}
        </Button>
      ) : undefined}
    >
      {Object.keys(analyses).filter((k) => !k.startsWith("_")).length === 0 ? (
        <p className="text-sm text-ink-2">The anomaly ensemble, forecaster and risk model run every 15 simulated minutes once 15 minutes of stream exist, or on request.</p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {crew.map((c) => {
            const a = analyses[c.astronaut_id];
            if (!a) return null;
            return (
              <li key={c.astronaut_id} className="rounded-md border border-bulkhead/70 p-3 text-sm">
                <p className="flex items-center gap-1.5 font-medium"><span className="size-2 rounded-full" style={{ background: crewColor(c.astronaut_id) }} aria-hidden />{c.name}
                  {a.sim_time && s.sim_start && <span className="ml-auto text-xs font-normal text-ink-3">at {tPlus(s.sim_start, a.sim_time)}</span>}</p>
                {!a.available ? <p className="mt-1 text-ink-2">{a.reason}</p> : (
                  <>
                    <p className="mt-1"><span className="readout text-xl font-semibold">{fmt(a.risk?.risk_score, 0)}</span><span className="text-xs text-ink-3">/100</span> {a.risk?.category_label} <span className="text-xs text-ink-3">confidence {a.risk?.confidence.level}</span></p>
                    <p className="text-xs text-ink-2">{a.flagged_windows} of {a.windows} windows flagged, {a.detections?.length ?? 0} detection(s)</p>
                    {a.risk?.warnings.slice(0, 2).map((w) => <p key={w.title} className="truncate text-xs text-ink-2">{w.title}</p>)}
                    {a.forecast ? (
                      <p className="mt-1 text-xs text-ink-3">
                        6 h forecast: {a.forecast.map((f) => { const h = f.horizons.find((x) => x.horizon_h === 6); return h ? `${f.label} ${fmt(h.value, 1)} (${fmt(h.lower, 1)} to ${fmt(h.upper, 1)})` : null; }).filter(Boolean).join("; ")}
                      </p>
                    ) : <p className="mt-1 text-xs text-ink-3">{a.forecast_error ?? "No forecast"}</p>}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </DataCard>
  );
}

function SandboxAlerts({ simId }: { simId: string }) {
  const alerts = useAlertCenter({ context: "simulation", simulation_id: simId, hours: 24 * 30 });
  const events = useMissionEvents({ context: "simulation", simulation_id: simId, limit: 60 });
  const report = useSimReport();
  const router = useRouter();
  const canReport = useCan("reports:write");
  const rows = alerts.data ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <DataCard sandbox title={`Sandbox alerts (${rows.filter((a) => a.status !== "resolved").length} unresolved)`} href="/alerts" hrefLabel="Alert centre (choose Simulation sandbox)">
        {rows.length === 0 ? <p className="text-sm text-ink-2">No sandbox alerts yet.</p> : (
          <ul className="scroll-quiet max-h-96 overflow-y-auto">
            {rows.map((a) => (
              <li key={a.id} className="flex items-start gap-2 border-b border-bulkhead/50 py-2 last:border-0">
                <PriorityBadge priority={a.priority} compact className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <Link href={`/alerts?alert=${a.id}`} className="line-clamp-2 text-sm hover:text-telemetry">{a.title}</Link>
                  <p className="text-xs text-ink-3">{a.status}, {a.classification_label}, sim. {utcTime(a.created_at)}</p>
                </div>
                {canReport && a.astronaut_id && (
                  <Button size="xs" variant="ghost" disabled={report.isPending} title="Create a sandbox incident report from this alert"
                    onClick={() => report.mutate({ id: simId, alertId: a.id }, { onSuccess: (r) => { toast.success("Sandbox incident report created"); router.push(`/reports?report=${r.id}`); }, onError })}>
                    <ClipboardList aria-hidden /> Report
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </DataCard>
      <DataCard sandbox title="Sandbox events" href={`/timeline?simulation=${simId}`} hrefLabel="Open on the timeline">
        {(events.data ?? []).length === 0 ? <p className="text-sm text-ink-2">No events yet.</p> : (
          <ol className="scroll-quiet max-h-96 overflow-y-auto">
            {(events.data ?? []).map((e) => (
              <li key={e.id} className="flex gap-2 border-b border-bulkhead/40 py-1.5 text-sm last:border-0">
                <SeverityDot severity={e.severity} className="mt-1.5" />
                <span className="min-w-0 flex-1"><span className="line-clamp-1">{e.title}</span>
                  <span className="text-xs text-ink-3">{String(e.payload.sim_offset_s != null ? `T+${Math.floor(Number(e.payload.sim_offset_s) / 60)} min` : utcTime(e.occurred_at))}, {e.category_label}</span></span>
              </li>
            ))}
          </ol>
        )}
      </DataCard>
    </div>
  );
}

// ------------------------------------------------------------------ playback ----
function Playback({ runs }: { runs: SimRun[] }) {
  const [id, setId] = useState<string | null>(runs[0]?.id ?? null);
  const pb = usePlayback(id);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const data = pb.data;
  const start = data ? Date.parse(data.start) : 0;
  const end = data ? Date.parse(data.end) : 0;
  const pos = cursor ?? end;
  useEffect(() => {
    if (!playing || !data) return;
    const step = Math.max(1000, (end - start) / 120);
    const timer = setInterval(() => setCursor((c) => {
      const next = (c ?? start) + step;
      if (next >= end) { setPlaying(false); return end; }
      return next;
    }), 250);
    return () => clearInterval(timer);
  }, [playing, data, start, end]);
  const frameAt = data ? new Date(Math.round(pos / 10_000) * 10_000).toISOString() : null;
  const frame = useSimFrame(id, frameAt);
  const rows: ChartRow[] = useMemo(() => {
    if (!data) return [];
    const map = new Map<number, ChartRow>();
    for (const s of data.series) for (const p of s.points as { ts: string; heart_rate: number; spo2: number }[]) {
      const t = Date.parse(p.ts);
      if (t > pos) continue;
      const row = map.get(t) ?? ({ t } as ChartRow);
      row[`hr_${s.astronaut_id}`] = p.heart_rate;
      row[`spo2_${s.astronaut_id}`] = p.spo2;
      map.set(t, row);
    }
    return [...map.values()].sort((a, b) => a.t - b.t);
  }, [data, pos]);
  const series = (prefix: string) => (data?.series ?? []).map((s) => ({ key: `${prefix}_${s.astronaut_id}`, label: s.name.split(" ")[0], color: crewColor(s.astronaut_id), dash: crewDash(s.astronaut_id) }));
  const shownEvents = (data?.events ?? []).filter((e) => Date.parse(e.occurred_at) <= pos && e.priority <= 3).slice(-12).reverse();

  if (runs.length === 0) return <EmptyState title="No recorded runs yet">Start a simulated mission; every run is stored for playback.</EmptyState>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Recorded run</p>
          <Select value={id ?? undefined} onValueChange={(v) => { setId(v); setCursor(null); setPlaying(false); }}>
            <SelectTrigger className="w-80" aria-label="Recorded run"><SelectValue placeholder="Choose a run" /></SelectTrigger>
            <SelectContent>{runs.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}, {utcDayTime(r.wall_started_at)} ({r.status}, {r.t_plus})</SelectItem>)}</SelectContent>
          </Select>
        </div>
        {data && (
          <>
            <Button variant="outline" size="sm" onClick={() => { if (pos >= end) setCursor(start); setPlaying((p) => !p); }}>
              {playing ? <><Pause aria-hidden /> Pause playback</> : <><Play aria-hidden /> Play</>}
            </Button>
            <span className="text-sm tabular-nums text-sandbox">{tPlus(data.start, pos)}</span>
          </>
        )}
      </div>
      {pb.isPending && id ? <LoadingState rows={4} /> : pb.error ? <ErrorState error={pb.error} onRetry={() => pb.refetch()} /> : data ? (
        <>
          <Slider value={[pos]} min={start} max={Math.max(end, start + 1)} step={10_000} onValueChange={([v]) => { setPlaying(false); setCursor(v); }} aria-label="Playback position" />
          <div className="grid gap-4 lg:grid-cols-2">
            <div><p className="mb-1 text-xs text-ink-2">Heart rate (bpm), {data.resolution_seconds} s buckets</p>
              {rows.length > 1 ? <TrendChart data={rows} series={series("hr")} unit="bpm" height={170} endLabels ariaLabel="Playback heart rate" /> : <p className="text-sm text-ink-2">Move the cursor forward.</p>}</div>
            <div><p className="mb-1 text-xs text-ink-2">SpO₂ (%)</p>
              {rows.length > 1 ? <TrendChart data={rows} series={series("spo2")} unit="%" decimals={1} height={170} endLabels ariaLabel="Playback SpO2" /> : null}</div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title={`State at ${tPlus(data.start, pos)}`} bodyClassName="pt-2">
              {frame.data ? (
                <ul className="space-y-1.5 text-sm">
                  {frame.data.crew.map((c) => {
                    const r = c.reading as { heart_rate?: number; spo2?: number; respiratory_rate?: number; scenario?: string | null; source?: string } | null;
                    return (
                      <li key={String(c.astronaut_id)} className="flex flex-wrap items-center gap-x-3">
                        <span className="w-28 truncate">{String(c.name)}</span>
                        {r ? <span className="tabular-nums text-ink-2">HR {fmt(r.heart_rate, 0)}, SpO₂ {fmt(r.spo2, 1)}, RR {fmt(r.respiratory_rate, 0)}</span> : <span className="text-ink-3">no sample yet</span>}
                        {r?.scenario && <span className="text-xs text-caution">{r.scenario.replace(/_/g, " ")}</span>}
                        {r?.source === "external" && <span className="text-xs text-sandbox">sent externally</span>}
                      </li>
                    );
                  })}
                  <li className="pt-1 text-xs text-ink-3">{frame.data.active_injections.length} injection(s) active, {frame.data.alerts.length} alert(s) raised so far</li>
                </ul>
              ) : <LoadingState rows={2} />}
            </Panel>
            <Panel title="Events up to the cursor" bodyClassName="pt-2">
              {shownEvents.length === 0 ? <p className="text-sm text-ink-2">None yet.</p> : (
                <ol className="space-y-1 text-sm">{shownEvents.map((e) => <li key={e.id} className="flex gap-2"><span className="w-20 shrink-0 text-xs text-ink-3 tabular-nums">{tPlus(data.start, e.occurred_at)}</span><span className="line-clamp-1">{e.title}</span></li>)}</ol>
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function SimulationView() {
  const cat = useSimCatalogue();
  const s = useSimState();
  const runs = useSimRuns();
  const active = s?.active;
  const latestId = s?.id ?? null;
  return (
    <div className="space-y-4">
      <SandboxBanner />
      {cat.isPending || !s ? <LoadingState rows={6} /> : cat.error ? <ErrorState error={cat.error} onRetry={() => cat.refetch()} /> : (
        <ErrorBoundary label="Mission simulation">
          {active || (s.id && s.status !== "reset") ? (
            <div className="space-y-4">
              <ControlBar s={s} />
              {!active && (
                <Panel title="Start another run">
                  <StartPanel cat={cat.data} />
                </Panel>
              )}
              <div className="grid gap-4 2xl:grid-cols-[1fr_24rem]">
                <LiveTelemetry s={s} />
                <div className="space-y-4">
                  <InjectPanel s={s} cat={cat.data} />
                  <TelemetryPanel s={s} />
                </div>
              </div>
              <AiPanel s={s} />
              {latestId && <SandboxAlerts simId={latestId} />}
            </div>
          ) : (
            <StartPanel cat={cat.data} />
          )}
        </ErrorBoundary>
      )}
      <Panel title="Mission playback" description="Replay any recorded sandbox run from the stored samples, events and alerts.">
        <ErrorBoundary label="Playback">
          <Playback runs={runs.data ?? []} />
        </ErrorBoundary>
      </Panel>
    </div>
  );
}
