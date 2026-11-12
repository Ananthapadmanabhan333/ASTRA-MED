"use client";

import { Bot, ClipboardPlus, ExternalLink, Send, ShieldAlert, Siren, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { useAsk, useAssistantStatus, useCreateReport } from "@/lib/api/medical-hooks";
import type { AssistantAnswer } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip } from "./common";

const SUGGESTIONS = [
  "How is Lukas doing right now?",
  "Explain the latest alert for AST-02",
  "Summarize heart rate trends for Maya over the last 30 days",
  "Show sleep for the last nights",
  "What space weather happened in the last 30 days?",
  "How is the personal baseline computed?",
  "Generate an incident report for the latest alert",
];

interface Turn {
  id: number;
  question: string;
  answer?: AssistantAnswer;
  error?: string;
}

function Answer({ a, turnId }: { a: AssistantAnswer; turnId: number }) {
  const [focus, setFocus] = useState<string | null>(null);
  const create = useCreateReport();
  const canWrite = useCan("reports:write");
  const router = useRouter();
  const anchor = (sid: string) => `t${turnId}-${sid}`;
  return (
    <div className="space-y-3">
      {a.escalation.required && (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-critical/50 bg-critical/10 px-3 py-2 text-sm">
          <Siren className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden />
          <div>
            <p className="font-medium text-critical">{a.escalation.message}</p>
            <ul className="mt-0.5 list-disc pl-5 text-xs text-ink-2">{a.escalation.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        </div>
      )}
      <ul className="space-y-2">
        {a.statements.filter((s) => !(s.kind === "safety" && a.escalation.required && s.text === a.escalation.message)).map((s, i) => (
          <li key={i} className={cn("text-sm leading-relaxed", s.kind === "safety" && "flex items-start gap-2 text-critical")}>
            {s.kind === "safety" ? <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> : <KindChip kind={s.kind} className="mr-1.5 align-middle" />}
            <span>{s.text}</span>
            {s.citations.map((c) => (
              <a
                key={c}
                href={`#${anchor(c)}`}
                onClick={() => setFocus(c)}
                className="ml-1 rounded border border-bulkhead px-1 text-[11px] text-telemetry hover:bg-telemetry/10"
                aria-label={`Source ${c}`}
              >
                {c}
              </a>
            ))}
          </li>
        ))}
      </ul>
      {a.missing_information.length > 0 && (
        <div className="rounded-md border border-caution/40 bg-caution/5 px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-caution"><TriangleAlert className="size-3.5" aria-hidden /> Missing information</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-2">{a.missing_information.map((m) => <li key={m}>{m}</li>)}</ul>
        </div>
      )}
      {a.actions.map((act) => (
        canWrite && (
          <Button key={act.alert_id} size="sm" variant="outline" disabled={create.isPending}
            onClick={() => create.mutate({ alert_id: act.alert_id }, {
              onSuccess: (r) => { toast.success("Draft incident report created"); router.push(`/reports?report=${r.id}`); },
              onError: (e) => toast.error(e.message),
            })}>
            <ClipboardPlus aria-hidden /> {act.label}
          </Button>
        )
      ))}
      {a.sources.length > 0 && (
        <details className="rounded-md border border-bulkhead/70" open={a.sources.some((s) => s.id.startsWith("S"))}>
          <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-2">Sources ({a.sources.length})</summary>
          <ol className="space-y-2 px-3 pb-3">
            {a.sources.map((s) => (
              <li key={s.id} id={anchor(s.id)} className={cn("rounded-md border p-2 text-xs", focus === s.id ? "border-telemetry" : "border-bulkhead/50")}>
                <p className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono font-semibold text-telemetry">{s.id}</span> <KindChip kind={s.kind} />
                  <span className="font-medium text-foreground">{s.title}</span>
                  {s.detail && <span className="text-ink-3">· {s.detail}</span>}
                  {s.score != null && <span className="text-ink-3">· relevance {s.score.toFixed(2)}</span>}
                </p>
                {s.excerpt && s.id.startsWith("S") && <blockquote className="mt-1 border-l-2 border-bulkhead pl-2 text-ink-2">{s.excerpt}</blockquote>}
                <p className="mt-1 flex flex-wrap gap-3">
                  {s.path && <span className="text-ink-3">{s.path}</span>}
                  {s.link && <Link href={s.link} className="text-telemetry hover:underline">Open in ASTRA-MED</Link>}
                  {s.url && <a href={s.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-telemetry hover:underline">NASA source <ExternalLink className="size-3" aria-hidden /></a>}
                </p>
              </li>
            ))}
          </ol>
        </details>
      )}
      <p className="text-[11px] text-ink-3">
        {a.mode === "claude" ? "Answered by Claude from the cited sources." : "Offline answer composed from the cited records and passages."}
        {a.model_note && ` ${a.model_note}`}
      </p>
    </div>
  );
}

export function AssistantView() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [focus, setFocus] = useState<string | null>(null);
  const ask = useAsk();
  const status = useAssistantStatus();
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function submit(q: string) {
    const text = q.trim();
    if (text.length < 2 || ask.isPending) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: text }]);
    setQuestion("");
    ask.mutate({ question: text, astronaut_id: focus }, {
      onSuccess: (answer) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, answer } : x))),
      onError: (e) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: e.message } : x))),
    });
  }

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
      <Panel raised className="xl:col-span-2" title="Conversation" description="Every statement is cited. Questions are not stored; the audit log keeps only a hash.">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <span>Focus</span>
            <CrewPicker value={focus} onChange={setFocus} allowAll label="Crew member in focus" />
          </div>
          <div aria-live="polite" className="max-h-[60vh] space-y-5 overflow-y-auto pr-1">
            {turns.length === 0 && (
              <div className="space-y-2">
                <p className="text-sm text-ink-2">Ask about measurements, trends, alerts, records, the space environment or how the system works.</p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" onClick={() => submit(s)} className="rounded-full border border-bulkhead px-2.5 py-1 text-xs text-ink-2 hover:border-telemetry hover:text-foreground">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((t) => (
              <div key={t.id} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-sidebar-accent px-3 py-2 text-sm">{t.question}</p>
                <div className="flex gap-2">
                  <Bot className="mt-0.5 size-5 shrink-0 text-telemetry" aria-hidden />
                  <div className="min-w-0 flex-1">
                    {t.answer ? <Answer a={t.answer} turnId={t.id} /> : t.error ? <p role="alert" className="text-sm text-critical">{t.error}</p> : <p className="text-sm text-ink-3">Looking through the records and documentation…</p>}
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); submit(question); }} className="flex items-end gap-2">
            <label htmlFor="ask" className="sr-only">Question</label>
            <textarea
              id="ask"
              rows={2}
              maxLength={1000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(question); } }}
              placeholder="e.g. Why did the desaturation alert fire for AST-02?"
              className="min-h-[2.75rem] flex-1 resize-y rounded-md border border-input bg-abyss px-3 py-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <Button type="submit" size="lg" disabled={ask.isPending || question.trim().length < 2}><Send aria-hidden /> Ask</Button>
          </form>
        </div>
      </Panel>
      <div className="space-y-5">
        <Panel title="How the assistant answers">
          <ul className="space-y-1.5 text-sm text-ink-2">
            <li>Answers come only from cited data records and retrieved passages.</li>
            <li>It does not diagnose, recommend treatment or prescribe medication.</li>
            <li>It says what information is missing and escalates potentially serious situations to the flight surgeon.</li>
            <li>Labels separate simulated data, derived statistics, experimental model output, real NASA data and documentation.</li>
          </ul>
        </Panel>
        <Panel title="Knowledge sources">
          {status.data ? (
            <div className="space-y-2 text-sm">
              <p>Mode: <span className="font-medium">{String(status.data.mode.mode)}</span>{status.data.mode.reason ? <span className="text-ink-3"> ({String(status.data.mode.reason)})</span> : null}</p>
              <ul className="space-y-1">
                {status.data.source_types.map((s) => (
                  <li key={String(s.key)} className="flex justify-between gap-3"><span>{String(s.label)}</span><span className="tabular-nums text-ink-3">{String(s.passages)} passages</span></li>
                ))}
              </ul>
              {status.data.reference_note && <p className="rounded-md border border-caution/40 bg-caution/5 p-2 text-xs text-ink-2">{status.data.reference_note}</p>}
            </div>
          ) : <p className="text-sm text-ink-3">Loading…</p>}
        </Panel>
      </div>
    </div>
  );
}
