import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { DemoView } from "@/components/mission/demo-view";

export const metadata: Metadata = { title: "Demo mode" };

export default function DemoPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Demo mode"
        description="A guided walk through ASTRA-MED in the isolated simulation sandbox: start a scripted mission with a fixed seed, then watch twelve steps tick as the backend reports each one, from streaming telemetry to a structured incident report. All crew data is simulated."
      />
      <DemoView />
    </div>
  );
}
