import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { DetectionMethods, EventLog, RecentDetections } from "@/components/simulation/detection-panels";
import { ScenarioConsole } from "@/components/simulation/scenario-console";

export const metadata: Metadata = { title: "Anomalies & tests" };

export default function AnomaliesPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Anomaly detection and test scenarios"
        description="Exercise the monitoring pipeline end to end: inject a scenario, see it detected, alerted and logged."
      />
      <ScenarioConsole />
      <DetectionMethods />
      <div className="grid gap-5 xl:grid-cols-2">
        <RecentDetections />
        <EventLog />
      </div>
    </div>
  );
}
