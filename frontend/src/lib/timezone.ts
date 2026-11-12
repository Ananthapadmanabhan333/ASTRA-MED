"use client";

import { create } from "zustand";

/**
 * Display timezone. Data are UTC end to end (API, storage, computation); only rendering uses
 * the selected zone. UTC is the default because mission time on the ISS is UTC.
 */
export const ZONES = [
  { value: "UTC", label: "UTC (mission time)" },
  { value: "America/Chicago", label: "Houston (MCC-H)" },
  { value: "Europe/Moscow", label: "Moscow (TsUP)" },
  { value: "Europe/Berlin", label: "Cologne (EAC)" },
  { value: "Asia/Tokyo", label: "Tsukuba (JAXA)" },
  { value: "local", label: "This browser" },
] as const;

export type ZoneValue = (typeof ZONES)[number]["value"];
const STORAGE_KEY = "astra.displayZone";

function initialZone(): ZoneValue {
  try {
    const v = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    if (v && ZONES.some((z) => z.value === v)) return v as ZoneValue;
  } catch {
    /* storage unavailable: keep UTC */
  }
  return "UTC";
}

interface ZoneState {
  zone: ZoneValue;
  setZone: (z: ZoneValue) => void;
}

export const useDisplayZone = create<ZoneState>((set) => ({
  zone: "UTC",
  setZone: (zone) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, zone);
    } catch {
      /* ignore */
    }
    set({ zone });
  },
}));

let hydrated = false;
/** Read the stored zone once on the client (after hydration, so server and client HTML match). */
export function hydrateZone() {
  if (hydrated) return;
  hydrated = true;
  const z = initialZone();
  if (z !== "UTC") useDisplayZone.setState({ zone: z });
}

function resolve(zone: ZoneValue): string | undefined {
  return zone === "local" ? undefined : zone;
}

const cache = new Map<string, Intl.DateTimeFormat>();
function formatter(zone: ZoneValue, kind: "datetime" | "date" | "time", withZone = false): Intl.DateTimeFormat {
  const key = `${zone}|${kind}|${withZone}`;
  let f = cache.get(key);
  if (!f) {
    const opts: Intl.DateTimeFormatOptions =
      kind === "date"
        ? { day: "2-digit", month: "short", year: "numeric" }
        : kind === "time"
          ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }
          : { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
    f = new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: resolve(zone), ...(withZone ? { timeZoneName: "short" } : {}) });
    cache.set(key, f);
  }
  return f;
}

/** Current abbreviation of a zone (for headings). For a specific instant use inZone(..., withZone). */
export function zoneLabel(zone: ZoneValue): string {
  if (zone === "UTC") return "UTC";
  if (zone === "local") return "local";
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, timeZoneName: "short" }).formatToParts(new Date());
  return parts.find((p) => p.type === "timeZoneName")?.value ?? zone;
}

/** Format a UTC instant in a display zone. ``withZone`` appends the zone name valid at that instant
 * (so a date in summer shows daylight time even when viewed in winter). */
export function inZone(iso: string | number | Date, zone: ZoneValue, kind: "datetime" | "date" | "time" = "datetime",
                       withZone = false): string {
  return formatter(zone, kind, withZone && kind !== "date").format(new Date(iso));
}
