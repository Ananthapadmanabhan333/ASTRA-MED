"use client";

import { AlertList } from "@/components/alerts/alert-list";
import { Panel } from "@/components/data/panel";
import { EmptyState, QueryView } from "@/components/data/states";
import { useAlerts, useAstronauts, useSimulationEvents } from "@/lib/api/hooks";
import { duration, utcDayTime } from "@/lib/format";
import { SCENARIO_LABEL } from "@/lib/metrics";

const METHODS = [
  {
    name: "Threshold rules",
    body: "Fixed limits per signal, adjusted for activity (for example, higher heart-rate limits during exercise). A breach must persist for 5 s before an alert opens.",
  },
  {
    name: "Rhythm check",
    body: "Beat-to-beat intervals are measured from the synthetic ECG. Irregularity above 0.12 (mean |ΔRR| / mean RR) for 5 s raises a rhythm alert.",
  },
  {
    name: "Personal baseline",
    body: "Each reading is compared with the crew member's expected value for the time of day and activity. A z-score beyond ±4 for 20 s raises an advisory, even inside fixed limits.",
  },
];

export function DetectionMethods() {
  return (
    <Panel title="How anomalies are detected" description="Version 1 detectors are transparent and testable. ML models are planned for phase 3.">
      <dl className="grid gap-4 md:grid-cols-3">
        {METHODS.map((m) => (
          <div key={m.name}>
            <dt className="text-sm font-medium text-foreground">{m.name}</dt>
            <dd className="mt-1 text-sm text-ink-2">{m.body}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

export function RecentDetections() {
  const alerts = useAlerts({ hours: 24 });
  const crew = useAstronauts();
  return (
    <Panel title="Detections, last 24 hours" description="All alert states, newest first.">
      <QueryView
        query={alerts}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="Nothing detected in the last 24 hours">Start a scenario above to test detection.</EmptyState>}
      >
        {(data) => <AlertList alerts={data.slice(0, 12)} crew={crew.data} compact />}
      </QueryView>
    </Panel>
  );
}

export function EventLog() {
  const events = useSimulationEvents();
  const crew = useAstronauts();
  const names = new Map(crew.data?.map((a) => [a.id, a.name]));
  return (
    <Panel title="Scenario log, last 48 hours" description="Every injected test scenario, whether started by an operator or the simulator.">
      <QueryView query={events} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No scenarios in the last 48 hours" />}>
        {(data) => (
          <div className="max-h-96 overflow-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="sr-only">Simulation scenario log</caption>
              <thead className="sticky top-0 bg-hull text-xs text-ink-2">
                <tr>
                  {["Started (UTC)", "Scenario", "Crew", "Source", "Length", "Intensity", "State"].map((h) => (
                    <th key={h} scope="col" className="py-2 pr-4 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {data.map((e) => {
                  const end = e.cancelled_at ?? e.ends_at;
                  return (
                    <tr key={e.id} className="border-t border-bulkhead/60">
                      <td className="py-2 pr-4 text-ink-2">{utcDayTime(e.started_at)}</td>
                      <td className="py-2 pr-4">{SCENARIO_LABEL[e.scenario] ?? e.label}</td>
                      <td className="py-2 pr-4">{e.astronaut_id ? names.get(e.astronaut_id) ?? e.astronaut_id : "Whole crew"}</td>
                      <td className="py-2 pr-4 text-ink-2">{e.triggered_by === "random" ? "Simulator" : "Operator"}</td>
                      <td className="py-2 pr-4">{duration((Date.parse(end) - Date.parse(e.started_at)) / 1000)}</td>
                      <td className="py-2 pr-4">{e.intensity.toFixed(2)}×</td>
                      <td className="py-2 pr-4">
                        {e.active ? <span className="text-caution">Running</span> : e.cancelled_at ? "Stopped" : "Finished"}
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
