import type { Metadata } from "next";

import { CrewRoster } from "@/components/crew/crew-roster";
import { PageHeader } from "@/components/data/panel";

export const metadata: Metadata = { title: "Crew health" };

export default function CrewPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Crew health"
        description="Fictional Helios-7 crew with their latest simulated readings. Open a profile for live vitals, ECG and history."
      />
      <CrewRoster />
    </div>
  );
}
