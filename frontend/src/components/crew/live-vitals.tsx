"use client";

import { ThresholdNotice } from "@/components/data/states";
import { Readout } from "@/components/vitals/readout";
import { Sparkline } from "@/components/vitals/sparkline";
import { useThresholds } from "@/lib/api/hooks";
import type { VitalReading } from "@/lib/api/types";
import { relativeTime, utcTime } from "@/lib/format";
import { pickReading } from "@/lib/live/freshness";
import { useLive } from "@/lib/live/store";
import { ACTIVITY_LABEL } from "@/lib/metrics";
import { classify } from "@/lib/thresholds";
import { useNow } from "@/lib/use-now";

type Tile = {
  key: "heart_rate" | "spo2" | "systolic" | "temperature_c" | "respiratory_rate" | "activity_met";
  label: string;
  unit: string;
  decimals: number;
};

const TILES: Tile[] = [
  { key: "heart_rate", label: "Heart rate", unit: "bpm", decimals: 0 },
  { key: "spo2", label: "SpO₂", unit: "%", decimals: 1 },
  { key: "systolic", label: "Blood pressure", unit: "mmHg", decimals: 0 },
  { key: "temperature_c", label: "Body temperature", unit: "°C", decimals: 2 },
  { key: "respiratory_rate", label: "Respiratory rate", unit: "br/min", decimals: 0 },
  { key: "activity_met", label: "Activity", unit: "MET", decimals: 1 },
];

/** Six live tiles: current value, breach state and a 3-minute sparkline. */
export function LiveVitals({ astronautId, fallback }: { astronautId: string; fallback: VitalReading | null }) {
  const live = useLive((s) => s.latest[astronautId]);
  const trail = useLive((s) => s.trails[astronautId]);
  const connection = useLive((s) => s.connection);
  const rules = useThresholds();
  const now = useNow(5_000);
  // The stored reading wins whenever the stream is not live or has nothing newer.
  const picked = pickReading(live, fallback, connection);
  const r = picked.reading ?? undefined;

  return (
    <div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-bulkhead bg-bulkhead sm:grid-cols-3 xl:grid-cols-6">
        {TILES.map((t) => {
          const value = r?.[t.key];
          const breach = r && t.key !== "activity_met" ? classify(t.key, r[t.key], r.activity_state, rules.data) : null;
          const tone = breach?.severity === "critical" ? "text-critical" : breach ? "text-caution" : "text-telemetry/70";
          return (
            <div key={t.key} className="bg-hull p-4">
              <Readout
                label={t.label}
                value={value}
                unit={t.key === "activity_met" ? undefined : t.unit}
                decimals={t.decimals}
                size="lg"
                breach={breach}
                accent={t.key === "heart_rate"}
                secondary={
                  t.key === "systolic" && r
                    ? `${r.systolic}/${r.diastolic}`
                    : t.key === "activity_met" && r
                      ? ACTIVITY_LABEL[r.activity_state]
                      : undefined
                }
              />
              <div className="mt-2 flex items-end justify-between gap-2">
                <Sparkline points={trail} metric={t.key} className={tone} />
                {t.key === "activity_met" && r && (
                  <span className="text-xs text-ink-3 tabular-nums">{r.activity_met.toFixed(1)} MET</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <ThresholdNotice rules={rules} className="mt-2" />
      <p className="mt-2 text-xs text-ink-3">
        {!r
          ? "No readings yet."
          : picked.live
            ? `Live, last reading ${utcTime(r.ts)} UTC.`
            : `Last reading ${utcTime(r.ts)} UTC${now ? ` (${relativeTime(r.ts, now)})` : ""}; ${
                connection === "live" ? "no newer reading on the live stream" : "live stream not connected"
              }.`}{" "}
        Rhythm from synthetic ECG: {r ? r.rhythm : "no reading"}
        {r?.hrv_rmssd_ms ? `, RMSSD ${r.hrv_rmssd_ms.toFixed(0)} ms` : ""}.
      </p>
    </div>
  );
}
