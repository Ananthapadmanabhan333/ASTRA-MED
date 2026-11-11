"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { useAstronauts } from "@/lib/api/hooks";
import { crewColor } from "@/lib/crew";
import { fmt } from "@/lib/format";
import { liveStatus } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL } from "@/lib/metrics";

export function CrewRoster() {
  const crew = useAstronauts();
  const latest = useLive((s) => s.latest);
  const alerts = useLive((s) => s.openAlerts);
  const connection = useLive((s) => s.connection);

  return (
    <QueryView query={crew} isEmpty={(d) => d.length === 0}>
      {(data) => (
        <div className="overflow-x-auto rounded-lg border border-bulkhead">
          <table className="w-full min-w-[54rem] text-left text-sm">
            <caption className="sr-only">Crew roster with latest simulated vitals</caption>
            <thead className="bg-hull text-xs text-ink-2">
              <tr>
                {["Crew member", "Status", "Activity", "Heart rate", "SpO₂", "BP", "Temp", "Open alerts", ""].map((h) => (
                  <th key={h} scope="col" className="px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {data.map((a) => {
                const r = latest[a.id] ?? a.latest;
                const mine = Object.values(alerts).filter((x) => x.astronaut_id === a.id);
                const status = connection === "live" ? liveStatus(mine) : a.status;
                return (
                  <tr key={a.id} className="border-t border-bulkhead/70 bg-hull/40 hover:bg-hull">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="size-2.5 shrink-0 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
                        <div>
                          <Link href={`/crew/${a.id}`} className="font-medium text-foreground hover:text-telemetry">
                            {a.name}
                          </Link>
                          <p className="text-xs text-ink-2">
                            {a.role}, age {a.age}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={status} />
                    </td>
                    <td className="px-4 py-3 text-ink-2">{r ? ACTIVITY_LABEL[r.activity_state] : "—"}</td>
                    <td className="px-4 py-3">{fmt(r?.heart_rate)} <span className="text-xs text-ink-3">bpm</span></td>
                    <td className="px-4 py-3">{fmt(r?.spo2, 1)} <span className="text-xs text-ink-3">%</span></td>
                    <td className="px-4 py-3">{r ? `${r.systolic}/${r.diastolic}` : "—"}</td>
                    <td className="px-4 py-3">{fmt(r?.temperature_c, 1)} <span className="text-xs text-ink-3">°C</span></td>
                    <td className="px-4 py-3">{connection === "live" ? mine.length : a.open_alerts}</td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/crew/${a.id}`}
                        className="inline-flex items-center gap-1 text-sm text-telemetry hover:underline"
                        aria-label={`Open health profile for ${a.name}`}
                      >
                        Profile <ChevronRight className="size-4" aria-hidden />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </QueryView>
  );
}
