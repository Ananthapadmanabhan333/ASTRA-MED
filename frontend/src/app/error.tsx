"use client";

import { ErrorState } from "@/components/data/states";

export default function RouteError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <ErrorState
      title="This view failed to render"
      error={error}
      onRetry={() => retry()}
      className="mx-auto max-w-2xl"
    />
  );
}
