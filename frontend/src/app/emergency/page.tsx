import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { EmergencyView } from "@/components/medical/emergency-view";

export const metadata: Metadata = { title: "Emergency simulator" };

export default function EmergencyPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Emergency scenario simulator"
        description="Rehearse monitoring, AI analysis and the review workflow with labelled, simulated scenarios: heart-rate elevation, desaturation, abnormal respiration, sleep disruption, multiple deviations, a radiation event and a habitat anomaly."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <EmergencyView />
      </Suspense>
    </div>
  );
}
