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

type PillGroup = "all" | "health" | "environment" | "space" | "alerts";

const BOARD_FEED = [
  {
    id: "bf-1",
    time: "14:21",
    badge: "High",
    badgeTone: "border-critical/50 bg-critical/20 text-critical",
    dotTone: "bg-critical",
    title: "Elevated heart rate detected (Dr. Alex Carter)",
    group: "alerts" as PillGroup,
  },
  {
    id: "bf-2",
    time: "12:05",
    badge: "Info",
    badgeTone: "border-nominal/50 bg-nominal/15 text-nominal",
    dotTone: "bg-nominal",
    title: "Crew exercise session completed",
    group: "health" as PillGroup,
  },
  {
    id: "bf-3",
    time: "11:14",
    badge: "Env",
    badgeTone: "border-telemetry/50 bg-telemetry/15 text-telemetry",
    dotTone: "bg-telemetry",
    title: "C1.2 solar flare (NASA DONKI)",
    group: "space" as PillGroup,
  },
  {
    id: "bf-4",
    time: "09:30",
    badge: "Med",
    badgeTone: "border-caution/50 bg-caution/20 text-caution",
    dotTone: "bg-caution",
    title: "AI risk assessment updated (18%)",
    group: "health" as PillGroup,
  },
  {
    id: "bf-5",
    time: "06:00",
    badge: "Info",
    badgeTone: "border-nominal/50 bg-nominal/15 text-nominal",
    dotTone: "bg-nominal",
    title: "Daily health baseline updated",
    group: "environment" as PillGroup,
  },
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

function Swimlanes({
  t,
  selected,
  onSelect,
}: {
  t: MissionTimeline;
  selected: string | null;
  onSelect: (e: MissionEvent) => void;
}) {
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
  const fmtTick = (ms: number) =>
    span > 2 * 86_400_000 ? utcDay(ms) : span > 6 * 3_600_000 ? utcDayTime(ms) : utcTime(ms, false);

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label="Mission events by category over time">
        {lanes.map((lane, i) => (
          <g key={lane.key} transform={`translate(0, ${i * LANE_H})`}>
            <rect x={0} y={0} width={width} height={LANE_H} fill={i % 2 ? "transparent" : "var(--hull)"} opacity={0.5} />
            <text x={8} y={LANE_H / 2 + 4} fontSize={12} fill="var(--ink-2)">
              {lane.label}
            </text>
            <text x={LABEL_W - 8} y={LANE_H / 2 + 4} fontSize={11} fill="var(--ink-3)" textAnchor="end">
              {lane.items.length}
            </text>
            <line x1={LABEL_W} x2={width - 8} y1={LANE_H / 2} y2={LANE_H / 2} stroke="var(--bulkhead)" strokeWidth={1} />
            {lane.items.map((e) => {
              const cx = x(e.occurred_at);
              const r = e.priority === 1 ? 7 : e.priority === 2 ? 6 : e.priority === 3 ? 5 : 4;
              const sel = e.id === selected;
              return (
                <g key={e.id}>
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
                    strokeWidth={2}
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
            <text
              key={tk}
              x={LABEL_W + ((tk - start) / span) * plotW}
              y={14}
              fontSize={11}
              fill="var(--ink-3)"
              textAnchor="middle"
            >
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
          <p className="mt-0.5 text-ink-2">
            {utcDayTime(hover.e.occurred_at)} UTC, P{hover.e.priority} {hover.e.severity}
          </p>
          <p className="text-ink-3">
            {hover.e.source_label}
            {hover.e.occurrences > 1 ? `, reported ${hover.e.occurrences} times` : ""}
          </p>
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
        <dt className="text-ink-3">Event ID</dt>
        <dd>
          <code>{e.id}</code>
        </dd>
        <dt className="text-ink-3">Category</dt>
        <dd>{e.category_label}</dd>
        <dt className="text-ink-3">Source</dt>
        <dd>{e.source_label}</dd>
        <dt className="text-ink-3">Occurred</dt>
        <dd>{utcDayTime(e.occurred_at)} UTC</dd>
        <dt className="text-ink-3">Received</dt>
        <dd>
          {utcDayTime(e.received_at)} UTC (latency {Math.round(e.latency_s)} s)
        </dd>
        {e.clock_skew_s != null && (
          <>
            <dt className="text-ink-3">Clock skew</dt>
            <dd className="text-caution">source time {e.clock_skew_s} s ahead; clamped</dd>
          </>
        )}
        <dt className="text-ink-3">Reported</dt>
        <dd>
          {e.occurrences} time{e.occurrences === 1 ? "" : "s"} (duplicates merged)
        </dd>
        {e.astronaut_id && (
          <>
            <dt className="text-ink-3">Astronaut</dt>
            <dd>
              <Link className="text-telemetry hover:underline" href={`/crew/${e.astronaut_id}`}>
                {e.astronaut_id}
              </Link>
            </dd>
          </>
        )}
        {e.payload.alert_center_id ? (
          <>
            <dt className="text-ink-3">Alert</dt>
            <dd>
              <Link
                className="text-telemetry hover:underline"
                href={`/alerts?alert=${String(e.payload.alert_center_id)}`}
              >
                {String(e.payload.alert_center_id)}
              </Link>
            </dd>
          </>
        ) : null}
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
  const [pillGroup, setPillGroup] = useState<PillGroup>("all");
  const [selected, setSelected] = useState<MissionEvent | null>(null);
  const runs = useSimRuns();
  const context = sim ? "simulation" : "operations";

  function applyPillGroup(g: PillGroup) {
    setPillGroup(g);
    if (g === "all") setCats([]);
    else if (g === "health") setCats(["crew_physiology", "ai_prediction"]);
    else if (g === "environment") setCats(["environment", "radiation"]);
    else if (g === "space") setCats(["solar_activity", "radiation"]);
    else if (g === "alerts") setCats(["medical_incident", "crew_physiology"]);
  }

  const filters: TimelineFilters = useMemo(
    () => ({
      category: cats.length ? cats : undefined,
      astronaut_id: astronaut ?? undefined,
      context,
      simulation_id: sim ?? undefined,
      hours: sim ? undefined : Number(range),
    }),
    [cats, astronaut, context, sim, range],
  );
  const q = useMissionTimeline(filters);
  const t = q.data;
  const all = useMemo(
    () => (t ? t.lanes.flatMap((l) => l.items).sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)) : []),
    [t],
  );

  const visibleBoardFeed = useMemo(
    () => (pillGroup === "all" ? BOARD_FEED : BOARD_FEED.filter((item) => item.group === pillGroup)),
    [pillGroup],
  );

  return (
    <div className="space-y-5">
      {/* Header matching Screen 10 */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Mission Timeline
          </h1>
          <p className="text-sm text-ink-2">Unified view of health, environment and mission events</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CrewPicker value={astronaut} onChange={setAstronaut} allowAll />
        </div>
      </div>

      {/* Category Filter Pills matching Screen 10 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bulkhead pb-2.5">
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["all", "All Events"],
              ["health", "Health"],
              ["environment", "Environment"],
              ["space", "Space Weather"],
              ["alerts", "Alerts"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => applyPillGroup(key)}
              className={cn(
                "rounded-md px-4 py-1.5 text-xs font-semibold transition-colors",
                pillGroup === key
                  ? "bg-telemetry text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]"
                  : "bg-hull text-ink-2 hover:bg-panel-2 hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={sim ?? "operations"}
            onValueChange={(v) => {
              setSim(v === "operations" ? null : v);
              setSelected(null);
            }}
          >
            <SelectTrigger className="h-8 w-52 text-xs" aria-label="Data context">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="operations">Crew stream and NASA data</SelectItem>
              {(runs.data ?? []).map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  Sandbox: {r.name} ({r.status})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {!sim && (
            <ToggleGroup type="single" variant="outline" size="sm" value={range} onValueChange={(v) => v && setRange(v)}>
              {RANGES.map((r) => (
                <ToggleGroupItem key={r.value} value={r.value}>
                  {r.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        </div>
      </div>

      {/* Screen 10 Chronological Day-Grouped Vertical Feed */}
      <div className="rounded-xl border border-bulkhead bg-hull/80 p-5">
        <h2 className="text-base font-bold text-foreground">Nov 13, 2026 (Day 42)</h2>
        <div className="relative mt-4 space-y-2.5 pl-6 before:absolute before:bottom-2 before:left-2 before:top-2 before:w-0.5 before:bg-bulkhead">
          {visibleBoardFeed.map((item) => (
            <div
              key={item.id}
              className="relative flex flex-wrap items-center gap-3 rounded-lg border border-bulkhead/80 bg-[#091526]/90 px-4 py-3 transition-colors hover:border-telemetry/40"
            >
              <span
                className={cn(
                  "absolute -left-[21px] size-3 rounded-full ring-4 ring-hull",
                  item.dotTone,
                )}
                aria-hidden
              />
              <span className="w-12 font-mono text-xs font-semibold text-ink-2">{item.time}</span>
              <span
                className={cn(
                  "inline-flex w-14 justify-center rounded border px-2 py-0.5 text-[11px] font-semibold",
                  item.badgeTone,
                )}
              >
                {item.badge}
              </span>
              <span className="text-sm font-medium text-foreground">{item.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Multi-Lane Situational Swimlanes */}
      <Panel
        raised
        className={sim ? "sandbox-edge border-sandbox/40" : undefined}
        title={sim ? "Sandbox multi-lane swimlanes" : "Multi-lane situational swimlanes"}
        description={
          t
            ? `${utcDayTime(t.start)} to ${utcDayTime(t.end)} UTC, ${t.counts.total} events${sim ? " on the simulation clock" : ""}.`
            : undefined
        }
        actions={
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink-3" aria-label="Legend">
            {(["critical", "caution", "advisory", "info"] as const).map((s) => (
              <span key={s} className="inline-flex items-center gap-1">
                <span className="size-2.5 rounded-full" style={{ background: SEV_FILL[s] }} />
                {s}
              </span>
            ))}
            <span className="inline-flex items-center gap-1">
              <span className="size-2.5 rounded-full border border-dashed border-ink-2" />
              experimental AI
            </span>
          </div>
        }
      >
        <div className="mb-3">
          <ToggleGroup type="multiple" variant="outline" size="sm" value={cats} onValueChange={setCats} className="flex-wrap">
            {CATEGORIES.map((c) => (
              <ToggleGroupItem key={c.key} value={c.key}>
                {c.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>

        {q.isPending ? (
          <LoadingState rows={6} />
        ) : q.error && !t ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : t && all.length === 0 ? (
          <EmptyState title="No events in this window">
            Widen the time range or clear the filters. The event store records from the first start of the phase 6 backend.
          </EmptyState>
        ) : t ? (
          <div className="overflow-x-auto">
            <div className={cn("min-w-[640px]", q.isPlaceholderData && "opacity-60")}>
              <Swimlanes t={t} selected={selected?.id ?? null} onSelect={setSelected} />
            </div>
          </div>
        ) : null}
        {t && <p className="mt-3 text-xs text-ink-3">{t.notes.join(" ")}</p>}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <Panel title="Event list" description="The same events as a table, newest first.">
          {all.length === 0 ? (
            <p className="text-sm text-ink-2">Nothing to list.</p>
          ) : (
            <div className="scroll-quiet max-h-[28rem] overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-hull text-left text-xs text-ink-3">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Time (UTC)</th>
                    <th className="pr-3 font-medium">Priority</th>
                    <th className="pr-3 font-medium">Category</th>
                    <th className="font-medium">Event</th>
                  </tr>
                </thead>
                <tbody>
                  {all.slice(0, 300).map((e) => (
                    <tr
                      key={e.id}
                      className={cn(
                        "cursor-pointer border-t border-bulkhead/40 hover:bg-sidebar-accent/50",
                        selected?.id === e.id && "bg-sidebar-accent",
                      )}
                      onClick={() => setSelected(e)}
                    >
                      <td className="py-1.5 pr-3 whitespace-nowrap text-ink-2 tabular-nums">{utcDayTime(e.occurred_at)}</td>
                      <td className="pr-3">
                        <PriorityBadge priority={e.priority} compact />
                      </td>
                      <td className="pr-3 whitespace-nowrap text-ink-2">{e.category_label}</td>
                      <td className="min-w-0">
                        <button type="button" className="text-left hover:text-telemetry" onClick={() => setSelected(e)}>
                          {e.title}
                        </button>
                      </td>
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
