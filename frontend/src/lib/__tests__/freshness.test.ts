import { describe, expect, it } from "vitest";

import { sameSubject } from "@/lib/api/placeholder";
import { pickReading, preferLive } from "@/lib/live/freshness";

import { reading } from "./fixtures";

const OLD = "2026-11-09T11:00:00Z";
const NEW = "2026-11-09T11:00:05Z";

describe("preferLive", () => {
  it("uses the live reading only while the socket is live", () => {
    expect(preferLive("live", NEW, OLD)).toBe(true);
    for (const state of ["connecting", "stale", "reconnecting", "offline"] as const) {
      expect(preferLive(state, NEW, OLD)).toBe(false);
    }
  });

  it("lets a newer REST value win over an older live reading", () => {
    expect(preferLive("live", OLD, NEW)).toBe(false);
    expect(preferLive("live", OLD, OLD)).toBe(true); // same reading
  });

  it("accepts a live reading when the REST time is unknown, never a missing one", () => {
    expect(preferLive("live", NEW, null)).toBe(true);
    expect(preferLive("live", undefined, OLD)).toBe(false);
  });
});

describe("pickReading", () => {
  const live = reading({ ts: NEW, heart_rate: 80 });
  const rest = reading({ ts: OLD, heart_rate: 70 });

  it("shows the newer live reading while connected", () => {
    expect(pickReading(live, rest, "live")).toEqual({ reading: live, live: true });
  });

  it("falls back to the REST reading after a disconnect, even if the frozen one is newer", () => {
    expect(pickReading(live, rest, "reconnecting")).toEqual({ reading: rest, live: false });
  });

  it("prefers a fresher REST reading over a stale live one", () => {
    const fresher = reading({ ts: "2026-11-09T11:00:09Z", heart_rate: 72 });
    expect(pickReading(live, fresher, "live")).toEqual({ reading: fresher, live: false });
  });

  it("keeps the last live reading, marked not live, when there is no REST reading", () => {
    expect(pickReading(live, null, "offline")).toEqual({ reading: live, live: false });
    expect(pickReading(undefined, null, "live")).toEqual({ reading: null, live: false });
  });
});

describe("sameSubject", () => {
  type F = { astronaut_id?: string; context?: string; hours?: number };
  const fields = ["astronaut_id", "context"] as const;

  it("matches when only non-identity filters differ", () => {
    expect(sameSubject<F>({ astronaut_id: "AST-01", context: "operations", hours: 24 }, { astronaut_id: "AST-01", context: "operations", hours: 72 }, fields)).toBe(true);
  });

  it("rejects a different crew member or context", () => {
    expect(sameSubject<F>({ astronaut_id: "AST-01" }, { astronaut_id: "AST-02" }, fields)).toBe(false);
    expect(sameSubject<F>({ context: "operations" }, { context: "simulation" }, fields)).toBe(false);
    expect(sameSubject<F>({}, { astronaut_id: "AST-01" }, fields)).toBe(false);
  });

  it("treats missing and undefined as the same, and no previous query as no match", () => {
    expect(sameSubject<F>({ astronaut_id: undefined }, {}, fields)).toBe(true);
    expect(sameSubject<F>(undefined, {}, fields)).toBe(false);
  });
});
