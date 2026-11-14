import type { Metadata } from "next";

import { SpaceWeatherView } from "@/components/space/space-weather-view";

export const metadata: Metadata = { title: "Space Weather — ASTRA-MED" };

export default function SpaceWeatherPage() {
  return <SpaceWeatherView />;
}
