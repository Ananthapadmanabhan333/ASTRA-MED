import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { OverviewView } from "@/components/medical/overview-view";

export const metadata: Metadata = { title: "Mission health overview" };

export default function OverviewPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Mission health overview"
        description="Crew summaries, active alerts, incidents, trends, environmental context and a mission summary, filtered by crew member and period."
      />
      <OverviewView />
    </div>
  );
}
