import createClient from "openapi-fetch";

import { API_URL } from "@/lib/env";

import type { paths } from "./schema";

/** Typed REST client generated from the backend's OpenAPI contract. */
export const api = createClient<paths>({ baseUrl: API_URL });

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
