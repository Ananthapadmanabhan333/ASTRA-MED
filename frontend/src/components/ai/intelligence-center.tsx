"use client";

import { BrainCircuit, ChevronRight } from "lucide-react";
import Link from "next/link";

import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { useAiStatus, useCrewRisk, useRiskAssessment } from "@/lib/api/hooks";
import { useParamState } from "@/components/medical/common";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AnomalyTimeline } from "./anomaly-timeline";
import { BaselinePanel } from "./baseline-panel";
import { CONCERN, ConcernPill } from "./concern";
import { ExplanationView } from "./explanation-view";
import { ForecastPanel } from "./forecast-panel";
import { RiskCard, WarningQueue } from "./risk-board";

function ExperimentalNotice() {
  const status = useAiStatus();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-dashed border-caution/50 bg-caution/5 px-4 py-3 text-sm">
      <BrainCircuit className="size-5 shrink-0 text-caution" aria-hidden />
      <p className="min-w-0 flex-1 basis-64 text-ink-2">
        <span className="font-medium text-foreground">Experimental decision support.</span> Models are trained and evaluated on
        simulated data only; no output here is a diagnosis or a clinically validated prediction.
        {status.data?.model_version && <span className="text-ink-3"> Model {status.data.model_version}.</span>}
      </p>
      <Button asChild size="sm" variant="outline">
        <Link href="/intelligence/models">
          Model evaluation <ChevronRight aria-hidden />
        </Link>
      </Button>
    </div>
  );
}

function RiskDetail({ astronautId }: { astronautId: string }) {
  const q = useRiskAssessment(astronautId);
  if (q.isPending) return <LoadingState label="Assessing risk" rows={5} />;
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const r = q.data!;
  const c = CONCERN[r.category];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-xs text-ink-3">Health score</p>
          <p className={cn("readout text-6xl font-semibold", c.text)}>{r.health_score}</p>
        </div>
        <div className="space-y-1.5 pb-1">
          <ConcernPill category={r.category} />
          <p className="text-sm text-ink-2">Risk {fmt(r.risk_score, 0)} of 100</p>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 pb-1 text-sm">
          <dt className="text-ink-3">Anomaly ensemble</dt>
          <dd>{r.anomaly.available ? `${fmt(r.anomaly.score, 2)}x threshold, ${r.anomaly.votes} of ${r.anomaly.n_detectors} detectors` : "models unavailable"}</dd>
          <dt className="text-ink-3">Flagged for</dt>
          <dd>{r.anomaly.available ? `${fmt(r.anomaly.flagged_minutes, 0)} min` : "—"}</dd>
        </dl>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <ExplanationView explanation={r.explanation} />
        <div>
          <h3 className="text-sm font-medium">Prioritised warnings for {r.name}</h3>
          {r.warnings.length === 0 ? (
            <p className="mt-2 text-sm text-ink-2">No warnings. All rules are quiet for this crew member.</p>
          ) : (
            <ol className="mt-2 space-y-2.5">
              {r.warnings.map((w) => (
                <li key={w.title} className="grid grid-cols-[1.5rem_1fr] gap-2">
                  <span className="readout text-lg text-ink-3">{w.priority}</span>
                  <div>
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {w.title} <span className="text-xs font-normal text-ink-3">{fmt(w.points, 0)} pts, {w.source}</span>
                    </p>
                    <p className="text-xs text-ink-2">{w.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}

export function IntelligenceCenter() {
  const crew = useCrewRisk();
  const [selected, setSelected] = useParamState("astronaut");
  const active = selected ?? crew.data?.crew[0]?.astronaut_id ?? null;
  const activeName = crew.data?.crew.find((c) => c.astronaut_id === active)?.name ?? active ?? "";

  return (
    <div className="space-y-5">
      <ExperimentalNotice />

      <section aria-label="Crew health scores">
        {crew.isPending ? (
          <LoadingState label="Assessing crew" rows={2} />
        ) : crew.error && !crew.data ? (
          <ErrorState error={crew.error} onRetry={() => crew.refetch()} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {crew.data!.crew.map((c) => (
              <RiskCard key={c.astronaut_id} summary={c} selected={c.astronaut_id === active} onSelect={() => setSelected(c.astronaut_id)} />
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-5 xl:grid-cols-3">
        <Panel title="Early warning queue" description="Crew-wide, highest priority first. Select one to focus.">
          {crew.data ? <WarningQueue crew={crew.data.crew} onSelect={setSelected} /> : <LoadingState rows={4} />}
        </Panel>
        <Panel
          raised
          className="xl:col-span-2"
          title={activeName ? `Risk assessment: ${activeName}` : "Risk assessment"}
          description="Transparent rules combine baseline deviation, anomaly agreement, forecast trend and open alerts."
        >
          {active ? <RiskDetail astronautId={active} /> : <LoadingState rows={4} />}
        </Panel>
      </div>

      {active && (
        <>
          <ForecastPanel astronautId={active} name={activeName} />
          <div className="grid gap-5 2xl:grid-cols-2">
            <AnomalyTimeline astronautId={active} name={activeName} />
            <BaselinePanel astronautId={active} name={activeName} />
          </div>
        </>
      )}
    </div>
  );
}
