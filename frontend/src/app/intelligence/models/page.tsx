import type { Metadata } from "next";

import { ModelPerformanceView } from "@/components/ai/model-performance";
import { PageHeader } from "@/components/data/panel";

export const metadata: Metadata = { title: "Model evaluation" };

export default function ModelsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Model evaluation"
        description="How each detector and forecaster performed on held-out simulated data. These results describe the simulator, not real crew."
      />
      <ModelPerformanceView />
    </div>
  );
}
