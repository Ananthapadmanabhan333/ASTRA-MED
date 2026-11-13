import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { ProfileView } from "@/components/crew/profile-view";
import { CrewProfileNav } from "@/components/mission/crew-profile-nav";

export default function AstronautPage({ params }: PageProps<"/crew/[id]">) {
  return (
    <Suspense fallback={<LoadingState label="Loading crew member" rows={6} />}>
      {params.then(({ id }) => {
        const aid = decodeURIComponent(id);
        return (
          <div className="space-y-4">
            <CrewProfileNav id={aid} />
            <ProfileView id={aid} />
          </div>
        );
      })}
    </Suspense>
  );
}
