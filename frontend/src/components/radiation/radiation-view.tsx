"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Panel } from "@/components/data/panel";
import { QueryView } from "@/components/data/states";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { useMissionStatus, useRadiation } from "@/lib/api/hooks";
import type { RadiationOverview } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt, utcDay } from "@/lib/format";

function CareerDose({ data }: { data: RadiationOverview }) {
  const limit = data.reference_career_limit_msv;
  const scale = limit * 1.1;
  return (
    <ul className="space-y-5">
      {data.crew.map((c) => {
        const prior = (c.prior_career_dose_msv / scale) * 100;
        const mission = (c.mission_dose_msv / scale) * 100;
        return (
          <li key={c.astronaut_id}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium">{c.name}</span>
              <span className="text-sm tabular-nums">
                <span className="readout text-xl">{fmt(c.career_dose_msv, 0)}</span>{" "}
                <span className="text-ink-3">mSv, {fmt(c.career_limit_pct, 0)}% of reference</span>
              </span>
            </div>
            <div className="relative mt-2 h-3 rounded-full bg-bulkhead/50" aria-hidden>
              <div className="absolute inset-y-0 left-0 flex gap-0.5 overflow-hidden rounded-full" style={{ width: `${prior + mission}%` }}>
                {c.prior_career_dose_msv > 0 && (
                  <div
                    className="h-full"
                    style={{
                      width: `${(prior / (prior + mission)) * 100}%`,
                      background: `repeating-linear-gradient(135deg, var(--ink-3) 0 3px, transparent 3px 6px)`,
                    }}
                  />
                )}
                <div className="h-full flex-1" style={{ background: crewColor(c.astronaut_id) }} />
              </div>
              <div className="absolute -top-1 -bottom-1 w-0.5 bg-caution" style={{ left: `${(limit / scale) * 100}%` }} />
            </div>
            <p className="mt-1.5 text-xs text-ink-3">
              Prior missions {fmt(c.prior_career_dose_msv, 0)} mSv (hatched), this mission {fmt(c.mission_dose_msv, 0)} mSv.
            </p>
          </li>
        );
      })}
      <li className="flex items-center gap-2 text-xs text-ink-2">
        <span className="inline-block h-3 w-0.5 bg-caution" aria-hidden /> {limit} mSv reference career limit
      </li>
    </ul>
  );
}

function DailyDose({ data }: { data: RadiationOverview }) {
  const days = new Map<string, { day: string; total: number; n: number; spe: boolean }>();
  for (const c of data.crew)
    for (const d of c.daily) {
      const e = days.get(d.day) ?? { day: d.day, total: 0, n: 0, spe: false };
      e.total += d.dose_msv;
      e.n += 1;
      e.spe ||= d.solar_particle_event;
      days.set(d.day, e);
    }
  const rows = [...days.values()]
    .sort((a, b) => a.day.localeCompare(b.day))
    .map((d, i, all) => ({ ...d, mean: d.total / d.n, partial: i === all.length - 1 }));
  const speDays = rows.filter((r) => r.spe);
  return (
    <div>
      <div className="h-56" role="img" aria-label="Crew mean daily dose over the last 30 days">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
            <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.55} vertical={false} />
            <XAxis
              dataKey="day"
              tickFormatter={(d: string) => utcDay(d)}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "var(--bulkhead)" }}
              minTickGap={24}
            />
            <YAxis tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
            <Tooltip
              cursor={{ fill: "var(--accent)", opacity: 0.4 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const r = payload[0].payload as (typeof rows)[number];
                return (
                  <div className="rounded-md border border-bulkhead bg-popover px-3 py-2 text-xs">
                    <p className="text-ink-2">{utcDay(r.day)}{r.partial ? " (today, so far)" : ""}</p>
                    <p className="font-medium tabular-nums">{fmt(r.mean, 2)} mSv crew mean</p>
                    {r.spe && <p className="text-caution">Solar particle event</p>}
                  </div>
                );
              }}
            />
            <Bar dataKey="mean" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.day} fill={r.spe ? "var(--caution)" : "var(--telemetry)"} fillOpacity={r.partial ? 0.45 : 0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-ink-2">
        Bars show the crew mean dose per UTC day; today is partial (faded).{" "}
        {speDays.length
          ? `Amber bars mark solar particle events: ${speDays.map((d) => utcDay(d.day)).join(", ")}.`
          : "No solar particle events in this window."}
      </p>
    </div>
  );
}

export function RadiationView() {
  const rad = useRadiation(30);
  const mission = useMissionStatus();
  const rate = mission.data?.habitat_dose_rate_msv_day;
  const elevated = rate !== undefined && rad.data && rate > rad.data.gcr_reference_rate_msv_day * 1.5;

  return (
    <QueryView query={rad}>
      {(data) => (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-3">
            <Panel raised title="Career dose against the reference limit" className="lg:col-span-2">
              <CareerDose data={data} />
            </Panel>
            <Panel title="Habitat dose rate now">
              <p className={`readout text-5xl font-semibold ${elevated ? "text-caution" : "text-telemetry"}`}>
                {fmt(rate, 2)}
                <span className="ml-1 text-base text-ink-3">mSv/day</span>
              </p>
              <p className="mt-2 text-sm text-ink-2">
                {elevated
                  ? "Elevated: a solar particle event scenario is running. Crew would shelter in the storm shelter."
                  : `At the galactic cosmic ray background of ${data.gcr_reference_rate_msv_day} mSv/day (reference value from MSL RAD cruise measurements).`}
              </p>
              <ul className="mt-4 space-y-1.5 text-sm">
                {data.crew.map((c) => (
                  <li key={c.astronaut_id} className="flex justify-between gap-2">
                    <span className="text-ink-2">{c.name}</span>
                    <span className="tabular-nums">{fmt(c.dose_rate_msv_day, 2)} mSv/day</span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-ink-3">Per-person rates differ with sleep-station shielding.</p>
            </Panel>
          </div>
          <Panel title="Daily dose, last 30 days">
            <DailyDose data={data} />
          </Panel>
          <SimulatedNote>{data.reference_note}</SimulatedNote>
        </div>
      )}
    </QueryView>
  );
}
