"use client";

import {
  BrainCircuit,
  Check,
  CheckCheck,
  CircleSlash,
  ClipboardList,
  Clock,
  FastForward,
  Lock,
  MessageSquareText,
  MousePointerClick,
  Pause,
  Play,
  RotateCcw,
  ShieldOff,
  Siren,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { DataCard, Meter, Stat } from "@/components/mc/card";
import { ExperimentalTag, OriginChip, SandboxTag } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAstronauts, useWeatherSummary } from "@/lib/api/hooks";
import { useAsk } from "@/lib/api/medical-hooks";
import {
  type AlertCenterFilters,
  useAlertCenter,
  useAlertCenterAction,
  useSandboxState,
  useSimAnalyze,
  useSimCatalogue,
  useSimControl,
  useSimFrame,
  useSimReport,
  useSimReports,
  useSimRun,
  useSimSpeed,
  useStartSim,
} from "@/lib/api/mission-hooks";
import type { AssistantAnswer, IncidentReport, SimCatalogue, SimState } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { crewColor } from "@/lib/crew";
import {
  type CrewAnalysis,
  defaultFocus,
  evaluateSteps,
  mergeAnalyses,
  parseAnalyses,
  pickFocusAlert,
  type StepResult,
  type StepStatus,
} from "@/lib/demo/steps";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The speeds the sandbox console offers (simulation-view.tsx), capped by the catalogue's max_speed. */
const SPEEDS = [1, 5, 10, 20, 30, 40, 60, 120];
/** The preset whose description covers rule alerts, AI detection and the incident report path. */
const DEMO_PRESET = "desaturation_emergency";
/**
 * Fixed random seed sent with every demo start: with the same preset and speed the scripted events and
 * the engine's noise stream repeat (the crew activity schedule still follows the start time of day).
 */
const DEMO_SEED = 2026;

const STATUS_TEXT: Record<string, string> = {
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
  reset: "Reset",
  idle: "Idle",
};

const errMessage = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");
const onError = (e: unknown) => toast.error(errMessage(e));
const firstName = (name: string) => name.split(" ")[0] ?? name;

const STEP_META: Record<StepStatus, { label: string; icon: typeof Check; cls: string; rail: string }> = {
  done: { label: "Observed", icon: Check, cls: "border-nominal/50 text-nominal", rail: "border-nominal/60 bg-nominal/10 text-nominal" },
  waiting: { label: "Waiting for data", icon: Clock, cls: "border-ink-3/50 text-ink-2", rail: "border-bulkhead text-ink-2" },
  action: { label: "Your action", icon: MousePointerClick, cls: "border-telemetry/50 text-telemetry", rail: "border-telemetry/60 text-telemetry" },
  locked: { label: "Not started", icon: Lock, cls: "border-bulkhead text-ink-3", rail: "border-bulkhead/70 text-ink-3" },
  blocked: { label: "Not permitted", icon: ShieldOff, cls: "border-bulkhead text-ink-3", rail: "border-bulkhead/70 text-ink-3" },
  unavailable: { label: "Unavailable", icon: CircleSlash, cls: "border-caution/50 text-caution", rail: "border-caution/50 text-caution" },
};

// ------------------------------------------------------------------- banner ----
function DemoBanner({ label }: { label?: string }) {
  return (
    <div className="flex items-stretch overflow-hidden rounded-lg border border-sandbox/50 bg-sandbox/8" role="note">
      <span className="sandbox-tape w-3 shrink-0 opacity-80" aria-hidden />
      <div className="px-4 py-2.5 text-sm text-foreground">
        <p>
          <span className="font-semibold text-sandbox">Simulated demonstration in the isolated sandbox.</span> Every crew
          value on this page comes from the mission simulation sandbox: fictional crew, a software test mission, its own
          engine and clock. Nothing reaches the live crew stream, the operational digital twin or the AI baselines. The
          NASA space-weather data in step 7 is real
          <span className="mx-1 inline-block align-middle"><OriginChip origin="nasa" /></span>
          and shown for context only. Nothing here is a diagnosis or a clinical assessment.
        </p>
        {label && <p className="mt-1 text-xs text-ink-3">{label}</p>}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- controls ----
function Controls({
  cat,
  state,
  followed,
  onFollow,
  onReset,
}: {
  cat: SimCatalogue;
  state: SimState | undefined;
  followed: SimState | null;
  onFollow: (id: string) => void;
  onReset: () => void;
}) {
  const canControl = useCan("simulation:control");
  const start = useStartSim();
  const control = useSimControl();
  const speed = useSimSpeed();
  const [presetChoice, setPresetChoice] = useState<string | null>(null);
  const [speedChoice, setSpeedChoice] = useState<string | null>(null);
  const presetKey =
    presetChoice ?? (cat.presets.some((p) => p.key === DEMO_PRESET) ? DEMO_PRESET : cat.presets[0]?.key ?? "");
  const preset = cat.presets.find((p) => p.key === presetKey) ?? null;
  const shown = followed ?? (state?.id && state.status !== "idle" ? state : null);
  const foreign = state?.id && state.status !== "idle" && state.id !== followed?.id ? state : null;
  const anyActive = !!state?.active;
  const speeds = [...new Set([...SPEEDS.filter((v) => v <= cat.max_speed), ...(preset ? [preset.speed] : []), ...(followed?.speed ? [followed.speed] : [])])].sort((a, b) => a - b);
  const speedValue = followed?.active ? String(followed.speed ?? "") : speedChoice ?? String(preset?.speed ?? 30);
  const busy = start.isPending || control.isPending;

  const act = (id: string, action: "pause" | "resume" | "reset") =>
    control.mutate(
      { id, action },
      {
        onSuccess: () => {
          toast.success(action === "reset" ? "Sandbox run reset" : action === "pause" ? "Sandbox run paused" : "Sandbox run resumed");
          if (action === "reset") onReset();
        },
        onError,
      },
    );

  return (
    <DataCard
      sandbox
      title={<span className="flex items-center gap-2">Demonstration controls <SandboxTag>sandbox</SandboxTag></span>}
      meta={<span>one sandbox run at a time</span>}
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full space-y-1 sm:w-72">
          <Label htmlFor="demo-preset" className="text-xs text-ink-3">Scenario</Label>
          <Select value={presetKey} onValueChange={(v) => { setPresetChoice(v); setSpeedChoice(null); }} disabled={!!followed?.active}>
            <SelectTrigger id="demo-preset" className="w-full" aria-label="Scenario preset"><SelectValue placeholder="Choose a scenario" /></SelectTrigger>
            <SelectContent>{cat.presets.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="demo-speed" className="text-xs text-ink-3">Speed</Label>
          <Select
            value={speedValue}
            onValueChange={(v) => {
              if (followed?.active && followed.id) speed.mutate({ id: followed.id, speed: Number(v) }, { onError });
              else setSpeedChoice(v);
            }}
            disabled={!canControl || speed.isPending || (anyActive && !followed?.active)}
          >
            <SelectTrigger id="demo-speed" className="w-28" aria-label="Simulation speed"><FastForward className="size-3.5" aria-hidden /><SelectValue /></SelectTrigger>
            <SelectContent>{speeds.map((v) => <SelectItem key={v} value={String(v)}>{v}x</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!canControl || !cat.enabled || anyActive || busy || !preset}
            onClick={() =>
              preset &&
              start.mutate(
                { preset: preset.key, speed: Number(speedValue), seed: DEMO_SEED, name: `Demo mode: ${preset.label}` },
                {
                  onSuccess: (r) => {
                    if (r.id) onFollow(r.id);
                    toast.success("Demonstration run started in the sandbox");
                  },
                  onError,
                },
              )
            }
          >
            <Play aria-hidden /> Start
          </Button>
          <Button variant="outline" disabled={!canControl || busy || followed?.status !== "running"} onClick={() => followed?.id && act(followed.id, "pause")}>
            <Pause aria-hidden /> Pause
          </Button>
          <Button variant="outline" disabled={!canControl || busy || followed?.status !== "paused"} onClick={() => followed?.id && act(followed.id, "resume")}>
            <Play aria-hidden /> Resume
          </Button>
          <Button
            variant="ghost"
            disabled={!canControl || busy || !followed?.id}
            onClick={() => followed?.id && act(followed.id, "reset")}
            title="Abandon the run, close its sandbox alerts and return the sandbox to idle. Stored data stay available for playback."
          >
            <RotateCcw aria-hidden /> Reset
          </Button>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 sm:ml-auto" aria-live="polite">
          <Stat label="Simulation clock" value={shown?.t_plus ?? "T+00:00:00"} tone="sandbox" sub={shown?.sim_time ? `${utcDayTime(shown.sim_time)} UTC (sim.)` : "no run"} />
          <Stat label="Speed" value={shown?.speed ? `${shown.speed}x` : "—"} />
          <Stat label="Status" value={STATUS_TEXT[shown?.status ?? "idle"] ?? shown?.status ?? "Idle"} sub={shown ? `${fmt((shown.progress ?? 0) * 100, 0)}% of planned length` : undefined} />
        </div>
      </div>

      {preset && !followed && (
        <p className="mt-3 text-sm text-ink-2">
          {preset.description}{" "}
          <span className="text-ink-3">
            {preset.crew_size} crew, {preset.duration_minutes} simulated minutes at {preset.speed}x by default
            {preset.script.length ? `, ${preset.script.length} scripted event${preset.script.length === 1 ? "" : "s"}` : ", no scripted events"}.
            Every demo run uses seed {DEMO_SEED}, so the scripted events and the generated noise repeat.
          </span>
        </p>
      )}
      {!cat.enabled && <p className="mt-3 text-sm text-caution">Mission simulation is disabled on this deployment, so no demonstration run can start.</p>}
      {!canControl && (
        <p className="mt-3 text-sm text-ink-2">
          Starting, pausing, resuming, resetting and changing the speed need the simulation:control permission (mission
          operator role). You can still follow a run someone else started.
        </p>
      )}
      {foreign && (
        <div role="status" className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-sandbox/40 bg-sandbox/5 px-3 py-2 text-sm">
          <p className="min-w-0 flex-1">
            {foreign.active ? (
              <>Another sandbox run is {foreign.status}: <span className="font-medium">{foreign.name}</span> ({foreign.t_plus}, started by {foreign.created_by}). Only one sandbox run can be active at a time.</>
            ) : (
              <>The most recent sandbox run, <span className="font-medium">{foreign.name}</span>, is {foreign.status} at {foreign.t_plus}. Review its steps or start a new demonstration run.</>
            )}
          </p>
          <Button size="sm" variant="outline" onClick={() => foreign.id && onFollow(foreign.id)}>
            {foreign.active ? "Take control of this run" : "Review this run"}
          </Button>
          {foreign.active && (
            <Button size="sm" variant="ghost" disabled={!canControl || busy} onClick={() => foreign.id && act(foreign.id, "reset")}>
              <RotateCcw aria-hidden /> Reset it
            </Button>
          )}
        </div>
      )}
      {followed?.error && <p className="mt-3 text-sm text-critical">{followed.error}</p>}
    </DataCard>
  );
}

// -------------------------------------------------------------------- steps ----
function StatusChip({ status }: { status: StepStatus }) {
  const m = STEP_META[status];
  const Icon = m.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-px text-[11px] font-medium whitespace-nowrap", m.cls)}>
      <Icon className="size-3" aria-hidden />
      {m.label}
    </span>
  );
}

function StepItem({ step, tags, children }: { step: StepResult; tags?: ReactNode; children?: ReactNode }) {
  const m = STEP_META[step.status];
  const headingId = `demo-step-${step.id}`;
  return (
    <li
      aria-labelledby={headingId}
      className={cn("rounded-lg border bg-hull px-4 py-3", step.status === "done" ? "border-nominal/30" : step.status === "action" ? "border-telemetry/40" : "border-bulkhead/70")}
    >
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-semibold tabular-nums", m.rail)} aria-hidden>
          {step.status === "done" ? <Check className="size-4" /> : step.id}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 id={headingId} className="font-heading text-[15px] font-semibold leading-tight">
              <span className="text-ink-3">{step.id}.</span> {step.title}
            </h3>
            <StatusChip status={step.status} />
            {tags}
          </div>
          <p className="mt-1 text-sm text-ink-2">{step.summary}</p>
          {step.evidence.length > 0 && (
            <dl className="mt-2 grid gap-x-4 gap-y-1 rounded-md border border-bulkhead/50 bg-panel-2/40 px-3 py-2 text-sm sm:grid-cols-[minmax(7rem,11rem)_1fr]">
              {step.evidence.map((e, i) => (
                <div key={i} className="contents">
                  <dt className="text-xs text-ink-3 sm:pt-0.5">{e.label}</dt>
                  <dd className="min-w-0 break-words tabular-nums text-foreground">{e.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {children}
          {step.href && (
            <Link href={step.href} className="mt-2 inline-block text-xs font-medium text-telemetry hover:underline">
              {step.hrefLabel ?? "Open"}
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

const Note = ({ children }: { children: ReactNode }) => <p className="mt-2 text-xs text-ink-3">{children}</p>;

// --------------------------------------------------------------------- view ----
export function DemoView() {
  const cat = useSimCatalogue();
  const { state, query: stateQ } = useSandboxState();
  const astronauts = useAstronauts();
  const weather = useWeatherSummary(30);
  const canControl = useCan("simulation:control");
  const canManage = useCan("alerts:manage");
  const canReport = useCan("reports:write");
  const canReadReports = useCan("reports:read");
  const canAsk = useCan("assistant:use");

  const [followedId, setFollowedId] = useState<string | null>(null);
  const [focusChoice, setFocusChoice] = useState<{ runId: string; aid: string } | null>(null);
  const [fresh, setFresh] = useState<{ runId: string; data: Record<string, CrewAnalysis> } | null>(null);
  const [answer, setAnswer] = useState<{ runId: string; aid: string; question: string; data: AssistantAnswer } | null>(null);
  const [created, setCreated] = useState<{ runId: string; data: IncidentReport } | null>(null);

  const followed = state?.id && state.id === followedId && state.status !== "idle" ? state : null;
  const runId = followed?.id ?? null;
  // Polled while followed (not only while active) so the analysis stored as the run ends is picked up.
  const run = useSimRun(runId, !!followed);
  const alertFilters: AlertCenterFilters = useMemo(
    () => ({ context: "simulation", simulation_id: runId ?? undefined, hours: 24 * 30 }),
    [runId],
  );
  const alerts = useAlertCenter(alertFilters, !!runId);
  const reports = useSimReports(runId, canReadReports);
  const analyze = useSimAnalyze();
  const ask = useAsk();
  const ack = useAlertCenterAction("acknowledge");
  const report = useSimReport();

  const crew = followed?.crew ?? [];
  const names: Record<string, string> = {};
  const roles: Record<string, string> = {};
  for (const a of astronauts.data ?? []) {
    names[a.id] = a.name;
    roles[a.id] = a.role;
  }
  for (const r of followed?.latest ?? []) names[r.astronaut_id] = r.name;

  const storedRun = run.data?.id === runId ? run.data : null;
  const focusId =
    runId && focusChoice?.runId === runId && crew.includes(focusChoice.aid) ? focusChoice.aid : defaultFocus(storedRun, crew);
  const analyses = mergeAnalyses(parseAnalyses(storedRun?.analyses), fresh?.runId === runId ? fresh.data : {});
  const analysis = focusId ? analyses[focusId] ?? null : null;
  // The run frame at the instant of the latest analysis: the sandbox twin snapshot pairs the two.
  const frameAt = analysis?.available && analysis.sim_time ? new Date(analysis.sim_time).toISOString() : null;
  const frame = useSimFrame(runId, frameAt);
  const alertRows = runId ? alerts.data : undefined;
  const focusAlert = pickFocusAlert(alertRows, focusId);
  const runReport =
    created?.runId === runId
      ? created.data
      : [...(reports.data ?? [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0] ?? null;
  const shownAnswer = answer && answer.runId === runId && answer.aid === focusId ? answer : null;
  const focusFirst = focusId ? firstName(names[focusId] ?? focusId) : "";
  const question = `How is ${focusFirst} doing right now?`;

  const steps = evaluateSteps({
    state: followed,
    run: storedRun,
    presetLabel: cat.data?.presets.find((p) => p.key === followed?.preset)?.label ?? null,
    focusId,
    names,
    roles,
    analysis,
    analyses,
    alerts: alertRows,
    alertsError: alerts.error && !alerts.data ? errMessage(alerts.error) : null,
    frame: frame.data?.simulation_id === runId ? frame.data : null,
    weather: weather.data ?? null,
    weatherError: weather.error && !weather.data ? errMessage(weather.error) : null,
    answer: shownAnswer?.data ?? null,
    report: runReport,
    perms: { control: canControl, manageAlerts: canManage, writeReports: canReport, assistant: canAsk },
  });
  const done = steps.filter((s) => s.status === "done").length;
  const aiStep = [3, 5, 6, 8].find((n) => steps[n - 1].status !== "done");

  const follow = (id: string) => {
    setFollowedId(id);
    setFocusChoice(null);
  };

  if (cat.isPending || (!state && stateQ.isPending)) return <div className="space-y-4"><DemoBanner /><LoadingState rows={8} label="Loading the sandbox" /></div>;
  if (cat.error) return <div className="space-y-4"><DemoBanner /><ErrorState title="Couldn't load the sandbox catalogue" error={cat.error} onRetry={() => cat.refetch()} /></div>;
  if (!state && stateQ.error) return <div className="space-y-4"><DemoBanner /><ErrorState title="Couldn't load the sandbox state" error={stateQ.error} onRetry={() => stateQ.refetch()} /></div>;

  const aiAction = (
    <div className="mt-2 space-y-1">
      {canControl && followed?.active ? (
        <Button
          size="sm"
          variant="outline"
          disabled={analyze.isPending}
          onClick={() =>
            runId &&
            analyze.mutate(runId, {
              onSuccess: (r) => {
                setFresh({ runId, data: parseAnalyses(r) });
                toast.success("AI analysis of the sandbox stream complete");
              },
              onError,
            })
          }
        >
          <BrainCircuit aria-hidden /> {analyze.isPending ? "Analysing" : "Run AI analysis now"}
        </Button>
      ) : followed && !followed.active ? (
        <Note>The run has ended; an on-request analysis needs an active run. The stored analyses are shown.</Note>
      ) : followed && !canControl ? (
        <Note>Running the analysis on request needs the simulation:control permission; the periodic analysis still runs.</Note>
      ) : null}
    </div>
  );

  const extras: Record<number, { tags?: ReactNode; body?: ReactNode }> = {
    1: { tags: <OriginChip origin="sandbox" /> },
    2: { tags: <OriginChip origin="sandbox" /> },
    3: { tags: <ExperimentalTag />, body: aiStep === 3 ? aiAction : undefined },
    4: { tags: <OriginChip origin="sandbox" /> },
    5: { tags: <ExperimentalTag />, body: aiStep === 5 ? aiAction : undefined },
    6: { tags: <ExperimentalTag />, body: aiStep === 6 ? aiAction : undefined },
    7: {
      tags: <OriginChip origin="nasa" />,
      body: weather.error && !weather.data ? (
        <Button size="sm" variant="outline" className="mt-2" onClick={() => weather.refetch()}>Retry</Button>
      ) : undefined,
    },
    8: {
      tags: <><OriginChip origin="sandbox" /><ExperimentalTag /></>,
      body: (
        <>
          {aiStep === 8 && aiAction}
          <Note>
            This is a sandbox twin snapshot built from the run frame and the AI analysis. The operational{" "}
            <Link href="/twin" className="text-telemetry hover:underline">Digital twin</Link> tracks the live crew stream
            and is not updated by sandbox runs.
          </Note>
        </>
      ),
    },
    9: {
      body: followed ? (
        <div className="mt-2 space-y-2">
          <p className="text-sm"><span className="text-ink-3">Prepared question: </span>&ldquo;{shownAnswer?.question ?? question}&rdquo;</p>
          {canAsk && (
            <Button
              size="sm"
              variant={steps[8].status === "done" ? "outline" : "default"}
              disabled={ask.isPending || !focusId}
              onClick={() =>
                runId &&
                focusId &&
                ask.mutate(
                  { question, astronaut_id: focusId },
                  { onSuccess: (data) => setAnswer({ runId, aid: focusId, question, data }), onError },
                )
              }
            >
              <MessageSquareText aria-hidden /> {ask.isPending ? "Asking" : steps[8].status === "done" ? "Ask again" : "Ask the assistant"}
            </Button>
          )}
          {shownAnswer?.data.escalation.required && (
            <p role="alert" className="flex items-start gap-2 text-sm text-critical">
              <Siren className="mt-0.5 size-4 shrink-0" aria-hidden /> {shownAnswer.data.escalation.message}
            </p>
          )}
          <Note>
            The assistant answers from ASTRA-MED&apos;s stored records and reference documents for this crew member, not
            from the sandbox stream itself.{shownAnswer ? ` ${shownAnswer.data.mode === "claude" ? "Answered by Claude from the cited sources." : "Offline answer composed from the cited records and passages."}` : ""}
          </Note>
        </div>
      ) : undefined,
    },
    10: { tags: <OriginChip origin="sandbox" /> },
    11: {
      body:
        focusAlert && steps[10].status === "action" ? (
          <Button
            size="sm"
            className="mt-2"
            disabled={ack.isPending}
            onClick={() => ack.mutate({ id: focusAlert.id }, { onSuccess: () => toast.success("Sandbox alert acknowledged"), onError })}
          >
            <CheckCheck aria-hidden /> {ack.isPending ? "Acknowledging" : "Acknowledge"}
          </Button>
        ) : undefined,
    },
    12: {
      body:
        steps[11].status === "action" && runId ? (
          <Button
            size="sm"
            className="mt-2"
            disabled={report.isPending}
            onClick={() =>
              report.mutate(
                { id: runId, alertId: focusAlert?.id, astronautId: focusId ?? undefined },
                {
                  onSuccess: (r) => {
                    setCreated({ runId, data: r });
                    toast.success("Sandbox incident report created");
                  },
                  onError,
                },
              )
            }
          >
            <ClipboardList aria-hidden /> {report.isPending ? "Generating" : "Generate report"}
          </Button>
        ) : undefined,
    },
  };

  return (
    <div className="space-y-4">
      <DemoBanner label={cat.data.label} />
      {cat.data.presets.length === 0 ? (
        <EmptyState title="No scenario presets">The sandbox catalogue returned no presets, so there is nothing to demonstrate.</EmptyState>
      ) : (
        <ErrorBoundary label="Demo mode">
          <Controls cat={cat.data} state={state} followed={followed} onFollow={follow} onReset={() => setFollowedId(null)} />

          <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
            <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
              <DataCard title="Progress">
                <p className="text-sm" aria-live="polite">
                  <span className="readout text-2xl font-semibold">{done}</span>
                  <span className="text-ink-3"> of {steps.length} steps observed</span>
                </p>
                <div className="mt-2"><Meter value={done} max={steps.length} tone="nominal" label="Demonstration steps observed" /></div>
                <p className="mt-2 text-xs text-ink-3">A step is ticked only when the condition appears in the backend responses; the evidence shown is what was observed.</p>
              </DataCard>
              {followed && crew.length > 0 && (
                <DataCard title="Crew member followed">
                  <ToggleGroup
                    type="single"
                    variant="outline"
                    size="sm"
                    value={focusId ?? ""}
                    onValueChange={(v) => v && runId && setFocusChoice({ runId, aid: v })}
                    aria-label="Crew member the steps follow"
                    className="flex-wrap justify-start"
                  >
                    {crew.map((aid) => (
                      <ToggleGroupItem key={aid} value={aid} aria-label={names[aid] ?? aid}>
                        <span className="size-2 rounded-full" style={{ background: crewColor(aid) }} aria-hidden />
                        {firstName(names[aid] ?? aid)}
                      </ToggleGroupItem>
                    ))}
                  </ToggleGroup>
                  <p className="mt-2 text-xs text-ink-3">Steps 2, 3, 5, 6, 8, 9 and 10 follow this fictional crew member. The default is the target of the run&apos;s first scripted event.</p>
                </DataCard>
              )}
            </aside>

            <ol className="min-w-0 space-y-3" aria-label="Demonstration steps">
              {steps.map((step) => (
                <StepItem key={step.id} step={step} tags={extras[step.id]?.tags}>
                  {extras[step.id]?.body}
                </StepItem>
              ))}
            </ol>
          </div>
        </ErrorBoundary>
      )}
    </div>
  );
}
