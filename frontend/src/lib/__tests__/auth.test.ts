import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionInfo } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/store";

const fetchMock = vi.fn<(input: Request) => Promise<Response>>();
let api: typeof import("@/lib/api/client").api;
let routePermissions: typeof import("@/components/shell/nav").routePermissions;

const session: SessionInfo = {
  user: { id: "u1", username: "op", display_name: "Op", role: "mission_operator", role_label: "Mission operator", active: true, last_login_at: null },
  permissions: ["health:read", "simulation:control"],
  method: "session",
  csrf_token: "csrf-123",
  expires_at: null,
  auth_enabled: true,
};

beforeAll(async () => {
  // openapi-fetch captures fetch when the client is created, so stub it before importing.
  vi.stubGlobal("fetch", fetchMock);
  ({ api } = await import("@/lib/api/client"));
  ({ routePermissions } = await import("@/components/shell/nav"));
});

beforeEach(() => {
  fetchMock.mockReset();
  useAuth.getState().setSession(session);
});

describe("API client security", () => {
  it("sends the session cookie and the CSRF token only on writes", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await api.POST("/api/auth/logout");
    const write = fetchMock.mock.calls[0][0];
    expect(write.headers.get("X-CSRF-Token")).toBe("csrf-123");
    expect(write.credentials).toBe("include");

    fetchMock.mockResolvedValue(Response.json([]));
    await api.GET("/api/astronauts");
    const read = fetchMock.mock.calls[1][0];
    expect(read.headers.get("X-CSRF-Token")).toBeNull();
    expect(read.credentials).toBe("include");
  });

  it("treats a 401 as an ended session, except on the sign-in call itself", async () => {
    fetchMock.mockImplementation(async () => Response.json({ error: { code: "unauthenticated" } }, { status: 401 }));
    await api.POST("/api/auth/login", { body: { username: "x", password: "y" } });
    expect(useAuth.getState().status).toBe("signed_in");
    await api.GET("/api/astronauts");
    expect(useAuth.getState().status).toBe("signed_out");
    expect(useAuth.getState().reason).toBe("expired");
    expect(useAuth.getState().session).toBeNull();
  });
});

describe("route permissions", () => {
  it("maps pages to the permission that opens them", () => {
    expect(routePermissions("/twin")).toEqual(["health:read"]);
    expect(routePermissions("/crew/AST-01")).toEqual(["health:read"]);
    expect(routePermissions("/reports")).toEqual(["reports:read"]);
    expect(routePermissions("/assistant")).toEqual(["assistant:use"]);
    expect(routePermissions("/space/weather")).toEqual(["space:read"]);
    expect(routePermissions("/space/correlation")).toEqual(["health:read"]);
    expect(routePermissions("/admin")).toEqual(["users:manage", "audit:read"]);
    expect(routePermissions("/")).toEqual(["health:read"]);
  });
});
