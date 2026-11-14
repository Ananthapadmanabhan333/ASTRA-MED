import type { Metadata } from "next";

import { AnalyticsView } from "@/components/mission/analytics-view";

export const metadata: Metadata = { title: "Analytics & Research — ASTRA-MED" };

export default function AnalyticsPage() {
  return <AnalyticsView />;
}
