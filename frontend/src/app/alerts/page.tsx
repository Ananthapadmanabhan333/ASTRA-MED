import type { Metadata } from "next";

import { AlertsConsole } from "@/components/alerts/alerts-console";
import { PageHeader } from "@/components/data/panel";

export const metadata: Metadata = { title: "Alerts" };

export default function AlertsPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Alerts and incidents"
        description="Every alert from threshold rules, rhythm checks and personal-baseline deviation, with its full lifecycle. Limits are prototype test values, not clinical criteria."
      />
      <AlertsConsole />
    </div>
  );
}
