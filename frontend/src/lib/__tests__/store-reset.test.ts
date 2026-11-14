import { describe, expect, it } from "vitest";

import { clearEcg, ecgChunks, pushEcg } from "@/lib/live/ecg-buffer";
import { initialLive } from "@/lib/live/reducer";
import { useLive } from "@/lib/live/store";

import { alert, reading } from "./fixtures";

describe("sign-out clean-up", () => {
  it("reset() drops every reading, alert and counter from the live store", () => {
    const s = useLive.getState();
    s.setConnection("live", 0);
    s.receive(
      {
        type: "hello",
        server_time: "2026-11-09T11:00:00Z",
        tick_seconds: 1,
        ecg_sample_rate_hz: 125,
        astronaut_ids: ["AST-01"],
        latest: [reading()],
        open_alerts: [alert()],
        active_scenarios: [],
        data_source: "simulated",
      },
      Date.parse("2026-11-09T11:00:00Z"),
    );
    expect(Object.keys(useLive.getState().latest)).toEqual(["AST-01"]);

    useLive.getState().reset();
    const after = useLive.getState();
    const { connection, attempts, ...data } = after;
    expect(connection).toBe("connecting");
    expect(attempts).toBe(0);
    for (const [key, value] of Object.entries(initialLive())) {
      expect(data[key as keyof typeof data]).toEqual(value);
    }
  });

  it("clearEcg() empties the sample buffer", () => {
    pushEcg({ astronaut_id: "AST-01", start: "2026-11-09T11:00:00Z", sample_rate_hz: 125, values_mv: [0, 0.1, 0.2] });
    expect(ecgChunks("AST-01")).toHaveLength(1);
    clearEcg();
    expect(ecgChunks("AST-01")).toHaveLength(0);
  });
});
