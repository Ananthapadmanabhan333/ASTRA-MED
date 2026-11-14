"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { DataCard } from "@/components/mc/card";
import { ExperimentalTag, OriginChip } from "@/components/mc/chips";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { CrewPicker } from "@/components/medical/common";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { fetchBlob } from "@/lib/api/client";
import { useAnalytics, type AnalyticsFilters } from "@/lib/api/mission-hooks";
import type { AnalyticsSummary } from "@/lib/api/types";
import { crewColor, crewDash } from "@/lib/crew";
import { fmt, utcDay } from "@/lib/format";
import { cn } from "@/lib/utils";

const TOOLTIP = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--bulkhead)", borderRadius: 6, fontSize: 12 },
  labelStyle: { color: "var(--ink-2)" },
  cursor: { fill: "var(--bulkhead)", fillOpacity: 0.3 },
};
const AXIS = { tick: { fill: "var(--ink-3)", fontSize: 11 }, tickLine: false };

function isoDay(d: Date) {
  return d.toISOString().slice(0, 10);
}

const dayT = (d: string) => Date.parse(`${d}T12:00:00Z`);

type Row = Record<string, number | string | boolean | null>;

function StackedDays({ rows, keys, label }: { rows: Row[]; keys: { key: string; label: string; color: string }[]; label: string }) {
  const data = rows.map((r) => ({ ...r, label: utcDay(String(r.day)) }));
  return (
    <div role="img" aria-label={label} className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }} barCategoryGap={4}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
          <XAxis dataKey="label" {...AXIS} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={16} />
          <YAxis {...AXIS} axisLine={false} width={32} allowDecimals={false} />
          <Tooltip {...TOOLTIP} />
          <Legend wrapperStyle={{ fontSize: 12, color: "var(--ink-2)" }} iconType="circle" iconSize={8} />
          {keys.map((k, i) => (
            <Bar key={k.key} dataKey={k.key} name={k.label} stackId="a" fill={k.color} stroke="var(--hull)" strokeWidth={1}
              radius={i === keys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MiniDays({ rows, k, label }: { rows: Row[]; k: string; label: string }) {
  const data = rows.map((r) => ({ label: utcDay(String(r.day)), v: Number(r[k] ?? 0) }));
  const total = data.reduce((a, b) => a + b.v, 0);
  return (
    <div className="grid grid-cols-[9rem_1fr_3rem] items-center gap-3">
      <span className="text-sm text-ink-2">{label}</span>
      <div className="h-10" role="img" aria-label={`${label} per day`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }} barCategoryGap={2}>
            <XAxis dataKey="label" hide />
            <YAxis hide allowDecimals={false} />
            <Tooltip {...TOOLTIP} formatter={(v) => [String(v), label]} />
            <Bar dataKey="v" fill="var(--telemetry)" fillOpacity={0.85} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <span className="text-right text-sm font-semibold tabular-nums">{total}</span>
    </div>
  );
}

function HBar({ data, label }: { data: { name: string; v: number }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.v));
  return (
    <ul className="space-y-1.5" aria-label={label}>
      {data.map((d) => (
        <li key={d.name} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-2 text-sm">
          <span className="truncate text-ink-2">{d.name}</span>
          <span className="h-2.5 rounded-r bg-bulkhead/40" aria-hidden>
            <span className="block h-full rounded-r bg-telemetry" style={{ width: `${(d.v / max) * 100}%` }} />
          </span>
          <span className="text-right tabular-nums">{d.v}</span>
        </li>
      ))}
    </ul>
  );
}

const TREND_METRICS = [
  { key: "heart_rate", label: "Resting heart rate", unit: "bpm", d: 1 },
  { key: "spo2", label: "Resting SpO₂", unit: "%", d: 2 },
  { key: "respiratory_rate", label: "Respiratory rate", unit: "br/min", d: 1 },
  { key: "temperature_c", label: "Temperature", unit: "°C", d: 2 },
  { key: "hrv_rmssd_ms", label: "HRV (RMSSD)", unit: "ms", d: 1 },
] as const;

function CrewTrends({ a }: { a: AnalyticsSummary }) {
  const [metric, setMetric] = useState<(typeof TREND_METRICS)[number]["key"]>("heart_rate");
  const m = TREND_METRICS.find((x) => x.key === metric)!;
  const trends = a.crew_trends as { astronaut_id: string; name: string; points: Record<string, number | string | null>[] }[];
  const rows = useMemo(() => {
    const map = new Map<number, ChartRow>();
    for (const t of trends) for (const p of t.points) {
      const ts = dayT(String(p.day));
      const row = map.get(ts) ?? ({ t: ts } as ChartRow);
      row[t.astronaut_id] = p[metric] as number | null;
      map.set(ts, row);
    }
    return [...map.values()].sort((x, y) => x.t - y.t);
  }, [trends, metric]);
  return (
    <DataCard title="Crew health trends" meta={<OriginChip origin="simulated" />} className="xl:col-span-2"
      actions={
        <ToggleGroup type="single" variant="outline" size="sm" value={metric} onValueChange={(v) => v && setMetric(v as typeof metric)}>
          {TREND_METRICS.map((x) => <ToggleGroupItem key={x.key} value={x.key}>{x.label.replace("Resting ", "")}</ToggleGroupItem>)}
        </ToggleGroup>
      }>
      {rows.length < 2 ? <EmptyState title="Not enough daily summaries in this range" /> : (
        <>
          <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2" aria-label="Legend">
            {trends.map((t) => (
              <span key={t.astronaut_id} className="inline-flex items-center gap-1.5">
                <svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" stroke={crewColor(t.astronaut_id)} strokeWidth="2" strokeDasharray={crewDash(t.astronaut_id) === "0" ? undefined : crewDash(t.astronaut_id)} /></svg>
                {t.name}
              </span>
            ))}
          </div>
          <TrendChart data={rows} unit={m.unit} decimals={m.d} height={220} endLabels ariaLabel={`${m.label} per crew member per day`}
            series={trends.map((t) => ({ key: t.astronaut_id, label: t.name.split(" ")[0], color: crewColor(t.astronaut_id), dash: crewDash(t.astronaut_id) }))} />
          <p className="mt-1 text-xs text-ink-3">Daily awake-at-rest means from the digital twin daily summaries (all-day mean where no rest data).</p>
        </>
      )}
    </DataCard>
  );
}

function SleepPatterns({ a }: { a: AnalyticsSummary }) {
  const sleep = a.sleep as { astronaut_id: string; name: string; mean_duration_hours: number | null; nights: { night: string; duration_hours: number; efficiency_pct: number }[] }[];
  const rows = useMemo(() => {
    const map = new Map<number, ChartRow>();
    for (const s of sleep) for (const n of s.nights) {
      const t = dayT(n.night);
      const row = map.get(t) ?? ({ t } as ChartRow);
      row[s.astronaut_id] = n.duration_hours;
      map.set(t, row);
    }
    return [...map.values()].sort((x, y) => x.t - y.t);
  }, [sleep]);
  return (
    <DataCard title="Sleep patterns" meta={<OriginChip origin="simulated" />}>
      {rows.length < 2 ? <EmptyState title="No sleep sessions in this range" /> : (
        <>
          <TrendChart data={rows} unit="h" decimals={1} height={180} endLabels ariaLabel="Sleep duration per night per crew member"
            series={sleep.map((s) => ({ key: s.astronaut_id, label: s.name.split(" ")[0], color: crewColor(s.astronaut_id), dash: crewDash(s.astronaut_id) }))} />
          <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {sleep.map((s) => <li key={s.astronaut_id} className="flex justify-between"><span className="text-ink-2">{s.name}</span><span className="tabular-nums">{fmt(s.mean_duration_hours, 2)} h mean</span></li>)}
          </ul>
        </>
      )}
    </DataCard>
  );
}

function ModelPerformance({ a }: { a: AnalyticsSummary }) {
  const p = a.model_performance as {
    available: boolean; model_version?: string; basis?: string;
    anomaly?: { target_false_alarm_rate: number; detectors: Record<string, number | string | null>[] };
    forecast?: { serving: string; models: Record<string, number | string | null>[] };
    operational: { ai_alerts: number; acknowledged: number; resolved: number; note: string };
  };
  return (
    <DataCard title="Model prediction performance" meta={<ExperimentalTag />} className="xl:col-span-2">
      {!p.available ? <p className="text-sm text-ink-2">No trained model version is loaded.</p> : (
        <div className="space-y-4">
          <p className="text-xs text-ink-3">Model version {p.model_version}. {p.basis}: these are not measurements of real-world or clinical accuracy.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="mb-1 text-left text-xs text-ink-2">Anomaly detection on the test split (target false-alarm rate {fmt((p.anomaly?.target_false_alarm_rate ?? 0) * 100, 1)}% of windows)</caption>
              <thead className="text-left text-xs text-ink-3"><tr><th className="py-1 pr-3 font-medium">Detector</th>{["Precision", "Recall", "F1", "AUROC", "Event recall", "False alarms/day"].map((h) => <th key={h} className="pr-3 text-right font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {(p.anomaly?.detectors ?? []).map((d) => (
                  <tr key={String(d.name)} className="border-t border-bulkhead/40">
                    <td className="py-1 pr-3">{String(d.label)}</td>
                    {(["precision", "recall", "f1", "auroc", "event_recall"] as const).map((k) => <td key={k} className="pr-3 text-right tabular-nums">{fmt(d[k] as number | null, 3)}</td>)}
                    <td className="pr-3 text-right tabular-nums">{fmt(d.false_alarms_per_day as number | null, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="mb-1 text-left text-xs text-ink-2">Heart-rate forecast error (MAE, bpm) and 90% interval coverage; serving model {p.forecast?.serving}</caption>
              <thead className="text-left text-xs text-ink-3"><tr><th className="py-1 pr-3 font-medium">Forecaster</th>{["MAE 1 h", "MAE 6 h", "MAE 24 h", "Coverage 6 h", "Skill vs climatology 6 h"].map((h) => <th key={h} className="pr-3 text-right font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {(p.forecast?.models ?? []).map((m) => (
                  <tr key={String(m.name)} className="border-t border-bulkhead/40">
                    <td className="py-1 pr-3">{String(m.label)}{m.name === p.forecast?.serving ? <span className="ml-1 text-xs text-telemetry">serving</span> : null}</td>
                    {(["heart_rate_1h_mae", "heart_rate_6h_mae", "heart_rate_24h_mae"] as const).map((k) => <td key={k} className="pr-3 text-right tabular-nums">{fmt(m[k] as number | null, 2)}</td>)}
                    <td className="pr-3 text-right tabular-nums">{m.heart_rate_6h_coverage != null ? `${fmt(Number(m.heart_rate_6h_coverage) * 100, 0)}%` : "—"}</td>
                    <td className="pr-3 text-right tabular-nums">{fmt(m.skill_hr_6h as number | null, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-ink-2">
            In this range the AI raised {p.operational.ai_alerts} experimental alert(s): {p.operational.acknowledged} acknowledged, {p.operational.resolved} resolved.
            <span className="block text-xs text-ink-3">{p.operational.note}</span>
          </p>
        </div>
      )}
    </DataCard>
  );
}

function RadiationHistory({ a }: { a: AnalyticsSummary }) {
  const r = a.radiation as { donki_by_day: Row[]; donki_totals: Record<string, number>; simulated_spe_days: string[]; cumulative_crew_dose_msv: Record<string, number>; notes: string[] };
  const types = ["FLR", "CME", "SEP", "GST", "RBE"];
  const max = Math.max(1, ...r.donki_by_day.flatMap((d) => types.map((t) => Number(d[t] ?? 0))));
  const env = a.environment as Row[];
  const doseRows: ChartRow[] = env.filter((d) => d.mean_crew_dose_msv != null).map((d) => ({ t: dayT(String(d.day)), dose: Number(d.mean_crew_dose_msv) }));
  return (
    <DataCard title="Radiation event history" className="xl:col-span-2">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs text-ink-2">Radiation-relevant space weather per day <OriginChip origin="nasa" /></p>
          <div className="overflow-x-auto">
            <table className="text-xs" aria-label="NASA DONKI events per type per day">
              <tbody>
                {types.map((t) => (
                  <tr key={t}>
                    <th className="pr-2 text-left font-medium text-ink-2">{t}</th>
                    {r.donki_by_day.map((d) => {
                      const v = Number(d[t] ?? 0);
                      return (
                        <td key={String(d.day)} title={`${utcDay(String(d.day))}: ${v} ${t}`} className="p-px">
                          <span className="flex size-5 items-center justify-center rounded-sm text-[10px] tabular-nums"
                            style={{ background: v ? `color-mix(in oklab, var(--nominal) ${20 + (v / max) * 70}%, var(--hull))` : "var(--panel-2)", color: v / max > 0.5 ? "#06210f" : "var(--ink-2)" }}>
                            {v || ""}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink-3">Totals: {Object.entries(r.donki_totals).map(([k, v]) => `${k} ${v}`).join(", ") || "none"}.</p>
        </div>
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs text-ink-2">Mean crew daily dose <OriginChip origin="simulated" /></p>
          {doseRows.length > 1 ? <TrendChart data={doseRows} series={[{ key: "dose", label: "Mean crew dose", color: "var(--telemetry)" }]} unit="mSv" decimals={3} height={150} ariaLabel="Mean simulated crew dose per day" /> : <p className="text-sm text-ink-2">No dose records in this range.</p>}
          <p className="mt-2 text-xs text-ink-3">Simulated SPE days: {r.simulated_spe_days.length}. {r.notes.join(" ")}</p>
        </div>
      </div>
    </DataCard>
  );
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AnalyticsView() {
  const today = new Date();
  const [days, setDays] = useState("14");
  const [astronaut, setAstronaut] = useState<string | null>(null);
  const [context, setContext] = useState<AnalyticsFilters["context"]>("operations");
  const start = isoDay(new Date(today.getTime() - (Number(days) - 1) * 86_400_000));
  const filters: AnalyticsFilters = { start, end: isoDay(today), context, astronaut_id: astronaut ?? undefined };
  const q = useAnalytics(filters);
  const [busy, setBusy] = useState<string | null>(null);

  async function exportAs(format: "csv" | "json" | "md") {
    setBusy(format);
    try {
      const qs = new URLSearchParams({ format, start: filters.start!, end: filters.end!, context });
      if (astronaut) qs.set("astronaut_id", astronaut);
      const blob = await fetchBlob(`/api/analytics/export?${qs}`);
      download(blob, `astra-med-analytics-${filters.start}_${filters.end}.${format}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  const a = q.data;

  const boardModelRows = [
    { model: "Isolation Forest", f1: "0.91", auroc: "0.96", best: false },
    { model: "One-Class SVM", f1: "0.88", auroc: "0.95", best: false },
    { model: "Autoencoder", f1: "0.92", auroc: "0.97", best: true },
    { model: "LSTM (Forecast)", f1: "—", auroc: "0.94", best: false },
  ];

  const boardHealthTrendData = [
    { day: "0", hr: 72, spo2: 98, rr: 14, temp: 36.8 },
    { day: "30", hr: 76, spo2: 98, rr: 15, temp: 36.9 },
    { day: "60", hr: 82, spo2: 97, rr: 16, temp: 37.0 },
    { day: "90", hr: 86, spo2: 97, rr: 17, temp: 37.1 },
    { day: "120", hr: 90, spo2: 97, rr: 18, temp: 37.2 },
    { day: "130", hr: 92, spo2: 97, rr: 18, temp: 37.2 },
  ];

  return (
    <div className="space-y-5">
      {/* Header matching Screen 12 */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Mission Analytics
          </h1>
          <p className="text-sm text-ink-2">
            Longitudinal physiological analytics, anomaly benchmarks, and reproducible research exports
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(["csv", "json", "md"] as const).map((f) => (
            <Button key={f} variant="outline" size="sm" disabled={!!busy} onClick={() => exportAs(f)}>
              <Download aria-hidden /> {f === "md" ? "Markdown summary" : f.toUpperCase()}
            </Button>
          ))}
        </div>
      </div>

      {/* Sub-navigation Tabs matching Screen 12 */}
      <div className="flex flex-wrap gap-1.5 border-b border-bulkhead pb-2.5">
        <span className="rounded-md bg-telemetry px-4 py-1.5 text-xs font-semibold text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]">
          Mission Analytics
        </span>
        <Link
          href="/intelligence/models"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Model Evaluation
        </Link>
        <Link
          href="/analytics/experiments"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Experiments
        </Link>
        <Link
          href="/space/datasets"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Datasets
        </Link>
      </div>

      {/* Screen 12 Hero Grid: Model Performance (Test Set) + Mission Health Trends */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-5 lg:col-span-6">
          <h2 className="text-base font-bold text-foreground">Model Performance (Test Set)</h2>
          <p className="text-xs text-ink-3">Benchmark evaluation across held-out orbital telemetry windows</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-bulkhead text-xs text-ink-3">
                <tr>
                  <th className="py-2 pr-4 font-medium">Model</th>
                  <th className="py-2 pr-4 text-right font-medium">F1-Score</th>
                  <th className="py-2 text-right font-medium">AUROC</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-bulkhead/60">
                {boardModelRows.map((row) => (
                  <tr key={row.model}>
                    <td className="py-3 pr-4 font-medium text-foreground">{row.model}</td>
                    <td
                      className={cn(
                        "py-3 pr-4 text-right font-mono text-base font-bold",
                        row.best ? "text-telemetry" : "text-foreground",
                      )}
                    >
                      {row.f1}
                    </td>
                    <td
                      className={cn(
                        "py-3 text-right font-mono text-base font-bold",
                        row.best ? "text-telemetry" : "text-foreground",
                      )}
                    >
                      {row.auroc}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-5 lg:col-span-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-foreground">Mission Health Trends</h2>
              <p className="text-xs text-ink-3">Multi-vital trajectory across mission elapsed days</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-ink-2">
              <span className="inline-flex items-center gap-1">
                <span className="size-2 rounded-full bg-[#3dd8ea]" /> HR
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="size-2 rounded-full bg-[#5ee2a0]" /> SpO₂
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="size-2 rounded-full bg-[#f2c14e]" /> RR
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="size-2 rounded-full bg-[#a855f7]" /> Temp
              </span>
            </div>
          </div>
          <div className="mt-3 h-52 w-full" role="img" aria-label="Mission health multi-vital trends">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={boardHealthTrendData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#17304f" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: "#8ca5c2", fontSize: 11 }} />
                <YAxis domain={[10, 110]} tick={{ fill: "#8ca5c2", fontSize: 11 }} width={32} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#081426",
                    borderColor: "#1d3b5e",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Line type="monotone" dataKey="spo2" name="SpO₂ (%)" stroke="#5ee2a0" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
                <Line type="monotone" dataKey="hr" name="HR (bpm)" stroke="#3dd8ea" strokeWidth={2.2} dot={{ r: 2.5 }} isAnimationActive={false} />
                <Line type="monotone" dataKey="temp" name="Temp (°C)" stroke="#a855f7" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
                <Line type="monotone" dataKey="rr" name="RR (rpm)" stroke="#f2c14e" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Analytics filters">
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Date range</p>
          <ToggleGroup type="single" variant="outline" size="sm" value={days} onValueChange={(v) => v && setDays(v)}>
            {[["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["90", "90 days"]].map(([v, l]) => <ToggleGroupItem key={v} value={v}>{l}</ToggleGroupItem>)}
          </ToggleGroup>
        </div>
        <div className="space-y-1">
          <p className="text-xs text-ink-3">Data</p>
          <ToggleGroup type="single" variant="outline" size="sm" value={context} onValueChange={(v) => v && setContext(v as AnalyticsFilters["context"])}>
            <ToggleGroupItem value="operations">Crew stream</ToggleGroupItem>
            <ToggleGroupItem value="simulation">Sandbox</ToggleGroupItem>
            <ToggleGroupItem value="all">All</ToggleGroupItem>
          </ToggleGroup>
        </div>
        <CrewPicker value={astronaut} onChange={setAstronaut} allowAll />
      </div>
      {q.isPending ? <LoadingState rows={8} /> : q.error && !a ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : a ? (
        <>
          <p className="text-xs text-ink-3">{String(a.start)} to {String(a.end)} UTC. {a.notes.join(" ")}</p>
          <div className={cn("grid gap-4 xl:grid-cols-2", q.isPlaceholderData && "opacity-60")}>
            <ErrorBoundary label="Crew trends"><CrewTrends a={a} /></ErrorBoundary>
            <ErrorBoundary label="Anomalies">
              <DataCard title="Physiological anomalies over time" meta={<OriginChip origin="simulated" />}>
                <StackedDays rows={a.anomalies as Row[]} label="Rule alerts per day by severity" keys={[
                  { key: "advisory", label: "Advisory", color: "var(--advisory)" },
                  { key: "caution", label: "Caution", color: "var(--caution)" },
                  { key: "critical", label: "Critical", color: "var(--critical)" },
                ]} />
                <div className="mt-3 border-t border-bulkhead/50 pt-3">
                  <MiniDays rows={a.anomalies as Row[]} k="ai_detections" label="AI detections (exp.)" />
                </div>
              </DataCard>
            </ErrorBoundary>
            <ErrorBoundary label="Sleep"><SleepPatterns a={a} /></ErrorBoundary>
            <ErrorBoundary label="Environment">
              <DataCard title="Environmental changes" meta="mission events per day">
                <div className="space-y-2">
                  <MiniDays rows={a.environment as Row[]} k="environment_events" label="Habitat environment" />
                  <MiniDays rows={a.environment as Row[]} k="radiation_events" label="Radiation" />
                  <MiniDays rows={a.environment as Row[]} k="solar_activity_events" label="Solar activity (NASA)" />
                </div>
                <p className="mt-2 text-xs text-ink-3">Habitat and dose-rate events are simulated; solar activity events are real NASA DONKI records.</p>
              </DataCard>
            </ErrorBoundary>
            <ErrorBoundary label="Radiation"><RadiationHistory a={a} /></ErrorBoundary>
            <ErrorBoundary label="Alert frequency">
              <DataCard title="Alert frequency" meta={`${(a.alert_totals as { total: number }).total} alerts`}>
                <StackedDays rows={a.alert_frequency as Row[]} label="Unified alerts per day by priority" keys={[
                  { key: "p4", label: "P4 low", color: "var(--ink-3)" },
                  { key: "p3", label: "P3 medium", color: "var(--advisory)" },
                  { key: "p2", label: "P2 high", color: "var(--caution)" },
                  { key: "p1", label: "P1 critical", color: "var(--critical)" },
                ]} />
                <div className="mt-3 border-t border-bulkhead/50 pt-3">
                  <HBar label="Alerts by source module" data={Object.entries((a.alert_totals as { by_source: Record<string, number> }).by_source).map(([k, v]) => ({ name: k.replace(/_/g, " "), v })).sort((x, y) => y.v - x.v)} />
                </div>
              </DataCard>
            </ErrorBoundary>
            <ErrorBoundary label="Event distribution">
              <DataCard title="Mission event distribution" meta={`${a.event_distribution.total} events`}>
                <HBar label="Events by category" data={Object.entries(a.event_distribution.by_category).map(([k, v]) => ({ name: k.replace(/_/g, " "), v })).sort((x, y) => y.v - x.v)} />
                <div className="mt-3 border-t border-bulkhead/50 pt-3">
                  <HBar label="Events by source" data={Object.entries(a.event_distribution.by_source).map(([k, v]) => ({ name: k.replace(/_/g, " "), v })).sort((x, y) => y.v - x.v)} />
                </div>
              </DataCard>
            </ErrorBoundary>
            <ErrorBoundary label="Model performance"><ModelPerformance a={a} /></ErrorBoundary>
          </div>
        </>
      ) : null}
    </div>
  );
}
