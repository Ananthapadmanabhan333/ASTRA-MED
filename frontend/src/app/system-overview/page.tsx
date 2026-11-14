import type { Metadata } from "next";

import { SystemOverviewView } from "@/components/screens/system-overview";

export const metadata: Metadata = { title: "System Overview — ASTRA-MED" };

export default function SystemOverviewPage() {
  return <SystemOverviewView />;
}
