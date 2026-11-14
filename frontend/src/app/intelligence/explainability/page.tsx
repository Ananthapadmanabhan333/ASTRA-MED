import { Suspense } from "react";

import { ExplainabilityWorkbench } from "@/components/ai/explainability-workbench";
import { LoadingState } from "@/components/data/states";

export default function ExplainabilityPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading AI Explainability Workbench" rows={6} />}>
      <ExplainabilityWorkbench />
    </Suspense>
  );
}
