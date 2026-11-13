"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { ExperimentalTag, OriginChip, PriorityBadge, SandboxTag } from "@/components/mc/chips";
import { CrewPicker, useParamState } from "@/components/medical/common";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMissionTimeline, useSimRuns, type TimelineFilters } from "@/lib/api/mission-hooks";
import type { EventSeverity, MissionEvent, MissionTimeline } from "@/lib/api/types";
import { utcDay, utcDayTime, utcTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { key: "crew_physiology", label: "Crew physiology" },
  { key: "ai_prediction", label: "AI predictions" },
  { key: "environment", label: "Environment" },
  { key: "radiation", label: "Radiation" },
  { key: "solar_activity", label: "Solar activity" },
  { key: "medical_incident", label: "Medical incidents" },
  { key: "simulation", label: "Simulation control" },
];

const RANGES = [
  { value: "1", label: "1 h" },
  { value: "6", label: "6 h" },
  { value: "24", label: "24 h" },
  { value: "168", label: "7 days" },
  { value: "720", label: "30 days" },
];

const SEV_FILL: Record<EventSeverity, string> = {
  info: "var(--ink-3)",
  advisory: "var(--advisory)",
  caution: "var(--caution)",
  critical: "var(--critical)",
};

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

const LANE_H = 34;
const LABEL_W = 132;

function Swimlanes({ t, selected, onSelect }: { t: MissionTimeline; selected: string | null; onSelect: (e: MissionEvent) => void }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ e: MissionEvent; x: number; y: number } | null>(null);
  const start = Date.parse(t.start);
  const end = Math.max(Date.parse(t.end), start + 60_000);
  const plotW = width - LABEL_W - 16;
  const x = (ts: string) => LABEL_W + ((Date.parse(ts) - start) / (end - start)) * plotW;
  const lanes = t.lanes;
  const height = lanes.length * LANE_H + 28;
  const span = end - start;
  const ticks = Array.from({ length: 6 }, (_, i) => start + (span * i) / 5);
  const fmtTick = (ms: number) => (span > 2 * 86_400_000 ? utcDay(ms) : span > 6 * 3_600_000 ? utcDayTime(ms) : utcTime(ms, false));

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label="Mission events by category over time">
        {lanes.map((lane, i) => (
          <g key={lane.key} transform={`translate(0, ${i * LANE_H})`}>
            <rect x={0} y={0} width={width} height={LANE_H} fill={i % 2 ? "transparent" : "var(--hull)"} opacity={0.5} />
            <text x={8} y={LANE_H / 2 + 4} fontSize={12} fill="var(--ink-2)">{lane.label}</text>
            <text x={LABEL_W - 8} y={LANE_H / 2 + 4} fontSize={11} fill="var(--ink-3)" textAnchor="end">{lane.items.length}</text>
            <line x1={LABEL_W} x2={width - 8} y1={LANE_H / 2} y2={LANE_H / 2} stroke="var(--bulkhead)" strokeWidth={1} />
            {lane.items.map((e) => {
              const cx = x(e.occurred_at);
              const r = e.priority === 1 ? 7 : e.priority === 2 ? 6 : e.priority === 3 ? 5 : 4;
              const sel = e.id === selected;
              return (
                <g key={e.id}>
                  {/* Hit target larger than the mark. */}
                  <circle
                    cx={cx}
                    cy={LANE_H / 2}
                    r={12}
                    fill="transparent"
                    className="cursor-pointer"
                    onMouseEnter={() => setHover({ e, x: cx, y: i * LANE_H })}
                    onClick={() => onSelect(e)}
                  />
                  <circle
                    cx={cx}
                    cy={LANE_H / 2}
                    r={r}
                    fill={e.experimental ? "var(--abyss)" : SEV_FILL[e.severity]}
                    stroke={e.experimental ? SEV_FILL[e.severity] : sel ? "var(--foreground)" : "var(--abyss)"}
                    strokeWidth={e.experimental || sel ? 2 : 2}
                    strokeDasharray={e.experimental ? "2 2" : undefined}
                    pointerEvents="none"
                  />
                </g>
              );
            })}
          </g>
        ))}
        <g transform={`translate(0, ${lanes.length * LANE_H + 4})`}>
          {ticks.map((tk) => (
            <text key={tk} x={LABEL_W + ((tk - start) / span) * plotW} y={14} fontSize={11} fill="var(--ink-3)" textAnchor="middle">
              {fmtTick(tk)}
            </text>
          ))}
        </g>
      </svg>
      {hover && (
        <div
          className="pointer-events-none absolute z-10 w-72 rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs shadow-lg"
          style={{ left: Math.min(Math.max(0, hover.x - 144), width - 288), top: hover.y + LANE_H }}
        >
          <p className="font-medium text-foreground">{hover.e.title}</p>
          <p className="mt-0.5 text-ink-2">{utcDayTime(hover.e.occurred_at)} UTC, P{hover.e.priority} {hover.e.severity}</p>
          <p className="text-ink-3">{hover.e.source_label}{hover.e.occurrences > 1 ? `, reported ${hover.e.occurrences} times` : ""}</p>
        </div>
      )}
    </div>
  );
}

function EventDetail({ e }: { e: MissionEvent }) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <PriorityBadge priority={e.priority} />
        {e.context === "simulation" ? <SandboxTag /> : <OriginChip origin={e.data_origin} />}
        {e.experimental && <ExperimentalTag />}
      </div>
      <p className="font-medium">{e.title}</p>
      {e.summary && <p className="text-ink-2">{e.summary}</p>}
      <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-xs">
        <dt className="text-ink-3">Event ID</dt><dd><code>{e.id}</code></dd>
        <dt className="text-ink-3">Category</dt><dd>{e.category_label}</dd>
        <dt className="text-ink-3">Source</dt><dd>{e.source_label}</dd>
        <dt className="text-ink-3">Occurred</dt><dd>{utcDayTime(e.occurred_at)} UTC</dd>
        <dt className="text-ink-3">Received</dt><dd>{utcDayTime(e.received_at)} UTC (latency {Math.round(e.latency_s)} s)</dd>
        {e.clock_skew_s != null && (<><dt className="text-ink-3">Clock skew</dt><dd className="text-caution">source time {e.clock_skew_s} s ahead; clamped</dd></>)}
        <dt className="text-ink-3">Reported</dt><dd>{e.occurrences} time{e.occurrences === 1 ? "" : "s"} (duplicates merged)</dd>
        {e.astronaut_id && (<><dt className="text-ink-3">Astronaut</dt><dd><Link className="text-telemetry hover:underline" href={`/crew/${e.astronaut_id}`}>{e.astronaut_id}</Link></dd></>)}
        {e.payload.alert_center_id ? (<><dt className="text-ink-3">Alert</dt><dd><Link className="text-telemetry hover:underline" href={`/alerts?alert=${String(e.payload.alert_center_id)}`}>{String(e.payload.alert_center_id)}</Link></dd></>) : null}
      </dl>
      {e.classification_note && <p className="text-xs text-ink-3">{e.classification_note}</p>}
    </div>
  );
}

export function SituationalTimeline() {
  const [astronaut, setAstronaut] = useParamState("astronaut");
  const [sim, setSim] = useParamState("simulation");
  const [range, setRange] = useState("24");
  const [cats, setCats] = useState<string[]>([]);
  const [selected, setSelected] = useState<MissionEvent | null>(null);
  const runs = useSimRuns();
  const context = sim ? "simulation" : "operations";
  const filters: TimelineFilters = useMemo(() => ({
    category: cats.length ? cats : undefined,
    astronaut_id: astronaut ?? undefined,
    context,
    simulation_id: sim ?? undefined,
    hours: sim ? undefined : Number(range),
  }), [cats, astronaut, context, sim, range]);
  const q = useMissionTimeline(filters);
  const t = q.data;
  const all = useMemo(() => (t ? t.lanes.flatMap((l) => l.items).sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)) : []), [t]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Timeline filters">
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Data</p>
          <Select value={sim ?? "operations"} onValueChange={(v) => { setSim(v === "operations" ? null : v); setSelected(null); }}>
            <SelectTrigger className="w-64" aria-label="Data context"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="operations">Crew stream and NASA data</SelectItem>
              {(runs.data ?? []).map((r) => (
                <SelectItem key={r.id} value={r.id}>Sandbox: {r.name} ({r.status})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!sim && (
          <div className="space-y-1">
            <p className="text-xs text-ink-3">Time range</p>
            <ToggleGroup type="single" variant="outline" size="sm" value={range} onValueChange={(v) => v && setRange(v)}>
              {RANGES.map((r) => <ToggleGroupItem key={r.value} value={r.value}>{r.label}</ToggleGroupItem>)}
            </ToggleGroup>
          </div>
        )}
        <CrewPicker value={astronaut} onChange={setAstronaut} allowAll />
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Categories (none selected: all)</p>
          <ToggleGroup type="multiple" variant="outline" size="sm" value={cats} onValueChange={setCats} className="flex-wrap">
            {CATEGORIES.map((c) => <ToggleGroupItem key={c.key} value={c.key}>{c.label}</ToggleGroupItem>)}
          </ToggleGroup>
        </div>
      </div>

      <Panel
        raised
        className={sim ? "sandbox-edge border-sandbox/40" : undefined}
        title={sim ? "Sandbox mission timeline" : "Mission timeline"}
        description={t ? `${utcDayTime(t.start)} to ${utcDayTime(t.end)} UTC, ${t.counts.total} events${sim ? " on the simulation clock" : ""}.` : undefined}
        actions={
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink-3" aria-label="Legend">
            {(["critical", "caution", "advisory", "info"] as const).map((s) => (
              <span key={s} className="inline-flex items-center gap-1"><span className="size-2.5 rounded-full" style={{ background: SEV_FILL[s] }} />{s}</span>
            ))}
            <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-full border border-dashed border-ink-2" />experimental AI</span>
          </div>
        }
      >
        {q.isPending ? <LoadingState rows={6} /> : q.error && !t ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : t && all.length === 0 ? (
          <EmptyState title="No events in this window">Widen the time range or clear the filters. The event store records from the first start of the phase 6 backend.</EmptyState>
        ) : t ? (
          <div className="overflow-x-auto">
            <div className="min-w-[640px]"><Swimlanes t={t} selected={selected?.id ?? null} onSelect={setSelected} /></div>
          </div>
        ) : null}
        {t && <p className="mt-3 text-xs text-ink-3">{t.notes.join(" ")}</p>}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Panel title="Event list" description="The same events as a table, newest first.">
          {all.length === 0 ? <p className="text-sm text-ink-2">Nothing to list.</p> : (
            <div className="scroll-quiet max-h-[28rem] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-hull text-left text-xs text-ink-3">
                  <tr><th className="py-1.5 pr-3 font-medium">Time (UTC)</th><th className="pr-3 font-medium">Priority</th><th className="pr-3 font-medium">Category</th><th className="font-medium">Event</th></tr>
                </thead>
                <tbody>
                  {all.slice(0, 300).map((e) => (
                    <tr key={e.id} className={cn("cursor-pointer border-t border-bulkhead/40 hover:bg-sidebar-accent/50", selected?.id === e.id && "bg-sidebar-accent")} onClick={() => setSelected(e)}>
                      <td className="py-1.5 pr-3 whitespace-nowrap text-ink-2 tabular-nums">{utcDayTime(e.occurred_at)}</td>
                      <td className="pr-3"><PriorityBadge priority={e.priority} compact /></td>
                      <td className="pr-3 whitespace-nowrap text-ink-2">{e.category_label}</td>
                      <td className="min-w-0"><button type="button" className="text-left hover:text-telemetry" onClick={() => setSelected(e)}>{e.title}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Selected event">
          {selected ? <EventDetail e={selected} /> : <p className="text-sm text-ink-2">Select a mark or a row to see its details.</p>}
        </Panel>
      </div>
    </div>
  );
}
