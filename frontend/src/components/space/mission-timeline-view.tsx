"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAstronauts, useIssMissions, useNearbyEvents, useSpaceTimeline } from "@/lib/api/hooks";
import type { Timeline, TimelineItem } from "@/lib/api/types";
import { fmt } from "@/lib/format";
import { inZone, useDisplayZone, ZONES } from "@/lib/timezone";

import { CATEGORY, CategoryBadge, When, ZoneSelect } from "./provenance";

const ITEM_COLOUR: Record<string, string> = {
  space_weather: "var(--advisory)",
  notifications: "var(--ink-3)",
  crew_alerts: "var(--critical)",
  ai: "var(--telemetry)",
  simulation: "var(--caution)",
  milestones: "var(--ink-2)",
};

function severityColour(item: TimelineItem): string {
  if (item.lane === "crew_alerts") return item.severity === "critical" ? "var(--critical)" : item.severity === "caution" ? "var(--caution)" : "var(--advisory)";
  if (item.lane === "space_weather" && item.severity === "caution") return "var(--caution)";
  return ITEM_COLOUR[item.lane] ?? "var(--ink-2)";
}

function Lanes({ t, domain, onSelect, selected }: {
  t: Timeline; domain: [number, number]; onSelect: (i: TimelineItem) => void; selected: string | null;
}) {
  const zone = useDisplayZone((s) => s.zone);
  const lanes = t.lanes;
  const rows = lanes.flatMap((lane, li) => lane.items.map((item) => ({ t: Date.parse(item.ts), y: li, item })));
  return (
    <div style={{ height: 60 + lanes.length * 44 }} role="img" aria-label="Mission timeline lanes">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.45} />
          <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={(v: number) => inZone(v, zone, domain[1] - domain[0] > 3 * 86_400_000 ? "date" : "datetime")}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={64} />
          <YAxis dataKey="y" type="number" domain={[-0.5, lanes.length - 0.5]} ticks={lanes.map((_, i) => i)} reversed width={150}
            tickFormatter={(i: number) => lanes[i]?.label ?? ""} tick={{ fill: "var(--ink-2)", fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ strokeDasharray: "3 3", stroke: "var(--ink-3)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const it = (payload[0].payload as { item: TimelineItem }).item;
              return (
                <div className="max-w-xs rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="font-medium">{it.title}</p>
                  {it.detail && <p className="text-ink-2">{it.detail}</p>}
                  <p className="text-ink-3">{inZone(it.ts, zone, "datetime", true)} · {CATEGORY[it.category].label}</p>
                </div>
              );
            }}
          />
          <Scatter
            data={rows}
            isAnimationActive={false}
            onClick={(p) => onSelect((p as unknown as { item: TimelineItem }).item)}
            shape={(props: { cx?: number; cy?: number; payload?: { item: TimelineItem } }) => {
              const it = props.payload!.item;
              const col = severityColour(it);
              const isSel = it.id === selected;
              const dashed = it.category === "simulated";
              return (
                <rect x={(props.cx ?? 0) - (isSel ? 6 : 4.5)} y={(props.cy ?? 0) - (isSel ? 9 : 7)} width={isSel ? 12 : 9} height={isSel ? 18 : 14} rx={2}
                  fill={col} fillOpacity={isSel ? 0.9 : 0.45} stroke={col} strokeWidth={isSel ? 2 : 1} strokeDasharray={dashed ? "2 1.5" : undefined}
                  className="cursor-pointer" />
              );
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function Series({ t, domain }: { t: Timeline; domain: [number, number] }) {
  const zone = useDisplayZone((s) => s.zone);
  const [key, setKey] = useState<string | null>(null);
  const series = t.series.find((s) => s.key === key) ?? t.series[0];
  if (!series) return null;
  const rows = series.points.map((p) => ({ t: Date.parse(p.ts), v: p.value, approximate: p.approximate }));
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <ToggleGroup type="single" value={series.key} onValueChange={(v) => v && setKey(v)} variant="outline" size="sm" aria-label="Series">
          {t.series.map((s) => <ToggleGroupItem key={s.key} value={s.key}>{s.label}</ToggleGroupItem>)}
        </ToggleGroup>
        <CategoryBadge category={series.category} />
        <span className="text-xs text-ink-3">{series.unit}</span>
      </div>
      <div className="h-44" role="img" aria-label={`${series.label} on the same time axis`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.45} vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={(v: number) => inZone(v, zone, "date")}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={64} />
            <YAxis domain={["auto", "auto"]} width={150} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false}
              tickFormatter={(v: number) => fmt(v, series.unit === "mGy/day" ? 2 : 0)} />
            <Line dataKey="v" stroke={series.category === "simulated" ? "var(--caution)" : "var(--telemetry)"} strokeWidth={1.6} dot={false} isAnimationActive={false} />
            <Tooltip isAnimationActive={false} content={({ active, payload, label }) => active && payload?.length ? (
              <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                <p className="text-ink-2">{inZone(Number(label), zone)}</p>
                <p>{series.label} {fmt(payload[0].value as number, 2)} {series.unit}</p>
              </div>
            ) : null} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Nearby({ item }: { item: TimelineItem }) {
  const [hours, setHours] = useState(48);
  const q = useNearbyEvents(item.ts, hours);
  return (
    <Panel
      raised
      title={item.title}
      description={<><When iso={item.ts} /> · {item.source}</>}
      actions={<CategoryBadge category={item.category} />}
    >
      {item.detail && <p className="mb-3 text-sm text-ink-2">{item.detail}</p>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Space weather near this moment</h3>
        <ToggleGroup type="single" value={String(hours)} onValueChange={(v) => v && setHours(Number(v))} variant="outline" size="sm" aria-label="Window">
          {[12, 48, 168].map((h) => <ToggleGroupItem key={h} value={String(h)}>±{h < 168 ? `${h} h` : "7 d"}</ToggleGroupItem>)}
        </ToggleGroup>
      </div>
      {q.isPending ? (
        <LoadingState rows={2} className="mt-2" />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data && q.data.events.length ? (
        <ul className="mt-2 space-y-1.5 text-sm">
          {q.data.events.map((e) => (
            <li key={e.id} className="flex flex-wrap items-baseline gap-x-3">
              <span className="w-20 shrink-0 text-right tabular-nums text-ink-2">{e.offset_hours > 0 ? "+" : ""}{fmt(e.offset_hours, 1)} h</span>
              <span>{e.title}</span>
              <span className="text-xs text-ink-3">{e.detail}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-ink-3">No DONKI events within ±{hours} h.</p>
      )}
      {q.data && <p className="mt-3 text-xs text-ink-3">{q.data.note}</p>}
    </Panel>
  );
}

export function MissionTimelineView() {
  const [mode, setMode] = useState<"mission" | "iss">("mission");
  const [days, setDays] = useState(7);
  const [aid, setAid] = useState<string>("AST-01");
  const [chosenMission, setMission] = useState<string | null>(null);
  const [selected, setSelected] = useState<TimelineItem | null>(null);
  const astronauts = useAstronauts();
  const missions = useIssMissions();
  const withData = (missions.data ?? []).filter((m) => m.has_radiation || m.has_telemetry);
  const mission = chosenMission ?? withData[0]?.name ?? null;  // default: first mission with data
  const q = useSpaceTimeline(mode === "mission" ? { mode, days, astronaut_id: aid } : { mode, mission: mission ?? undefined });
  const t = q.data;
  const domain = useMemo<[number, number]>(() => (t ? [Date.parse(t.start), Date.parse(t.end)] : [0, 1]), [t]);
  const zone = useDisplayZone((s) => s.zone);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <ToggleGroup type="single" value={mode} onValueChange={(v) => { if (v) { setMode(v as typeof mode); setSelected(null); } }} variant="outline" size="sm" aria-label="Timeline mode">
          <ToggleGroupItem value="mission">Current mission</ToggleGroupItem>
          <ToggleGroupItem value="iss">Historical ISS mission</ToggleGroupItem>
        </ToggleGroup>
        {mode === "mission" ? (
          <>
            <ToggleGroup type="single" value={String(days)} onValueChange={(v) => v && setDays(Number(v))} variant="outline" size="sm" aria-label="Range">
              {[1, 3, 7, 30].map((d) => <ToggleGroupItem key={d} value={String(d)}>{d === 1 ? "24 h" : `${d} d`}</ToggleGroupItem>)}
            </ToggleGroup>
            <Select value={aid} onValueChange={setAid}>
              <SelectTrigger size="sm" className="w-48" aria-label="Crew member"><SelectValue /></SelectTrigger>
              <SelectContent>
                {(astronauts.data ?? []).map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </>
        ) : (
          <Select value={mission ?? undefined} onValueChange={setMission}>
            <SelectTrigger size="sm" className="w-64" aria-label="ISS mission"><SelectValue placeholder="Choose a mission" /></SelectTrigger>
            <SelectContent>
              {withData.map((m) => <SelectItem key={m.name} value={m.name}>{m.name}: {m.title}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <ZoneSelect />
      </div>

      {q.isPending ? (
        <LoadingState rows={6} />
      ) : q.error && !t ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : t ? (
        <>
          <Panel
            raised
            title={t.mode === "mission" ? "Mission timeline" : `ISS mission ${t.mission}`}
            description={<>From <When iso={t.start} /> to <When iso={t.end} />. Internally UTC; shown in {ZONES.find((z) => z.value === zone)?.label ?? zone} time. Select an item to see space weather around it.</>}
          >
            <div className="mb-2 flex flex-wrap gap-2">
              {t.lanes.map((l) => (
                <span key={l.key} className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                  <span className="size-2.5 rounded-sm" style={{ background: ITEM_COLOUR[l.key] }} aria-hidden />
                  {l.label} ({l.items.length})
                </span>
              ))}
            </div>
            {t.lanes.every((l) => l.items.length === 0) ? (
              <EmptyState title="Nothing in this window">Space-weather data may still be synchronising.</EmptyState>
            ) : (
              <Lanes t={t} domain={domain} onSelect={setSelected} selected={selected?.id ?? null} />
            )}
            <div className="mt-4 border-t border-bulkhead/50 pt-3">
              <Series t={t} domain={domain} />
            </div>
          </Panel>
          {selected && <Nearby item={selected} />}
          <Panel title="Reading this timeline">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
              {t.notes.map((n) => <li key={n}>{n}</li>)}
              <li>Dashed outlines mark simulated items; solid outlines are NASA data.</li>
            </ul>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
