import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { EmergencyView } from "@/components/medical/emergency-view";

export const metadata: Metadata = { title: "Emergency Simulator — ASTRA-MED" };

export default function EmergencyPage() {
  return (
    <Suspense fallback={<LoadingState rows={6} />}>
      <EmergencyView />
    </Suspense>
  );
}
