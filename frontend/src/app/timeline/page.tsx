import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { SituationalTimeline } from "@/components/mission/situational-timeline";

export const metadata: Metadata = { title: "Mission Timeline — ASTRA-MED" };

export default function TimelinePage() {
  return (
    <Suspense fallback={<LoadingState rows={8} />}>
      <SituationalTimeline />
    </Suspense>
  );
}
