import type { Metadata } from "next";

import { SpaceWeatherView } from "@/components/space/space-weather-view";

export const metadata: Metadata = { title: "Space Environment — ASTRA-MED" };

export default function SpaceEnvironmentPage() {
  return <SpaceWeatherView />;
}
