import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { CrewMonitoringView } from "@/components/mission/crew-monitoring";

export const metadata: Metadata = { title: "Crew monitoring" };

export default function CrewPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Crew monitoring"
        description="Every crew member at a glance: current simulated measurements, deviation from their personal baseline, open anomalies, the experimental AI risk assessment and the last week. Open a crew member for their complete health profile."
      />
      <CrewMonitoringView />
    </div>
  );
}
