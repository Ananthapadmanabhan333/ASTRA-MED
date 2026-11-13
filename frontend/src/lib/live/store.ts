"use client";

import { create } from "zustand";

import type { WsServerMessage } from "@/lib/api/types";

import { applyMessage, initialLive, type LiveData } from "./reducer";

export type ConnectionState = "connecting" | "live" | "stale" | "reconnecting" | "offline";

interface LiveStore extends LiveData {
  connection: ConnectionState;
  attempts: number;
  receive: (msg: WsServerMessage, at: number) => void;
  setConnection: (state: ConnectionState, attempts?: number) => void;
  markRead: () => void;
}

export const useLive = create<LiveStore>((set) => ({
  ...initialLive(),
  connection: "connecting",
  attempts: 0,
  receive: (msg, at) => set((s) => applyMessage(s, msg, at)),
  setConnection: (connection, attempts) =>
    set((s) => ({ connection, attempts: attempts ?? s.attempts })),
  markRead: () => set({ unread: 0 }),
}));
