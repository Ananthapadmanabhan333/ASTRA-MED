import type { Metadata } from "next";

import { SystemView } from "@/components/mission/system-view";

export const metadata: Metadata = { title: "Deployment & System Health — ASTRA-MED" };

export default function SystemPage() {
  return <SystemView />;
}
