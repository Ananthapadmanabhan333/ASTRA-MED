import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { DatasetDetailsView } from "@/components/space/dataset-details-view";

export const metadata: Metadata = { title: "Dataset Details — ASTRA-MED" };

export default function DatasetDetailsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading Dataset Details" rows={5} />}>
      <DatasetDetailsView />
    </Suspense>
  );
}
