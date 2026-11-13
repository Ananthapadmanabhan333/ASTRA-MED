"use client";

import { create } from "zustand";

const KEY = "astra-sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

interface ShellState {
  collapsed: boolean;
  mobileOpen: boolean;
  hydrated: boolean;
  hydrate: () => void;
  toggleCollapsed: () => void;
  setMobileOpen: (open: boolean) => void;
}

/** Sidebar state. The collapsed preference is a per-viewer convenience kept in localStorage. */
export const useShell = create<ShellState>((set, get) => ({
  collapsed: false,
  mobileOpen: false,
  hydrated: false,
  hydrate: () => {
    if (!get().hydrated) set({ collapsed: readCollapsed(), hydrated: true });
  },
  toggleCollapsed: () => {
    const collapsed = !get().collapsed;
    try {
      window.localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch {
      /* storage blocked: the toggle still works for this visit */
    }
    set({ collapsed });
  },
  setMobileOpen: (mobileOpen) => set({ mobileOpen }),
}));
