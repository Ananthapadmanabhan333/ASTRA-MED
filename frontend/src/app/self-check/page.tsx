import type { Metadata } from "next";
import { Suspense } from "react";

import { SelfCheckView } from "@/components/crew/self-check-view";
import { PageHeader } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";

export const metadata: Metadata = { title: "Crew self-check" };

export default function SelfCheckPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Crew self-check"
        description="The astronaut's own view: body systems at a glance, glucose, mood and symptom check-ins, today's checks and when to involve the flight surgeon."
      />
      <Suspense fallback={<LoadingState rows={6} />}>
        <SelfCheckView />
      </Suspense>
    </div>
  );
}
