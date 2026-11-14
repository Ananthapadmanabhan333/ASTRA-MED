import type { Metadata } from "next";
import Link from "next/link";

import { CorrelationView } from "@/components/space/correlation-view";

export const metadata: Metadata = { title: "Environmental-Health Correlation — ASTRA-MED" };

export default function CorrelationPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Environmental-Health Correlation
        </h1>
        <p className="text-sm text-ink-2">
          Exploratory Pearson, Spearman, time-lagged and rolling correlations between space weather, ISS cabin environment and crew physiology
        </p>
      </div>

      {/* Space Environment Sub-navigation Tabs */}
      <div className="flex flex-wrap gap-1.5 border-b border-bulkhead pb-2.5">
        <Link
          href="/space"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Space Weather
        </Link>
        <Link
          href="/radiation"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Radiation
        </Link>
        <Link
          href="/space/iss"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          ISS Environment
        </Link>
        <span className="rounded-md bg-telemetry px-4 py-1.5 text-xs font-semibold text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]">
          Correlation
        </span>
      </div>

      <CorrelationView />
    </div>
  );
}
