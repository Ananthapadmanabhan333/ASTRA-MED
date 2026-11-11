"use client";

import { FlaskConical, Lightbulb } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AstronautSwitcher } from "@/components/crew/astronaut-switcher";
import { Panel } from "@/components/data/panel";
import { EmptyState, QueryView } from "@/components/data/states";
import { StatusPill } from "@/components/status/status";
import { useAstronauts, useInsights } from "@/lib/api/hooks";
import type { Insight } from "@/lib/api/types";

const CATEGORY: Record<Insight["category"], string> = {
  sleep: "Sleep",
  circadian: "Circadian",
  cardiovascular: "Cardiovascular",
  respiratory: "Respiratory",
  radiation: "Radiation",
  countermeasures: "Countermeasures",
  alerts: "Alert pattern",
};

function InsightItem({ insight, name }: { insight: Insight; name?: string }) {
  return (
    <article className="border-b border-bulkhead/60 py-4 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        {insight.severity === "info" ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-bulkhead px-2 py-0.5 text-xs text-ink-2">
            <FlaskConical className="size-3.5" aria-hidden /> Info
          </span>
        ) : (
          <StatusPill status={insight.severity} />
        )}
        <span className="text-xs text-ink-3">{CATEGORY[insight.category]}</span>
        {name && (
          <Link href={`/crew/${insight.astronaut_id}`} className="text-xs text-ink-2 hover:text-telemetry">
            {name}
          </Link>
        )}
      </div>
      <h3 className="mt-2 font-heading text-lg font-semibold">{insight.title}</h3>
      <p className="mt-0.5 max-w-prose text-sm text-ink-2">{insight.summary}</p>
      <div className="mt-3 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <h4 className="text-xs font-medium text-ink-3">Evidence</h4>
          <dl className="mt-1 space-y-0.5 text-sm">
            {insight.evidence.map((e) => (
              <div key={e.label} className="flex justify-between gap-4">
                <dt className="text-ink-2">{e.label}</dt>
                <dd className="text-right tabular-nums">{e.value}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h4 className="text-xs font-medium text-ink-3">Suggested review</h4>
          <p className="mt-1 text-sm">{insight.suggested_action}</p>
        </div>
      </div>
    </article>
  );
}

export function InsightsView() {
  const [who, setWho] = useState("all");
  const crew = useAstronauts();
  const insights = useInsights(who === "all" ? undefined : who);
  const names = new Map(crew.data?.map((a) => [a.id, a.name]));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        {crew.data && <AstronautSwitcher crew={crew.data} value={who} onChange={setWho} includeAll label="Filter by crew member" />}
      </div>
      <Panel
        raised
        title="Generated risk insights"
        description="Produced by a transparent rule engine from simulated data. Each one lists the evidence behind it. They flag patterns for a flight surgeon to review; they are not diagnoses or treatment advice."
      >
        <QueryView
          query={insights}
          isEmpty={(d) => d.length === 0}
          empty={
            <EmptyState title="No review rules are triggered" icon={<Lightbulb className="size-5" />}>
              Insights appear when sleep, heart-rate trends, recurring alerts, exercise or radiation dose cross a rule.
            </EmptyState>
          }
        >
          {(data) => (
            <div>
              {data.map((i) => (
                <InsightItem key={i.id} insight={i} name={names.get(i.astronaut_id)} />
              ))}
            </div>
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
