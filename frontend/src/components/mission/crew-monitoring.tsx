"use client";

import {
  Activity,
  BellRing,
  BrainCircuit,
  Fingerprint,
  FlaskConical,
  GanttChart,
  History,
  LayoutGrid,
  List,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ErrorState, LoadingState } from "@/components/data/states";
import { DataCard, Meter, Unavailable } from "@/components/mc/card";
import { ExperimentalTag, LivePulse, OriginChip, PriorityBadge } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { StatusPill } from "@/components/status/status";
import { useCrewMonitoring } from "@/lib/api/mission-hooks";
import type { CrewMonitorCard, Deviation } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt, relativeTime, utcDay, utcTime } from "@/lib/format";
import { pickReading } from "@/lib/live/freshness";
import { liveStatus } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL } from "@/lib/metrics";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

const RISK_TONE: Record<string, "nominal" | "advisory" | "caution" | "critical"> = {
  normal: "nominal",
  low_concern: "advisory",
  moderate_concern: "caution",
  high_concern: "critical",
};

/** z on a fixed -5..+5 track with a neutral centre; the number and flag carry the meaning. */
function DeviationRow({ d }: { d: Deviation }) {
  const z = d.z ?? 0;
  const pos = Math.max(-5, Math.min(5, z));
  const left = 50 + (Math.min(0, pos) / 5) * 50;
  const width = (Math.abs(pos) / 5) * 50;
  const tone = d.flag === "far" ? "bg-critical" : d.flag === "outside" ? "bg-caution" : d.flag === "edge" ? "bg-advisory" : "bg-ink-3";
  return (
    <li className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-2 text-sm">
      <span className="truncate text-ink-2">{d.label}</span>
      <span className="relative h-2 rounded-full bg-bulkhead/50" aria-hidden>
        <span className="absolute inset-y-[-2px] left-1/2 w-px bg-ink-3/70" />
        {d.z != null && <span className={cn("absolute inset-y-0 rounded-full", tone)} style={{ left: `${left}%`, width: `${Math.max(width, 1.5)}%` }} />}
      </span>
      <span className="text-right text-xs tabular-nums" title={d.expected != null ? `Expected ${fmt(d.expected, 1)} ${d.unit}` : "No comparable baseline for this activity"}>
        {d.z == null ? <span className="text-ink-3">no ref.</span> : <>z {d.z > 0 ? "+" : ""}{fmt(d.z, 1)}</>}
      </span>
    </li>
  );
}

function TrendMini({ card }: { card: CrewMonitorCard }) {
  const rows = card.trend_7d.map((p) => ({ day: utcDay(p.day), hr: p.heart_rate, spo2: p.spo2, sleep: p.sleep_hours }));
  if (rows.length < 2) return <p className="text-sm text-ink-2">Daily summaries appear once the digital twin has built them.</p>;
  const charts: { key: "hr" | "spo2" | "sleep"; label: string; unit: string; d: number }[] = [
    { key: "hr", label: "Resting heart rate", unit: "bpm", d: 0 },
    { key: "spo2", label: "Resting SpO₂", unit: "%", d: 1 },
    { key: "sleep", label: "Sleep", unit: "h", d: 1 },
  ];
  return (
    <div className="grid grid-cols-3 gap-3">
      {charts.map((c) => {
        const last = [...rows].reverse().find((r) => r[c.key] != null)?.[c.key];
        return (
          <div key={c.key} className="min-w-0">
            <p className="truncate text-[11px] text-ink-3">{c.label}</p>
            <p className="text-sm font-medium tabular-nums">
              {fmt(last ?? null, c.d)} <span className="text-xs font-normal text-ink-3">{c.unit}</span>
            </p>
            <div className="h-10" role="img" aria-label={`${c.label}, last 7 days`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
                  <XAxis dataKey="day" hide />
                  <YAxis hide domain={["dataMin", "dataMax"]} />
                  <Tooltip
                    cursor={{ stroke: "var(--ink-3)" }}
                    contentStyle={{ background: "var(--popover)", border: "1px solid var(--bulkhead)", borderRadius: 6, fontSize: 11 }}
                    labelStyle={{ color: "var(--ink-2)" }}
                    formatter={(v) => [`${fmt(Number(v), c.d)} ${c.unit}`, c.label]}
                  />
                  <Line dataKey={c.key} stroke={crewColor(card.astronaut_id)} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CrewCard({ card }: { card: CrewMonitorCard }) {
  const live = useLive((s) => s.latest[card.astronaut_id]);
  const connection = useLive((s) => s.connection);
  const openAlerts = useLive((s) => s.openAlerts);
  const now = useNow(10_000);
  // The REST reading wins whenever the stream is not live or has nothing newer.
  const picked = pickReading(live, card.latest, connection);
  const r = picked.reading;
  const status = connection === "live" ? liveStatus(Object.values(openAlerts).filter((a) => a.astronaut_id === card.astronaut_id)) : card.status;
  const ai = card.ai;
  const aiAlerts = card.open_alerts.filter((a) => a.source !== "physiological_monitoring");
  const tone = status === "nominal" ? undefined : status;
  return (
    <DataCard
      id={`crew-${card.astronaut_id}`}
      tone={tone}
      title={
        <Link href={`/crew/${card.astronaut_id}`} className="flex items-center gap-2 hover:text-telemetry">
          <span className="size-2.5 rounded-full" style={{ background: crewColor(card.astronaut_id) }} aria-hidden />
          {card.name}
        </Link>
      }
      meta={
        <span className="flex items-center gap-2">
          {picked.live ? (
            <span className="inline-flex items-center gap-1.5 text-telemetry"><LivePulse /> live</span>
          ) : r ? (
            <span>last reading {now ? relativeTime(r.ts, now) : `${utcTime(r.ts)} UTC`}</span>
          ) : null}
          <StatusPill status={status} />
        </span>
      }
      footer={
        <nav aria-label={`${card.name} views`} className="flex flex-wrap gap-x-4 gap-y-1">
          <Link className="inline-flex items-center gap-1 hover:text-telemetry" href={`/crew/${card.astronaut_id}`}><Activity className="size-3.5" aria-hidden />Full profile</Link>
          <Link className="inline-flex items-center gap-1 hover:text-telemetry" href={`/crew/history?astronaut=${card.astronaut_id}`}><History className="size-3.5" aria-hidden />Health history</Link>
          <Link className="inline-flex items-center gap-1 hover:text-telemetry" href={`/twin?astronaut=${card.astronaut_id}`}><Fingerprint className="size-3.5" aria-hidden />Digital twin</Link>
          <Link className="inline-flex items-center gap-1 hover:text-telemetry" href={`/alerts?astronaut=${card.astronaut_id}`}><BellRing className="size-3.5" aria-hidden />Alerts</Link>
          <Link className="inline-flex items-center gap-1 hover:text-telemetry" href={`/timeline?astronaut=${card.astronaut_id}`}><GanttChart className="size-3.5" aria-hidden />Timeline</Link>
        </nav>
      }
    >
      <p className="-mt-1 mb-3 text-xs text-ink-3">
        {card.role}. {card.specialty}. Fictional crew member. Mission dose {fmt(card.mission_dose_msv, 1)} mSv (simulated).
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-label="Current measurements">
          <h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-ink-2">Current measurements <OriginChip origin="simulated" /></h3>
          <dl className="grid grid-cols-3 gap-x-3 gap-y-2">
            {([
              ["Heart rate", r?.heart_rate, "bpm", 0],
              ["SpO₂", r?.spo2, "%", 1],
              ["Resp. rate", r?.respiratory_rate, "/min", 0],
              ["Temp", r?.temperature_c, "°C", 1],
              ["Systolic", r?.systolic, "mmHg", 0],
              ["Diastolic", r?.diastolic, "mmHg", 0],
            ] as const).map(([label, v, unit, d]) => (
              <div key={label} className="min-w-0">
                <dt className="text-[11px] text-ink-3">{label}</dt>
                <dd className="readout text-xl font-semibold">
                  {fmt(v ?? null, d)}
                  <span className="ml-1 font-sans text-[11px] font-normal text-ink-3">{unit}</span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-ink-2">
            <span>{r?.activity_state ? ACTIVITY_LABEL[r.activity_state] : "No reading"}</span>
            <span>Rhythm {r?.rhythm ?? "—"}</span>
            {card.active_scenarios.length > 0 && (
              <span className="inline-flex items-center gap-1 text-caution"><FlaskConical className="size-3" aria-hidden />{card.active_scenarios.join(", ")}</span>
            )}
          </p>
        </section>

        <section aria-label="Personal baseline deviations">
          <h3 className="mb-2 text-xs font-medium text-ink-2">Deviation from personal baseline</h3>
          {card.deviations.available ? (
            <ul className="space-y-1.5">
              {card.deviations.signals.map((d) => <DeviationRow key={d.signal} d={d} />)}
            </ul>
          ) : (
            <Unavailable reason={card.deviations.reason} className="py-2" />
          )}
          <p className="mt-1.5 text-[11px] text-ink-3">Centre line is the expected value for this activity and time of day.</p>
        </section>

        <section aria-label="Active anomalies">
          <h3 className="mb-2 text-xs font-medium text-ink-2">Active anomalies ({card.open_alerts.length})</h3>
          {card.open_alerts.length === 0 ? (
            <p className="text-sm text-ink-2">None open.</p>
          ) : (
            <ul className="space-y-1.5">
              {card.open_alerts.slice(0, 5).map((a) => (
                <li key={a.id} className="flex items-start gap-2 text-sm">
                  <PriorityBadge priority={a.priority} compact className="mt-0.5" />
                  <Link href={`/alerts?alert=${a.id}`} className="min-w-0 flex-1 truncate hover:text-telemetry">{a.title.replace(`${card.name}: `, "")}</Link>
                  {a.condition_cleared_at && <span className="shrink-0 text-xs text-nominal">cleared</span>}
                </li>
              ))}
            </ul>
          )}
          {aiAlerts.length > 0 && <p className="mt-1 text-[11px] text-ink-3">{aiAlerts.length} from AI models (experimental).</p>}
        </section>

        <section aria-label="AI risk assessment">
          <h3 className="mb-2 flex items-center gap-2 text-xs font-medium text-ink-2">AI risk assessment <ExperimentalTag /></h3>
          {ai.available && ai.risk_score != null ? (
            <>
              <div className="flex items-baseline justify-between text-sm">
                <span><span className="readout text-xl font-semibold">{fmt(ai.risk_score, 0)}</span><span className="text-xs text-ink-3">/100</span> {ai.category_label}</span>
                <span className="text-xs text-ink-3">confidence {(ai.confidence as { level?: string } | null)?.level ?? "—"}</span>
              </div>
              <Meter value={ai.risk_score} tone={RISK_TONE[ai.category ?? "normal"] ?? "telemetry"} label={`${card.name} AI risk`} />
              <ul className="mt-2 space-y-0.5 text-xs text-ink-2">
                {(ai.warnings as { title: string }[]).slice(0, 3).map((w) => <li key={w.title} className="truncate">{w.title}</li>)}
              </ul>
              <p className="mt-1 text-[11px] text-ink-3">{ai.generated_at && now ? `Assessed ${relativeTime(ai.generated_at, now)}` : null}</p>
            </>
          ) : (
            <Unavailable reason={ai.reason} className="py-2" />
          )}
        </section>
      </div>
      <section aria-label="Seven-day trend" className="mt-4 border-t border-bulkhead/50 pt-3">
        <h3 className="mb-2 text-xs font-medium text-ink-2">Last 7 days (daily summaries)</h3>
        <TrendMini card={card} />
      </section>
    </DataCard>
  );
}

export function CrewMonitoringView() {
  const q = useCrewMonitoring();
  const now = useNow(30_000);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "nominal" | "monitor" | "critical">("all");

  if (q.isPending) return <LoadingState label="Loading crew" rows={6} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;

  const filtered = d.crew.filter((c) => {
    const matchesSearch =
      !search.trim() ||
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.role.toLowerCase().includes(search.toLowerCase()) ||
      c.astronaut_id.toLowerCase().includes(search.toLowerCase());
    const matchesStatus =
      statusFilter === "all"
        ? true
        : statusFilter === "nominal"
          ? c.status === "nominal"
          : statusFilter === "critical"
            ? c.status === "critical"
            : c.status === "caution" || c.status === "advisory";
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-4">
      {/* Header matching Screen 4 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">Crew Monitoring</h1>
          <p className="text-sm text-ink-2">Real-time health status of all astronauts</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-ink-3" aria-hidden />
            <input
              type="search"
              placeholder="Search astronaut..."
              aria-label="Search astronaut"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 w-48 rounded-md border border-input bg-abyss pr-3 pl-8 text-xs outline-none focus-visible:border-telemetry"
            />
          </div>

          <div className="flex rounded-md border border-bulkhead bg-abyss p-0.5 text-xs">
            {(
              [
                ["all", "All"],
                ["nominal", "Stable"],
                ["monitor", "Monitor"],
                ["critical", "Critical"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setStatusFilter(k)}
                className={cn(
                  "rounded px-2.5 py-1 font-medium transition-colors",
                  statusFilter === k ? "bg-telemetry text-[#04131c]" : "text-ink-2 hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex rounded-md border border-bulkhead bg-abyss p-0.5 text-xs" role="group" aria-label="View mode">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              aria-pressed={viewMode === "grid"}
              className={cn(
                "inline-flex items-center gap-1 rounded px-2.5 py-1 font-medium transition-colors",
                viewMode === "grid" ? "bg-telemetry text-[#04131c]" : "text-ink-2 hover:text-foreground",
              )}
            >
              <LayoutGrid className="size-3.5" aria-hidden /> Grid
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              aria-pressed={viewMode === "list"}
              className={cn(
                "inline-flex items-center gap-1 rounded px-2.5 py-1 font-medium transition-colors",
                viewMode === "list" ? "bg-telemetry text-[#04131c]" : "text-ink-2 hover:text-foreground",
              )}
            >
              <List className="size-3.5" aria-hidden /> List
            </button>
          </div>

          <Link
            href="/crew/history"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-telemetry/40 bg-telemetry/10 px-3 text-xs font-medium text-telemetry hover:bg-telemetry/20"
          >
            <History className="size-3.5" aria-hidden /> Detailed Health History
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-ink-3">
        <BrainCircuit className="size-4 text-telemetry" aria-hidden />
        <span>{d.ai_sweep_at && now ? `AI sweep ${relativeTime(d.ai_sweep_at, now)}` : "Waiting for the first AI sweep"}</span>
        <span>{d.notes.join(" ")}</span>
      </div>

      {viewMode === "grid" ? (
        <div className="grid gap-4 2xl:grid-cols-2">
          {filtered.map((c) => (
            <ErrorBoundary key={c.astronaut_id} label={c.name}>
              <CrewCard card={c} />
            </ErrorBoundary>
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-bulkhead bg-hull">
          <table className="w-full min-w-[780px] text-left text-sm">
            <thead className="border-b border-bulkhead bg-abyss/60 text-xs text-ink-2">
              <tr>
                <th className="px-4 py-3 font-medium">Astronaut</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">HR</th>
                <th className="px-4 py-3 font-medium">SpO₂</th>
                <th className="px-4 py-3 font-medium">Temp</th>
                <th className="px-4 py-3 font-medium">BP</th>
                <th className="px-4 py-3 font-medium">AI Risk</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bulkhead/50 tabular-nums">
              {filtered.map((c) => (
                <tr key={c.astronaut_id} className="hover:bg-panel-2/60">
                  <td className="px-4 py-3 font-medium">
                    <Link href={`/crew/${c.astronaut_id}`} className="flex items-center gap-2 hover:text-telemetry">
                      <span className="size-2.5 rounded-full" style={{ background: crewColor(c.astronaut_id) }} />
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-2">{c.role}</td>
                  <td className="px-4 py-3"><StatusPill status={c.status} compact /></td>
                  <td className="px-4 py-3 font-semibold text-telemetry">{fmt(c.latest?.heart_rate ?? null, 0)} bpm</td>
                  <td className="px-4 py-3">{fmt(c.latest?.spo2 ?? null, 1)}%</td>
                  <td className="px-4 py-3">{fmt(c.latest?.temperature_c ?? null, 1)}°C</td>
                  <td className="px-4 py-3">{fmt(c.latest?.systolic ?? null, 0)}/{fmt(c.latest?.diastolic ?? null, 0)}</td>
                  <td className="px-4 py-3">{c.ai.risk_score != null ? `${fmt(c.ai.risk_score, 0)}/100` : "—"}</td>
                  <td className="px-4 py-3 text-xs">
                    <div className="flex gap-2">
                      <Link href={`/twin?astronaut=${c.astronaut_id}`} className="text-telemetry hover:underline">Twin</Link>
                      <Link href={`/crew/history?astronaut=${c.astronaut_id}`} className="text-telemetry hover:underline">History</Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
