import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { DataExplorerView } from "@/components/space/data-explorer-view";

export const metadata: Metadata = { title: "NASA data explorer" };

export default function DataExplorerPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="NASA data explorer"
        description="Every external dataset ASTRA-MED uses: where it comes from, what it measures, how complete and fresh it is, and the terms it is published under."
      />
      <DataExplorerView />
    </div>
  );
}
