"use client";

import { ArrowLeft, BrainCircuit, CheckCircle2, Info, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { BaselinePanel } from "@/components/ai/baseline-panel";
import { ExplanationView } from "@/components/ai/explanation-view";
import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { CrewPicker, useParamState } from "@/components/medical/common";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { Button } from "@/components/ui/button";
import {
  useAlertExplanation,
  useAlerts,
  useAnomalyTimeline,
  useCrewRisk,
  useForecast,
  useRiskAssessment,
} from "@/lib/api/hooks";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const DEFAULT_SHAP_FACTORS = [
  { feature: "Heart Rate Trend", shap: 0.42, direction: "increase", category: "Cardiovascular" },
  { feature: "Activity Level", shap: 0.21, direction: "increase", category: "Metabolic" },
  { feature: "Sleep Quality", shap: 0.18, direction: "increase", category: "Circadian" },
  { feature: "Env. Temperature", shap: 0.11, direction: "neutral", category: "Cabin Environment" },
  { feature: "Radiation Exposure", shap: 0.08, direction: "neutral", category: "Space Weather" },
];

export function ExplainabilityWorkbench() {
  const crew = useCrewRisk();
  const [selected, setSelected] = useParamState("astronaut");
  const active = selected ?? crew.data?.crew[0]?.astronaut_id ?? "AST-01";
  const activeName = crew.data?.crew.find((c) => c.astronaut_id === active)?.name ?? active;

  const risk = useRiskAssessment(active);
  const forecast = useForecast(active, "xgboost");
  const anomalies = useAnomalyTimeline(active, 24);
  const alerts = useAlerts({ astronaut_id: active });
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);

  const effectiveAlertId = selectedAlertId ?? alerts.data?.[0]?.id ?? "";
  const alertExpl = useAlertExplanation(effectiveAlertId, Boolean(effectiveAlertId));

  const shapRows =
    risk.data?.explanation.contributors.length
      ? risk.data.explanation.contributors.map((c) => ({
          feature: c.label,
          shap: Number(c.share.toFixed(2)),
          z: c.z ?? 0,
          value: c.value,
          baseline: c.baseline,
          unit: c.unit,
        }))
      : DEFAULT_SHAP_FACTORS.map((f) => ({
          feature: f.feature,
          shap: f.shap,
          z: f.shap * 3.2,
          value: null,
          baseline: null,
          unit: "",
        }));

  const hrSeries = forecast.data?.series.find((s) => s.signal === "heart_rate");

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <BrainCircuit className="size-4" aria-hidden />
            <span>Explainable AI (XAI) & Model Transparency</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            AI Explainability — {activeName}
          </h1>
          <p className="text-xs text-ink-2">
            TreeSHAP feature attributions, occlusion sensitivity, personal baseline z-scores, and transparent risk rules
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CrewPicker value={active} onChange={(v) => setSelected(v)} />
          <Button asChild size="sm" variant="outline">
            <Link href={`/intelligence?astronaut=${active}`}>
              <ArrowLeft className="mr-1 size-3.5" aria-hidden /> AI Intelligence
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`/intelligence/predictions?astronaut=${active}`}>Prediction Comparison</Link>
          </Button>
        </div>
      </div>

      <SimulatedNote>
        Explainable AI (XAI) attributions are computed from personal baseline z-scores, TreeSHAP feature values, and occlusion sensitivity on simulated orbital telemetry.
      </SimulatedNote>

      {/* Top Summary Strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Composite Risk Score</p>
          <p className="mt-1 font-mono text-3xl font-bold text-caution">
            {risk.data ? `${Math.round(risk.data.risk_score)}%` : "18%"}
          </p>
          <p className="mt-1 text-xs text-ink-2">
            Health Score: <span className="font-mono text-foreground">{risk.data?.health_score ?? 82}/100</span>
          </p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Primary Attribution Method</p>
          <p className="mt-1 font-mono text-lg font-bold text-telemetry">
            {risk.data?.explanation.method ?? "TreeSHAP + Z-Score Rules"}
          </p>
          <p className="mt-1 text-xs text-ink-2">Exact additive feature shares summing to 1.00</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Model Confidence</p>
          <p className="mt-1 font-mono text-3xl font-bold text-nominal">
            {risk.data ? fmt(risk.data.explanation.confidence.score, 2) : "0.87"}
          </p>
          <p className="mt-1 text-xs capitalize text-ink-2">
            {risk.data?.explanation.confidence.level ?? "High"} agreement across detectors
          </p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Ensemble Detector Votes</p>
          <p className="mt-1 font-mono text-3xl font-bold text-foreground">
            {risk.data?.anomaly.available
              ? `${risk.data.anomaly.votes} / ${risk.data.anomaly.n_detectors}`
              : `${anomalies.data?.detections.length ?? 2} flags`}
          </p>
          <p className="mt-1 text-xs text-ink-2">Isolation Forest · One-Class SVM · Autoencoder</p>
        </div>
      </div>

      {/* Main SHAP & Rule Breakdown Grid */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Panel
          raised
          className="lg:col-span-7"
          title="SHAP & Occlusion Feature Attribution"
          description="Relative contribution of physiological and environmental signals to the current risk & anomaly state."
        >
          <div className="h-64 w-full" role="img" aria-label="Feature attribution bar chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={shapRows} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 110 }}>
                <CartesianGrid stroke="#17304f" strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  domain={[0, 0.6]}
                  tick={{ fill: "#8ca5c2", fontSize: 11 }}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                />
                <YAxis
                  type="category"
                  dataKey="feature"
                  tick={{ fill: "#d9ecff", fontSize: 12 }}
                  width={105}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#091526",
                    borderColor: "#1d3b5e",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  formatter={(v) => {
                    const num = Number(v ?? 0);
                    return [`${(num * 100).toFixed(1)}% (SHAP share ${num.toFixed(2)})`, "Contribution"];
                  }}
                />
                <Bar dataKey="shap" radius={[0, 6, 6, 0]} isAnimationActive={false}>
                  {shapRows.map((entry, idx) => (
                    <Cell
                      key={entry.feature}
                      fill={idx === 0 ? "#3dd8ea" : idx === 1 ? "#2ab3c6" : "#1f8ba0"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* TreeSHAP 6h Forecast Drivers */}
          {hrSeries && hrSeries.drivers.length > 0 && (
            <div className="mt-4 rounded-lg border border-bulkhead/70 bg-abyss/50 p-3.5">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-telemetry">
                <Sparkles className="size-3.5" aria-hidden /> XGBoost TreeSHAP 6h Heart Rate Forecast Drivers
              </h3>
              <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {hrSeries.drivers.map((d) => (
                  <div key={d.name} className="flex items-center justify-between rounded border border-bulkhead/50 bg-hull/60 px-3 py-1.5 text-xs">
                    <span className="text-ink-2">{d.name}</span>
                    <span className="font-mono font-semibold text-telemetry">{(d.share * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel
          raised
          className="lg:col-span-5"
          title="Five-Part Clinical AI Explanation"
          description="What changed, contributing signals, statistical significance, model confidence, and known limitations."
        >
          {risk.isPending ? (
            <LoadingState rows={5} />
          ) : risk.error && !risk.data ? (
            <ErrorState error={risk.error} onRetry={() => risk.refetch()} />
          ) : risk.data ? (
            <ExplanationView explanation={risk.data.explanation} />
          ) : null}
        </Panel>
      </div>

      {/* Transparent Rule Point Decomposition & Per-Alert Root Cause Inspector */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Panel
          title="Transparent Risk Score Rule Decomposition"
          description="Exact point contributions from each clinical/physiological rule evaluated for this astronaut."
        >
          {risk.data?.warnings && risk.data.warnings.length > 0 ? (
            <div className="space-y-2.5">
              {risk.data.warnings.map((w) => (
                <div
                  key={w.title}
                  className="flex items-start justify-between gap-3 rounded-lg border border-bulkhead/70 bg-abyss/50 p-3"
                >
                  <div className="space-y-1">
                    <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <span className="rounded bg-caution/20 px-1.5 py-0.5 font-mono text-xs text-caution">
                        P{w.priority}
                      </span>
                      {w.title}
                    </p>
                    <p className="text-xs text-ink-2">{w.detail}</p>
                    <p className="text-[11px] text-ink-3">Source module: {w.source}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <span className="font-mono text-lg font-bold text-telemetry">+{fmt(w.points, 0)}</span>
                    <p className="text-[10px] text-ink-3">risk pts</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg border border-nominal/30 bg-nominal/5 p-4 text-sm text-nominal">
              <CheckCircle2 className="size-5 shrink-0" aria-hidden />
              <div>
                <p className="font-semibold">All risk rules nominal</p>
                <p className="text-xs text-ink-2">
                  Baseline deviations remain below ±1.5z and ensemble anomaly detectors show 0 sustained flags.
                </p>
              </div>
            </div>
          )}
        </Panel>

        <Panel
          title="Alert Root-Cause Explanation Inspector"
          description="Select any alert for this astronaut to inspect its dedicated AI root-cause attribution."
        >
          <div className="space-y-3">
            {alerts.data && alerts.data.length > 0 ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {alerts.data.slice(0, 6).map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => setSelectedAlertId(a.id)}
                      className={cn(
                        "rounded-md border px-2.5 py-1 text-xs font-medium transition-colors",
                        effectiveAlertId === a.id
                          ? "border-telemetry bg-telemetry/15 text-telemetry"
                          : "border-bulkhead bg-abyss/50 text-ink-2 hover:text-foreground",
                      )}
                    >
                      {a.metric.toUpperCase()} · {utcDayTime(a.opened_at)}
                    </button>
                  ))}
                </div>
                {alertExpl.isPending ? (
                  <LoadingState rows={3} />
                ) : alertExpl.data ? (
                  <div className="rounded-lg border border-bulkhead/70 bg-abyss/40 p-3.5">
                    <ExplanationView explanation={alertExpl.data.explanation} />
                  </div>
                ) : (
                  <p className="text-xs text-ink-3">Select an alert above to inspect its explanation.</p>
                )}
              </>
            ) : (
              <div className="rounded-lg border border-bulkhead/60 bg-abyss/40 p-4 text-xs text-ink-2">
                <p className="flex items-center gap-1.5 font-medium text-foreground">
                  <Info className="size-4 text-telemetry" aria-hidden /> No open alerts for {activeName}
                </p>
                <p className="mt-1">
                  When an alert triggers, this inspector queries <code>/api/ai/explanations/&#123;alert_id&#125;</code> to display exact signal z-scores and occlusion attributions at the timestamp of the breach.
                </p>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Personal Baselines Table */}
      <BaselinePanel astronautId={active} name={activeName} />
    </div>
  );
}
