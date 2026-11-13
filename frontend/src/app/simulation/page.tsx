import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { SimulationView } from "@/components/mission/simulation-view";

export const metadata: Metadata = { title: "Mission simulation" };

export default function SimulationPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Mission simulation"
        description="A complete demonstration mission in an isolated sandbox: choose crew and a scenario, set the speed, inject health, environmental and space-weather events, watch the AI models respond, and replay any run."
      />
      <SimulationView />
    </div>
  );
}
