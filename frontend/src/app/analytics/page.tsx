import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { AnalyticsView } from "@/components/mission/analytics-view";

export const metadata: Metadata = { title: "Mission analytics" };

export default function AnalyticsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Mission analytics"
        description="Trends across the mission: crew health, anomalies, sleep, the environment, radiation, model performance, alert frequency and how events are distributed. Export any range as CSV, JSON or a Markdown summary."
      />
      <AnalyticsView />
    </div>
  );
}
