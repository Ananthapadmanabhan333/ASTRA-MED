import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { CorrelationView } from "@/components/space/correlation-view";

export const metadata: Metadata = { title: "Environment-health correlation" };

export default function CorrelationPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Environment-health correlation"
        description="Exploratory statistics between space-weather indicators, ISS environment measurements and crew physiology: Pearson, Spearman, time-lagged, rolling and cross-correlation."
      />
      <CorrelationView />
    </div>
  );
}
