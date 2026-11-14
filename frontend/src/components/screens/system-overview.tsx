"use client";

import {
  Activity,
  ArrowUpRight,
  BrainCircuit,
  CheckCircle2,
  Globe,
  Orbit,
  Radar,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ALL_26_SCREENS } from "@/components/shell/breadcrumbs";
import { useAiStatus, useMissionStatus, useSpaceSources } from "@/lib/api/hooks";
import { usePlatformStatus } from "@/lib/api/mission-hooks";
import { cn } from "@/lib/utils";

const PILLARS = [
  {
    id: "monitoring",
    label: "Monitoring",
    subtitle: "Real-Time Crew Telemetry & Alerts",
    icon: Activity,
    href: "/crew",
    details:
      "Continuous 5-second vital streaming (ECG, HR, SpO₂, RR, Temp, BP, HRV), sleep architecture tracking, and multi-tier clinical threshold alerts.",
  },
  {
    id: "ai",
    label: "Predictive AI",
    subtitle: "Ensemble Anomaly & Conformal Forecasting",
    icon: BrainCircuit,
    href: "/intelligence",
    details:
      "Isolation Forest, One-Class SVM, and Autoencoder anomaly detection paired with 24-hour XGBoost/LSTM/TCN forecasts and TreeSHAP explainability.",
  },
  {
    id: "twin",
    label: "Digital Twin",
    subtitle: "Personalized Physiological Baselines",
    icon: UserRoundCheck,
    href: "/twin",
    details:
      "Per-astronaut activity-conditioned baseline models, 6-organ system status holograms, longitudinal trend decomposition, and emergency what-if simulation.",
  },
  {
    id: "nasa",
    label: "NASA Data",
    subtitle: "DONKI, OSDR, EDA & MSL RAD Integration",
    icon: Globe,
    href: "/space/explorer",
    details:
      "Live ingestion and caching of NASA CCMC DONKI space weather events, Open Science Data Repository (OSDR) studies, and ISS environmental telemetry.",
  },
  {
    id: "control",
    label: "Mission Control",
    subtitle: "Unified Situational Awareness & Governance",
    icon: Radar,
    href: "/",
    details:
      "Integrated command dashboard, chronological mission timeline, RAG medical copilot, SHA-256 sealed incident reports, and RBAC security audit logs.",
  },
];

export function SystemOverviewView() {
  const [selectedPillar, setSelectedPillar] = useState(PILLARS[0].id);
  const [groupFilter, setGroupFilter] = useState<"all" | "Primary 16 Screens" | "Additional 10 Screens">("all");
  const mission = useMissionStatus();
  const ai = useAiStatus();
  const sources = useSpaceSources();
  const sys = usePlatformStatus();

  const activePillar = PILLARS.find((p) => p.id === selectedPillar) ?? PILLARS[0];
  const filteredScreens = ALL_26_SCREENS.filter((s) => groupFilter === "all" || s.category === groupFilter);

  return (
    <div className="space-y-6">
      {/* Screen 16 Full-Width Aerospace Horizon Banner */}
      <div className="relative overflow-hidden rounded-2xl border border-telemetry/40 bg-gradient-to-b from-[#061224] via-[#091d36] to-[#051020] p-6 sm:p-10 shadow-[0_0_45px_rgba(61,216,234,0.12)]">
        {/* Vector Starfield & Orbital Horizon */}
        <svg
          viewBox="0 0 1200 360"
          className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-85"
          aria-hidden
        >
          <defs>
            <radialGradient id="earthHorizonGlow" cx="50%" cy="115%" r="70%">
              <stop offset="0%" stopColor="#3dd8ea" stopOpacity="0.55" />
              <stop offset="35%" stopColor="#0284c7" stopOpacity="0.28" />
              <stop offset="70%" stopColor="#07111f" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="atmoArc" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#3dd8ea" stopOpacity="0.1" />
              <stop offset="50%" stopColor="#7ef0ff" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#3dd8ea" stopOpacity="0.1" />
            </linearGradient>
          </defs>
          <ellipse cx="600" cy="430" rx="760" ry="220" fill="url(#earthHorizonGlow)" />
          <path d="M -80 340 Q 600 180 1280 340" fill="none" stroke="url(#atmoArc)" strokeWidth="3.5" />
          <path d="M -80 348 Q 600 192 1280 348" fill="#040b16" />

          {/* Detailed ISS Silhouette on Right */}
          <g transform="translate(940, 56) rotate(-10)" stroke="#9bd8eb" strokeWidth="1.5" fill="#102742">
            <line x1="-85" y1="30" x2="85" y2="30" strokeWidth="3.2" />
            <rect x="-18" y="20" width="36" height="20" rx="3" />
            <rect x="-78" y="4" width="18" height="52" fill="#163b63" />
            <rect x="-52" y="4" width="18" height="52" fill="#163b63" />
            <rect x="34" y="4" width="18" height="52" fill="#163b63" />
            <rect x="60" y="4" width="18" height="52" fill="#163b63" />
          </g>
        </svg>

        <div className="relative z-10 mx-auto max-w-3xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-telemetry/40 bg-telemetry/10 px-3.5 py-1 text-xs font-semibold text-telemetry">
            <Orbit className="size-4" aria-hidden /> NASA Space Apps Challenge · Complete System Architecture
          </div>
          <h1 className="mt-4 font-heading text-3xl font-extrabold tracking-wider text-white sm:text-5xl">
            ASTRA-MED<sup className="ml-1 text-lg text-telemetry">®</sup>
          </h1>
          <p className="mt-2 text-base font-medium text-[#bfe8f5] sm:text-lg">
            Complete Astronaut Health Intelligence Platform
          </p>
        </div>

        {/* 5 Pillars Dock matching Screen 16 */}
        <div className="relative z-10 mt-10 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {PILLARS.map((p) => {
            const Icon = p.icon;
            const active = p.id === selectedPillar;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setSelectedPillar(p.id)}
                className={cn(
                  "group flex flex-col items-center rounded-xl border p-4 text-center backdrop-blur-md transition-all",
                  active
                    ? "border-telemetry bg-telemetry/20 text-white shadow-[0_0_20px_rgba(61,216,234,0.28)]"
                    : "border-bulkhead/80 bg-[#071526]/75 text-ink-2 hover:border-telemetry/50 hover:text-white",
                )}
              >
                <div
                  className={cn(
                    "flex size-11 items-center justify-center rounded-full border transition-colors",
                    active ? "border-telemetry bg-telemetry/25 text-telemetry" : "border-bulkhead bg-abyss/80 text-telemetry",
                  )}
                >
                  <Icon className="size-5" aria-hidden />
                </div>
                <span className="mt-2.5 text-sm font-bold">{p.label}</span>
                <span className="mt-0.5 text-[11px] text-ink-3">{p.subtitle}</span>
              </button>
            );
          })}
        </div>

        {/* Selected Pillar Spotlight Bar */}
        <div className="relative z-10 mt-5 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-bulkhead bg-[#071426]/90 px-5 py-3.5 text-xs">
          <div className="space-y-0.5">
            <p className="font-semibold text-telemetry">
              {activePillar.label} — {activePillar.subtitle}
            </p>
            <p className="text-ink-2">{activePillar.details}</p>
          </div>
          <Link
            href={activePillar.href}
            className="inline-flex items-center gap-1.5 rounded-lg bg-telemetry px-4 py-2 font-bold text-abyss transition-all hover:brightness-110"
          >
            Launch {activePillar.label} <ArrowUpRight className="size-4" aria-hidden />
          </Link>
        </div>
      </div>

      {/* Live Platform Telemetry Counters */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">Active Crew &amp; Mission Day</p>
          <p className="mt-1 font-mono text-2xl font-bold text-foreground">
            4 Astronauts · Day {mission.data?.mission_day ?? 42}
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs text-nominal">
            <CheckCircle2 className="size-3.5" aria-hidden /> 24/24 Physiological Sensors Online
          </p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">AI Intelligence Engine</p>
          <p className="mt-1 font-mono text-2xl font-bold text-telemetry">
            {ai.data?.model_version ?? "v3.2-orbital"}
          </p>
          <p className="mt-1 text-xs text-ink-2">3 Anomaly Detectors · 5 Forecast Models</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">NASA Open Data Integration</p>
          <p className="mt-1 font-mono text-2xl font-bold text-foreground">
            {(sources.data?.sources ?? []).reduce((a, b) => a + b.records, 0).toLocaleString() || "1,420"} Records
          </p>
          <p className="mt-1 text-xs text-ink-2">DONKI · OSDR · ISS EDA · MSL RAD</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <p className="text-xs text-ink-3">System Integrity &amp; Security</p>
          <p className="mt-1 font-mono text-2xl font-bold text-nominal">
            {sys.data?.status ?? "nominal"}
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs text-ink-2">
            <ShieldCheck className="size-3.5 text-telemetry" aria-hidden /> RBAC + CSRF + SHA-256 Reports
          </p>
        </div>
      </div>

      {/* Complete 26-Screen Interactive Launch Matrix */}
      <div className="rounded-xl border border-bulkhead bg-hull/80 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bulkhead pb-3.5">
          <div>
            <h2 className="text-lg font-bold text-foreground">
              Complete 26-Screen Navigation Matrix
            </h2>
            <p className="text-xs text-ink-3">
              Every primary design board screen (1–16) and specialized operational console (17–26)
            </p>
          </div>
          <div className="flex gap-1.5">
            {(["all", "Primary 16 Screens", "Additional 10 Screens"] as const).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGroupFilter(g)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                  groupFilter === g
                    ? "bg-telemetry text-abyss"
                    : "bg-abyss/70 text-ink-2 hover:text-foreground",
                )}
              >
                {g === "all" ? "All 26 Screens" : g}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredScreens.map((scr) => (
            <Link
              key={scr.number}
              href={scr.href}
              className="group flex flex-col justify-between rounded-lg border border-bulkhead/80 bg-[#091526]/85 p-3.5 transition-all hover:border-telemetry hover:bg-telemetry/10"
            >
              <div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="rounded bg-telemetry/15 px-2 py-0.5 font-mono font-bold text-telemetry">
                    Screen #{scr.number}
                  </span>
                  <span className="text-ink-3">{scr.category}</span>
                </div>
                <p className="mt-2 text-sm font-bold text-foreground group-hover:text-telemetry">
                  {scr.title}
                </p>
                <p className="mt-0.5 text-xs text-ink-3">{scr.subtitle}</p>
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-bulkhead/50 pt-2 font-mono text-[11px] text-ink-3">
                <span>{scr.href}</span>
                <ArrowUpRight className="size-3.5 text-telemetry" aria-hidden />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
