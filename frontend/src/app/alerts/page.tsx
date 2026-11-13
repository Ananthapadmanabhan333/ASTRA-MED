import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { AlertCenter } from "@/components/mission/alert-center";

export const metadata: Metadata = { title: "Alert centre" };

export default function AlertsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Alert centre"
        description="One lifecycle for alerts from every module: physiological rules, AI models, NASA space weather and the simulated habitat. Experimental AI output is labelled and never ranked above P3. Limits are prototype test values, not clinical criteria."
      />
      <Suspense fallback={<LoadingState rows={8} />}>
        <AlertCenter />
      </Suspense>
    </div>
  );
}
