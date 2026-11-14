"use client";

import { Layers } from "lucide-react";
import { useState } from "react";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState, QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { useCrewSystems, useDecisionQueue, useSystems } from "@/lib/api/medical-hooks";
import type { Severity, SystemAssessment, SystemStatus } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip, SimulatedBanner, SystemStatusPill, useParamState } from "./common";
import { DecisionPacketPanel } from "./decision-packet";

function Matrix({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const q = useCrewSystems();
  return (
    <Panel title="Crew systems" description="Six systems per crew member, against each person's own baseline. Select a row.">
      <QueryView query={q}>
        {(d) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <caption className="sr-only">System status per crew member</caption>
              <thead className="text-xs text-ink-2">
                <tr className="border-b border-bulkhead">
                  <th scope="col" className="py-2 pr-3 font-medium">Crew member</th>
                  {d.systems.map((s) => <th key={s.key} scope="col" className="py-2 pr-2 font-medium">{s.label}</th>)}
                  <th scope="col" className="py-2 font-medium">Patterns</th>
                </tr>
              </thead>
              <tbody>
                {d.crew.map((c) => (
                  <tr key={c.astronaut_id} className={cn("border-b border-bulkhead/50", selected === c.astronaut_id && "bg-sidebar-accent/50")}>
                    <th scope="row" className="py-2 pr-3 font-medium">
                      <button type="button" onClick={() => onSelect(c.astronaut_id)} className="flex items-center gap-2 text-left hover:underline" aria-pressed={selected === c.astronaut_id}>
                        <span className="size-2 rounded-full" style={{ background: crewColor(c.astronaut_id) }} aria-hidden /> {c.name}
                      </button>
                    </th>
                    {d.systems.map((s) => <td key={s.key} className="py-2 pr-2"><SystemStatusPill status={c.statuses[s.key] as SystemStatus} /></td>)}
                    <td className="py-2 text-xs text-ink-2">{c.patterns.length ? c.patterns.join("; ") : "none"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

function SystemCard({ s }: { s: SystemAssessment }) {
  const [open, setOpen] = useState(s.status === "deviation" || s.status === "marked_deviation");
  return (
    <article className={cn("rounded-lg border p-3", s.status === "marked_deviation" ? "border-critical/40" : s.status === "deviation" ? "border-caution/40" : "border-bulkhead/70")}>
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-heading text-base font-semibold">{s.label}</h3>
        <SystemStatusPill status={s.status} />
        <span className="ml-auto text-xs text-ink-3">{s.data_quality.assessed} of {s.data_quality.inputs} inputs assessed</span>
      </header>
      <p className="mt-1.5 text-sm text-ink-2">{s.explanation}</p>
      {s.open_alerts.length > 0 && (
        <ul className="mt-2 space-y-1">{s.open_alerts.map((a) => <li key={a.id} className="flex items-center gap-2 text-sm"><StatusPill status={a.severity as Severity} /> {a.title}</li>)}</ul>
      )}
      {s.ai_outputs.length > 0 && (
        <ul className="mt-2 space-y-1">
          {s.ai_outputs.map((o) => <li key={o.title} className="text-sm"><KindChip kind={o.category} /> <span className="font-medium">{o.title}</span> <span className="text-xs text-ink-2">{o.detail}</span></li>)}
        </ul>
      )}
      <button type="button" className="mt-2 text-xs text-telemetry hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide inputs" : "Show the inputs used"}
      </button>
      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs tabular-nums">
            <thead className="text-ink-2"><tr><th className="py-1 font-medium">Input</th><th className="py-1 font-medium">Value</th><th className="py-1 font-medium">Reference</th><th className="py-1 font-medium">z</th><th className="py-1 font-medium">Status</th><th className="py-1 font-medium">Kind</th></tr></thead>
            <tbody>
              {s.features.map((f) => (
                <tr key={f.key} className="border-t border-bulkhead/50 align-top">
                  <td className="py-1 pr-2">{f.label}<span className="block text-[11px] text-ink-3">{f.source}</span></td>
                  <td className="py-1 pr-2">{typeof f.value === "number" ? fmt(f.value, 2) : f.value ?? "—"} {f.unit}</td>
                  <td className="py-1 pr-2">{f.reference != null ? fmt(f.reference, 2) : "—"}{f.reference_label && <span className="block text-[11px] text-ink-3">{f.reference_label}</span>}</td>
                  <td className="py-1 pr-2">{f.z != null ? `${f.z > 0 ? "+" : ""}${fmt(f.z, 1)}` : "—"}</td>
                  <td className="py-1 pr-2"><SystemStatusPill status={f.status === "info" ? "info" : (f.status as SystemStatus)} /></td>
                  <td className="py-1"><KindChip kind={f.category} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {s.features.some((f) => f.note) && (
            <ul className="mt-1 space-y-0.5 text-[11px] text-ink-3">{s.features.filter((f) => f.note).map((f) => <li key={f.key}>{f.label}: {f.note}</li>)}</ul>
          )}
        </div>
      )}
    </article>
  );
}

function Systems({ aid }: { aid: string }) {
  const q = useSystems(aid);
  if (q.isPending) return <LoadingState label="Assessing systems" rows={6} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data!;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <p className="font-medium">{a.summary}</p>
        {a.ai && <p className="text-ink-2"><KindChip kind="model" /> Phase 3 rules: {a.ai.category_label} ({fmt(a.ai.risk_score, 0)}/100), confidence {String(a.ai.confidence.level)}</p>}
        {a.data_quality.notes.map((n) => <p key={n} className="text-xs text-caution">{n}</p>)}
      </div>
      {a.patterns.length > 0 && (
        <div className="rounded-lg border border-caution/40 bg-caution/5 p-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Layers className="size-4 text-caution" aria-hidden /> Cross-system patterns</h3>
          <ul className="mt-1.5 space-y-2">
            {a.patterns.map((p) => (
              <li key={p.key} className="text-sm">
                <span className="font-medium">{p.label}</span>
                <ul className="mt-0.5 list-disc pl-5 text-xs text-ink-2">{p.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
                <p className="text-xs text-ink-2">Review: {p.review} <span className="text-ink-3">{p.note}</span></p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-2">{a.systems.map((s) => <SystemCard key={s.key} s={s} />)}</div>
      <p className="text-xs text-ink-3">{a.config.note} Bands: deviation |z| ≥ {a.config.z_deviation}, marked |z| ≥ {a.config.z_marked} ({a.config.source}).</p>
    </div>
  );
}

function Queue({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const [advisory, setAdvisory] = useState(false);
  const q = useDecisionQueue(advisory);
  return (
    <Panel
      title="Alerts needing review"
      description="Caution and critical alerts in the last 48 h, with their escalation level."
      actions={
        <label className="flex items-center gap-2 text-xs text-ink-2">
          <input type="checkbox" checked={advisory} onChange={(e) => setAdvisory(e.target.checked)} /> Include advisory
        </label>
      }
    >
      <QueryView query={q} isEmpty={(d) => d.items.length === 0} empty={<EmptyState title="No open significant alerts">Alerts that need medical review appear here.</EmptyState>}>
        {(d) => (
          <ul className="max-h-[32rem] space-y-1.5 overflow-auto">
            {d.items.map((i) => (
              <li key={i.alert_id}>
                <button
                  type="button"
                  onClick={() => onSelect(i.alert_id)}
                  aria-pressed={selected === i.alert_id}
                  className={cn("w-full rounded-md border px-3 py-2 text-left", selected === i.alert_id ? "border-telemetry bg-telemetry/5" : "border-bulkhead/70 hover:border-bulkhead")}
                >
                  <span className="flex flex-wrap items-center gap-2 text-sm"><StatusPill status={i.severity as Severity} /> <span className="font-medium">{i.title}</span></span>
                  <span className="mt-0.5 block text-xs text-ink-2">{i.name} · {utcDayTime(i.opened_at)} UTC · {i.status}{i.simulated_test_scenario ? " · simulated test" : ""}</span>
                  <span className={cn("mt-0.5 block text-xs", i.escalation.level === "immediate" ? "text-critical" : i.escalation.level === "prompt" ? "text-caution" : "text-ink-3")}>{i.escalation.label}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Panel>
  );
}

export function MedicalCenter() {
  const [aidParam, setAid] = useParamState("astronaut");
  const [alertId, setAlert] = useParamState("alert");
  const crew = useCrewSystems();
  const aid = aidParam ?? crew.data?.crew[0]?.astronaut_id ?? null;
  return (
    <div className="space-y-5">
      <SimulatedBanner />
      <Matrix selected={aid} onSelect={setAid} />
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <Panel raised className="xl:col-span-3" title="Multisystem assessment" description="Inputs, status, model outputs and an explanation built only from those inputs."
          actions={<CrewPicker value={aid} onChange={(v) => setAid(v)} />}>
          {aid ? (
            <Systems aid={aid} />
          ) : crew.error ? (
            <ErrorState title="Couldn't load the crew list" error={crew.error} onRetry={() => crew.refetch()} />
          ) : crew.data ? (
            <EmptyState title="No crew members">The multisystem assessment appears once the backend lists a crew member.</EmptyState>
          ) : (
            <LoadingState rows={5} />
          )}
        </Panel>
        <div className="space-y-5 xl:col-span-2">
          <Queue selected={alertId} onSelect={setAlert} />
          <Panel title="Explainable decision support" description="Eight-part packet for the selected alert.">
            {alertId ? <DecisionPacketPanel alertId={alertId} /> : <EmptyState title="Select an alert">Choose an alert above to see its observation, measurements, baseline comparison, context, AI output, uncertainty, data quality and review workflow.</EmptyState>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
