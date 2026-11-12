"use client";

import { useState } from "react";

import { Panel } from "@/components/data/panel";
import { QueryView } from "@/components/data/states";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useModelPerformance } from "@/lib/api/hooks";
import type { ModelPerformance } from "@/lib/api/types";
import { fmt, utcDayTime } from "@/lib/format";

// The performance payload is the experiment's results.json; these are the parts shown here.
interface Clf { precision: number; recall: number; f1: number; auroc: number; auprc: number; false_alarm_rate: number }
interface EvKind { recall: number | null; events: number }
interface AnomalyModel {
  label: string; selected_features?: string; test: Clf;
  events: { event_recall: number; by_kind: Record<string, EvKind> };
  events_by_intensity: Record<string, EvKind>;
  operational: { false_warnings_per_crew_day: number; event_recall: number };
}
interface Reg { mae: number; rmse: number; coverage?: number }
interface FcModel { label: string; family: string; by_signal?: Record<string, Record<string, Reg>>; skill_vs_climatology?: Record<string, Record<string, number>> }

const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);
const SIGNALS = [
  ["heart_rate", "Heart rate", "bpm"],
  ["spo2", "SpO₂", "%"],
  ["respiratory_rate", "Resp. rate", "br/min"],
  ["temperature_c", "Temperature", "°C"],
] as const;

function AnomalyTable({ p }: { p: ModelPerformance }) {
  const an = p.anomaly as { models: Record<string, AnomalyModel>; ensemble: AnomalyModel; fixed_thresholds: AnomalyModel; test_windows: number; test_label_rate: number; target_false_alarm_rate: number };
  const rows = [...Object.values(an.models).filter((m) => m.test), an.ensemble, an.fixed_thresholds];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[56rem] text-left text-sm">
        <caption className="sr-only">Anomaly detection performance on the simulated test split</caption>
        <thead className="text-xs text-ink-2">
          <tr>
            {["Model", "Features", "Precision", "Recall", "F1", "AUROC", "False-alarm rate", "Events", "Gradual", "Subtle", "False warnings / crew-day"].map((h) => (
              <th key={h} scope="col" className="py-2 pr-4 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((m) => (
            <tr key={m.label} className="border-t border-bulkhead/60">
              <td className="py-2 pr-4">{m.label}</td>
              <td className="py-2 pr-4 text-xs text-ink-3">{m.selected_features?.replaceAll("_", " ") ?? "—"}</td>
              <td className="py-2 pr-4">{fmt(m.test.precision, 2)}</td>
              <td className="py-2 pr-4">{fmt(m.test.recall, 2)}</td>
              <td className="py-2 pr-4 font-medium">{fmt(m.test.f1, 2)}</td>
              <td className="py-2 pr-4">{fmt(m.test.auroc, 3)}</td>
              <td className="py-2 pr-4">{fmt(m.test.false_alarm_rate * 100, 2)}%</td>
              <td className="py-2 pr-4">{pct(m.events.event_recall)}</td>
              <td className="py-2 pr-4">{pct(m.events.by_kind.gradual?.recall)}</td>
              <td className="py-2 pr-4">{pct(m.events_by_intensity.subtle?.recall)}</td>
              <td className="py-2 pr-4">{fmt(m.operational.false_warnings_per_crew_day, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-ink-3">
        {an.test_windows.toLocaleString()} test windows, {pct(an.test_label_rate)} anomalous. Thresholds set on validation data for a{" "}
        {pct(an.target_false_alarm_rate)} window false-alarm rate. Feature sets chosen per detector on validation data. A warning needs 10
        minutes of consecutive flags.
      </p>
    </div>
  );
}

function ForecastTable({ p }: { p: ModelPerformance }) {
  const [signal, setSignal] = useState<string>("heart_rate");
  const fc = p.forecast as { models: Record<string, FcModel>; horizons_hours: number[]; interval_nominal_coverage: number };
  const unit = SIGNALS.find((s) => s[0] === signal)?.[2];
  return (
    <div className="space-y-3">
      <ToggleGroup type="single" size="sm" variant="outline" value={signal} onValueChange={(v) => v && setSignal(v)} aria-label="Signal">
        {SIGNALS.map(([v, l]) => (
          <ToggleGroupItem key={v} value={v} className="px-2.5 text-xs">{l}</ToggleGroupItem>
        ))}
      </ToggleGroup>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[48rem] text-left text-sm">
          <caption className="sr-only">Forecast error on the simulated test split</caption>
          <thead className="text-xs text-ink-2">
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Model</th>
              {fc.horizons_hours.map((h) => (
                <th key={h} scope="col" className="py-2 pr-4 font-medium">MAE {h} h <span className="text-ink-3">({unit})</span></th>
              ))}
              <th scope="col" className="py-2 pr-4 font-medium">90% coverage 1 h / 24 h</th>
              <th scope="col" className="py-2 pr-4 font-medium">Skill vs climatology 1 h / 24 h</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {Object.entries(fc.models).filter(([, m]) => m.by_signal).map(([name, m]) => {
              const s = m.by_signal![signal];
              const sk = m.skill_vs_climatology?.[signal];
              return (
                <tr key={name} className="border-t border-bulkhead/60">
                  <td className="py-2 pr-4">{m.label}</td>
                  {fc.horizons_hours.map((h) => (
                    <td key={h} className="py-2 pr-4">{fmt(s[`${h}h`].mae, signal === "temperature_c" ? 3 : 2)}</td>
                  ))}
                  <td className="py-2 pr-4">{pct(s["1h"].coverage)} / {pct(s["24h"].coverage)}</td>
                  <td className={`py-2 pr-4 ${sk && sk["1h"] > 0 ? "text-nominal" : "text-ink-2"}`}>
                    {sk ? `${fmt(sk["1h"], 2)} / ${fmt(sk["24h"], 2)}` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-3">
        Skill = 1 minus MAE relative to personal climatology (the baseline for the planned activity); positive is better. Intervals are
        split-conformal at {pct(fc.interval_nominal_coverage)} nominal coverage.
      </p>
    </div>
  );
}

export function ModelPerformanceView() {
  const q = useModelPerformance();
  return (
    <QueryView query={q}>
      {(p) => {
        const ds = p.dataset as { samples: number; crew: string[]; config: { days: number; seed: number }; events: { total: number; sudden: number; gradual: number; subtle: number }; fingerprint: string; real_data: string };
        return (
          <div className="space-y-5">
            <Panel title={`Model version ${p.version}`}>
              <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                <div><dt className="text-xs text-ink-3">Trained</dt><dd>{utcDayTime(p.created_at)} UTC in {fmt(p.runtime_seconds, 0)} s</dd></div>
                <div><dt className="text-xs text-ink-3">Code</dt><dd>commit {p.git_commit ?? "unknown"}</dd></div>
                <div><dt className="text-xs text-ink-3">Dataset</dt><dd>{ds.samples.toLocaleString()} simulated samples, {ds.crew.length} crew, {ds.config.days} days, seed {ds.config.seed}</dd></div>
                <div><dt className="text-xs text-ink-3">Injected events</dt><dd>{ds.events.total} ({ds.events.sudden} sudden, {ds.events.gradual} gradual, {ds.events.subtle} subtle)</dd></div>
              </dl>
              <p className="mt-3 text-xs text-ink-3">Real data: {ds.real_data}. Dataset fingerprint {ds.fingerprint}.</p>
            </Panel>
            <Panel raised title="Anomaly detection" description="Chronological test split, never used for training, calibration or model selection.">
              <AnomalyTable p={p} />
            </Panel>
            <Panel title="Forecasting" description="Mean absolute error by horizon against three baselines.">
              <ForecastTable p={p} />
            </Panel>
            <Panel title="Limitations">
              <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
                {p.limitations.map((l) => <li key={l}>{l}</li>)}
              </ul>
            </Panel>
            {p.report_markdown && (
              <details className="rounded-lg border border-bulkhead bg-hull/55 p-4">
                <summary className="cursor-pointer text-sm font-medium">Full evaluation report (markdown)</summary>
                <pre className="mt-3 max-h-[32rem] overflow-auto whitespace-pre-wrap text-xs text-ink-2">{p.report_markdown}</pre>
              </details>
            )}
          </div>
        );
      }}
    </QueryView>
  );
}
