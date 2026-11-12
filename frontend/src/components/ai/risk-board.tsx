"use client";

import { ListOrdered } from "lucide-react";

import { EmptyState } from "@/components/data/states";
import type { CrewRiskSummary, RiskWarning } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CONCERN, ConcernPill } from "./concern";

const SIGNAL_SHORT: Record<string, string> = {
  heart_rate: "HR",
  spo2: "SpO₂",
  systolic: "SYS",
  diastolic: "DIA",
  temperature_c: "Temp",
  respiratory_rate: "RR",
};

export function RiskCard({
  summary,
  selected,
  onSelect,
}: {
  summary: CrewRiskSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const c = CONCERN[summary.category];
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex min-w-0 flex-col rounded-lg border p-4 text-left transition-colors",
        selected ? "border-telemetry bg-telemetry/6" : "border-bulkhead bg-hull hover:border-ink-3",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-heading text-lg font-semibold leading-tight">
            <span className="size-2 shrink-0 rounded-full" style={{ background: crewColor(summary.astronaut_id) }} aria-hidden />
            <span className="truncate">{summary.name}</span>
          </p>
          <p className="text-xs text-ink-2">{summary.role}</p>
        </div>
        <ConcernPill category={summary.category} />
      </div>
      <div className="mt-3 flex items-end gap-3">
        <span className={cn("readout text-5xl font-semibold", c.text)}>{summary.health_score}</span>
        <span className="pb-1 text-xs text-ink-2">
          health score
          <span className="block text-ink-3">
            risk {fmt(summary.risk_score, 0)} of 100, {summary.confidence_level} confidence
          </span>
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-bulkhead/60" aria-hidden>
        <div className={cn("h-full rounded-full", c.bar)} style={{ width: `${Math.max(3, summary.risk_score)}%` }} />
      </div>
      <p className="mt-3 line-clamp-2 min-h-10 text-sm text-ink-2">{summary.top_warning ?? "No warnings."}</p>
      {summary.top_signals.length > 0 && (
        <p className="mt-1 text-xs text-ink-3">Signals: {summary.top_signals.map((s) => SIGNAL_SHORT[s] ?? s).join(", ")}</p>
      )}
    </button>
  );
}

export function WarningQueue({
  crew,
  onSelect,
}: {
  crew: CrewRiskSummary[];
  onSelect: (id: string) => void;
}) {
  const rows: (RiskWarning & { astronaut_id: string; name: string })[] = crew
    .flatMap((c) => c.warnings.map((w) => ({ ...w, astronaut_id: c.astronaut_id, name: c.name })))
    .sort((a, b) => b.points - a.points)
    .slice(0, 8);
  if (!rows.length) {
    return (
      <EmptyState title="No early warnings" icon={<ListOrdered className="size-5" />}>
        No crew member has a baseline deviation, flagged pattern, forecast crossing or open alert right now.
      </EmptyState>
    );
  }
  return (
    <ol className="space-y-2">
      {rows.map((w, i) => (
        <li key={`${w.astronaut_id}-${w.title}`}>
          <button
            type="button"
            onClick={() => onSelect(w.astronaut_id)}
            className="grid w-full grid-cols-[1.75rem_1fr] gap-3 rounded-md px-2 py-2 text-left hover:bg-accent/40"
          >
            <span className="readout pt-0.5 text-lg text-ink-3">{i + 1}</span>
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2">
                <ConcernPill category={w.concern} />
                <span className="text-sm font-medium text-foreground">{w.title}</span>
              </span>
              <span className="mt-1 block text-xs text-ink-2">
                {w.name}. {w.detail}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
