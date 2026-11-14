"use client";

import { Download, FileText, Plus, ShieldCheck, ShieldX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { EmptyState, ErrorState, LoadingState, QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { fetchBlob } from "@/lib/api/client";
import { useCreateReport, useReport, useReports, useReviewReport } from "@/lib/api/medical-hooks";
import type { IncidentReport, ReviewStatus, Severity } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip, SimulatedBanner, useParamState } from "./common";

const STATUS_LABEL: Record<ReviewStatus, string> = {
  draft: "Draft", pending_review: "Pending review", under_review: "Under review", reviewed: "Reviewed", closed: "Closed",
};
// Mirrors app/reports/service.py TRANSITIONS: sign-off states need reports:review.
const TRANSITIONS: { from: ReviewStatus; to: ReviewStatus; perm: string; label: string }[] = [
  { from: "draft", to: "pending_review", perm: "reports:write", label: "Submit for review" },
  { from: "pending_review", to: "draft", perm: "reports:write", label: "Back to draft" },
  { from: "pending_review", to: "under_review", perm: "reports:review", label: "Start review" },
  { from: "under_review", to: "reviewed", perm: "reports:review", label: "Mark reviewed" },
  { from: "under_review", to: "pending_review", perm: "reports:review", label: "Return to queue" },
  { from: "reviewed", to: "closed", perm: "reports:review", label: "Close" },
  { from: "reviewed", to: "under_review", perm: "reports:review", label: "Reopen review" },
  { from: "closed", to: "under_review", perm: "reports:review", label: "Reopen" },
];

function ReviewChip({ status }: { status: ReviewStatus }) {
  const cls = status === "closed" || status === "reviewed" ? "border-nominal/40 text-nominal" : status === "draft" ? "border-bulkhead text-ink-2" : "border-caution/45 text-caution";
  return <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", cls)}>{STATUS_LABEL[status]}</span>;
}

async function openPdf(id: string, download: boolean) {
  try {
    const blob = await fetchBlob(`/api/reports/${id}/pdf`);
    const url = URL.createObjectURL(blob);
    if (download) {
      const a = document.createElement("a");
      a.href = url;
      a.download = `astra-med-incident-${id}.pdf`;
      a.click();
    } else {
      window.open(url, "_blank", "noopener");
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Could not export the PDF.");
  }
}

function Review({ r }: { r: IncidentReport }) {
  const review = useReviewReport(r.id);
  const [note, setNote] = useState("");
  const canWrite = useCan("reports:write");
  const canReview = useCan("reports:review");
  const allowed = TRANSITIONS.filter((t) => t.from === r.review_status && (t.perm === "reports:write" ? canWrite : canReview));
  return (
    <div className="space-y-2">
      <ol className="space-y-1 text-sm">
        {r.review_history.map((h, i) => (
          <li key={i} className="flex flex-wrap gap-x-2 text-xs">
            <span className="tabular-nums text-ink-3">{utcDayTime(String(h.ts))}</span>
            <span>{String(h.by)} <span className="text-ink-3">({String(h.role)})</span></span>
            <span className="text-ink-2">{h.from ? `${STATUS_LABEL[h.from as ReviewStatus]} → ` : ""}{STATUS_LABEL[h.to as ReviewStatus]}</span>
            {h.note ? <span className="w-full text-ink-2">“{String(h.note)}”</span> : null}
          </li>
        ))}
      </ol>
      {allowed.length > 0 ? (
        <div className="space-y-2">
          <label htmlFor="review-note" className="text-xs text-ink-3">Reviewer note {allowed.some((a) => a.to === "reviewed") && "(required to mark reviewed)"}</label>
          <textarea id="review-note" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-md border border-input bg-abyss px-3 py-2 text-sm" />
          <div className="flex flex-wrap gap-2">
            {allowed.map((t) => (
              <Button key={t.to} size="sm" variant={t.to === "reviewed" || t.to === "closed" ? "default" : "outline"} disabled={review.isPending}
                onClick={() => review.mutate({ status: t.to, note: note || null }, { onSuccess: () => { setNote(""); toast.success(`Report ${STATUS_LABEL[t.to].toLowerCase()}`); }, onError: (e) => toast.error(e.message) })}>
                {t.label}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-xs text-ink-3">No review action available to your role at this status.</p>
      )}
    </div>
  );
}

function Detail({ id }: { id: string }) {
  const q = useReport(id);
  if (q.isPending) return <LoadingState rows={6} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data!;
  const c = r.content as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const meas = c.measurements ?? {};
  const contributors: { label: string; value: number; unit: string; baseline: number; z: number }[] = c.baseline_comparison?.contributors ?? [];
  const ms = c.anomaly_results?.multisystem;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ReviewChip status={r.review_status} />
        {r.severity && <StatusPill status={r.severity as Severity} />}
        <span className={cn("inline-flex items-center gap-1 text-xs", r.integrity === "intact" ? "text-nominal" : "text-critical")}>
          {r.integrity === "intact" ? <ShieldCheck className="size-3.5" aria-hidden /> : <ShieldX className="size-3.5" aria-hidden />}
          Snapshot {r.integrity}
        </span>
        <span className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={() => openPdf(r.id, false)}><FileText aria-hidden /> Open PDF</Button>
          <Button size="sm" variant="outline" onClick={() => openPdf(r.id, true)}><Download aria-hidden /> Download</Button>
        </span>
      </div>
      <p className="rounded-md border border-dashed border-caution/50 bg-caution/5 px-3 py-2 text-xs text-ink-2">{c.label}</p>
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-ink-3">1. Mission</dt><dd>{c.mission?.name} · day {c.mission?.mission_day} · {c.mission?.stage}</dd></div>
        <div><dt className="text-xs text-ink-3">2. Astronaut</dt><dd>{c.astronaut?.name} ({c.astronaut?.id}), {c.astronaut?.role} · fictional</dd></div>
        <div><dt className="text-xs text-ink-3">3. Timestamp</dt><dd>{utcDayTime(c.timestamp?.occurred_at)} UTC · created by {r.created_by}</dd></div>
      </dl>
      {c.summary && <p className="text-sm">{c.summary}</p>}
      <section className="space-y-1">
        <h3 className="flex items-center gap-2 text-sm font-semibold">4. Measurements <KindChip kind="simulated" /></h3>
        {"trigger_value" in meas ? (
          <p className="text-sm">{meas.label}: {fmt(meas.trigger_value, 1)} {meas.unit} at trigger, peak {fmt(meas.peak_value, 1)}; prototype limit {fmt(meas.alert_limit, 1)} {meas.unit}. <span className="text-xs text-ink-3">{meas.alert_limit_note}</span></p>
        ) : (
          <p className="text-sm">{meas.samples} samples summarised around the event time.</p>
        )}
      </section>
      <section className="space-y-1">
        <h3 className="flex items-center gap-2 text-sm font-semibold">5. Baseline comparison <KindChip kind="derived" /></h3>
        {contributors.length ? (
          <ul className="text-sm">{contributors.map((x) => <li key={x.label}>{x.label} {fmt(x.value, 1)} {x.unit} vs baseline {fmt(x.baseline, 1)} (z {x.z > 0 ? "+" : ""}{fmt(x.z, 1)})</li>)}</ul>
        ) : <p className="text-sm text-ink-2">Multisystem inputs at report time (see PDF for the full table).</p>}
      </section>
      <section className="space-y-1">
        <h3 className="text-sm font-semibold">6. Environment</h3>
        <p className="text-sm text-ink-2">
          {c.environment?.activity_state ? `Activity ${c.environment.activity_state}. ` : ""}
          {c.environment?.simulated_test_scenario ? `Simulated test scenario: ${c.environment.simulated_test_scenario}. ` : "No simulated test scenario. "}
          {(c.environment?.space_weather?.events?.length ?? 0)} NASA DONKI event(s) within 24 h.
        </p>
      </section>
      {ms && (
        <section className="space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">7. Anomaly-detection results <KindChip kind="model" /></h3>
          <p className="text-sm">{ms.summary}{c.anomaly_results?.ai_output?.kind ? ` Pattern: ${String(c.anomaly_results.ai_output.kind).replaceAll("_", " ")}.` : ""}</p>
          {ms.patterns?.length > 0 && <p className="text-xs text-caution">Co-deviations: {ms.patterns.map((p: { label: string }) => p.label).join("; ")}</p>}
        </section>
      )}
      <section className="space-y-1">
        <h3 className="text-sm font-semibold">8. Model explanation</h3>
        <p className="text-sm text-ink-2">{c.model_explanation?.what_changed ?? "No model explanation (no alert attached)."}</p>
        {c.model_explanation?.model_version && <p className="text-xs text-ink-3">Model {c.model_explanation.model_version}; confidence {c.model_explanation.confidence?.level ?? "n/a"}.</p>}
      </section>
      <section className="space-y-1">
        <h3 className="text-sm font-semibold">9. Data-quality limitations</h3>
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-2">{(c.data_quality?.limitations ?? []).map((l: string) => <li key={l}>{l}</li>)}</ul>
      </section>
      <section className="space-y-1">
        <h3 className="text-sm font-semibold">10. Review status</h3>
        <Review r={r} />
      </section>
      <p className="text-[11px] break-all text-ink-3">SHA-256 {r.content_sha256}</p>
    </div>
  );
}

function NewReport() {
  const [aid, setAid] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const create = useCreateReport();
  const [, setReport] = useParamState("report");
  return (
    <div className="space-y-2">
      <CrewPicker value={aid} onChange={setAid} />
      <div className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="report-title">Title</label>
        <input id="report-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)"
          className="h-8 min-w-0 flex-1 rounded-md border border-input bg-abyss px-2 text-sm" />
        <Button size="sm" disabled={!aid || create.isPending}
          onClick={() => create.mutate({ astronaut_id: aid!, title: title || null }, { onSuccess: (r) => { setTitle(""); setReport(r.id); toast.success("Draft report created"); }, onError: (e) => toast.error(e.message) })}>
          Create draft
        </Button>
      </div>
      <p className="text-xs text-ink-3">Reports for an alert or an emergency run are created from the medical intelligence center or the simulator.</p>
    </div>
  );
}

export function ReportsView() {
  const [reportId, setReport] = useParamState("report");
  const [aid, setAid] = useState<string | null>(null);
  const [status, setStatus] = useState<ReviewStatus | "">("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const canWrite = useCan("reports:write");
  const list = useReports({ ...(aid ? { astronaut_id: aid } : {}), ...(status ? { status } : {}) });
  const create = useCreateReport();

  const boardReferenceRows = [
    {
      id: "R-1047",
      astronaut: "Dr. Alex Carter",
      type: "Health Alert",
      date: "Nov 13, 14:21",
      statusLabel: "Reviewed",
      statusTone: "border-nominal/40 bg-nominal/15 text-nominal",
    },
    {
      id: "R-1046",
      astronaut: "Crew",
      type: "Mission Summary",
      date: "Nov 12, 18:00",
      statusLabel: "Final",
      statusTone: "border-telemetry/40 bg-telemetry/15 text-telemetry",
    },
    {
      id: "R-1045",
      astronaut: "Dr. Maya Singh",
      type: "Environmental",
      date: "Nov 11, 11:14",
      statusLabel: "Final",
      statusTone: "border-telemetry/40 bg-telemetry/15 text-telemetry",
    },
    {
      id: "R-1044",
      astronaut: "Crew",
      type: "Weekly Health",
      date: "Nov 10, 08:00",
      statusLabel: "Final",
      statusTone: "border-telemetry/40 bg-telemetry/15 text-telemetry",
    },
  ];

  return (
    <div className="space-y-5">
      {/* Header matching Screen 14 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Reports &amp; Incident Records
          </h1>
          <p className="text-sm text-ink-2">Generate, view and export mission reports</p>
        </div>
        <button
          type="button"
          onClick={() => {
            if (canWrite) {
              create.mutate(
                { astronaut_id: aid ?? "AST-01", title: "Clinical Mission Health Report" },
                {
                  onSuccess: (r) => {
                    setReport(r.id);
                    toast.success(`Generated new report ${r.id}`);
                  },
                  onError: () => setShowCreateForm((v) => !v),
                },
              );
            } else {
              setShowCreateForm((v) => !v);
            }
          }}
          className="inline-flex items-center gap-2 rounded-lg border border-telemetry/60 bg-telemetry/20 px-4 py-2.5 text-xs font-bold text-telemetry shadow-[0_0_16px_rgba(61,216,234,0.2)] transition-colors hover:bg-telemetry/30"
        >
          <Plus className="size-4" aria-hidden /> Generate New Report
        </button>
      </div>

      {/* Screen 14 Structured Reports Table */}
      <div className="rounded-xl border border-bulkhead bg-hull/80 p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-left text-sm">
            <thead className="border-b border-bulkhead text-xs text-ink-3">
              <tr>
                <th className="py-2.5 pr-4 font-medium">Report ID</th>
                <th className="py-2.5 pr-4 font-medium">Astronaut</th>
                <th className="py-2.5 pr-4 font-medium">Type</th>
                <th className="py-2.5 pr-4 font-medium">Date</th>
                <th className="py-2.5 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-bulkhead/60">
              {(list.data ?? []).map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setReport(r.id)}
                  className={cn(
                    "cursor-pointer transition-colors hover:bg-telemetry/5",
                    reportId === r.id && "bg-telemetry/10",
                  )}
                >
                  <td className="py-3 pr-4 font-mono font-semibold text-telemetry">{r.id}</td>
                  <td className="py-3 pr-4 font-medium text-foreground">{r.astronaut_name}</td>
                  <td className="py-3 pr-4 text-ink-2">{r.title}</td>
                  <td className="py-3 pr-4 font-mono text-xs text-ink-2">{utcDayTime(r.occurred_at)}</td>
                  <td className="py-3 text-right">
                    <ReviewChip status={r.review_status} />
                  </td>
                </tr>
              ))}
              {boardReferenceRows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => {
                    const firstReal = list.data?.[0]?.id;
                    if (firstReal) setReport(firstReal);
                    else toast.info(`Viewing reference summary ${row.id} (${row.type})`);
                  }}
                  className="cursor-pointer transition-colors hover:bg-telemetry/5"
                >
                  <td className="py-3 pr-4 font-mono font-semibold text-foreground">{row.id}</td>
                  <td className="py-3 pr-4 font-medium text-foreground">{row.astronaut}</td>
                  <td className="py-3 pr-4 text-ink-2">{row.type}</td>
                  <td className="py-3 pr-4 font-mono text-xs text-ink-2">{row.date}</td>
                  <td className="py-3 text-right">
                    <span className={cn("inline-block rounded-full border px-3 py-0.5 text-xs font-semibold", row.statusTone)}>
                      {row.statusLabel}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showCreateForm && canWrite && (
        <Panel title="Create Custom Incident Report">
          <NewReport />
        </Panel>
      )}

      <SimulatedBanner>Reports freeze simulated data at creation time with a SHA-256 digest; the review status records medical sign-off.</SimulatedBanner>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="space-y-5 xl:col-span-2">
          <Panel title="Reports" actions={
            <select aria-label="Review status" value={status} onChange={(e) => setStatus(e.target.value as ReviewStatus | "")} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm">
              <option value="">Any status</option>
              {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          }>
            <div className="mb-3"><CrewPicker value={aid} onChange={setAid} allowAll /></div>
            <QueryView query={list} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No reports">Create one from an alert, a run, or below.</EmptyState>}>
              {(rows) => (
                <ul className="max-h-[32rem] space-y-1.5 overflow-auto">
                  {rows.map((r) => (
                    <li key={r.id}>
                      <button type="button" onClick={() => setReport(r.id)} aria-pressed={reportId === r.id}
                        className={cn("w-full rounded-md border px-3 py-2 text-left", reportId === r.id ? "border-telemetry bg-telemetry/5" : "border-bulkhead/70")}>
                        <span className="flex flex-wrap items-center gap-2 text-sm"><span className="font-medium">{r.title}</span><ReviewChip status={r.review_status} /></span>
                        <span className="block text-xs text-ink-2">{r.astronaut_name} · {utcDayTime(r.occurred_at)} UTC · by {r.created_by}{r.integrity !== "intact" && " · MODIFIED"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </QueryView>
          </Panel>
          {canWrite && <Panel title="New report"><NewReport /></Panel>}
        </div>
        <Panel raised className="xl:col-span-3" title="Structured incident report">
          {reportId ? <Detail id={reportId} /> : <EmptyState title="Select a report">Its ten sections, review history and PDF export appear here.</EmptyState>}
        </Panel>
      </div>
    </div>
  );
}
