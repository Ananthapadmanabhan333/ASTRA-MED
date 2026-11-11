import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { InsightsView } from "@/components/insights/insights-view";

export const metadata: Metadata = { title: "Insights" };

export default function InsightsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Insights"
        description="Patterns across sleep, cardiovascular trends, alerts, countermeasures and radiation that merit a closer look."
      />
      <InsightsView />
    </div>
  );
}
