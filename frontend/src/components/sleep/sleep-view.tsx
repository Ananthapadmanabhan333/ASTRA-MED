"use client";

import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState, QueryView } from "@/components/data/states";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { useAstronauts, useSleep } from "@/lib/api/hooks";
import type { AstronautSummary, SleepSession } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt, hoursMinutes, utcDay, utcTime } from "@/lib/format";

// Night axis: 18:00 UTC on the night's date through 14:00 UTC next day (20 h).
const AXIS_START_H = 18;
const AXIS_SPAN_H = 20;
const TICKS = [18, 21, 24, 27, 30, 33, 36];

function position(iso: string, night: string) {
  const base = Date.parse(`${night}T00:00:00Z`) + AXIS_START_H * 3_600_000;
  return ((Date.parse(iso) - base) / (AXIS_SPAN_H * 3_600_000)) * 100;
}

function NightRow({ s, color }: { s: SleepSession; color: string }) {
  const schedL = position(s.scheduled_start, s.night);
  const schedW = position(s.scheduled_end, s.night) - schedL;
  const actL = position(s.start, s.night);
  const actW = position(s.end, s.night) - actL;
  return (
    <li className="grid grid-cols-[3.5rem_1fr_7.5rem] items-center gap-3 text-xs">
      <span className="text-ink-2">{utcDay(s.night)}</span>
      <div className="relative h-5" aria-hidden>
        <div className="absolute inset-y-0 rounded-sm border border-dashed border-ink-3/70" style={{ left: `${schedL}%`, width: `${schedW}%` }} />
        <div className="absolute inset-y-1 rounded-sm" style={{ left: `${actL}%`, width: `${actW}%`, background: color, opacity: 0.85 }} />
      </div>
      <span className="text-right tabular-nums">
        {hoursMinutes(s.duration_hours)}
        <span className="block text-ink-3">
          {s.onset_offset_minutes >= 0 ? "+" : ""}
          {fmt(s.onset_offset_minutes, 0)} min, {fmt(s.efficiency_pct, 0)}%
        </span>
      </span>
      <span className="sr-only">
        Scheduled {utcTime(s.scheduled_start, false)} to {utcTime(s.scheduled_end, false)}, slept{" "}
        {utcTime(s.start, false)} to {utcTime(s.end, false)} UTC.
      </span>
    </li>
  );
}

function CrewSleep({ a }: { a: AstronautSummary }) {
  const sleep = useSleep(a.id, 7);
  const color = crewColor(a.id);
  return (
    <Panel
      title={a.name}
      description={`${a.role}. Target ${a.sleep_target_hours} h from ${String(Math.floor(a.sleep_start_hour)).padStart(2, "0")}:${String(Math.round((a.sleep_start_hour % 1) * 60)).padStart(2, "0")} UTC.`}
    >
      {sleep.isPending ? (
        <LoadingState rows={4} />
      ) : sleep.error ? (
        <ErrorState error={sleep.error} onRetry={() => sleep.refetch()} />
      ) : (
        (() => {
          const nights = [...sleep.data].reverse();
          const avg = nights.reduce((t, n) => t + n.duration_hours, 0) / Math.max(1, nights.length);
          const debt = nights.reduce((t, n) => t + Math.max(0, a.sleep_target_hours - n.duration_hours), 0);
          const offset = nights.reduce((t, n) => t + n.onset_offset_minutes, 0) / Math.max(1, nights.length);
          return (
            <>
              <dl className="mb-4 grid grid-cols-3 gap-4">
                <div>
                  <dt className="text-xs text-ink-3">7-night average</dt>
                  <dd className={`readout text-2xl ${avg < a.sleep_target_hours - 0.75 ? "text-caution" : ""}`}>
                    {fmt(avg, 1)} <span className="text-xs text-ink-3">h</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">Sleep debt</dt>
                  <dd className="readout text-2xl">
                    {fmt(debt, 1)} <span className="text-xs text-ink-3">h</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-3">Mean onset drift</dt>
                  <dd className={`readout text-2xl ${Math.abs(offset) >= 45 ? "text-caution" : ""}`}>
                    {offset >= 0 ? "+" : ""}
                    {fmt(offset, 0)} <span className="text-xs text-ink-3">min</span>
                  </dd>
                </div>
              </dl>
              <div className="grid grid-cols-[3.5rem_1fr_7.5rem] gap-3 text-[11px] text-ink-3" aria-hidden>
                <span />
                <div className="relative h-4">
                  {TICKS.map((h) => (
                    <span key={h} className="absolute -translate-x-1/2" style={{ left: `${((h - AXIS_START_H) / AXIS_SPAN_H) * 100}%` }}>
                      {String(h % 24).padStart(2, "0")}
                    </span>
                  ))}
                </div>
                <span />
              </div>
              <ul className="space-y-1.5">
                {nights.map((n) => (
                  <NightRow key={n.night} s={n} color={color} />
                ))}
              </ul>
            </>
          );
        })()
      )}
    </Panel>
  );
}

export function SleepView() {
  const crew = useAstronauts();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-3 w-6 rounded-sm border border-dashed border-ink-3" aria-hidden /> Scheduled sleep window
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2 w-6 rounded-sm bg-telemetry/80" aria-hidden /> Actual sleep (crew colour)
        </span>
        <span>Right column: duration, onset offset from schedule, sleep efficiency.</span>
      </div>
      <QueryView query={crew}>
        {(data) => (
          <div className="grid gap-5 xl:grid-cols-2">
            {data.map((a) => (
              <CrewSleep key={a.id} a={a} />
            ))}
          </div>
        )}
      </QueryView>
      <SimulatedNote>Simulated sleep sessions; times in UTC (mission time).</SimulatedNote>
    </div>
  );
}
