import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { AssistantView } from "@/components/medical/assistant-view";

export const metadata: Metadata = { title: "AI medical assistant" };

export default function AssistantPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="AI medical assistant"
        description="Source-grounded answers about simulated crew data, ASTRA-MED documentation and NASA open data, with a citation for every statement."
      />
      <AssistantView />
    </div>
  );
}
