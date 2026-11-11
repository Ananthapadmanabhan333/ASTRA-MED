import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { RadiationView } from "@/components/radiation/radiation-view";

export const metadata: Metadata = { title: "Radiation" };

export default function RadiationPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Radiation exposure"
        description="Simulated cumulative and daily dose for each crew member during interplanetary cruise."
      />
      <RadiationView />
    </div>
  );
}
