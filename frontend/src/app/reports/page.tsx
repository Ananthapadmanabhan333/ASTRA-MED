import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { ReportsView } from "@/components/medical/reports-view";

export const metadata: Metadata = { title: "Incident reports" };

export default function ReportsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Incident reports"
        description="Structured reports with mission information, measurements, baseline comparison, environment, anomaly results, model explanation, data-quality limitations, review status and PDF export."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <ReportsView />
      </Suspense>
    </div>
  );
}
