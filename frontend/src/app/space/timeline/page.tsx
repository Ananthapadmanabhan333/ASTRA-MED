import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { MissionTimelineView } from "@/components/space/mission-timeline-view";

export const metadata: Metadata = { title: "Mission timeline" };

export default function MissionTimelinePage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Mission timeline"
        description="Crew physiology, alerts and AI detections on one time axis with NASA space-weather events, or a historical ISS mission with its measured environment."
      />
      <MissionTimelineView />
    </div>
  );
}
