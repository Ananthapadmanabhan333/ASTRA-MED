import type { Metadata } from "next";

import { RadiationView } from "@/components/radiation/radiation-view";
import { RadiationIntelligence } from "@/components/space/radiation-intel";

export const metadata: Metadata = { title: "Radiation Intelligence — ASTRA-MED" };

export default function RadiationPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Radiation Intelligence
        </h1>
        <p className="text-sm text-ink-2">Radiation events and mission exposure analysis</p>
      </div>
      <RadiationView />
      <RadiationIntelligence />
    </div>
  );
}
