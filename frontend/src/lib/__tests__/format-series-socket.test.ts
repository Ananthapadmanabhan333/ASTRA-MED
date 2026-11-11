import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, unwrap } from "@/lib/api/client";
import { duration, fmt, hoursMinutes, missionElapsed, relativeTime, utcTime } from "@/lib/format";
import { backoffDelay, LiveSocket } from "@/lib/live/socket";
import { mergeSeries } from "@/lib/series";

describe("format", () => {
  it("formats numbers and placeholders", () => {
    expect(fmt(36.789, 1)).toBe("36.8");
    expect(fmt(null)).toBe("—");
    expect(fmt(Number.NaN)).toBe("—");
  });

  it("formats mission time in UTC", () => {
    expect(utcTime("2026-11-09T06:04:05Z")).toBe("06:04:05");
    expect(missionElapsed(142 * 86400 + 3725)).toEqual({ day: 142, clock: "01:02:05" });
  });

  it("formats durations and relative times", () => {
    expect(duration(42)).toBe("42 s");
    expect(duration(150)).toBe("2 min 30 s");
    expect(duration(3720)).toBe("1 h 2 min");
    expect(hoursMinutes(6.5)).toBe("6 h 30 min");
    const now = Date.parse("2026-11-09T12:00:00Z");
    expect(relativeTime("2026-11-09T11:58:00Z", now)).toBe("2 min ago");
    expect(relativeTime("2026-11-09T11:59:58Z", now)).toBe("just now");
  });
});

describe("mergeSeries", () => {
  it("joins crew series on bucket timestamps with stable identity encoding", () => {
    const { rows, series } = mergeSeries({
      metric: "heart_rate",
      range: "1h",
      start: "2026-11-09T11:00:00Z",
      end: "2026-11-09T12:00:00Z",
      resolution_seconds: 60,
      data_source: "simulated",
      series: [
        { astronaut_id: "AST-02", name: "Lukas Brandt", points: [{ ts: "2026-11-09T11:00:30Z", value: 60 }] },
        {
          astronaut_id: "AST-01",
          name: "Maya Okafor",
          points: [
            { ts: "2026-11-09T11:01:30Z", value: 65 },
            { ts: "2026-11-09T11:00:30Z", value: 64 },
          ],
        },
      ],
    });
    expect(rows.map((r) => [r["AST-01"], r["AST-02"] ?? null])).toEqual([
      [64, 60],
      [65, null],
    ]);
    expect(series.map((s) => s.label)).toEqual(["Brandt", "Okafor"]);
    // Colour follows the crew member, not their position in the response.
    expect(series[0].color).toBe("var(--crew-2)");
    expect(series[1].color).toBe("var(--crew-1)");
  });
});

describe("unwrap", () => {
  it("maps transport failures to a network ApiError", async () => {
    await expect(unwrap(Promise.reject(new TypeError("fetch failed")))).rejects.toMatchObject({
      code: "network",
      status: 0,
    });
  });

  it("maps the backend error envelope", async () => {
    const response = new Response(null, { status: 404 });
    const err = await unwrap(
      Promise.resolve({ error: { error: { code: "not_found", message: "Astronaut AST-99 not found." } }, response }),
    ).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found", message: "Astronaut AST-99 not found." });
  });
});

class FakeSocket {
  static instances: FakeSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
}

describe("LiveSocket", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    FakeSocket.instances = [];
  });

  it("caps exponential backoff", () => {
    expect([1, 2, 3, 4, 5, 9].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 15000, 15000]);
  });

  it("goes live on messages and reconnects after a drop", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    const states: string[] = [];
    const messages: string[] = [];
    const socket = new LiveSocket("ws://test/ws", {
      onState: (s) => states.push(s),
      onMessage: (m) => messages.push(m.type),
    });
    socket.connect();
    const first = FakeSocket.instances[0];
    first.readyState = 1;
    first.onopen?.();
    first.onmessage?.({ data: JSON.stringify({ type: "pong", server_time: new Date().toISOString() }) });
    expect(states.at(-1)).toBe("live");
    expect(messages).toEqual(["pong"]);

    first.close();
    expect(states.at(-1)).toBe("reconnecting");
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.instances).toHaveLength(2);

    socket.close();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(2); // no retries after an intentional close
  });

  it("reports offline after repeated failures", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    const states: string[] = [];
    const socket = new LiveSocket("ws://test/ws", { onState: (s) => states.push(s), onMessage: () => {} });
    socket.connect();
    for (let i = 0; i < 4; i++) {
      FakeSocket.instances.at(-1)!.close();
      vi.advanceTimersByTime(20_000);
    }
    expect(states).toContain("offline");
    socket.close();
  });
});
