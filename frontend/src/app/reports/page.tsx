import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { ReportsView } from "@/components/medical/reports-view";

export const metadata: Metadata = { title: "Reports & Incident Records — ASTRA-MED" };

export default function ReportsPage() {
  return (
    <Suspense fallback={<LoadingState rows={6} />}>
      <ReportsView />
    </Suspense>
  );
}
