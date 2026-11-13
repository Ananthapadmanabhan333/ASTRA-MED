"use client";

import { ClipboardList, ExternalLink, Fingerprint, Satellite, Stethoscope, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { AlertsConsole } from "@/components/alerts/alerts-console";
import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { DataCard } from "@/components/mc/card";
import { ExperimentalTag, OriginChip, PriorityBadge, SandboxTag, SeverityDot } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { CrewPicker, useParamState } from "@/components/medical/common";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCreateReport } from "@/lib/api/medical-hooks";
import {
  type AlertCenterFilters,
  useAlertCenter,
  useAlertCenterAction,
  useAlertCenterSummary,
  useAlertDetail,
  useSimReport,
} from "@/lib/api/mission-hooks";
import type { AlertCenterStatus, MissionAlert, MissionAlertDetail, MissionContext } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { fmt, relativeTime, utcDayTime } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

const SOURCES: { value: string; label: string }[] = [
  { value: "all", label: "All modules" },
  { value: "physiological_monitoring", label: "Physiological monitoring" },
  { value: "anomaly_detection", label: "AI anomaly detection" },
  { value: "predictive_forecast", label: "AI predictive forecasting" },
  { value: "space_weather", label: "NASA space weather" },
  { value: "environment_monitoring", label: "Environmental monitoring" },
];

const STATUS_LABEL: Record<AlertCenterStatus, string> = { open: "Open", acknowledged: "Acknowledged", resolved: "Resolved" };

function AlertRow({ a, selected, onSelect }: { a: MissionAlert; selected: boolean; onSelect: () => void }) {
  const now = useNow(15_000);
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
        className={cn(
          "relative grid w-full grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-b border-bulkhead/50 px-3 py-2.5 text-left transition-colors last:border-0",
          selected ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/50",
          a.context === "simulation" && "sandbox-edge",
          a.status === "resolved" && "opacity-70",
        )}
      >
        <PriorityBadge priority={a.priority} compact />
        <span className="min-w-0">
          <span className="line-clamp-2 text-sm font-medium">{a.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
            <SeverityDot severity={a.severity} />
            <span>{STATUS_LABEL[a.status]}</span>
            <span>{a.source_label}</span>
            {a.experimental && <span className="text-advisory">experimental</span>}
            <span className="tabular-nums">{now ? relativeTime(a.created_at, now) : utcDayTime(a.created_at)}</span>
            {a.condition_cleared_at && a.status !== "resolved" && <span className="text-nominal">condition cleared</span>}
            {a.occurrences > 1 && <span>x{a.occurrences}</span>}
          </span>
        </span>
      </button>
    </li>
  );
}

function KeyValues({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-3">{k}</dt>
          <dd className="min-w-0 break-words">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

function valueText(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : fmt(v, 2);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string") return v.replace(/_/g, " ");
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" && x ? (x as { label?: string; title?: string; signal?: string }).label ?? (x as { title?: string }).title ?? (x as { signal?: string }).signal ?? "" : valueText(x))).filter(Boolean).join(", ");
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("value" in o) return `${valueText(o.value)}${o.unit ? ` ${o.unit}` : ""}${o.deviation_sigma != null ? ` (${valueText(o.deviation_sigma)} σ)` : ""}`;
    return Object.entries(o).map(([k, x]) => `${k} ${valueText(x)}`).join(", ");
  }
  return String(v);
}

function Measurements({ m }: { m: Record<string, unknown> }) {
  const entries = Object.entries(m).filter(([k, v]) => v !== null && v !== undefined && !["link"].includes(k));
  if (entries.length === 0) return <p className="text-sm text-ink-2">No measurements attached.</p>;
  return <KeyValues rows={entries.map(([k, v]) => [k.replace(/_/g, " "), valueText(v)])} />;
}

function Correlations({ c }: { c: Record<string, unknown> }) {
  if (!c || Object.keys(c).length === 0) return <p className="text-sm text-ink-2">No correlation was computed for this alert.</p>;
  const scen = (c.injected_scenarios as { id: string; label: string; triggered_by: string; intensity: number }[]) ?? [];
  const sw = (c.space_weather as { events: { id: string; title: string; offset_hours: number; detail: string | null }[]; note: string } | null) ?? null;
  const hab = c.habitat as { parameter: string; value: number; unit: string; deviation_sigma: number } | null;
  const related = (c.related_events as { id: string; title: string; occurred_at: string }[]) ?? [];
  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs text-ink-3">Injected test scenarios at the time</p>
        {scen.length ? (
          <ul className="mt-1 space-y-0.5">
            {scen.map((s) => <li key={s.id} className="text-caution">{s.label} ({s.triggered_by}, intensity {fmt(s.intensity, 2)})</li>)}
          </ul>
        ) : (
          <p className="mt-1 text-ink-2">None</p>
        )}
      </div>
      {hab && (
        <p><span className="text-xs text-ink-3">Simulated habitat: </span>{hab.parameter} {hab.value} {hab.unit} ({fmt(hab.deviation_sigma, 1)} σ)</p>
      )}
      {c.dose_rate_multiplier != null && <p><span className="text-xs text-ink-3">Habitat dose rate: </span>x{valueText(c.dose_rate_multiplier)} background</p>}
      <div>
        <p className="flex items-center gap-2 text-xs text-ink-3">Real NASA events within {fmt(Number((sw as { window_hours?: number } | null)?.window_hours ?? 48), 0)} h <OriginChip origin="nasa" /></p>
        {sw && sw.events.length ? (
          <ul className="mt-1 space-y-0.5">
            {sw.events.map((e) => (
              <li key={e.id} className="flex gap-2"><Satellite className="mt-0.5 size-3.5 shrink-0 text-nominal" aria-hidden />{e.title} {e.detail ? <span className="text-ink-2">{e.detail}</span> : null} <span className="text-ink-3">{e.offset_hours > 0 ? "+" : ""}{fmt(e.offset_hours, 1)} h</span></li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ink-2">None in the window.</p>
        )}
        {sw?.note && <p className="mt-1 text-xs text-ink-3">{sw.note}</p>}
      </div>
      {related.length > 0 && (
        <div>
          <p className="text-xs text-ink-3">Related mission events (30 min before)</p>
          <ul className="mt-1 space-y-0.5">{related.slice(0, 6).map((e) => <li key={e.id} className="truncate">{e.title}</li>)}</ul>
        </div>
      )}
      {typeof c.method === "string" && <p className="text-xs text-ink-3">{c.method}</p>}
    </div>
  );
}

function Lifecycle({ a, pin }: { a: MissionAlertDetail; pin: () => void }) {
  const canManage = useCan("alerts:manage");
  const canReport = useCan("reports:write");
  const ack = useAlertCenterAction("acknowledge");
  const resolve = useAlertCenterAction("resolve");
  const report = useCreateReport();
  const simReport = useSimReport();
  const router = useRouter();
  const [note, setNote] = useState("");
  const closed = a.status === "resolved";
  const onError = (e: unknown) => toast.error(e instanceof Error ? e.message : "The action failed.");
  const ruleAlert = a.source === "physiological_monitoring" && a.context === "operations";
  const canMakeReport = canReport && !!a.astronaut_id && (ruleAlert || a.context === "simulation");
  return (
    <div className="space-y-3">
      {canManage && !closed ? (
        <div className="space-y-2">
          <Label htmlFor="alert-note" className="text-xs text-ink-2">
            Note (optional to acknowledge, required to resolve)
          </Label>
          <Textarea id="alert-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={3}
            placeholder="What was done or decided" />
          <div className="flex flex-wrap gap-2">
            {a.status === "open" && (
              <Button size="sm" variant="outline" disabled={ack.isPending}
                onClick={() => { pin(); ack.mutate({ id: a.id, note }, { onSuccess: () => { toast.success("Alert acknowledged"); setNote(""); }, onError }); }}>
                Acknowledge
              </Button>
            )}
            <Button size="sm" disabled={resolve.isPending || note.trim().length === 0}
              onClick={() => { pin(); resolve.mutate({ id: a.id, note }, { onSuccess: () => { toast.success("Alert resolved"); setNote(""); }, onError }); }}>
              Resolve
            </Button>
          </div>
        </div>
      ) : !closed ? (
        <p className="text-sm text-ink-2">Your role can view this alert but not acknowledge or resolve it.</p>
      ) : null}
      {canMakeReport && (
        <Button size="sm" variant="outline" disabled={report.isPending || simReport.isPending}
          onClick={() => {
            if (a.context === "simulation" && a.simulation_id) {
              simReport.mutate({ id: a.simulation_id, alertId: a.id }, {
                onSuccess: (r) => { toast.success("Sandbox incident report created"); router.push(`/reports?report=${r.id}`); },
                onError,
              });
            } else {
              report.mutate({ alert_id: a.source_ref }, {
                onSuccess: (r) => { toast.success("Incident report created"); router.push(`/reports?report=${r.id}`); },
                onError,
              });
            }
          }}>
          <ClipboardList aria-hidden /> Create incident report
        </Button>
      )}
    </div>
  );
}

function AlertDetailPanel({ id, pin }: { id: string; pin: () => void }) {
  const q = useAlertDetail(id);
  if (q.isPending) return <LoadingState rows={6} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data;
  const expl = a.explanation as Record<string, unknown>;
  return (
    <div className="space-y-4">
      <DataCard
        title={a.title}
        sandbox={a.context === "simulation"}
        tone={a.priority === 1 ? "critical" : a.priority === 2 ? "caution" : a.priority === 3 ? "advisory" : undefined}
        meta={<PriorityBadge priority={a.priority} />}
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-bulkhead px-1.5 py-px text-xs">{STATUS_LABEL[a.status]}</span>
          {a.context === "simulation" ? <SandboxTag /> : <OriginChip origin={a.data_origin} />}
          {a.experimental && <ExperimentalTag />}
          <span className="text-xs text-ink-2">{a.classification_label}</span>
        </div>
        {a.experimental && (
          <p className="mb-3 flex gap-2 rounded-md border border-advisory/40 bg-advisory/8 px-3 py-2 text-sm text-advisory">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            Experimental AI prediction. It is not a confirmed medical emergency and needs review by qualified personnel.
          </p>
        )}
        {a.summary && <p className="mb-3 text-sm text-ink-2">{a.summary}</p>}
        <KeyValues rows={[
          ["Alert ID", <code key="id" className="text-xs">{a.id}</code>],
          ["Source module", a.source_label],
          ["Astronaut", a.astronaut_id ? <Link key="a" className="text-telemetry hover:underline" href={`/crew/${a.astronaut_id}`}>{a.astronaut_id}</Link> : "Whole crew / environment"],
          ["Observed", `${utcDayTime(a.created_at)} UTC${a.context === "simulation" ? " (simulation clock)" : ""}`],
          ["Received", `${utcDayTime(a.received_at)} UTC`],
          ["Severity", a.severity],
          ["Confidence", a.confidence != null ? `${fmt(a.confidence * 100, 0)}% (${a.confidence_level})` : a.confidence_level ?? "—"],
          ["Acknowledged", a.acknowledged_at ? `${utcDayTime(a.acknowledged_at)} by ${a.acknowledged_by}${a.ack_note ? `: ${a.ack_note}` : ""}` : "no"],
          ["Resolution", a.resolved_at ? `${utcDayTime(a.resolved_at)} by ${a.resolved_by}: ${a.resolution_notes ?? ""}` : "unresolved"],
        ]} />
        <p className="mt-3 text-xs text-ink-3">{a.classification_note}</p>
      </DataCard>

      <div className="grid gap-4 2xl:grid-cols-2">
        <DataCard title="Supporting measurements">
          <Measurements m={a.measurements as Record<string, unknown>} />
        </DataCard>
        <DataCard title={a.experimental ? "AI explanation" : "Explanation"}>
          <div className="space-y-2 text-sm">
            {typeof expl.what_changed === "string" && <p>{expl.what_changed}</p>}
            {typeof expl.rule === "string" && <p className="text-ink-2"><span className="text-ink-3">Rule: </span>{expl.rule}</p>}
            {Array.isArray(expl.contributors) && expl.contributors.length > 0 && (
              <ul className="space-y-0.5">
                {(expl.contributors as { signal: string; label: string; share: number; z: number | null }[]).map((c) => (
                  <li key={c.signal} className="flex justify-between gap-2"><span>{c.label}</span><span className="text-ink-2 tabular-nums">{fmt(c.share * 100, 0)}%{c.z != null ? `, z ${fmt(c.z, 1)}` : ""}</span></li>
                ))}
              </ul>
            )}
            {typeof expl.method === "string" && <p className="text-xs text-ink-3">{expl.method}</p>}
            {typeof expl.model_version === "string" && <p className="text-xs text-ink-3">Model version {expl.model_version}</p>}
          </div>
          <div className="mt-3 border-t border-bulkhead/50 pt-2">
            <p className="text-xs text-ink-3">Uncertainty</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-ink-2">
              {a.uncertainty.map((u) => <li key={u}>{u}</li>)}
            </ul>
          </div>
        </DataCard>
        <DataCard title="Correlated mission context">
          <Correlations c={a.correlations as Record<string, unknown>} />
        </DataCard>
        <DataCard title="Lifecycle">
          <Lifecycle a={a} pin={pin} />
          <ol className="mt-4 space-y-2 border-t border-bulkhead/50 pt-3" aria-label="Audit trail">
            {a.actions.map((x) => (
              <li key={x.id} className="grid grid-cols-[auto_1fr] gap-x-2 text-sm">
                <span className="mt-1.5 size-1.5 rounded-full bg-telemetry" aria-hidden />
                <span>
                  <span className="font-medium">{x.action.replace(/_/g, " ")}</span>
                  <span className="text-ink-2"> by {x.actor}{x.actor_role ? ` (${x.actor_role.replace(/_/g, " ")})` : ""}</span>
                  <span className="block text-xs text-ink-3">{utcDayTime(x.ts)} UTC{x.from_status && x.to_status && x.from_status !== x.to_status ? `, ${x.from_status} to ${x.to_status}` : ""}</span>
                  {x.note && <span className="block text-xs text-ink-2">{x.note}</span>}
                </span>
              </li>
            ))}
          </ol>
        </DataCard>
      </div>
      {a.astronaut_id && (
        <nav className="flex flex-wrap gap-4 text-sm" aria-label="Related views">
          <Link href={`/twin?astronaut=${a.astronaut_id}`} className="inline-flex items-center gap-1.5 text-telemetry hover:underline"><Fingerprint className="size-4" aria-hidden />Digital twin</Link>
          {a.source === "physiological_monitoring" && a.context === "operations" && (
            <Link href={`/medical?astronaut=${a.astronaut_id}&alert=${a.source_ref}`} className="inline-flex items-center gap-1.5 text-telemetry hover:underline"><Stethoscope className="size-4" aria-hidden />Decision-support packet</Link>
          )}
          {typeof (a.measurements as { link?: string }).link === "string" && (
            <a href={(a.measurements as { link: string }).link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-telemetry hover:underline"><ExternalLink className="size-4" aria-hidden />NASA DONKI record</a>
          )}
        </nav>
      )}
    </div>
  );
}

function SummaryBar({ context }: { context: MissionContext }) {
  const s = useAlertCenterSummary(context);
  if (!s.data) return null;
  const d = s.data;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-2">
      <span><span className="font-semibold text-foreground tabular-nums">{d.open}</span> open</span>
      <span><span className="font-semibold text-foreground tabular-nums">{d.acknowledged}</span> acknowledged</span>
      <span><span className="font-semibold text-foreground tabular-nums">{d.resolved_24h}</span> resolved in 24 h</span>
      <span>{d.experimental_open} experimental AI open</span>
      {d.mean_minutes_to_acknowledge_7d != null && <span>mean time to acknowledge {fmt(d.mean_minutes_to_acknowledge_7d, 0)} min (7 d)</span>}
    </div>
  );
}

export function AlertCenter() {
  const [alertId, setAlertId] = useParamState("alert");
  const [astronaut, setAstronaut] = useParamState("astronaut");
  const [context, setContext] = useState<MissionContext>("operations");
  const [status, setStatus] = useState<"unresolved" | "all" | "resolved">("unresolved");
  const [source, setSource] = useState("all");
  const [priority, setPriority] = useState<string[]>([]);
  const filters: AlertCenterFilters = useMemo(() => ({
    status: status === "unresolved" ? ["open", "acknowledged"] : status === "resolved" ? ["resolved"] : undefined,
    priority: priority.length ? priority.map(Number) : undefined,
    source: source === "all" ? undefined : [source],
    astronaut_id: astronaut ?? undefined,
    context,
    hours: 24 * 14,
  }), [status, priority, source, astronaut, context]);
  const q = useAlertCenter(filters);
  const rows = q.data ?? [];
  const selected = alertId && rows.some((r) => r.id === alertId) ? alertId : alertId ?? rows[0]?.id ?? null;

  return (
    <Tabs defaultValue="unified" className="space-y-4">
      <TabsList>
        <TabsTrigger value="unified">Unified alert centre</TabsTrigger>
        <TabsTrigger value="rules">Rule alert log</TabsTrigger>
      </TabsList>
      <TabsContent value="unified" className="space-y-4">
        <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filters">
          <div className="space-y-1">
            <p className="text-xs text-ink-3">Data</p>
            <ToggleGroup type="single" variant="outline" size="sm" value={context} onValueChange={(v) => v && setContext(v as MissionContext)}>
              <ToggleGroupItem value="operations">Crew stream</ToggleGroupItem>
              <ToggleGroupItem value="simulation">Simulation sandbox</ToggleGroupItem>
            </ToggleGroup>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-ink-3">Status</p>
            <ToggleGroup type="single" variant="outline" size="sm" value={status} onValueChange={(v) => v && setStatus(v as typeof status)}>
              <ToggleGroupItem value="unresolved">Unresolved</ToggleGroupItem>
              <ToggleGroupItem value="resolved">Resolved</ToggleGroupItem>
              <ToggleGroupItem value="all">All</ToggleGroupItem>
            </ToggleGroup>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-ink-3">Priority</p>
            <ToggleGroup type="multiple" variant="outline" size="sm" value={priority} onValueChange={setPriority} aria-label="Priority">
              {["1", "2", "3", "4"].map((p) => <ToggleGroupItem key={p} value={p}>P{p}</ToggleGroupItem>)}
            </ToggleGroup>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-ink-3">Source module</p>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="w-56" aria-label="Source module"><SelectValue /></SelectTrigger>
              <SelectContent>{SOURCES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <CrewPicker value={astronaut} onChange={setAstronaut} allowAll />
        </div>
        <SummaryBar context={context} />
        <div className="grid gap-4 xl:grid-cols-[minmax(22rem,30rem)_1fr]">
          <Panel title={`${rows.length} alert${rows.length === 1 ? "" : "s"}`} bodyClassName="px-0 pb-0 pt-2" className={context === "simulation" ? "border-sandbox/40" : undefined}>
            {q.isPending ? (
              <LoadingState className="px-4 pb-4" />
            ) : q.error && !q.data ? (
              <ErrorState error={q.error} onRetry={() => q.refetch()} className="m-4" />
            ) : rows.length === 0 ? (
              <EmptyState className="m-4" title="No alerts match these filters">
                {context === "simulation" ? "Sandbox alerts appear here while a mission simulation runs." : "New alerts from every module appear here as they open."}
              </EmptyState>
            ) : (
              <ul className="scroll-quiet max-h-[70vh] overflow-y-auto">
                {rows.map((a) => <AlertRow key={a.id} a={a} selected={a.id === selected} onSelect={() => setAlertId(a.id)} />)}
              </ul>
            )}
          </Panel>
          <div className="min-w-0">
            {selected ? (
              <ErrorBoundary label="Alert detail">
                <AlertDetailPanel id={selected} pin={() => { if (!alertId) setAlertId(selected); }} />
              </ErrorBoundary>
            ) : (
              <EmptyState title="Select an alert">Its measurements, explanation, correlations and lifecycle appear here.</EmptyState>
            )}
          </div>
        </div>
      </TabsContent>
      <TabsContent value="rules">
        <p className="mb-3 text-sm text-ink-2">
          The phase 2 rule alert log with its full detector history. Acknowledging or resolving here is recorded in the unified alert centre too.
        </p>
        <AlertsConsole />
      </TabsContent>
    </Tabs>
  );
}
