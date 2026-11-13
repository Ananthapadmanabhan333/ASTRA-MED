import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { SystemView } from "@/components/mission/system-view";

export const metadata: Metadata = { title: "System status" };

export default function SystemPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="System status"
        description="Health of every component (database, simulator, live stream, AI models, NASA sources, event orchestration, sandbox) and the database consistency checks."
      />
      <SystemView />
    </div>
  );
}
