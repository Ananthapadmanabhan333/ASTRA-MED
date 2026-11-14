import { Suspense } from "react";

import { PredictionComparisonView } from "@/components/ai/prediction-comparison-view";
import { LoadingState } from "@/components/data/states";

export default function PredictionComparisonPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading Prediction Comparison Studio" rows={6} />}>
      <PredictionComparisonView />
    </Suspense>
  );
}
