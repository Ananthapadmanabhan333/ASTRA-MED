import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { SituationalTimeline } from "@/components/mission/situational-timeline";

export const metadata: Metadata = { title: "Situational awareness" };

export default function TimelinePage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Situational awareness"
        description="Every mission event on one UTC timeline: crew physiology, AI predictions, the habitat environment, radiation, real NASA solar activity, medical incidents and simulation control. Filter by crew member, category and time range."
      />
      <Suspense fallback={<LoadingState rows={8} />}>
        <SituationalTimeline />
      </Suspense>
    </div>
  );
}
