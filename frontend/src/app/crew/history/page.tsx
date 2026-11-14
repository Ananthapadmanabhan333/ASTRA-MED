import type { Metadata } from "next";

import { HealthHistoryView } from "@/components/crew/health-history-view";

export const metadata: Metadata = { title: "Detailed Astronaut Health History" };

export default function CrewHistoryPage() {
  return <HealthHistoryView />;
}
