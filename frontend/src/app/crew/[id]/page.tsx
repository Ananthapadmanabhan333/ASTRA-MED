import { Suspense } from "react";

import { LoadingState } from "@/components/data/states";
import { ProfileView } from "@/components/crew/profile-view";

export default function AstronautPage({ params }: PageProps<"/crew/[id]">) {
  return (
    <Suspense fallback={<LoadingState label="Loading crew member" rows={6} />}>
      {params.then(({ id }) => (
        <ProfileView id={decodeURIComponent(id)} />
      ))}
    </Suspense>
  );
}
