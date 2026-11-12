import createClient from "openapi-fetch";

import { currentCsrf, useAuth } from "@/lib/auth/store";
import { API_URL } from "@/lib/env";

import type { paths } from "./schema";

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Typed REST client generated from the backend's OpenAPI contract. Requests carry the HttpOnly
 * session cookie (credentials: include); writes also carry the session's CSRF token.
 */
export const api = createClient<paths>({ baseUrl: API_URL, credentials: "include" });

api.use({
  onRequest({ request }) {
    const csrf = currentCsrf();
    if (csrf && UNSAFE.has(request.method)) request.headers.set("X-CSRF-Token", csrf);
    return request;
  },
  onResponse({ request, response }) {
    // A 401 outside the sign-in endpoints means the session ended (expired, revoked or idle).
    if (response.status === 401 && !new URL(request.url).pathname.startsWith("/api/auth/login")) {
      const { status, signedOut } = useAuth.getState();
      if (status === "signed_in") signedOut("expired");
    }
    return response;
  },
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isNetwork() {
    return this.code === "network";
  }

  get isForbidden() {
    return this.status === 403;
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/** Resolve an openapi-fetch call to its data, or throw a readable ApiError. */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError(
      `Can't reach the monitoring API at ${API_URL}. Start the backend, then retry.`,
      0,
      "network",
    );
  }
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) {
    const envelope = (error ?? {}) as { error?: { code?: string; message?: string; details?: unknown } };
    throw new ApiError(
      envelope.error?.message ?? `The API returned ${response.status}.`,
      response.status,
      envelope.error?.code ?? "http_error",
      envelope.error?.details,
    );
  }
  return data as T;
}

/** Fetch a binary resource (e.g. a PDF) with the session cookie. */
export async function fetchBlob(path: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { credentials: "include" });
  } catch {
    throw new ApiError(`Can't reach the monitoring API at ${API_URL}.`, 0, "network");
  }
  if (!response.ok) {
    if (response.status === 401) useAuth.getState().signedOut("expired");
    throw new ApiError(`The API returned ${response.status}.`, response.status, "http_error");
  }
  return response.blob();
}
