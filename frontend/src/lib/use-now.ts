"use client";

import { useEffect, useState } from "react";

/**
 * Current time, updated every `intervalMs`. Returns null until mounted so server-rendered
 * HTML never contains a clock value that would mismatch on hydration.
 */
export function useNow(intervalMs = 1000): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    // Deliberate: the first value must come from the client, after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
