"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAnomalyTimeline } from "@/lib/api/hooks";
import type { AnomalyDetectionResponse } from "@/lib/api/types";
import { duration, fmt, utcDayTime, utcTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ExplanationView } from "./explanation-view";

const KIND = { sudden_change: "Sudden change", gradual_deviation: "Gradual deviation", sustained_offset: "Sustained offset" } as Record<string, string>;
const SIG = { heart_rate: "HR", spo2: "SpO₂", systolic: "SYS", diastolic: "DIA", temperature_c: "Temp", respiratory_rate: "RR" } as Record<string, string>;
const DISPLAY_CAP = 4;

function ScoreChart({ data }: { data: AnomalyDetectionResponse }) {
  const rows = data.timeline.map((p) => ({
    t: Date.parse(p.ts),
    score: Math.min(DISPLAY_CAP, p.ensemble_score),
    raw: p.ensemble_score,
    flag: p.flagged ? Math.min(DISPLAY_CAP, p.ensemble_score) : null,
    votes: p.votes,
  }));
  const span = rows.length > 1 ? rows[rows.length - 1].t - rows[0].t : 0;
  return (
    <div className="h-44" role="img" aria-label="Ensemble anomaly score over time; values above 1 are flagged">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.55} vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) => (span > 2 * 86_400_000 ? utcDayTime(t).split(",")[0] : utcTime(t, false))}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--bulkhead)" }} minTickGap={48} />
          <YAxis domain={[0, DISPLAY_CAP]} ticks={[0, 1, 2, 3, 4]} tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={32} />
          <ReferenceLine y={1} stroke="var(--caution)" strokeDasharray="4 4" strokeOpacity={0.8}
            label={{ value: "threshold", position: "insideTopRight", fill: "var(--ink-3)", fontSize: 10 }} />
          <Line dataKey="score" stroke="var(--telemetry)" strokeWidth={1.75} dot={false} isAnimationActive={false} />
          <Scatter dataKey="flag" fill="var(--critical)" shape="circle" isAnimationActive={false} />
          <Tooltip
            isAnimationActive={false}
            cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof rows)[number];
              return (
                <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                  <p className="text-ink-2">{utcDayTime(Number(label))} UTC</p>
                  <p>Ensemble {fmt(r.raw, 2)}x threshold{r.raw >= 1 ? ", flagged" : ""}</p>
                  <p className="text-ink-2">{r.votes} of {data.detectors.length} detectors above their threshold</p>
                </div>
              );
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function AgreementStrip({ data }: { data: AnomalyDetectionResponse }) {
  const n = data.detectors.length;
  return (
    <div>
      <div className="flex h-3 gap-px overflow-hidden rounded-sm" aria-label="Detector agreement per window">
        {data.timeline.map((p) => (
          <span
            key={p.ts}
            className={cn("flex-1", p.votes === 0 ? "bg-bulkhead/50" : p.flagged ? "bg-critical" : "bg-caution")}
            style={{ opacity: p.votes === 0 ? 1 : 0.35 + 0.65 * (p.votes / n) }}
            title={`${utcTime(p.ts, false)}: ${p.votes} of ${n} detectors`}
          />
        ))}
      </div>
      <p className="mt-1 text-[11px] text-ink-3">
        Detector agreement per 5-minute window: grey none, amber some, red flagged by the ensemble. Darker means more detectors agree.
      </p>
    </div>
  );
}

export function AnomalyTimeline({ astronautId, name }: { astronautId: string; name: string }) {
  const [hours, setHours] = useState("24");
  const [open, setOpen] = useState<string | null>(null);
  const q = useAnomalyTimeline(astronautId, Number(hours));

  return (
    <Panel
      title="Anomaly detection timeline"
      description={`Multivariate ensemble across heart rate, SpO₂, blood pressure, temperature and breathing rate for ${name}, against this person's own baseline.`}
      actions={
        <ToggleGroup type="single" size="sm" variant="outline" value={hours} onValueChange={(v) => v && setHours(v)} aria-label="Time range">
          {[["6", "6 h"], ["24", "24 h"], ["72", "3 d"]].map(([v, l]) => (
            <ToggleGroupItem key={v} value={v} className="px-2.5 text-xs">{l}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      }
    >
      {q.isPending ? (
        <LoadingState label="Scoring windows" rows={4} />
      ) : q.error && !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <div className="space-y-4">
          <ScoreChart data={q.data} />
          <AgreementStrip data={q.data} />
          <p className="text-xs text-ink-3">
            Detectors: {q.data.detectors.map((d) => `${d.label} (weight ${fmt(d.weight, 2)})`).join(", ")}.{" "}
            {q.data.data_quality.missing_fraction > 0.05 && `${Math.round(q.data.data_quality.missing_fraction * 100)}% of values missing. `}
            Model {q.data.model_version}.
          </p>
          <div>
            <h3 className="mb-2 text-sm font-medium">
              Detections <span className="font-normal text-ink-3">(flagged for 10 minutes or more)</span>
            </h3>
            {q.data.detections.length === 0 ? (
              <EmptyState title="No sustained anomalies in this range">
                Start a test scenario from Anomalies & tests to see a detection here within a few minutes.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-bulkhead/60 rounded-md border border-bulkhead/70">
                {[...q.data.detections].reverse().map((d) => {
                  const key = d.peak_ts;
                  const expanded = open === key;
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        onClick={() => setOpen(expanded ? null : key)}
                        aria-expanded={expanded}
                        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2.5 text-left text-sm hover:bg-accent/30"
                      >
                        <span className="font-medium">{KIND[d.kind] ?? d.kind}</span>
                        <span className="text-ink-2">{d.signals.map((s) => SIG[s] ?? s).join(", ")}</span>
                        <span className="text-xs text-ink-3">
                          {utcDayTime(d.start)} UTC, {duration(d.duration_minutes * 60)}, peak {fmt(d.peak_score, 1)}x, {d.votes} of {q.data!.detectors.length} detectors
                        </span>
                        <ChevronDown className={cn("ml-auto size-4 text-ink-3 transition-transform", expanded && "rotate-180")} aria-hidden />
                      </button>
                      {expanded && d.explanation && (
                        <div className="border-t border-bulkhead/60 px-3 py-3">
                          <ExplanationView explanation={d.explanation} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
