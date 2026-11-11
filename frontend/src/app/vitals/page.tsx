import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { CrewComparison } from "@/components/vitals/crew-comparison";
import { LiveMatrix } from "@/components/vitals/live-matrix";

export const metadata: Metadata = { title: "Vitals compare" };

export default function VitalsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Vitals compare"
        description="Put the whole crew side by side to spot who is drifting from the group."
      />
      <CrewComparison />
      <LiveMatrix />
    </div>
  );
}
