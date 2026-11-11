"use client";

import { ErrorState } from "@/components/data/states";

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState
      title="This view failed to render"
      error={error}
      onRetry={reset}
      className="mx-auto max-w-2xl"
    />
  );
}
