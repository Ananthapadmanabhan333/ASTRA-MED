import type { Metadata } from "next";

import { ExperimentManagementView } from "@/components/screens/experiment-management-view";

export const metadata: Metadata = { title: "Experiment Management — ASTRA-MED" };

export default function ExperimentManagementPage() {
  return <ExperimentManagementView />;
}
