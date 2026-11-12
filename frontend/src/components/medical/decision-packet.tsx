"use client";

import { ClipboardPlus, Siren } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { TrendChart, type ChartRow } from "@/components/charts/trend-chart";
import { ErrorState, LoadingState } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { useCreateReport, useDecisionPacket } from "@/lib/api/medical-hooks";
import type { DecisionPacket, Severity } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { KindChip } from "./common";

type Contributor = { signal: string; label: string; value: number | null; unit: string; baseline: number | null; z: number | null; percentile: number | null; share: number };

function Section({ n, title, kind, children }: { n: number; title: string; kind?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`dp-${n}`} className="rounded-md border border-bulkhead/70 p-3">
      <h3 id={`dp-${n}`} className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold">
        <span className="readout text-ink-3">{n}</span> {title} {kind && <KindChip kind={kind} />}
      </h3>
      {children}
    </section>
  );
}

const ESC_CLS = { immediate: "border-critical/50 bg-critical/10 text-critical", prompt: "border-caution/50 bg-caution/10 text-caution", routine: "border-bulkhead text-ink-2" };

export function PacketView({ p }: { p: DecisionPacket }) {
  const o = p.observation as Record<string, string | null>;
  const m = p.measurements as { label: string; unit: string; trigger_value: number; peak_value: number; alert_limit: number | null; alert_limit_note: string | null; series: Record<string, number | string | null>[]; metric: string };
  const b = p.baseline_comparison as { available: boolean; contributors: Contributor[]; significance: { description: string; max_abs_z: number } | null; method: string | null };
  const env = p.environmental_context as { activity_state: string | null; mission_stage: string; simulated_test_scenario: string | null; scenario_note: string | null; habitat: { parameters: Record<string, { label: string; value: number; unit: string }> } | null; space_weather: { events: { title: string; offset_hours: number; detail: string | null }[]; note: string } };
  const ai = p.ai_output as { available: boolean; model_version: string | null; rule: string | null; kind: string | null; what_changed: string | null; anomaly_peak: { ensemble_score: number; votes: number } | null; flagged_windows: number; windows: number; note: string };
  const cu = p.confidence_uncertainty as { confidence: { level: string; score: number | null; basis: string[] }; meaning: string; sources: string[] };
  const dq = p.data_quality as { samples: number; interval_s: number | null; largest_gap_s: number | null; completeness: number | null; latest_reading_age_s: number | null; notes: string[] };
  const rw = p.review_workflow;
  const series: ChartRow[] = m.series.map((r) => ({ t: Date.parse(String(r.ts)), v: (r[m.metric] as number | null) ?? null }));

  return (
    <div className="space-y-3">
      <div className={cn("flex flex-wrap items-start gap-3 rounded-md border px-3 py-2.5", ESC_CLS[rw.escalation.level])}>
        <Siren className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{rw.escalation.label}: {rw.escalation.who}</p>
          <p className="text-sm text-ink-2">{rw.escalation.why} {rw.escalation.reasons.join(" ")}</p>
        </div>
      </div>

      <Section n={1} title="Observation" kind="simulated">
        <p className="flex flex-wrap items-center gap-2 text-sm"><StatusPill status={o.severity as Severity} /> <span className="font-medium">{o.title}</span> <span className="text-ink-3">{utcDayTime(String(o.opened_at))} UTC · {o.status}</span></p>
        <p className="mt-1 text-sm text-ink-2">{o.summary}</p>
        {o.simulated_test_scenario && <p className="mt-1 text-sm text-caution">Simulated test scenario running: {o.simulated_test_scenario}.</p>}
      </Section>

      <Section n={2} title="Measurements" kind="simulated">
        <dl className="mb-2 grid grid-cols-3 gap-2 text-sm">
          <div><dt className="text-xs text-ink-3">At trigger</dt><dd>{fmt(m.trigger_value, 1)} {m.unit}</dd></div>
          <div><dt className="text-xs text-ink-3">Peak</dt><dd>{fmt(m.peak_value, 1)} {m.unit}</dd></div>
          <div><dt className="text-xs text-ink-3">Prototype limit</dt><dd>{m.alert_limit != null ? `${fmt(m.alert_limit, 1)} ${m.unit}` : "—"}</dd></div>
        </dl>
        {series.some((r) => r.v != null) && (
          <TrendChart data={series} series={[{ key: "v", label: m.label, color: "var(--telemetry)" }]} unit={m.unit} decimals={1} height={150}
            refs={m.alert_limit != null ? [{ value: m.alert_limit, label: "prototype limit" }] : []}
            ariaLabel={`${m.label}, one-minute means from 30 minutes before the alert`} />
        )}
        {m.alert_limit_note && <p className="mt-1 text-xs text-ink-3">{m.alert_limit_note}</p>}
      </Section>

      <Section n={3} title="Baseline comparison" kind="derived">
        {b.available && b.contributors.length ? (
          <>
            <table className="w-full text-left text-sm tabular-nums">
              <thead className="text-xs text-ink-2"><tr><th className="py-1 font-medium">Signal</th><th className="py-1 font-medium">Value</th><th className="py-1 font-medium">Personal baseline</th><th className="py-1 font-medium">z</th></tr></thead>
              <tbody>
                {b.contributors.map((c) => (
                  <tr key={c.signal} className="border-t border-bulkhead/50">
                    <td className="py-1">{c.label}</td><td className="py-1">{fmt(c.value, 1)} {c.unit}</td><td className="py-1">{fmt(c.baseline, 1)}</td>
                    <td className={cn("py-1", Math.abs(c.z ?? 0) >= 3 ? "text-critical" : Math.abs(c.z ?? 0) >= 2 ? "text-caution" : "")}>{c.z != null ? `${c.z > 0 ? "+" : ""}${fmt(c.z, 1)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {b.significance && <p className="mt-1 text-xs text-ink-2">{b.significance.description} (max |z| {fmt(b.significance.max_abs_z, 1)}).</p>}
          </>
        ) : (
          <p className="text-sm text-ink-2">No baseline comparison available.</p>
        )}
      </Section>

      <Section n={4} title="Environmental context">
        <ul className="space-y-1 text-sm">
          <li>Activity: {env.activity_state ?? "unknown"} · {env.mission_stage}</li>
          {env.scenario_note && <li className="text-caution">{env.scenario_note}</li>}
          {env.habitat && <li>Simulated habitat: {Object.values(env.habitat.parameters).map((x) => `${x.label} ${x.value} ${x.unit}`).join(", ")}</li>}
          <li className="flex flex-wrap items-center gap-1.5"><KindChip kind="indicator" /> {env.space_weather.events.length ? `${env.space_weather.events.length} NASA DONKI event(s) within 24 h: ${env.space_weather.events.slice(0, 3).map((e) => `${e.title} (${e.offset_hours > 0 ? "+" : ""}${fmt(e.offset_hours, 1)} h)`).join(", ")}` : "No NASA DONKI events within 24 h."}</li>
        </ul>
      </Section>

      <Section n={5} title="AI output" kind="model">
        {ai.available ? (
          <ul className="space-y-1 text-sm">
            <li>Rule: {ai.rule}</li>
            <li>Pattern: <span className="font-medium">{(ai.kind ?? "").replaceAll("_", " ")}</span>{ai.anomaly_peak && ` · ensemble peak ${fmt(ai.anomaly_peak.ensemble_score, 2)}× threshold, ${ai.anomaly_peak.votes} detectors`} · {ai.flagged_windows} of {ai.windows} windows flagged</li>
            <li className="text-ink-2">{ai.what_changed}</li>
            <li className="text-xs text-ink-3">Model {ai.model_version}. {ai.note}</li>
          </ul>
        ) : <p className="text-sm text-ink-2">{ai.note}</p>}
      </Section>

      <Section n={6} title="Confidence and uncertainty">
        <p className="text-sm">Confidence <span className="font-medium">{cu.confidence.level}</span>{cu.confidence.score != null && ` (${fmt(cu.confidence.score, 2)})`}: {cu.confidence.basis.join("; ")}.</p>
        <p className="mt-1 text-xs text-ink-2">{cu.meaning}</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-2">{cu.sources.map((s) => <li key={s}>{s}</li>)}</ul>
      </Section>

      <Section n={7} title="Data quality">
        <p className="text-sm">{dq.samples} samples around the alert{dq.interval_s ? `, every ${fmt(dq.interval_s, 0)} s` : ""}; completeness {dq.completeness != null ? `${fmt(dq.completeness * 100, 0)}%` : "unknown"}; largest gap {fmt(dq.largest_gap_s, 0)} s.</p>
        {dq.notes.map((n) => <p key={n} className="text-xs text-caution">{n}</p>)}
      </Section>

      <Section n={8} title="Recommended medical review workflow">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {rw.steps.map((s) => <li key={s.key}>{s.label} <span className="text-xs text-ink-3">({s.role_label})</span></li>)}
        </ol>
        <p className="mt-1 text-xs text-ink-3">{rw.note}</p>
      </Section>
      <p className="text-xs text-ink-3">{p.disclaimer}</p>
    </div>
  );
}

export function DecisionPacketPanel({ alertId }: { alertId: string }) {
  const q = useDecisionPacket(alertId);
  const create = useCreateReport();
  const canWrite = useCan("reports:write");
  const router = useRouter();
  if (q.isPending) return <LoadingState label="Building decision-support packet" rows={6} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-3">
      {canWrite && (
        <Button
          size="sm"
          variant="outline"
          disabled={create.isPending}
          onClick={() =>
            create.mutate({ alert_id: alertId }, {
              onSuccess: (r) => { toast.success("Draft incident report created"); router.push(`/reports?report=${r.id}`); },
              onError: (e) => toast.error(e.message),
            })
          }
        >
          <ClipboardPlus aria-hidden /> Create incident report
        </Button>
      )}
      <PacketView p={q.data!} />
    </div>
  );
}
