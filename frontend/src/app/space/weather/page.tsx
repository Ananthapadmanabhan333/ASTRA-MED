import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { SpaceWeatherView } from "@/components/space/space-weather-view";

export const metadata: Metadata = { title: "Space weather" };

export default function SpaceWeatherPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Space weather"
        description="Solar flares, coronal mass ejections, solar energetic particle events, geomagnetic storms and radiation belt enhancements from NASA's DONKI. Real observations from near Earth, not crew measurements."
      />
      <SpaceWeatherView />
    </div>
  );
}
