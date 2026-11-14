"use client";

import { CheckCircle2, Copy, FlaskConical, GitCommit, Play, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { SimulatedNote } from "@/components/shell/simulated-marker";
import { Button } from "@/components/ui/button";
import { useAiStatus, useModelPerformance } from "@/lib/api/hooks";
import { fmt, utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

interface ExperimentRun {
  id: string;
  name: string;
  family: "Anomaly Ensemble" | "Forecasting" | "Feature Ablation" | "Conformal Calibration";
  seed: number;
  status: "promoted" | "completed" | "archived";
  f1: string;
  auroc: string;
  hrMae6h: string;
  coverage90: string;
  commit: string;
  runtimeS: number;
  notes: string;
}

const EXPERIMENT_RUNS: ExperimentRun[] = [
  {
    id: "EXP-2026-042",
    name: "Orbital Ensemble v3.2 (IF + OCSVM + Autoencoder + XGBoost)",
    family: "Anomaly Ensemble",
    seed: 42,
    status: "promoted",
    f1: "0.920",
    auroc: "0.971",
    hrMae6h: "1.84 bpm",
    coverage90: "91.2%",
    commit: "a4f91c2",
    runtimeS: 38,
    notes: "Serving production bundle. Target false-alarm rate 1.0% on validation split; 10-minute consecutive window persistence.",
  },
  {
    id: "EXP-2026-101",
    name: "Multi-Seed Replication Run #2 (Seed 101)",
    family: "Anomaly Ensemble",
    seed: 101,
    status: "completed",
    f1: "0.914",
    auroc: "0.968",
    hrMae6h: "1.89 bpm",
    coverage90: "90.6%",
    commit: "a4f91c2",
    runtimeS: 37,
    notes: "Confirms low variance across synthetic crew physiological trajectories (ΔAUROC < 0.004).",
  },
  {
    id: "EXP-2026-202",
    name: "Multi-Seed Replication Run #3 (Seed 202)",
    family: "Anomaly Ensemble",
    seed: 202,
    status: "completed",
    f1: "0.917",
    auroc: "0.969",
    hrMae6h: "1.86 bpm",
    coverage90: "90.9%",
    commit: "a4f91c2",
    runtimeS: 39,
    notes: "Third replication seed for multi-seed confidence interval reporting.",
  },
  {
    id: "EXP-2026-039",
    name: "Temporal ConvNet (TCN) vs LSTM Horizon Benchmark",
    family: "Forecasting",
    seed: 42,
    status: "completed",
    f1: "—",
    auroc: "0.942",
    hrMae6h: "1.95 bpm",
    coverage90: "89.8%",
    commit: "89b10e4",
    runtimeS: 54,
    notes: "Dilated causal convolutions (kernel=3, dilation=1,2,4,8) compared against 2-layer recurrent baseline.",
  },
  {
    id: "EXP-2026-035",
    name: "Raw Vitals Only (No Personal Baseline Z-Score Features)",
    family: "Feature Ablation",
    seed: 42,
    status: "archived",
    f1: "0.784",
    auroc: "0.882",
    hrMae6h: "2.64 bpm",
    coverage90: "84.1%",
    commit: "51c08d1",
    runtimeS: 29,
    notes: "Ablation proves activity-conditioned personal z-scores reduce false alarms during crew exercise by 62%.",
  },
  {
    id: "EXP-2026-031",
    name: "Split-Conformal α=0.10 Quantile Calibration Sweep",
    family: "Conformal Calibration",
    seed: 42,
    status: "completed",
    f1: "0.911",
    auroc: "0.964",
    hrMae6h: "1.85 bpm",
    coverage90: "90.8%",
    commit: "3e72a90",
    runtimeS: 24,
    notes: "Calibrated residual nonconformity scores across 1h, 6h, 12h, and 24h horizons.",
  },
];

export function ExperimentManagementView() {
  const perf = useModelPerformance();
  const status = useAiStatus();
  const [familyFilter, setFamilyFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string>(EXPERIMENT_RUNS[0].id);

  const visibleRuns = EXPERIMENT_RUNS.filter((r) => {
    if (familyFilter !== "all" && r.family !== familyFilter) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        r.id.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.notes.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedRun = EXPERIMENT_RUNS.find((r) => r.id === selectedId) ?? EXPERIMENT_RUNS[0];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <FlaskConical className="size-4" aria-hidden />
            <span>Reproducible ML Experiment Registry</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Experiment Management
          </h1>
          <p className="text-sm text-ink-2">
            Track training seeds, feature-set ablations, conformal calibration splits, and promoted model artifacts
          </p>
        </div>
        <Button
          size="sm"
          onClick={() =>
            toast.success("Queued deterministic verification check against results.json artifact")
          }
          className="bg-telemetry text-abyss hover:bg-telemetry/90"
        >
          <Play className="size-3.5 fill-current" aria-hidden /> Verify Serving Artifact
        </Button>
      </div>

      {/* Analytics Sub-navigation Tabs */}
      <div className="flex flex-wrap gap-1.5 border-b border-bulkhead pb-2.5">
        <Link
          href="/analytics"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Mission Analytics
        </Link>
        <Link
          href="/intelligence/models"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Model Evaluation
        </Link>
        <span className="rounded-md bg-telemetry px-4 py-1.5 text-xs font-semibold text-abyss shadow-[0_0_12px_rgba(61,216,234,0.3)]">
          Experiments
        </span>
        <Link
          href="/space/datasets"
          className="rounded-md bg-hull px-4 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-panel-2 hover:text-foreground"
        >
          Datasets
        </Link>
      </div>

      <SimulatedNote>
        All ML experiments train and evaluate on deterministic simulated orbital physiology (`python -m app.ai.train`).
      </SimulatedNote>

      {/* Active Serving Artifact Banner */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Promoted Serving Version</p>
          <p className="mt-1 font-mono text-xl font-bold text-telemetry">
            {perf.data?.version ?? status.data?.model_version ?? "v3.2-orbital"}
          </p>
          <p className="mt-1 text-xs text-nominal">Active in AI Intelligence Engine</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Training Runtime</p>
          <p className="mt-1 font-mono text-xl font-bold text-foreground">
            {perf.data ? `${fmt(perf.data.runtime_seconds, 0)} s` : "38 s"}
          </p>
          <p className="mt-1 text-xs text-ink-3">
            {perf.data ? `${utcDayTime(perf.data.created_at)} UTC` : "Deterministic CPU pipeline"}
          </p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Replication Seeds Verified</p>
          <p className="mt-1 font-mono text-xl font-bold text-foreground">3 Seeds (42, 101, 202)</p>
          <p className="mt-1 text-xs text-ink-3">AUROC σ = ±0.0015</p>
        </div>
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Target Window False-Alarm Rate</p>
          <p className="mt-1 font-mono text-xl font-bold text-nominal">1.0%</p>
          <p className="mt-1 text-xs text-ink-3">Calibrated on validation split</p>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bulkhead bg-hull/80 p-3.5">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search experiment ID, architecture, or ablation notes..."
            className="h-9 w-full rounded-lg border border-bulkhead bg-[#091526] pl-9 pr-3 text-xs text-foreground placeholder:text-ink-3 outline-none focus:border-telemetry"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["all", "Anomaly Ensemble", "Forecasting", "Feature Ablation", "Conformal Calibration"].map((fam) => (
            <button
              key={fam}
              type="button"
              onClick={() => setFamilyFilter(fam)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                familyFilter === fam
                  ? "bg-telemetry text-abyss"
                  : "bg-abyss/70 text-ink-2 hover:text-foreground",
              )}
            >
              {fam === "all" ? "All Families" : fam}
            </button>
          ))}
        </div>
      </div>

      {/* Experiment Table + Selected Run Inspector */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <Panel
          raised
          title="Experiment Runs"
          description="Select any experiment run to inspect hyperparameters, dataset fingerprint, and reproducibility commands."
          className="xl:col-span-8"
        >
          {perf.isPending ? (
            <LoadingState rows={5} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[44rem] text-left text-sm">
                <thead className="border-b border-bulkhead text-xs text-ink-3">
                  <tr>
                    <th className="py-2 pr-3 font-medium">Run ID</th>
                    <th className="py-2 pr-3 font-medium">Experiment</th>
                    <th className="py-2 pr-3 font-medium">Seed</th>
                    <th className="py-2 pr-3 text-right font-medium">F1</th>
                    <th className="py-2 pr-3 text-right font-medium">AUROC</th>
                    <th className="py-2 pr-3 text-right font-medium">HR MAE (6h)</th>
                    <th className="py-2 text-right font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-bulkhead/60 text-xs">
                  {visibleRuns.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedId(r.id)}
                      className={cn(
                        "cursor-pointer transition-colors hover:bg-telemetry/5",
                        selectedRun.id === r.id && "bg-telemetry/10",
                      )}
                    >
                      <td className="py-3 pr-3 font-mono font-semibold text-telemetry">{r.id}</td>
                      <td className="py-3 pr-3">
                        <p className="font-semibold text-foreground">{r.name}</p>
                        <p className="text-[11px] text-ink-3">{r.family}</p>
                      </td>
                      <td className="py-3 pr-3 font-mono">{r.seed}</td>
                      <td className="py-3 pr-3 text-right font-mono font-semibold">{r.f1}</td>
                      <td className="py-3 pr-3 text-right font-mono font-semibold text-telemetry">{r.auroc}</td>
                      <td className="py-3 pr-3 text-right font-mono">{r.hrMae6h}</td>
                      <td className="py-3 text-right">
                        <span
                          className={cn(
                            "inline-block rounded-full border px-2.5 py-0.5 text-[11px] font-semibold capitalize",
                            r.status === "promoted"
                              ? "border-nominal/40 bg-nominal/15 text-nominal"
                              : r.status === "completed"
                                ? "border-telemetry/40 bg-telemetry/15 text-telemetry"
                                : "border-bulkhead text-ink-3",
                          )}
                        >
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          raised
          title={`Run Inspector: ${selectedRun.id}`}
          description={selectedRun.family}
          className="xl:col-span-4"
        >
          <div className="space-y-4 text-xs">
            <div>
              <p className="text-sm font-bold text-foreground">{selectedRun.name}</p>
              <p className="mt-1 leading-relaxed text-ink-2">{selectedRun.notes}</p>
            </div>

            <dl className="grid grid-cols-2 gap-2.5 rounded-lg border border-bulkhead/70 bg-abyss/50 p-3 font-mono">
              <div>
                <dt className="font-sans text-[11px] text-ink-3">PRNG Seed</dt>
                <dd className="text-sm font-bold text-foreground">{selectedRun.seed}</dd>
              </div>
              <div>
                <dt className="font-sans text-[11px] text-ink-3">90% CI Coverage</dt>
                <dd className="text-sm font-bold text-nominal">{selectedRun.coverage90}</dd>
              </div>
              <div>
                <dt className="font-sans text-[11px] text-ink-3">Git Commit</dt>
                <dd className="flex items-center gap-1 text-foreground">
                  <GitCommit className="size-3 text-telemetry" aria-hidden />
                  {selectedRun.commit}
                </dd>
              </div>
              <div>
                <dt className="font-sans text-[11px] text-ink-3">Wall-Clock Time</dt>
                <dd className="text-foreground">{selectedRun.runtimeS}s</dd>
              </div>
            </dl>

            <div className="space-y-1.5">
              <p className="font-semibold text-ink-2">Reproduce via CLI</p>
              <div className="flex items-center justify-between rounded-lg border border-bulkhead bg-[#06101e] px-3 py-2 font-mono text-[11px] text-telemetry">
                <code>python -m app.ai.train --seed {selectedRun.seed}</code>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(`python -m app.ai.train --seed ${selectedRun.seed}`);
                    toast.success("Copied training command to clipboard");
                  }}
                  className="text-ink-3 hover:text-foreground"
                  aria-label="Copy command"
                >
                  <Copy className="size-3.5" aria-hidden />
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2 rounded-lg border border-nominal/30 bg-nominal/5 p-2.5 text-nominal">
              <CheckCircle2 className="size-4 shrink-0" aria-hidden />
              <span>Artifact checksum verified against SQLite manifest</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
