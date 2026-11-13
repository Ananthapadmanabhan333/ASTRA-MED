import type { Metadata } from "next";
import { Suspense } from "react";

import { IntelligenceCenter } from "@/components/ai/intelligence-center";
import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";

export const metadata: Metadata = { title: "AI intelligence" };

export default function IntelligencePage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="AI intelligence center"
        description="Personal baselines, multivariate anomaly detection, 24-hour forecasts and an early-warning assessment for each crew member."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <IntelligenceCenter />
      </Suspense>
    </div>
  );
}
