import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { RadiationView } from "@/components/radiation/radiation-view";
import { RadiationIntelligence } from "@/components/space/radiation-intel";

export const metadata: Metadata = { title: "Radiation intelligence" };

export default function RadiationPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        title="Radiation exposure"
        description="Simulated cumulative and daily dose for each crew member during interplanetary cruise, then radiation intelligence from NASA open data."
      />
      <RadiationView />
      <RadiationIntelligence />
    </div>
  );
}
