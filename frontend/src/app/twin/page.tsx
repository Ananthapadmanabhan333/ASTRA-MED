import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { TwinView } from "@/components/medical/twin-view";

export const metadata: Metadata = { title: "Digital twin" };

export default function TwinPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Astronaut digital twin"
        description="Profile, health timeline, baseline against current values, longitudinal trends and changes across mission stages."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <TwinView />
      </Suspense>
    </div>
  );
}
