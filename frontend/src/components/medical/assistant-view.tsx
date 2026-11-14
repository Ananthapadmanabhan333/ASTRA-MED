"use client";

import {
  Bot,
  ClipboardPlus,
  ExternalLink,
  FileText,
  MessageSquare,
  Plus,
  Send,
  ShieldAlert,
  Siren,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { Button } from "@/components/ui/button";
import { useAsk, useAssistantStatus, useCreateReport } from "@/lib/api/medical-hooks";
import type { AssistantAnswer, StatementKind } from "@/lib/api/types";
import { useCan } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

import { CrewPicker, KindChip } from "./common";

const SUGGESTIONS = [
  "Why is Dr. Alex Carter's heart rate elevated?",
  "How is Lukas doing right now?",
  "Explain the latest alert for AST-02",
  "Summarize heart rate trends for Maya over the last 30 days",
  "Show sleep for the last nights",
  "What space weather happened in the last 30 days?",
  "Generate an incident report for the latest alert",
];

interface DisplaySource {
  id: string;
  kind: StatementKind;
  title: string;
  detail?: string | null;
  score?: number | null;
  excerpt?: string | null;
  path?: string | null;
  link?: string | null;
  url?: string | null;
}

interface DisplayAnswer {
  mode: "extractive" | "claude";
  model_note?: string | null;
  escalation: {
    required: boolean;
    message?: string | null;
    reasons: string[];
  };
  missing_information: string[];
  actions: AssistantAnswer["actions"];
  statements: {
    kind: StatementKind;
    text: string;
    citations: string[];
  }[];
  sources: DisplaySource[];
}

interface Turn {
  id: number;
  question: string;
  answer?: DisplayAnswer;
  error?: string;
}

interface ChatSession {
  id: string;
  title: string;
  timestamp: string;
  astronautId: string | null;
  turns: Turn[];
}

const INITIAL_SESSIONS: ChatSession[] = [
  {
    id: "sess-hr",
    title: "HR elevation analysis",
    timestamp: "Today, 14:20",
    astronautId: "AST-01",
    turns: [
      {
        id: 101,
        question: "Why is Dr. Alex Carter's heart rate elevated?",
        answer: {
          mode: "extractive",
          model_note: "Synthesized from personal baseline telemetry & NASA HRP reference corpus.",
          escalation: { required: false, message: null, reasons: [] },
          missing_information: [],
          actions: [],
          statements: [
            {
              kind: "derived",
              text: "The heart rate is 12% above the personal baseline (82 bpm → 92 bpm). Based on the current data:",
              citations: ["S1", "D1"],
            },
            {
              kind: "data",
              text: "Recent increase in physical activity (+38%) during scheduled resistive exercise.",
              citations: ["D1"],
            },
            {
              kind: "data",
              text: "Reduced sleep duration (6h 12m vs baseline 7h 30m) over the last 24-hour cycle.",
              citations: ["D2"],
            },
            {
              kind: "nasa",
              text: "No significant space weather or radiation event impacting cabin shielding.",
              citations: ["S2"],
            },
            {
              kind: "documentation",
              text: "This is likely a temporary physiological response. Continue monitoring for the next 6–12 hours.",
              citations: ["S1", "S2"],
            },
          ],
          sources: [
            {
              id: "S1",
              kind: "documentation",
              title: "NASA HRP",
              detail: "Human Research Program Cardiovascular Adaptation Standard",
              score: 0.94,
              excerpt: "Transient post-exercise tachycardia (+10–15% above in-flight baseline) paired with circadian sleep debt typically resolves within 6–12 hours of rest.",
              link: "/space/explorer",
            },
            {
              id: "S2",
              kind: "documentation",
              title: "Spaceflight Physiology Review",
              detail: "Autonomic Regulation in Microgravity (ISS Cohort)",
              score: 0.89,
              excerpt: "Shortened sleep duration (<6.5h) elevates sympathetic tone and resting heart rate by 4–9 bpm in orbital crews.",
              link: "/twin?astronaut=AST-01",
            },
            {
              id: "D1",
              kind: "derived",
              title: "Digital Twin Baseline Record (AST-01)",
              detail: "Personal baseline 82 bpm vs current 92 bpm",
              link: "/twin?astronaut=AST-01",
            },
            {
              id: "D2",
              kind: "data",
              title: "Sleep Telemetry Log (AST-01)",
              detail: "Last night duration 6h 12m (efficiency 84%)",
              link: "/crew/history?astronaut=AST-01",
            },
          ],
        },
      },
    ],
  },
  {
    id: "sess-sleep",
    title: "Sleep pattern summary",
    timestamp: "Today, 11:05",
    astronautId: "AST-02",
    turns: [
      {
        id: 102,
        question: "Show sleep pattern summary for the crew over the last 7 nights",
        answer: {
          mode: "extractive",
          escalation: { required: false, message: null, reasons: [] },
          missing_information: [],
          actions: [],
          statements: [
            {
              kind: "derived",
              text: "Crew mean sleep duration over the past 7 nights is 6.8 hours with 87% sleep efficiency.",
              citations: ["S1"],
            },
            {
              kind: "data",
              text: "Circadian phase alignment remains within ±22 minutes of the 06:00 UTC wake schedule.",
              citations: ["S2"],
            },
          ],
          sources: [
            {
              id: "S1",
              kind: "derived",
              title: "NASA HRP",
              detail: "Circadian & Sleep Countermeasures Protocol",
              score: 0.91,
              link: "/crew/history",
            },
            {
              id: "S2",
              kind: "documentation",
              title: "Spaceflight Physiology Review",
              detail: "ISS Slam-Shift & Light Therapy Guidelines",
              score: 0.86,
              link: "/twin",
            },
          ],
        },
      },
    ],
  },
  {
    id: "sess-rad",
    title: "Radiation exposure",
    timestamp: "Yesterday, 22:10",
    astronautId: null,
    turns: [
      {
        id: 103,
        question: "What is the current radiation exposure and solar flare impact?",
        answer: {
          mode: "extractive",
          escalation: { required: false, message: null, reasons: [] },
          missing_information: [],
          actions: [],
          statements: [
            {
              kind: "nasa",
              text: "Current dose rate is 0.34 mSv/day with cumulative mission exposure at 14.2 mSv (14% of 100 mSv reference limit).",
              citations: ["S1"],
            },
            {
              kind: "nasa",
              text: "A C1.2 Solar Flare (Moderate) peaked at 11:28 UTC; geomagnetic index Kp = 2 (Quiet).",
              citations: ["S2"],
            },
          ],
          sources: [
            {
              id: "S1",
              kind: "nasa",
              title: "NASA HRP",
              detail: "ISS RAD Dosimetry & Career Exposure Limits",
              score: 0.95,
              link: "/radiation",
            },
            {
              id: "S2",
              kind: "nasa",
              title: "DONKI Space Weather Feed",
              detail: "Solar Flare & Geomagnetic Storm Telemetry",
              score: 0.92,
              link: "/space",
            },
          ],
        },
      },
    ],
  },
  {
    id: "sess-report",
    title: "Mission health report",
    timestamp: "Nov 12, 18:30",
    astronautId: null,
    turns: [
      {
        id: 104,
        question: "Summarize the weekly mission health report status for all 4 astronauts.",
        answer: {
          mode: "extractive",
          escalation: { required: false, message: null, reasons: [] },
          missing_information: [],
          actions: [],
          statements: [
            {
              kind: "derived",
              text: "3 of 4 crew members remain within nominal physiological corridors; AST-01 is on active HR monitoring.",
              citations: ["S1"],
            },
            {
              kind: "documentation",
              text: "Incident Report R-1047 has been logged and reviewed by Flight Surgeon.",
              citations: ["S2"],
            },
          ],
          sources: [
            {
              id: "S1",
              kind: "derived",
              title: "NASA HRP",
              detail: "Weekly Crew Health Surveillance Summary",
              score: 0.9,
              link: "/reports",
            },
            {
              id: "S2",
              kind: "documentation",
              title: "Spaceflight Physiology Review",
              detail: "Flight Surgeon Handover Protocol",
              score: 0.85,
              link: "/reports",
            },
          ],
        },
      },
    ],
  },
];

function Answer({ a, turnId }: { a: DisplayAnswer; turnId: number }) {
  const [focus, setFocus] = useState<string | null>(null);
  const create = useCreateReport();
  const canWrite = useCan("reports:write");
  const router = useRouter();
  const anchor = (sid: string) => `t${turnId}-${sid}`;

  const leadStatement = a.statements[0];
  const bulletStatements = a.statements
    .slice(1)
    .filter((s) => !(s.kind === "safety" && a.escalation.required && s.text === a.escalation.message));

  return (
    <div className="space-y-3 rounded-xl border border-bulkhead/80 bg-[#0a1628]/90 p-4 shadow-md">
      {a.escalation.required && (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-critical/50 bg-critical/10 px-3 py-2 text-sm">
          <Siren className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden />
          <div>
            <p className="font-medium text-critical">{a.escalation.message}</p>
            <ul className="mt-0.5 list-disc pl-5 text-xs text-ink-2">
              {a.escalation.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {leadStatement && (
        <p className="text-sm leading-relaxed text-foreground">
          {leadStatement.text}
          {leadStatement.citations.map((c) => (
            <a
              key={c}
              href={`#${anchor(c)}`}
              onClick={() => setFocus(c)}
              className="ml-1.5 rounded border border-telemetry/40 bg-telemetry/10 px-1.5 py-0.5 font-mono text-[10px] text-telemetry hover:bg-telemetry/20"
            >
              {c}
            </a>
          ))}
        </p>
      )}

      {bulletStatements.length > 0 && (
        <ul className="space-y-1.5 pl-4">
          {bulletStatements.map((s, i) => (
            <li
              key={i}
              className={cn(
                "list-disc text-sm leading-relaxed text-ink-2 marker:text-telemetry",
                s.kind === "safety" && "list-none flex items-start gap-2 text-critical",
              )}
            >
              {s.kind === "safety" && <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />}
              <span>{s.text}</span>
              <KindChip kind={s.kind} className="ml-2 align-middle" />
              {s.citations.map((c) => (
                <a
                  key={c}
                  href={`#${anchor(c)}`}
                  onClick={() => setFocus(c)}
                  className="ml-1 rounded border border-bulkhead px-1 text-[10px] text-telemetry hover:bg-telemetry/10"
                  aria-label={`Source ${c}`}
                >
                  {c}
                </a>
              ))}
            </li>
          ))}
        </ul>
      )}

      {a.missing_information.length > 0 && (
        <div className="rounded-md border border-caution/40 bg-caution/5 px-3 py-2">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-caution">
            <TriangleAlert className="size-3.5" aria-hidden /> Missing information
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-2">
            {a.missing_information.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {a.actions.map(
        (act) =>
          canWrite && (
            <Button
              key={act.alert_id}
              size="sm"
              variant="outline"
              disabled={create.isPending}
              onClick={() =>
                create.mutate(
                  { alert_id: act.alert_id },
                  {
                    onSuccess: (r) => {
                      toast.success("Draft incident report created");
                      router.push(`/reports?report=${r.id}`);
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              <ClipboardPlus aria-hidden /> {act.label}
            </Button>
          ),
      )}

      {a.sources.length > 0 && (
        <div className="space-y-2 border-t border-bulkhead/60 pt-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-ink-3">Sources:</span>
            {a.sources.map((s) => (
              <a
                key={s.id}
                href={`#${anchor(s.id)}`}
                onClick={() => setFocus(s.id === focus ? null : s.id)}
                className="inline-flex items-center gap-1.5 rounded-md border border-bulkhead bg-abyss/80 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:border-telemetry/50 hover:text-telemetry"
              >
                <FileText className="size-3 text-telemetry" aria-hidden />
                {s.title}
              </a>
            ))}
          </div>

          <details className="rounded-md border border-bulkhead/60 bg-abyss/40">
            <summary className="cursor-pointer px-3 py-1.5 text-[11px] font-medium text-ink-3 hover:text-foreground">
              Inspect full citation provenance ({a.sources.length} records)
            </summary>
            <ol className="space-y-2 px-3 pb-3 pt-1">
              {a.sources.map((s) => (
                <li
                  key={s.id}
                  id={anchor(s.id)}
                  className={cn(
                    "rounded-md border p-2 text-xs",
                    focus === s.id ? "border-telemetry bg-telemetry/5" : "border-bulkhead/50",
                  )}
                >
                  <p className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono font-semibold text-telemetry">{s.id}</span> <KindChip kind={s.kind} />
                    <span className="font-medium text-foreground">{s.title}</span>
                    {s.detail && <span className="text-ink-3">· {s.detail}</span>}
                    {s.score != null && <span className="text-ink-3">· relevance {s.score.toFixed(2)}</span>}
                  </p>
                  {s.excerpt && (
                    <blockquote className="mt-1 border-l-2 border-bulkhead pl-2 text-ink-2">{s.excerpt}</blockquote>
                  )}
                  <p className="mt-1 flex flex-wrap gap-3">
                    {s.path && <span className="text-ink-3">{s.path}</span>}
                    {s.link && (
                      <Link href={s.link} className="text-telemetry hover:underline">
                        Open in ASTRA-MED
                      </Link>
                    )}
                    {s.url && (
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-telemetry hover:underline"
                      >
                        NASA source <ExternalLink className="size-3" aria-hidden />
                      </a>
                    )}
                  </p>
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}

      <p className="text-[11px] text-ink-3">
        {a.mode === "claude"
          ? "Answered by Claude from the cited sources."
          : "Offline answer composed from the cited records and passages."}
        {a.model_note && ` ${a.model_note}`}
      </p>
    </div>
  );
}

export function AssistantView() {
  const [sessions, setSessions] = useState<ChatSession[]>(INITIAL_SESSIONS);
  const [activeSessionId, setActiveSessionId] = useState<string>(INITIAL_SESSIONS[0].id);
  const [question, setQuestion] = useState("");
  const [focus, setFocus] = useState<string | null>("AST-01");
  const ask = useAsk();
  const status = useAssistantStatus();
  const nextId = useRef(200);
  const endRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];
  const turns = activeSession?.turns ?? [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  function startNewChat() {
    const newId = `sess-${Date.now()}`;
    const newSession: ChatSession = {
      id: newId,
      title: "New consultation",
      timestamp: "Just now",
      astronautId: focus,
      turns: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
    setQuestion("");
  }

  function submit(q: string) {
    const text = q.trim();
    if (text.length < 2 || ask.isPending) return;
    const id = nextId.current++;
    const shortTitle = text.length > 28 ? `${text.slice(0, 28)}…` : text;

    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeSession.id
          ? {
              ...s,
              title: s.turns.length === 0 ? shortTitle : s.title,
              timestamp: "Just now",
              turns: [...s.turns, { id, question: text }],
            }
          : s,
      ),
    );
    setQuestion("");
    ask.mutate(
      { question: text, astronaut_id: focus },
      {
        onSuccess: (answer) =>
          setSessions((prev) =>
            prev.map((s) =>
              s.id === activeSession.id
                ? {
                    ...s,
                    turns: s.turns.map((x) => (x.id === id ? { ...x, answer } : x)),
                  }
                : s,
            ),
          ),
        onError: (e) =>
          setSessions((prev) =>
            prev.map((s) =>
              s.id === activeSession.id
                ? {
                    ...s,
                    turns: s.turns.map((x) => (x.id === id ? { ...x, error: e.message } : x)),
                  }
                : s,
            ),
          ),
      },
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left Chat History Sidebar matching Screen 7 */}
        <div className="flex flex-col justify-between rounded-xl border border-bulkhead bg-hull/80 p-3.5 lg:col-span-3">
          <div className="space-y-4">
            <button
              type="button"
              onClick={startNewChat}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-telemetry/50 bg-telemetry/15 px-3 py-2.5 text-xs font-semibold text-telemetry shadow-[0_0_15px_rgba(61,216,234,0.15)] transition-colors hover:bg-telemetry/25"
            >
              <Plus className="size-4" aria-hidden /> New Chat
            </button>

            <div>
              <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
                Chat History
              </p>
              <div className="space-y-1.5">
                {sessions.map((sess) => {
                  const isActive = sess.id === activeSession.id;
                  return (
                    <button
                      key={sess.id}
                      type="button"
                      onClick={() => {
                        setActiveSessionId(sess.id);
                        if (sess.astronautId !== undefined) setFocus(sess.astronautId);
                      }}
                      className={cn(
                        "flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-all",
                        isActive
                          ? "border-telemetry/50 bg-telemetry/10 text-foreground"
                          : "border-transparent bg-abyss/40 text-ink-2 hover:border-bulkhead hover:bg-abyss/80 hover:text-foreground",
                      )}
                    >
                      <MessageSquare
                        className={cn("mt-0.5 size-3.5 shrink-0", isActive ? "text-telemetry" : "text-ink-3")}
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-semibold">{sess.title}</p>
                        <p className="mt-0.5 text-[10px] text-ink-3">{sess.timestamp}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Knowledge Corpus Status */}
          <div className="mt-6 rounded-lg border border-bulkhead/70 bg-abyss/60 p-3 text-xs">
            <p className="flex items-center gap-1.5 font-semibold text-foreground">
              <Sparkles className="size-3.5 text-telemetry" aria-hidden /> RAG Knowledge Engine
            </p>
            {status.data ? (
              <div className="mt-1.5 space-y-1 text-[11px] text-ink-3">
                <p>
                  Mode: <span className="font-mono text-telemetry">{String(status.data.mode.mode)}</span>
                </p>
                {status.data.source_types.slice(0, 3).map((s) => (
                  <div key={String(s.key)} className="flex justify-between">
                    <span>{String(s.label)}</span>
                    <span className="font-mono text-ink-2">{String(s.passages)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-[11px] text-ink-3">Corpus ready · Cited telemetry & NASA HRP</p>
            )}
          </div>
        </div>

        {/* Right Main AI Medical Assistant Panel */}
        <div className="flex flex-col justify-between rounded-xl border border-bulkhead bg-hull/80 p-5 lg:col-span-9">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-bulkhead/70 pb-4">
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground">AI Medical Assistant</h1>
              <p className="text-xs text-ink-2">Your mission health copilot — every statement is grounded in cited records</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-ink-3">
              <span>Focus:</span>
              <CrewPicker value={focus} onChange={setFocus} allowAll label="Crew member in focus" />
            </div>
          </div>

          {/* Conversation Turns */}
          <div aria-live="polite" className="my-4 max-h-[56vh] min-h-[340px] space-y-5 overflow-y-auto pr-1">
            {turns.length === 0 && (
              <div className="space-y-3 rounded-xl border border-bulkhead/60 bg-abyss/40 p-4">
                <p className="text-sm text-ink-2">
                  Ask about crew vital signs, personal baselines, sleep quality, radiation exposure, or NASA Human Research Program protocols.
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => submit(s)}
                      className="rounded-full border border-bulkhead bg-hull/60 px-3 py-1.5 text-xs text-ink-2 transition-colors hover:border-telemetry hover:text-foreground"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((t) => (
              <div key={t.id} className="space-y-3">
                <div className="flex justify-end">
                  <p className="max-w-[85%] rounded-xl border border-telemetry/40 bg-telemetry/15 px-4 py-2.5 text-sm font-medium text-foreground shadow-sm">
                    {t.question}
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-telemetry/40 bg-telemetry/15 text-telemetry">
                    <Bot className="size-4" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    {t.answer ? (
                      <Answer a={t.answer} turnId={t.id} />
                    ) : t.error ? (
                      <p role="alert" className="rounded-lg border border-critical/40 bg-critical/10 p-3 text-sm text-critical">
                        {t.error}
                      </p>
                    ) : (
                      <p className="rounded-lg border border-bulkhead/60 bg-abyss/50 p-3 text-sm text-ink-3">
                        Looking through crew telemetry records and NASA HRP documentation…
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          {/* Prompt Input Bar */}
          <div className="space-y-2.5 border-t border-bulkhead/70 pt-3">
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.slice(0, 4).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => submit(s)}
                  className="rounded-md border border-bulkhead/70 bg-abyss/50 px-2.5 py-1 text-[11px] text-ink-3 transition-colors hover:border-telemetry/40 hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                submit(question);
              }}
              className="flex items-center gap-2"
            >
              <label htmlFor="ask" className="sr-only">
                Question
              </label>
              <input
                id="ask"
                type="text"
                maxLength={1000}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about astronaut health, environment, or mission data..."
                className="h-11 flex-1 rounded-lg border border-bulkhead bg-abyss/90 px-4 text-sm text-foreground placeholder:text-ink-3 outline-none focus:border-telemetry"
              />
              <Button
                type="submit"
                size="lg"
                disabled={ask.isPending || question.trim().length < 2}
                className="h-11 bg-telemetry px-4 text-abyss hover:bg-telemetry/90"
              >
                <Send className="size-4" aria-hidden /> Ask
              </Button>
            </form>
          </div>
        </div>
      </div>

      {/* Safety & Grounding Governance Footer */}
      <Panel title="Clinical Safety & Retrieval Governance">
        <ul className="grid grid-cols-1 gap-2 text-xs text-ink-2 md:grid-cols-2 lg:grid-cols-4">
          <li className="rounded-md border border-bulkhead/50 bg-abyss/40 p-2.5">
            Answers come exclusively from cited data records and retrieved NASA HRP passages.
          </li>
          <li className="rounded-md border border-bulkhead/50 bg-abyss/40 p-2.5">
            Does not diagnose, recommend treatment, or prescribe medication.
          </li>
          <li className="rounded-md border border-bulkhead/50 bg-abyss/40 p-2.5">
            Explicitly flags missing information and escalates serious conditions to the Flight Surgeon.
          </li>
          <li className="rounded-md border border-bulkhead/50 bg-abyss/40 p-2.5">
            Distinguishes simulated telemetry, derived statistics, experimental ML output, and real NASA data.
          </li>
        </ul>
      </Panel>
    </div>
  );
}
