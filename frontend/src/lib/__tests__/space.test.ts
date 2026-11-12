import { describe, expect, it } from "vitest";

import { intersect, suggestPeriod } from "@/lib/periods";
import { inZone } from "@/lib/timezone";

describe("display timezone", () => {
  it("keeps UTC as UTC", () => {
    expect(inZone("2026-10-31T18:00:00Z", "UTC", "datetime", true)).toBe("31 Oct 2026, 18:00 UTC");
  });

  it("uses the offset valid at each instant, not today's", () => {
    // Houston was on daylight time (UTC-5) on 31 Oct 2026 and on standard time (UTC-6) on 11 Nov.
    expect(inZone("2026-10-31T18:00:00Z", "America/Chicago", "datetime", true)).toBe("31 Oct 2026, 13:00 GMT-5");
    expect(inZone("2026-11-11T21:21:00Z", "America/Chicago", "datetime", true)).toBe("11 Nov 2026, 15:21 GMT-6");
  });

  it("converts across the date line", () => {
    expect(inZone("2026-11-12T20:00:00Z", "Asia/Tokyo", "date")).toBe("13 Nov 2026");
  });
});

describe("correlation periods", () => {
  const now = Date.parse("2026-11-12T12:00:00Z");

  it("intersects ranges", () => {
    expect(intersect({ start: "2014-09-17", end: "2014-11-02" }, { start: "2014-09-20", end: "2014-11-01" }))
      .toEqual({ start: "2014-09-20", end: "2014-11-01" });
    expect(intersect({ start: "2014-01-01", end: "2014-02-01" }, { start: "2026-01-01", end: "2026-02-01" })).toBeNull();
  });

  it("finds the historical overlap even when the latest ranges do not overlap", () => {
    const donki = [{ start: "2014-09-17", end: "2014-11-02" }, { start: "2026-05-16", end: "2026-11-12" }];
    const iss = [{ start: "2014-09-20", end: "2014-11-01" }];
    expect(suggestPeriod(donki, iss, now)).toEqual({ start: "2014-09-20", end: "2014-11-01" });
  });

  it("treats series without coverage as the last 30 days", () => {
    const donki = [{ start: "2026-05-16", end: "2026-11-12" }];
    expect(suggestPeriod(donki, [], now)).toEqual({ start: "2026-10-13", end: "2026-11-12" });
  });
});
