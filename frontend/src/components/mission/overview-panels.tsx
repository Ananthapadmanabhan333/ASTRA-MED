"use client";

import { ChevronRight, FlaskConical, Lightbulb } from "lucide-react";
import Link from "next/link";

import { AlertList } from "@/components/alerts/alert-list";
import { Panel } from "@/components/data/panel";
import { EmptyState, QueryView } from "@/components/data/states";
import { StatusIcon } from "@/components/status/status";
import { Button } from "@/components/ui/button";
import { useAlerts, useAstronauts, useInsights, useRadiation, useSimulationEvents } from "@/lib/api/hooks";
import { crewColor, surname } from "@/lib/crew";
import { duration, fmt } from "@/lib/format";
import { SCENARIO_LABEL } from "@/lib/metrics";
import { useNow } from "@/lib/use-now";

const OPEN = { status: ["active", "acknowledged"] as ("active" | "acknowledged")[] };

export function OpenAlertsPanel() {
  const alerts = useAlerts(OPEN);
  const crew = useAstronauts();
  return (
    <Panel
      title="Open alerts"
      description="Alerts stay open until an operator resolves them."
      actions={
        <Button asChild size="sm" variant="ghost">
          <Link href="/alerts">
            All alerts <ChevronRight aria-hidden />
          </Link>
        </Button>
      }
    >
      <QueryView
        query={alerts}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No open alerts">
            All crew values are inside prototype limits. Start a test scenario from Anomalies & tests to
            exercise the alert path.
          </EmptyState>
        }
      >
        {(data) => <AlertList alerts={data.slice(0, 6)} crew={crew.data} compact />}
      </QueryView>
    </Panel>
  );
}

export function RadiationBriefPanel() {
  const rad = useRadiation(7);
  return (
    <Panel
      title="Career radiation dose"
      description="Share of the 600 mSv NASA reference limit"
      actions={
        <Button asChild size="sm" variant="ghost">
          <Link href="/radiation">
            Details <ChevronRight aria-hidden />
          </Link>
        </Button>
      }
    >
      <QueryView query={rad}>
        {(data) => (
          <ul className="space-y-3">
            {data.crew.map((c) => (
              <li key={c.astronaut_id}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="text-ink-2">{surname(c.name)}</span>
                  <span className="tabular-nums">
                    {fmt(c.career_dose_msv, 0)} mSv{" "}
                    <span className="text-ink-3">({fmt(c.career_limit_pct, 0)}%)</span>
                  </span>
                </div>
                <div
                  className="mt-1 h-1.5 overflow-hidden rounded-full bg-bulkhead/70"
                  role="meter"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={c.career_limit_pct}
                  aria-label={`${c.name} career dose, percent of reference limit`}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.min(100, c.career_limit_pct)}%`, background: crewColor(c.astronaut_id) }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Panel>
  );
}

export function ActiveScenariosPanel() {
  const events = useSimulationEvents();
  const crew = useAstronauts();
  const now = useNow(1000);
  const names = new Map(crew.data?.map((a) => [a.id, a.name]));
  return (
    <Panel
      title="Running test scenarios"
      actions={
        <Button asChild size="sm" variant="ghost">
          <Link href="/anomalies">
            Open console <ChevronRight aria-hidden />
          </Link>
        </Button>
      }
    >
      <QueryView
        query={events}
        isEmpty={(d) => !d.some((e) => e.active)}
        empty={<p className="text-sm text-ink-2">No test scenarios are running.</p>}
      >
        {(data) => (
          <ul className="space-y-2">
            {data
              .filter((e) => e.active)
              .map((e) => (
                <li key={e.id} className="flex items-start gap-2 text-sm">
                  <FlaskConical className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
                  <div className="min-w-0">
                    <p className="text-foreground">{SCENARIO_LABEL[e.scenario] ?? e.label}</p>
                    <p className="text-xs text-ink-2">
                      {e.astronaut_id ? names.get(e.astronaut_id) ?? e.astronaut_id : "Whole crew"}
                      {now && `, ${duration((Date.parse(e.ends_at) - now) / 1000)} left`}
                      {e.triggered_by === "random" && ", started by simulator"}
                    </p>
                  </div>
                </li>
              ))}
          </ul>
        )}
      </QueryView>
    </Panel>
  );
}

export function TopInsightsPanel() {
  const insights = useInsights();
  const crew = useAstronauts();
  const names = new Map(crew.data?.map((a) => [a.id, a.name]));
  return (
    <Panel
      title="Generated insights"
      description="Rule-based decision support, not diagnoses"
      actions={
        <Button asChild size="sm" variant="ghost">
          <Link href="/insights">
            All insights <ChevronRight aria-hidden />
          </Link>
        </Button>
      }
    >
      <QueryView
        query={insights}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState title="No insights right now" icon={<Lightbulb className="size-5" />}>
            Insights appear when sleep, trends, alerts or dose cross their review rules.
          </EmptyState>
        }
      >
        {(data) => (
          <ul className="space-y-3">
            {data.slice(0, 4).map((i) => (
              <li key={i.id} className="flex gap-2.5">
                {i.severity === "info" ? (
                  <FlaskConical className="mt-0.5 size-4 shrink-0 text-ink-3" aria-label="Info" />
                ) : (
                  <StatusIcon status={i.severity} className="mt-0.5" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{i.title}</p>
                  <p className="text-xs text-ink-2">
                    {names.get(i.astronaut_id) ?? i.astronaut_id}. {i.summary}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Panel>
  );
}
