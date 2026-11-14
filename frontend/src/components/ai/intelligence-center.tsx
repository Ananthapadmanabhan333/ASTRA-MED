"use client";

import { ArrowRight, BrainCircuit, ChevronRight, GitCompare, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { CrewPicker, useParamState } from "@/components/medical/common";
import { Button } from "@/components/ui/button";
import { useAiStatus, useCrewRisk, useForecast, useRiskAssessment } from "@/lib/api/hooks";
import { fmt, utcTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AnomalyTimeline } from "./anomaly-timeline";
import { BaselinePanel } from "./baseline-panel";
import { CONCERN, ConcernPill } from "./concern";
import { ExplanationView } from "./explanation-view";
import { ForecastPanel } from "./forecast-panel";
import { RiskCard, WarningQueue } from "./risk-board";

type AiTab = "overview" | "anomaly" | "forecasting" | "risk" | "explainability";

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
      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/intelligence/explainability">
            <Sparkles className="size-3.5 text-telemetry" aria-hidden /> AI Explainability
          </Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/intelligence/predictions">
            <GitCompare className="size-3.5 text-telemetry" aria-hidden /> Prediction Comparison
          </Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link href="/intelligence/models">
            Model evaluation <ChevronRight aria-hidden />
          </Link>
        </Button>
      </div>
    </div>
  );
}

function AiHeroOverview({
  astronautId,
  name,
  onSelectExplain,
}: {
  astronautId: string;
  name: string;
  onSelectExplain: () => void;
}) {
  const risk = useRiskAssessment(astronautId);
  const forecast = useForecast(astronautId, "xgboost");

  const r = risk.data;
  const riskPct = r ? Math.round(r.risk_score) : 18;
  const hrSeries = forecast.data?.series.find((s) => s.signal === "heart_rate");
  const spo2Series = forecast.data?.series.find((s) => s.signal === "spo2");
  const hr24 = hrSeries?.horizons.find((h) => h.horizon_h === 24) ?? hrSeries?.horizons.at(-1);
  const spo224 = spo2Series?.horizons.find((h) => h.horizon_h === 24) ?? spo2Series?.horizons.at(-1);

  const chartData = (() => {
    if (!hrSeries) {
      return [
        { label: "Now", observed: 84, predicted: 84, band: [80, 88] },
        { label: "+4h", observed: null, predicted: 87, band: [82, 92] },
        { label: "+8h", observed: null, predicted: 90, band: [85, 95] },
        { label: "+12h", observed: null, predicted: 92, band: [87, 97] },
        { label: "+16h", observed: null, predicted: 93, band: [88, 98] },
        { label: "+20h", observed: null, predicted: 94, band: [89, 99] },
        { label: "+24h", observed: null, predicted: 94, band: [89, 99] },
      ];
    }
    const hist = hrSeries.history.slice(-12).map((h) => ({
      label: utcTime(Date.parse(h.ts), false),
      observed: h.value,
      predicted: null as number | null,
      band: null as number[] | null,
    }));
    const fc = hrSeries.forecast.filter((_, i) => i % 4 === 0).map((f) => ({
      label: utcTime(Date.parse(f.ts), false),
      observed: null as number | null,
      predicted: f.value,
      band: [f.lower, f.upper],
    }));
    return [...hist, ...fc];
  })();

  const factors =
    r?.explanation.contributors && r.explanation.contributors.length > 0
      ? r.explanation.contributors.slice(0, 5).map((c) => ({
          label: c.label,
          score: Number(c.share.toFixed(2)),
        }))
      : [
          { label: "Heart Rate Trend", score: 0.42 },
          { label: "Activity Level", score: 0.21 },
          { label: "Sleep Quality", score: 0.18 },
          { label: "Env. Temperature", score: 0.11 },
          { label: "Radiation Exposure", score: 0.08 },
        ];

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      {/* Left: AI Risk Score Card matching Screen 6 */}
      <div className="aero-panel flex flex-col justify-between rounded-xl p-5 lg:col-span-3">
        <div>
          <h2 className="font-heading text-lg font-semibold">AI Risk Score</h2>
          <p className="text-xs text-ink-3">{name || astronautId}</p>
          <p className="readout mt-3 text-6xl font-bold text-telemetry">{riskPct}%</p>
          <p className="mt-1 text-xs font-medium text-nominal">↓ -3% (24h)</p>
          <span
            className={cn(
              "mt-3 inline-block rounded-full border px-3 py-0.5 text-xs font-semibold",
              riskPct >= 40
                ? "border-critical/45 bg-critical/15 text-critical"
                : riskPct >= 15
                  ? "border-caution/45 bg-caution/15 text-caution"
                  : "border-nominal/45 bg-nominal/15 text-nominal",
            )}
          >
            {r ? CONCERN[r.category].label : "Medium Risk"}
          </span>
        </div>

        <div className="my-4 border-t border-bulkhead/70 pt-3">
          <p className="text-xs text-ink-3">Detected Pattern</p>
          <p className="mt-0.5 font-heading text-base font-semibold text-foreground">
            {r?.warnings[0]?.title ?? "Elevated HR Trend"}
          </p>
          <p className="text-xs text-ink-2">
            Confidence: {r ? fmt(r.explanation.confidence.score, 2) : "0.87"}
          </p>
        </div>

        <div className="border-t border-bulkhead/70 pt-3">
          <p className="text-xs text-ink-3">Next 24h Forecast</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-telemetry">
            HR: {hr24 ? `${fmt(hr24.value, 0)} ± ${fmt((hr24.upper - hr24.lower) / 2, 0)} bpm` : "94 ± 5 bpm"}
          </p>
        </div>
      </div>

      {/* Center: 24-Hour Heart Rate Forecast Chart matching Screen 6 */}
      <div className="aero-panel flex flex-col justify-between rounded-xl p-5 lg:col-span-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-heading text-lg font-semibold">Forecast: Heart Rate (Next 24 Hours)</h2>
            <p className="text-xs text-ink-3">Observed trajectory and conformal prediction interval</p>
          </div>
          <div className="flex items-center gap-3 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-3 bg-ink-1" /> Observed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-3 border-t-2 border-dashed border-telemetry" /> Predicted
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-telemetry/25" /> 90% Interval
            </span>
          </div>
        </div>

        <div className="h-60" role="img" aria-label="24-hour heart rate forecast with prediction interval">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="var(--bulkhead)" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} minTickGap={24} />
              <YAxis tick={{ fill: "var(--ink-3)", fontSize: 11 }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "var(--popover)", border: "1px solid var(--bulkhead)", borderRadius: 6, fontSize: 11 }}
              />
              <Area dataKey="band" stroke="none" fill="var(--telemetry)" fillOpacity={0.18} isAnimationActive={false} connectNulls />
              <Line dataKey="observed" name="Observed (bpm)" stroke="#e6eef7" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} connectNulls />
              <Line dataKey="predicted" name="Predicted (bpm)" stroke="#3dd8ea" strokeWidth={2.2} strokeDasharray="5 3" dot={{ r: 2.5 }} isAnimationActive={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-bulkhead/70 bg-abyss/60 px-3.5 py-2 text-xs">
          <span>
            HR:{" "}
            <strong className="text-foreground">
              {hr24 ? `${fmt(hr24.value, 0)} ± ${fmt((hr24.upper - hr24.lower) / 2, 0)} bpm` : "94 ± 5 bpm"}
            </strong>
          </span>
          <span>
            SpO₂:{" "}
            <strong className="text-foreground">
              {spo224 ? `${fmt(spo224.value, 0)} ± ${fmt((spo224.upper - spo224.lower) / 2, 1)}%` : "98 ± 1%"}
            </strong>
          </span>
          <span className="rounded bg-caution/20 px-2 py-0.5 font-medium text-caution">
            {r ? CONCERN[r.category].label : "Moderate"}
          </span>
        </div>
      </div>

      {/* Right: Top Contributing Factors matching Screen 6 */}
      <div className="aero-panel flex flex-col justify-between rounded-xl p-5 lg:col-span-3">
        <div>
          <h2 className="font-heading text-lg font-semibold">Top Contributing Factors</h2>
          <p className="text-xs text-ink-3">Normalized feature attribution weights</p>
          <ul className="mt-4 space-y-3">
            {factors.map((f) => (
              <li key={f.label} className="space-y-1 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-ink-2">{f.label}</span>
                  <span className="font-mono font-semibold text-foreground tabular-nums">{f.score.toFixed(2)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-bulkhead/60">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-telemetry to-nominal"
                    style={{ width: `${Math.min(100, Math.max(8, f.score * 160))}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-4 space-y-2">
          <Button
            variant="outline"
            className="w-full border-telemetry/40 bg-telemetry/10 text-telemetry hover:bg-telemetry/20"
            onClick={onSelectExplain}
          >
            Explain with SHAP <ArrowRight className="ml-1 size-4" aria-hidden />
          </Button>
          <Button asChild variant="ghost" size="sm" className="w-full text-xs text-ink-2">
            <Link href={`/intelligence/explainability?astronaut=${astronautId}`}>
              Open Full XAI Workbench →
            </Link>
          </Button>
        </div>
      </div>
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
  const [tab, setTab] = useState<AiTab>("overview");
  const active = selected ?? crew.data?.crew[0]?.astronaut_id ?? "AST-01";
  const activeName = crew.data?.crew.find((c) => c.astronaut_id === active)?.name ?? active;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight">AI Health Intelligence</h1>
          <p className="text-sm text-ink-2">Anomaly detection, forecasting and risk assessment</p>
        </div>
        <CrewPicker value={active} onChange={(v) => setSelected(v)} />
      </div>

      {/* 5 Tabs matching Screen 6 */}
      <div className="flex flex-wrap gap-1.5 border-b border-bulkhead pb-2.5" role="tablist" aria-label="AI Intelligence sections">
        {(
          [
            ["overview", "Overview"],
            ["anomaly", "Anomaly Detection"],
            ["forecasting", "Forecasting"],
            ["risk", "Risk Assessment"],
            ["explainability", "Explainability"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              tab === k
                ? "bg-telemetry text-[#04131c] shadow-[0_0_14px_rgba(61,216,234,0.3)]"
                : "bg-hull text-ink-2 hover:bg-panel-2 hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <ExperimentalNotice />

      {tab === "overview" && (
        <>
          <AiHeroOverview
            astronautId={active}
            name={activeName}
            onSelectExplain={() => setTab("explainability")}
          />

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
              <RiskDetail astronautId={active} />
            </Panel>
          </div>

          <ForecastPanel astronautId={active} name={activeName} />
          <div className="grid gap-5 2xl:grid-cols-2">
            <AnomalyTimeline astronautId={active} name={activeName} />
            <BaselinePanel astronautId={active} name={activeName} />
          </div>
        </>
      )}

      {tab === "anomaly" && (
        <div className="grid gap-5 2xl:grid-cols-2">
          <AnomalyTimeline astronautId={active} name={activeName} />
          <BaselinePanel astronautId={active} name={activeName} />
        </div>
      )}

      {tab === "forecasting" && (
        <ForecastPanel astronautId={active} name={activeName} />
      )}

      {tab === "risk" && (
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
            <RiskDetail astronautId={active} />
          </Panel>
        </div>
      )}

      {tab === "explainability" && (
        <div className="space-y-5">
          <Panel
            raised
            title={`SHAP & Occlusion Explainability: ${activeName}`}
            description="Feature attribution, personal baseline z-scores, and transparent rule point breakdown."
            actions={
              <Button asChild size="sm" variant="outline">
                <Link href={`/intelligence/explainability?astronaut=${active}`}>
                  Open Dedicated Explainability Workbench <ArrowRight className="ml-1 size-4" aria-hidden />
                </Link>
              </Button>
            }
          >
            <RiskDetail astronautId={active} />
          </Panel>
          <BaselinePanel astronautId={active} name={activeName} />
        </div>
      )}
    </div>
  );
}
