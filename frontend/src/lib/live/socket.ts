import type { WsServerMessage } from "@/lib/api/types";

import type { ConnectionState } from "./store";

export interface SocketHandlers {
  onMessage: (msg: WsServerMessage, receivedAt: number) => void;
  onState: (state: ConnectionState, attempts: number) => void;
}

const STALE_AFTER_MS = 5_000;
const PING_EVERY_MS = 20_000;
const MAX_BACKOFF_MS = 15_000;
const OFFLINE_AFTER_ATTEMPTS = 3;

export function backoffDelay(attempt: number): number {
  return Math.min(MAX_BACKOFF_MS, 1000 * 2 ** Math.max(0, attempt - 1));
}

/**
 * Reconnecting WebSocket client for /ws/health-monitoring.
 * connecting → live → (stale) → reconnecting → offline, retrying with capped backoff.
 */
export class LiveSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private closedByUser = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private pinger: ReturnType<typeof setInterval> | null = null;
  private lastMessageAt = 0;

  constructor(
    private readonly url: string,
    private readonly handlers: SocketHandlers,
  ) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
  }

  private open(): void {
    this.handlers.onState(this.attempts === 0 ? "connecting" : this.retryState(), this.attempts);
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch {
      this.scheduleRetry();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.lastMessageAt = Date.now();
      this.startTimers();
    };
    ws.onmessage = (event) => {
      const now = Date.now();
      this.lastMessageAt = now;
      let msg: WsServerMessage;
      try {
        msg = JSON.parse(event.data as string) as WsServerMessage;
      } catch {
        return;
      }
      if (msg.type === "hello") {
        this.attempts = 0;
      }
      this.handlers.onState("live", 0);
      this.handlers.onMessage(msg, now);
    };
    ws.onclose = () => {
      this.clearTimers();
      if (this.ws === ws) this.ws = null;
      if (!this.closedByUser) this.scheduleRetry();
    };
    ws.onerror = () => ws.close();
  }

  private retryState(): ConnectionState {
    return this.attempts > OFFLINE_AFTER_ATTEMPTS ? "offline" : "reconnecting";
  }

  private scheduleRetry(): void {
    this.attempts += 1;
    this.handlers.onState(this.retryState(), this.attempts);
    this.retryTimer = setTimeout(() => this.open(), backoffDelay(this.attempts));
  }

  private startTimers(): void {
    this.clearTimers();
    this.watchdog = setInterval(() => {
      const silent = Date.now() - this.lastMessageAt;
      if (silent > STALE_AFTER_MS * 2) {
        this.ws?.close(); // force a reconnect
      } else if (silent > STALE_AFTER_MS) {
        this.handlers.onState("stale", this.attempts);
      }
    }, 1000);
    this.pinger = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ action: "ping" }));
    }, PING_EVERY_MS);
  }

  private clearTimers(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.watchdog) clearInterval(this.watchdog);
    if (this.pinger) clearInterval(this.pinger);
    this.retryTimer = this.watchdog = this.pinger = null;
  }
}
