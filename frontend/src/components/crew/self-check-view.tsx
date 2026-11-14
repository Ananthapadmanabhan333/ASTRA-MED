"use client";

import { ClipboardCheck, HeartPulse, ListChecks, Send } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState } from "@/components/data/states";
import { DataCard } from "@/components/mc/card";
import { CrewPicker, SimulatedBanner, useParamState } from "@/components/medical/common";
import { Button } from "@/components/ui/button";
import { useSystems } from "@/lib/api/medical-hooks";
import { type SelfCheckSummary, useAddSelfReport, useSelfCheck } from "@/lib/api/selfcheck-hooks";
import { useCan } from "@/lib/auth/store";
import { relativeTime, utcDayTime } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

/** One status vocabulary for the body map: from the multisystem bands and the self-check bands. */
type Tone = "nominal" | "caution" | "critical" | "none";
const TONE_CLASS: Record<Tone, { text: string; fill: string; label: string }> = {
  nominal: { text: "text-nominal", fill: "fill-nominal/25 stroke-nominal", label: "Within your usual range" },
  caution: { text: "text-caution", fill: "fill-caution/30 stroke-caution", label: "Needs attention" },
  critical: { text: "text-critical", fill: "fill-critical/30 stroke-critical", label: "Tell the flight surgeon" },
  none: { text: "text-ink-3", fill: "fill-bulkhead/40 stroke-bulkhead", label: "No data yet" },
};
const RANK: Record<Tone, number> = { none: 0, nominal: 1, caution: 2, critical: 3 };

const SYSTEM_TONE: Record<string, Tone> = {
  within_baseline: "nominal", deviation: "caution", marked_deviation: "critical", insufficient_data: "none",
};
const SELF_TONE: Record<string, Tone> = { normal: "nominal", attention: "caution", contact: "critical", no_data: "none" };

/**
 * Regions group the assessment systems for navigation. They do not show organ-level measurements:
 * each region is coloured by the systems and self-reported indicators listed against it.
 */
const REGIONS = [
  { key: "head", label: "Head: sleep and mood", systems: ["sleep_circadian"], self: ["mood"] },
  { key: "chest", label: "Chest: heart and lungs", systems: ["cardiovascular", "respiratory"], self: [] },
  { key: "abdomen", label: "Abdomen: metabolism", systems: [], self: ["glucose"] },
  { key: "limbs", label: "Limbs: activity and recovery", systems: ["activity_recovery"], self: [] },
  { key: "body", label: "Whole body: temperature, radiation, symptoms", systems: ["thermoregulation", "radiation"], self: ["symptoms"] },
] as const;
type RegionKey = (typeof REGIONS)[number]["key"];

interface RegionItem {
  key: string;
  label: string;
  tone: Tone;
  statusLabel: string;
  detail: string;
  source: string;
}

function worst(items: RegionItem[]): Tone {
  return items.reduce<Tone>((acc, i) => (RANK[i.tone] > RANK[acc] ? i.tone : acc), "none");
}

export function SelfCheckView() {
  const [param, setParam] = useParamState("astronaut");
  const aid = param ?? "AST-01";
  const summary = useSelfCheck(aid);
  const systems = useSystems(aid);
  const [region, setRegion] = useState<RegionKey>("chest");

  const regions = useMemo(() => {
    const out: Record<string, RegionItem[]> = {};
    for (const r of REGIONS) {
      const items: RegionItem[] = [];
      for (const key of r.systems) {
        const s = systems.data?.systems.find((x) => x.key === key);
        if (s) {
          items.push({ key, label: s.label, tone: SYSTEM_TONE[s.status] ?? "none",
            statusLabel: s.status.replaceAll("_", " "), detail: s.explanation, source: "simulated monitoring" });
        }
      }
      for (const key of r.self) {
        const ind = summary.data?.indicators.find((x) => x.key === key);
        if (ind) {
          items.push({ key, label: ind.label, tone: SELF_TONE[ind.status] ?? "none", statusLabel: ind.status_label,
            detail: ind.guidance, source: "self-reported" });
        }
      }
      out[r.key] = items;
    }
    return out;
  }, [systems.data, summary.data]);

  return (
    <div className="space-y-5">
      <SimulatedBanner>
        Vital signs are simulated; glucose, mood and symptoms are what you enter here. Status bands are for orientation and
        tell you when to involve the flight surgeon. They are not a diagnosis, and ASTRA-MED never recommends a treatment.
      </SimulatedBanner>
      <CrewPicker value={aid} onChange={(v) => setParam(v)} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <DataCard title="Body systems" icon={<HeartPulse />}
          footer="Regions group the assessment systems for navigation; they do not show organ-level measurements.">
          {systems.isPending && summary.isPending ? <LoadingState rows={5} /> : (
            <div className="grid gap-4 sm:grid-cols-[180px_minmax(0,1fr)]">
              <BodyMap regions={regions} selected={region} onSelect={setRegion} />
              <RegionDetail region={REGIONS.find((r) => r.key === region)!} items={regions[region] ?? []}
                systemsError={systems.error} />
            </div>
          )}
        </DataCard>
        <Indicators summary={summary.data} pending={summary.isPending} error={summary.error} onRetry={() => summary.refetch()} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Prompts summary={summary.data} pending={summary.isPending} />
        <EntryForm aid={aid} summary={summary.data} />
      </div>
      <History summary={summary.data} pending={summary.isPending} />
    </div>
  );
}

function BodyMap({ regions, selected, onSelect }: {
  regions: Record<string, RegionItem[]>;
  selected: RegionKey;
  onSelect: (r: RegionKey) => void;
}) {
  const shape = (key: RegionKey, child: React.ReactNode) => {
    const tone = worst(regions[key] ?? []);
    const meta = REGIONS.find((r) => r.key === key)!;
    return (
      <g
        role="button"
        tabIndex={0}
        aria-pressed={selected === key}
        aria-label={`${meta.label}: ${TONE_CLASS[tone].label}`}
        onClick={() => onSelect(key)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(key); } }}
        className={cn("cursor-pointer outline-none [&>*]:transition-[stroke-width]", TONE_CLASS[tone].fill,
          selected === key ? "[&>*]:stroke-[3]" : "[&>*]:stroke-[1.5] hover:[&>*]:stroke-[2.5] focus-visible:[&>*]:stroke-[3]")}
      >
        {child}
      </g>
    );
  };
  return (
    <svg viewBox="0 0 160 300" className="mx-auto h-72 w-auto" aria-label="Body systems map">
      {shape("body", <rect x="6" y="4" width="148" height="292" rx="18" className="fill-transparent" strokeDasharray="4 4" />)}
      {shape("head", <circle cx="80" cy="34" r="22" />)}
      {shape("chest", <rect x="50" y="62" width="60" height="60" rx="14" />)}
      {shape("abdomen", <rect x="54" y="126" width="52" height="44" rx="12" />)}
      {shape("limbs", (
        <path d="M46 70 L24 150 L34 154 L54 96 Z M114 70 L136 150 L126 154 L106 96 Z M58 174 L52 284 L68 284 L78 178 Z M102 174 L108 284 L92 284 L82 178 Z" />
      ))}
    </svg>
  );
}

function RegionDetail({ region, items, systemsError }: {
  region: (typeof REGIONS)[number];
  items: RegionItem[];
  systemsError: unknown;
}) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-foreground">{region.label}</h3>
      {systemsError != null && region.systems.length > 0 && (
        <p className="text-xs text-caution">Body-system assessment unavailable; showing self-reported items only.</p>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-ink-2">No data for this region yet.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((i) => (
            <li key={i.key} className="rounded-md border border-bulkhead p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-medium text-foreground">{i.label}</span>
                <span className={cn("text-xs font-medium", TONE_CLASS[i.tone].text)}>{i.statusLabel}</span>
              </div>
              <p className="mt-1 text-sm text-ink-2">{i.detail}</p>
              <p className="mt-1 text-xs text-ink-3">Source: {i.source}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Indicators({ summary, pending, error, onRetry }: {
  summary?: SelfCheckSummary; pending: boolean; error: unknown; onRetry: () => void;
}) {
  return (
    <DataCard title="My self-check" icon={<ClipboardCheck />}>
      {pending ? <LoadingState rows={3} /> : error && !summary ? <ErrorState error={error} onRetry={onRetry} /> : summary ? (
        <div className="space-y-3">
          {summary.indicators.map((i) => {
            const tone = SELF_TONE[i.status] ?? "none";
            return (
              <div key={i.key} className="rounded-md border border-bulkhead p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{i.label}</span>
                  <span className={cn("text-xs font-medium", TONE_CLASS[tone].text)}>{TONE_CLASS[tone].label}</span>
                </div>
                <p className="mt-1 font-mono text-lg text-foreground">
                  {i.value === null ? "—" : i.key === "symptoms" ? `${i.value} reported` : `${i.value} ${i.unit}`}
                  {i.context && <span className="ml-2 text-xs text-ink-3">{i.context.replace("_", " ")}</span>}
                </p>
                <p className="text-sm text-ink-2">{i.status_label}. {i.guidance}</p>
                {i.reference && <p className="mt-1 text-xs text-ink-3">{i.reference}</p>}
              </div>
            );
          })}
        </div>
      ) : null}
    </DataCard>
  );
}

function Prompts({ summary, pending }: { summary?: SelfCheckSummary; pending: boolean }) {
  const now = useNow(30_000);
  return (
    <DataCard title="Today's checks" icon={<ListChecks />}>
      {pending || !summary ? <LoadingState rows={4} /> : (
        <ul className="divide-y divide-bulkhead">
          {summary.prompts.map((p) => (
            <li key={p.key} className="flex flex-wrap items-start justify-between gap-2 py-2.5">
              <div>
                <p className="text-sm font-medium text-foreground">{p.label}</p>
                <p className="text-xs text-ink-3">{p.how}{p.detail ? ` Last: ${p.detail}.` : ""}</p>
              </div>
              <span className={cn("rounded-full border px-2 py-0.5 text-xs",
                p.status === "done" ? "border-nominal/40 text-nominal" : p.status === "overdue" ? "border-critical/50 text-critical" : "border-caution/50 text-caution")}>
                {p.status === "done" ? (p.automatic ? "Automatic" : "Done") : p.status === "overdue" ? "Overdue" : "Due"}
                {p.last_at && now ? `, ${relativeTime(p.last_at, now)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </DataCard>
  );
}

function EntryForm({ aid, summary }: { aid: string; summary?: SelfCheckSummary }) {
  const canWrite = useCan("selfcheck:write");
  const add = useAddSelfReport(aid);
  const [glucose, setGlucose] = useState("");
  const [context, setContext] = useState<"fasting" | "after_meal" | "random">("fasting");
  const [mood, setMood] = useState<number | null>(null);
  const [symptoms, setSymptoms] = useState<string[] | null>(null);
  const [note, setNote] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = glucose.trim() === "" ? null : Number(glucose);
    if (value !== null && (!Number.isFinite(value) || value < 20 || value > 600)) {
      toast.error("Glucose must be a number between 20 and 600 mg/dL.");
      return;
    }
    if (value === null && mood === null && symptoms === null && !note.trim()) {
      toast.error("Enter at least one of glucose, mood, symptoms or a note.");
      return;
    }
    add.mutate(
      { glucose_mg_dl: value, glucose_context: value === null ? null : context, mood, symptoms, note: note.trim() || null },
      {
        onSuccess: () => {
          toast.success("Self-check recorded");
          setGlucose(""); setMood(null); setSymptoms(null); setNote("");
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Could not record the self-check"),
      },
    );
  };

  const toggle = (key: string) =>
    setSymptoms((s) => { const cur = s ?? []; return cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]; });

  if (!canWrite) {
    return (
      <DataCard title="Record a self-check" icon={<Send />}>
        <p className="text-sm text-ink-2">Recording self-checks needs the self-check permission (flight surgeon or mission operator).</p>
      </DataCard>
    );
  }
  return (
    <DataCard title="Record a self-check" icon={<Send />}>
      <form onSubmit={submit} className="space-y-4">
        <fieldset className="grid gap-2 sm:grid-cols-[1fr_auto]">
          <legend className="mb-1 text-sm font-medium text-foreground">Blood glucose (mg/dL)</legend>
          <input inputMode="decimal" value={glucose} onChange={(e) => setGlucose(e.target.value)} placeholder="e.g. 92"
            aria-label="Blood glucose in mg/dL"
            className="h-9 rounded-md border border-bulkhead bg-transparent px-3 text-sm text-foreground" />
          <select value={context} onChange={(e) => setContext(e.target.value as typeof context)} aria-label="When the glucose was measured"
            className="h-9 rounded-md border border-bulkhead bg-panel-2 px-2 text-sm text-foreground">
            <option value="fasting">Fasting (8 h without food)</option>
            <option value="after_meal">After a meal</option>
            <option value="random">Random</option>
          </select>
        </fieldset>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-foreground">Mood today</legend>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Mood from 1 (very low) to 5 (very good)">
            {[1, 2, 3, 4, 5].map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mood === m} onClick={() => setMood(mood === m ? null : m)}
                className={cn("h-9 min-w-9 rounded-md border px-2 text-sm",
                  mood === m ? "border-telemetry bg-telemetry/10 text-foreground" : "border-bulkhead text-ink-2 hover:text-foreground")}>
                {m}
              </button>
            ))}
            <span className="self-center text-xs text-ink-3">1 very low, 5 very good</span>
          </div>
        </fieldset>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-foreground">Symptoms</legend>
          <div className="flex flex-wrap gap-1.5">
            <button type="button" aria-pressed={symptoms !== null && symptoms.length === 0}
              onClick={() => setSymptoms(symptoms !== null && symptoms.length === 0 ? null : [])}
              className={cn("rounded-md border px-2.5 py-1 text-sm",
                symptoms !== null && symptoms.length === 0 ? "border-nominal bg-nominal/10 text-foreground" : "border-bulkhead text-ink-2")}>
              Nothing today
            </button>
            {(summary?.symptom_catalogue ?? []).map((s) => (
              <button key={s.key} type="button" aria-pressed={symptoms?.includes(s.key) ?? false} onClick={() => toggle(s.key)}
                className={cn("rounded-md border px-2.5 py-1 text-sm",
                  symptoms?.includes(s.key) ? "border-caution bg-caution/10 text-foreground" : "border-bulkhead text-ink-2")}>
                {s.label}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-foreground">Note</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={2}
            className="w-full rounded-md border border-bulkhead bg-transparent px-3 py-2 text-sm text-foreground" />
        </label>
        <Button type="submit" disabled={add.isPending}><Send aria-hidden /> Record self-check</Button>
      </form>
    </DataCard>
  );
}

function History({ summary, pending }: { summary?: SelfCheckSummary; pending: boolean }) {
  return (
    <DataCard title="Recent self-checks" icon={<ClipboardCheck />} footer="Entered by hand; shown with the account that recorded them.">
      {pending || !summary ? <LoadingState rows={3} /> : summary.reports.length === 0 ? (
        <EmptyState title="No self-checks recorded yet">Record the first one with the form above.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-ink-3">
              <tr><th className="py-1.5 pr-3">Taken (UTC)</th><th className="pr-3">Glucose</th><th className="pr-3">Mood</th><th className="pr-3">Symptoms</th><th>Note</th></tr>
            </thead>
            <tbody className="divide-y divide-bulkhead">
              {summary.reports.map((r) => (
                <tr key={r.id} className="align-top text-ink-2">
                  <td className="py-1.5 pr-3 whitespace-nowrap">{utcDayTime(r.recorded_at)}</td>
                  <td className={cn("pr-3", r.glucose_status && TONE_CLASS[SELF_TONE[r.glucose_status] ?? "none"].text)}>
                    {r.glucose_mg_dl === null ? "—" : `${r.glucose_mg_dl} (${r.glucose_context?.replace("_", " ")})`}
                  </td>
                  <td className="pr-3">{r.mood ?? "—"}</td>
                  <td className="pr-3">{!r.symptoms_checked ? "—" : r.symptoms.length === 0 ? "none" : r.symptoms.map((s) => s.replaceAll("_", " ")).join(", ")}</td>
                  <td>{r.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DataCard>
  );
}
