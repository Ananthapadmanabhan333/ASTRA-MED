import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { MedicalCenter } from "@/components/medical/medical-center";

export const metadata: Metadata = { title: "Medical intelligence" };

export default function MedicalPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Medical intelligence center"
        description="Cardiovascular, respiratory, thermoregulation, sleep, activity and radiation indicators per crew member, cross-system patterns, and explainable decision support for every significant alert."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <MedicalCenter />
      </Suspense>
    </div>
  );
}
