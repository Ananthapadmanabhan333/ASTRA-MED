import { describe, expect, it } from "vitest";

import { classify, referenceLines } from "@/lib/thresholds";

import { RULES } from "./fixtures";

describe("classify", () => {
  it("returns null without rules or inside limits", () => {
    expect(classify("heart_rate", 130, "work", undefined)).toBeNull();
    expect(classify("heart_rate", 80, "work", RULES)).toBeNull();
  });

  it("flags caution and critical in both directions", () => {
    expect(classify("heart_rate", 125, "work", RULES)?.severity).toBe("caution");
    expect(classify("heart_rate", 150, "rest", RULES)?.severity).toBe("critical");
    expect(classify("spo2", 93.5, "work", RULES)).toMatchObject({ severity: "caution", limit: 94 });
    expect(classify("spo2", 88, "sleep", RULES)).toMatchObject({ severity: "critical", limit: 90 });
  });

  it("applies activity overrides like the backend", () => {
    expect(classify("heart_rate", 150, "exercise", RULES)).toBeNull();
    expect(classify("heart_rate", 175, "exercise", RULES)?.severity).toBe("caution");
    expect(classify("heart_rate", 42, "sleep", RULES)).toBeNull();
    expect(classify("heart_rate", 42, "work", RULES)?.severity).toBe("caution");
  });
});

describe("referenceLines", () => {
  it("uses resting caution limits", () => {
    expect(referenceLines("heart_rate", RULES).map((r) => r.value)).toEqual([120, 45]);
    expect(referenceLines("temperature_c", RULES)).toEqual([]);
  });
});
