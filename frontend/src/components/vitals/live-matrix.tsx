"use client";

import { OctagonX, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Panel } from "@/components/data/panel";
import { QueryView } from "@/components/data/states";
import { useAstronauts, useThresholds } from "@/lib/api/hooks";
import type { VitalReading } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt } from "@/lib/format";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL } from "@/lib/metrics";
import { classify } from "@/lib/thresholds";
import { cn } from "@/lib/utils";

const COLUMNS: { key: keyof VitalReading; label: string; unit: string; decimals: number }[] = [
  { key: "heart_rate", label: "Heart rate", unit: "bpm", decimals: 0 },
  { key: "spo2", label: "SpO₂", unit: "%", decimals: 1 },
  { key: "systolic", label: "Systolic", unit: "mmHg", decimals: 0 },
  { key: "diastolic", label: "Diastolic", unit: "mmHg", decimals: 0 },
  { key: "temperature_c", label: "Temp", unit: "°C", decimals: 2 },
  { key: "respiratory_rate", label: "Resp. rate", unit: "/min", decimals: 0 },
  { key: "hrv_rmssd_ms", label: "RMSSD", unit: "ms", decimals: 0 },
];

export function LiveMatrix() {
  const crew = useAstronauts();
  const rules = useThresholds();
  const latest = useLive((s) => s.latest);

  return (
    <Panel title="Live vitals" description="Current simulated reading for each crew member. Out-of-limit values show an icon.">
      <QueryView query={crew}>
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] text-left text-sm">
              <caption className="sr-only">Live simulated vitals by crew member</caption>
              <thead className="text-xs text-ink-2">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Crew member
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Activity
                  </th>
                  {COLUMNS.map((c) => (
                    <th key={c.key} scope="col" className="py-2 pr-4 text-right font-medium">
                      {c.label} <span className="text-ink-3">{c.unit}</span>
                    </th>
                  ))}
                  <th scope="col" className="py-2 font-medium">
                    Rhythm
                  </th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.map((a) => {
                  const r = latest[a.id] ?? a.latest;
                  return (
                    <tr key={a.id} className="border-t border-bulkhead/60">
                      <td className="py-2.5 pr-4">
                        <Link href={`/crew/${a.id}`} className="inline-flex items-center gap-2 hover:text-telemetry">
                          <span className="size-2 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
                          {a.name}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-4 text-ink-2">{r ? ACTIVITY_LABEL[r.activity_state] : "—"}</td>
                      {COLUMNS.map((c) => {
                        const v = r?.[c.key] as number | null | undefined;
                        const breach = r && v != null ? classify(c.key, v, r.activity_state, rules.data) : null;
                        const Icon = breach?.severity === "critical" ? OctagonX : breach ? TriangleAlert : null;
                        return (
                          <td
                            key={c.key}
                            className={cn(
                              "py-2.5 pr-4 text-right",
                              breach?.severity === "critical" && "text-critical",
                              breach?.severity === "caution" && "text-caution",
                            )}
                          >
                            <span className="inline-flex items-center justify-end gap-1">
                              {Icon && <Icon className="size-3.5" aria-label={breach!.severity} />}
                              {fmt(v, c.decimals)}
                            </span>
                          </td>
                        );
                      })}
                      <td className={cn("py-2.5", r?.rhythm === "irregular" ? "text-caution" : "text-ink-2")}>
                        {r ? (r.rhythm === "irregular" ? "Irregular" : "Regular") : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </Panel>
  );
}
