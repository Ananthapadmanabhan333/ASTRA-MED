/** Formatting helpers. Mission time is UTC throughout, as on the ISS. */

export function fmt(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(decimals);
}

const timeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

const shortTimeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "2-digit", month: "short" });

export function utcTime(iso: string | number, withSeconds = true): string {
  const d = new Date(iso);
  return (withSeconds ? timeFmt : shortTimeFmt).format(d);
}

export function utcDay(iso: string | number): string {
  return dayFmt.format(new Date(iso));
}

export function utcDayTime(iso: string | number): string {
  return `${utcDay(iso)}, ${utcTime(iso, false)}`;
}

export function relativeTime(iso: string, now: number): string {
  const diff = Math.round((now - Date.parse(iso)) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff} s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem ? `${m} min ${rem} s` : `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** Mission elapsed time: whole days plus HH:MM:SS. */
export function missionElapsed(seconds: number): { day: number; clock: string } {
  const s = Math.max(0, Math.floor(seconds));
  const day = Math.floor(s / 86400);
  const rest = s % 86400;
  const hh = String(Math.floor(rest / 3600)).padStart(2, "0");
  const mm = String(Math.floor((rest % 3600) / 60)).padStart(2, "0");
  const ss = String(rest % 60).padStart(2, "0");
  return { day, clock: `${hh}:${mm}:${ss}` };
}

export function hoursMinutes(hours: number): string {
  const total = Math.round(hours * 60);
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")} min`;
}
