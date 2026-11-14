import type { Metadata } from "next";

import { DataExplorerView } from "@/components/space/data-explorer-view";

export const metadata: Metadata = { title: "NASA Data Explorer — ASTRA-MED" };

export default function DataExplorerPage() {
  return <DataExplorerView />;
}
