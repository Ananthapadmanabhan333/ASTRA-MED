"use client";

import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Compass,
  Database,
  Fingerprint,
  LayoutDashboard,
  Orbit,
  Play,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ScreenDirectoryDialog } from "@/components/shell/breadcrumbs";
import { Button } from "@/components/ui/button";

const PILLARS = [
  {
    icon: Activity,
    label: "Health Monitoring",
    sub: "1 Hz vitals, synthetic ECG & baseline deviation",
    href: "/crew",
  },
  {
    icon: BrainCircuit,
    label: "Predictive AI",
    sub: "5-detector ensemble & 24h conformal forecasts",
    href: "/intelligence",
  },
  {
    icon: Fingerprint,
    label: "Digital Twin",
    sub: "Personalized physiological model & timeline",
    href: "/twin",
  },
  {
    icon: Database,
    label: "NASA Data",
    sub: "Live DONKI space weather & OSDR ISS records",
    href: "/space/explorer",
  },
  {
    icon: LayoutDashboard,
    label: "Mission Control",
    sub: "Unified command, alerts & emergency sandbox",
    href: "/",
  },
];

const FEATURE_CARDS = [
  {
    title: "Real-Time Crew Physiological Telemetry",
    badge: "Simulated 1 Hz Stream",
    detail:
      "Tracks heart rate, SpO₂, systolic/diastolic blood pressure, core temperature, respiratory rate, HRV (RMSSD), sleep architecture, and synthetic ECG waveforms across 4 astronauts in Mars transit.",
    href: "/crew",
  },
  {
    title: "Explainable AI & Conformal Forecasting",
    badge: "SHAP + 90% Intervals",
    detail:
      "Combines Isolation Forest, Local Outlier Factor, One-Class SVM, Statistical Z-Score, and Autoencoder anomaly detectors with XGBoost/LSTM/GRU/TCN 24-hour vital-sign forecasting.",
    href: "/intelligence",
  },
  {
    title: "Interactive Astronaut Digital Twin",
    badge: "6-System Assessment",
    detail:
      "Maintains a longitudinal daily twin per astronaut comparing awake-at-rest measurements against personal baselines across cardiovascular, respiratory, neuro, sleep, thermoregulation, and radiation systems.",
    href: "/twin",
  },
  {
    title: "Authentic NASA Open-Science Integration",
    badge: "DONKI • OSDR • EDA",
    detail:
      "Ingests solar flares, CMEs, SEP events, and geomagnetic storms from NASA CCMC DONKI alongside historical ISS cabin environment and dosimetry from NASA OSDR.",
    href: "/space",
  },
];

function SpaceHeroArtwork() {
  return (
    <div className="relative mx-auto w-full max-w-xl">
      <svg
        viewBox="0 0 600 460"
        className="h-auto w-full drop-shadow-[0_0_45px_rgba(61,216,234,0.22)]"
        role="img"
        aria-label="Orbital International Space Station, Earth horizon, and Astronaut HUD illustration"
      >
        <defs>
          <radialGradient id="earthGlow" cx="50%" cy="110%" r="85%">
            <stop offset="0%" stopColor="#3dd8ea" stopOpacity="0.45" />
            <stop offset="45%" stopColor="#0f3c66" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#07111f" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="visorGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0b2847" />
            <stop offset="50%" stopColor="#07162c" />
            <stop offset="100%" stopColor="#040c18" />
          </linearGradient>
          <linearGradient id="cyanLine" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3dd8ea" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#3dd8ea" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#5ee2a0" stopOpacity="0.2" />
          </linearGradient>
        </defs>

        {/* Deep space starfield */}
        {[
          [42, 48, 1.5], [120, 26, 1], [230, 62, 1.8], [310, 28, 1.2], [480, 44, 1.5],
          [540, 88, 1.2], [75, 160, 1], [190, 130, 1.4], [520, 180, 1.6], [35, 260, 1.2],
        ].map(([cx, cy, r], idx) => (
          <circle key={idx} cx={cx} cy={cy} r={r} fill="#a9b9cf" opacity="0.65" />
        ))}

        {/* Earth Horizon Arc */}
        <ellipse cx="300" cy="510" rx="460" ry="190" fill="url(#earthGlow)" />
        <path
          d="M -80 430 Q 300 280 680 430"
          fill="none"
          stroke="url(#cyanLine)"
          strokeWidth="2.5"
        />

        {/* Orbital ISS Silhouette */}
        <g transform="translate(85, 78) rotate(-12)" stroke="#3dd8ea" strokeWidth="1.4" fill="#0c1a2e">
          <line x1="0" y1="36" x2="170" y2="36" stroke="#8fb4ff" strokeWidth="2" />
          {/* Left solar wings */}
          <rect x="6" y="4" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="6" y="42" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="34" y="4" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="34" y="42" width="22" height="26" fill="#123052" opacity="0.9" />
          {/* Central pressurized modules */}
          <rect x="70" y="28" width="30" height="16" rx="3" fill="#1b355a" />
          <rect x="80" y="16" width="12" height="40" rx="2" fill="#1b355a" />
          {/* Right solar wings */}
          <rect x="114" y="4" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="114" y="42" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="142" y="4" width="22" height="26" fill="#123052" opacity="0.9" />
          <rect x="142" y="42" width="22" height="26" fill="#123052" opacity="0.9" />
        </g>

        {/* Astronaut Helmet & Suit Silhouette */}
        <g transform="translate(250, 70)">
          {/* Suit shoulders & torso */}
          <path
            d="M 20 340 C 20 265, 70 235, 155 235 C 240 235, 290 265, 290 340 Z"
            fill="#10233d"
            stroke="#3dd8ea"
            strokeOpacity="0.45"
            strokeWidth="2"
          />
          {/* Chest telemetry pack & NASA-inspired mission patch */}
          <rect x="95" y="268" width="120" height="58" rx="8" fill="#091628" stroke="#1b3050" strokeWidth="1.5" />
          <text x="112" y="292" fill="#3dd8ea" fontSize="11" fontFamily="monospace" fontWeight="bold">
            ASTRA-MED HUD
          </text>
          <text x="112" y="310" fill="#5ee2a0" fontSize="12" fontFamily="monospace">
            HR 72 BPM • SpO2 98%
          </text>

          {/* Outer Helmet Dome */}
          <ellipse
            cx="155"
            cy="145"
            rx="105"
            ry="112"
            fill="#162d4c"
            stroke="#3dd8ea"
            strokeOpacity="0.6"
            strokeWidth="2.5"
          />
          {/* Helmet Visor */}
          <ellipse
            cx="148"
            cy="145"
            rx="82"
            ry="76"
            fill="url(#visorGrad)"
            stroke="#3dd8ea"
            strokeWidth="2"
          />
          {/* Visor HUD reflection & live ECG waveform */}
          <path
            d="M 82 148 L 106 148 L 114 134 L 122 164 L 130 118 L 138 168 L 146 142 L 158 148 L 210 148"
            fill="none"
            stroke="#3dd8ea"
            strokeWidth="2.2"
          />
          <text x="92" y="110" fill="#8fb4ff" fontSize="10" fontFamily="monospace">
            TWIN SYNC: NOMINAL
          </text>
          <text x="92" y="188" fill="#5ee2a0" fontSize="10" fontFamily="monospace">
            RAD: 0.34 mSv/d • KP 2
          </text>
        </g>
      </svg>
    </div>
  );
}

export function LandingPageView() {
  const [dirOpen, setDirOpen] = useState(false);

  return (
    <div className="min-h-dvh bg-[#050d1a] text-foreground">
      {/* Top Navigation Bar matching Screen 1 */}
      <header className="sticky top-0 z-30 border-b border-bulkhead/80 bg-[#061020]/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-8">
          <Link href="/landing" className="flex items-center gap-2.5">
            <Orbit className="size-7 text-telemetry" aria-hidden />
            <span className="font-heading text-2xl font-bold tracking-wider">
              ASTRA<span className="text-telemetry">-MED</span>
            </span>
          </Link>

          <nav aria-label="Landing navigation" className="hidden items-center gap-7 text-sm text-ink-2 md:flex">
            <a href="#features" className="transition-colors hover:text-telemetry">
              Features
            </a>
            <a href="#research" className="transition-colors hover:text-telemetry">
              Research
            </a>
            <a href="#documentation" className="transition-colors hover:text-telemetry">
              Documentation
            </a>
            <Link href="/system-overview" className="transition-colors hover:text-telemetry">
              System Overview
            </Link>
            <button
              type="button"
              onClick={() => setDirOpen(true)}
              className="inline-flex items-center gap-1.5 text-telemetry hover:underline"
            >
              <Compass className="size-4" aria-hidden />
              All 26 Screens
            </button>
          </nav>

          <div className="flex items-center gap-3">
            <Button asChild variant="outline" size="sm" className="border-bulkhead bg-hull/70 px-4">
              <Link href="/login">Login</Link>
            </Button>
            <Button asChild size="sm" className="aero-glow bg-telemetry px-4 font-semibold text-[#04131c] hover:bg-telemetry/90">
              <Link href="/">Get Started</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero Section matching Screen 1 */}
      <section className="aero-grid relative overflow-hidden border-b border-bulkhead/70 py-12 sm:py-20">
        <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 sm:px-8 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-telemetry/35 bg-telemetry/10 px-3.5 py-1 text-xs font-medium text-telemetry">
              <Sparkles className="size-3.5" aria-hidden />
              NASA Space Apps Challenge 2026 • Crew Health Intelligence Platform
            </div>

            <h1 className="font-heading text-5xl font-bold tracking-wider sm:text-6xl">
              ASTRA <span className="text-telemetry">—</span> MED
            </h1>

            <p className="font-heading text-2xl font-semibold text-ink-1 sm:text-3xl">
              AI-Driven Astronaut Health Intelligence
            </p>

            <p className="max-w-xl text-base leading-relaxed text-ink-2">
              A unified platform for astronaut health monitoring, predictive analytics, and space environment
              intelligence using NASA data. Designed for autonomous crew self-checks and flight-surgeon decision
              support on long-duration missions.
            </p>

            <div className="flex flex-wrap items-center gap-4 pt-2">
              <Button
                asChild
                size="lg"
                className="aero-glow bg-telemetry px-6 font-semibold text-[#04131c] hover:bg-telemetry/90"
              >
                <Link href="/">
                  Get Started <ArrowRight className="ml-1 size-4" aria-hidden />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="border-bulkhead bg-hull/80 px-6 hover:border-telemetry">
                <Link href="/demo">
                  <Play className="mr-1.5 size-4 text-telemetry" aria-hidden /> Watch Demo
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="lg"
                onClick={() => setDirOpen(true)}
                className="text-ink-2 hover:text-telemetry"
              >
                <Compass className="mr-1.5 size-4 text-telemetry" aria-hidden /> Browse 26 Screens
              </Button>
            </div>

            <p className="text-xs text-ink-3">
              All crew physiological telemetry is simulated and labelled <code className="text-ink-2">simulated</code>.
              Space weather and historical ISS environmental records are sourced from NASA DONKI and OSDR.
            </p>
          </div>

          <div className="lg:col-span-5">
            <SpaceHeroArtwork />
          </div>
        </div>

        {/* Bottom 5-Pillar Feature Strip matching Screen 1 */}
        <div className="mx-auto mt-12 max-w-7xl px-4 sm:px-8">
          <div className="grid grid-cols-2 gap-3 rounded-xl border border-bulkhead/90 bg-hull/85 p-4 backdrop-blur sm:grid-cols-3 lg:grid-cols-5">
            {PILLARS.map((p) => {
              const Icon = p.icon;
              return (
                <Link
                  key={p.label}
                  href={p.href}
                  className="group flex flex-col items-center rounded-lg border border-transparent p-3 text-center transition-all hover:border-telemetry/40 hover:bg-panel-2"
                >
                  <div className="flex size-11 items-center justify-center rounded-full border border-telemetry/35 bg-telemetry/10 text-telemetry transition-transform group-hover:scale-105">
                    <Icon className="size-5" aria-hidden />
                  </div>
                  <span className="mt-2.5 font-heading text-base font-semibold text-foreground group-hover:text-telemetry">
                    {p.label}
                  </span>
                  <span className="mt-0.5 text-xs text-ink-3">{p.sub}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="mx-auto max-w-7xl px-4 py-16 sm:px-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-wider text-telemetry uppercase">Core Capabilities</p>
            <h2 className="mt-1 font-heading text-3xl font-bold">End-to-End Mission Medical Operations</h2>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href="/system-overview">
              Full System Overview <ArrowRight className="ml-1 size-4" aria-hidden />
            </Link>
          </Button>
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          {FEATURE_CARDS.map((f) => (
            <Link
              key={f.title}
              href={f.href}
              className="aero-panel group flex flex-col justify-between rounded-xl p-6 transition-all hover:border-telemetry/50"
            >
              <div>
                <span className="inline-block rounded-full border border-telemetry/30 bg-telemetry/10 px-2.5 py-0.5 text-xs font-medium text-telemetry">
                  {f.badge}
                </span>
                <h3 className="mt-3 font-heading text-xl font-semibold group-hover:text-telemetry">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-2">{f.detail}</p>
              </div>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-telemetry">
                Open module <ArrowRight className="size-3.5" aria-hidden />
              </span>
            </Link>
          ))}
        </div>
      </section>

      {/* Research & Validation Section */}
      <section id="research" className="border-y border-bulkhead/70 bg-hull/40 py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-8">
          <p className="text-xs font-semibold tracking-wider text-telemetry uppercase">Scientific Validation</p>
          <h2 className="mt-1 font-heading text-3xl font-bold">Reproducible Evaluation on Simulated Cohorts</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-bulkhead bg-hull p-5">
              <p className="text-xs text-ink-3">Anomaly Detection F1 (Learned vs Fixed Limits)</p>
              <p className="readout mt-2 text-4xl font-bold text-telemetry">0.81 vs 0.36</p>
              <p className="mt-2 text-xs text-ink-2">
                Calibrated at a 1% validation false-alarm rate across 3 independent random seeds.
              </p>
            </div>
            <div className="rounded-xl border border-bulkhead bg-hull p-5">
              <p className="text-xs text-ink-3">1-Hour Heart Rate Forecast MAE</p>
              <p className="readout mt-2 text-4xl font-bold text-nominal">2.19 bpm</p>
              <p className="mt-2 text-xs text-ink-2">
                XGBoost with activity-conditioned features vs 3.85 bpm personal climatology baseline.
              </p>
            </div>
            <div className="rounded-xl border border-bulkhead bg-hull p-5">
              <p className="text-xs text-ink-3">90% Conformal Interval Coverage</p>
              <p className="readout mt-2 text-4xl font-bold text-foreground">89–91%</p>
              <p className="mt-2 text-xs text-ink-2">
                Split-conformal prediction intervals maintain honest uncertainty across 1–24h horizons.
              </p>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild variant="outline" size="sm">
              <Link href="/analytics/experiments">Explore ML Experiments</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/intelligence/predictions">Prediction Comparison Studio</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/intelligence/explainability">SHAP Explainability Workbench</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Documentation & Governance Footer */}
      <footer id="documentation" className="mx-auto max-w-7xl px-4 py-12 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-telemetry" aria-hidden />
              <span className="font-heading text-lg font-semibold">ASTRA-MED Open-Source Research Prototype</span>
            </div>
            <p className="text-xs text-ink-3">
              Licensed under Apache-2.0 for the NASA Space Apps Challenge 2026. Not a medical device.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 text-xs">
            <Link href="/space/datasets" className="rounded-md border border-bulkhead px-3 py-1.5 hover:border-telemetry">
              Dataset Inventory
            </Link>
            <Link href="/security" className="rounded-md border border-bulkhead px-3 py-1.5 hover:border-telemetry">
              Security & Audit
            </Link>
            <Link href="/system" className="rounded-md border border-bulkhead px-3 py-1.5 hover:border-telemetry">
              Deployment & Health
            </Link>
            <Link href="/" className="rounded-md bg-telemetry px-3 py-1.5 font-semibold text-[#04131c]">
              Launch Mission Control
            </Link>
          </div>
        </div>
      </footer>

      <ScreenDirectoryDialog open={dirOpen} onOpenChange={setDirOpen} />
    </div>
  );
}
