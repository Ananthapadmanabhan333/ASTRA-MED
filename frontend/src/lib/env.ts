/**
 * Public runtime configuration. Only non-secret values belong here: anything prefixed
 * NEXT_PUBLIC_ is inlined into the browser bundle.
 */
const DEFAULT_API = "http://localhost:8000";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API).replace(/\/$/, "");

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  `${API_URL.replace(/^http/, "ws")}/ws/health-monitoring`;
