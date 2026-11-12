import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { IssEnvironmentView } from "@/components/space/iss-environment-view";

export const metadata: Metadata = { title: "ISS environment" };

export default function IssEnvironmentPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="ISS environment"
        description="Cabin temperature, relative humidity, CO₂ and radiation dosimetry measured during historical ISS missions, from NASA's Environmental Data App."
      />
      <IssEnvironmentView />
    </div>
  );
}
