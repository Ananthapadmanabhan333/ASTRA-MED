"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";

import { StatusIcon, StatusPill } from "@/components/status/status";
import type { Alert, AstronautSummary } from "@/lib/api/types";
import { fmt, relativeTime, utcDayTime } from "@/lib/format";
import { SCENARIO_LABEL } from "@/lib/metrics";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

import { AlertActions } from "./alert-actions";

const CATEGORY_LABEL: Record<Alert["category"], string> = {
  threshold: "Threshold rule",
  rhythm: "Rhythm check",
  baseline: "Personal baseline",
};

const STATUS_LABEL: Record<Alert["status"], string> = {
  active: "Active",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

function decimalsFor(unit: string) {
  return unit === "°C" || unit === "%" ? 1 : 0;
}

export function AlertRow({
  alert,
  name,
  compact = false,
}: {
  alert: Alert;
  name?: string;
  compact?: boolean;
}) {
  const now = useNow(15_000);
  const d = decimalsFor(alert.unit);
  const showPeak = alert.peak_value !== alert.trigger_value && alert.category !== "rhythm";
  return (
    <li
      className={cn(
        "grid gap-x-4 gap-y-2 border-b border-bulkhead/60 py-3 last:border-b-0",
        compact ? "grid-cols-[auto_1fr]" : "grid-cols-[auto_1fr] md:grid-cols-[auto_1fr_auto]",
      )}
    >
      <StatusIcon status={alert.severity} className="mt-0.5" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-foreground">{alert.title}</span>
          {name && (
            <Link href={`/crew/${alert.astronaut_id}`} className="text-sm text-ink-2 hover:text-telemetry">
              {name}
            </Link>
          )}
        </div>
        <p className="mt-0.5 text-sm text-ink-2">{alert.message}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
          {!compact && <StatusPill status={alert.severity} />}
          <span>{CATEGORY_LABEL[alert.category]}</span>
          <span title={utcDayTime(alert.opened_at)}>
            Opened {now ? relativeTime(alert.opened_at, now) : utcDayTime(alert.opened_at)}
          </span>
          {showPeak && (
            <span>
              Peak {fmt(alert.peak_value, d)} {alert.unit}
            </span>
          )}
          <span className={alert.status === "active" ? "text-foreground" : undefined}>
            {STATUS_LABEL[alert.status]}
          </span>
          {alert.condition_cleared_at && alert.status !== "resolved" && (
            <span className="text-nominal">Values back within limits</span>
          )}
          {alert.scenario && (
            <span className="inline-flex items-center gap-1 text-caution">
              <FlaskConical className="size-3" aria-hidden />
              Test scenario: {SCENARIO_LABEL[alert.scenario] ?? alert.scenario}
            </span>
          )}
        </div>
        {alert.operator_note && !compact && (
          <p className="mt-1.5 text-xs text-ink-2">Note: {alert.operator_note}</p>
        )}
      </div>
      {!compact && (
        <div className="col-span-2 md:col-span-1 md:self-center">
          <AlertActions alert={alert} />
        </div>
      )}
    </li>
  );
}

export function AlertList({
  alerts,
  crew,
  compact,
}: {
  alerts: Alert[];
  crew?: AstronautSummary[];
  compact?: boolean;
}) {
  const names = new Map(crew?.map((a) => [a.id, a.name]));
  return (
    <ul>
      {alerts.map((a) => (
        <AlertRow key={a.id} alert={a} name={names.get(a.astronaut_id)} compact={compact} />
      ))}
    </ul>
  );
}
