"use client";

import { ChevronRight, Compass, Home, Layers } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface ScreenEntry {
  number: number;
  title: string;
  subtitle: string;
  href: string;
  category: "Primary 16 Screens" | "Additional 10 Screens";
}

export const ALL_26_SCREENS: ScreenEntry[] = [
  { number: 1, title: "Landing Page", subtitle: "AI-Driven Astronaut Health Intelligence showcase", href: "/landing", category: "Primary 16 Screens" },
  { number: 2, title: "Authentication", subtitle: "Secure Access to Mission Systems", href: "/login", category: "Primary 16 Screens" },
  { number: 3, title: "Mission Control", subtitle: "Unified Astronaut Health & Space Environment Operations", href: "/", category: "Primary 16 Screens" },
  { number: 4, title: "Crew Monitoring", subtitle: "Real-time health status of all astronauts", href: "/crew", category: "Primary 16 Screens" },
  { number: 5, title: "Astronaut Digital Twin", subtitle: "Personalized physiological model & health timeline", href: "/twin", category: "Primary 16 Screens" },
  { number: 6, title: "AI Intelligence", subtitle: "Anomaly detection, forecasting and risk assessment", href: "/intelligence", category: "Primary 16 Screens" },
  { number: 7, title: "AI Medical Assistant", subtitle: "Source-grounded RAG mission health copilot", href: "/assistant", category: "Primary 16 Screens" },
  { number: 8, title: "Space Environment", subtitle: "Space weather, solar activity and environmental conditions", href: "/space", category: "Primary 16 Screens" },
  { number: 9, title: "Radiation Intelligence", subtitle: "Radiation events and mission exposure analysis", href: "/radiation", category: "Primary 16 Screens" },
  { number: 10, title: "Mission Timeline", subtitle: "Unified view of health, environment and mission events", href: "/timeline", category: "Primary 16 Screens" },
  { number: 11, title: "Emergency Simulator", subtitle: "Test and validate mission response with controlled scenarios", href: "/emergency", category: "Primary 16 Screens" },
  { number: 12, title: "Analytics & Research", subtitle: "Mission analytics, model evaluation and longitudinal research", href: "/analytics", category: "Primary 16 Screens" },
  { number: 13, title: "NASA Data Explorer", subtitle: "Access and explore NASA open datasets", href: "/space/explorer", category: "Primary 16 Screens" },
  { number: 14, title: "Reports", subtitle: "Generate, view and export mission incident reports", href: "/reports", category: "Primary 16 Screens" },
  { number: 15, title: "Settings", subtitle: "Manage mission, users and system configuration", href: "/settings", category: "Primary 16 Screens" },
  { number: 16, title: "System Overview", subtitle: "Complete Astronaut Health Intelligence Platform architecture", href: "/system-overview", category: "Primary 16 Screens" },
  { number: 17, title: "Detailed Astronaut Health History", subtitle: "Multi-parameter historical vitals, sleep, exercise and self-reports", href: "/crew/history", category: "Additional 10 Screens" },
  { number: 18, title: "AI Explainability", subtitle: "SHAP attributions, occlusion sensitivity and rule breakdowns", href: "/intelligence/explainability", category: "Additional 10 Screens" },
  { number: 19, title: "Prediction Comparison", subtitle: "Multi-model forecast comparison across horizons with conformal intervals", href: "/intelligence/predictions", category: "Additional 10 Screens" },
  { number: 20, title: "Environmental-Health Correlation", subtitle: "Pearson, Spearman and lagged FDR-controlled correlation analysis", href: "/space/correlation", category: "Additional 10 Screens" },
  { number: 21, title: "Experiment Management", subtitle: "ML training runs, seed replication studies and model registry", href: "/analytics/experiments", category: "Additional 10 Screens" },
  { number: 22, title: "Dataset Details", subtitle: "Schema, provenance, units and sample inspector for NASA & synthetic datasets", href: "/space/datasets", category: "Additional 10 Screens" },
  { number: 23, title: "Security and Audit Logs", subtitle: "Append-only access audit log, session protection and RBAC monitoring", href: "/security", category: "Additional 10 Screens" },
  { number: 24, title: "Deployment and System Health", subtitle: "Probes, component telemetry, orchestrator queues and consistency checks", href: "/system", category: "Additional 10 Screens" },
  { number: 25, title: "Notification Centre", subtitle: "Unified dispatch feed for mission alerts, AI warnings and space weather", href: "/notifications", category: "Additional 10 Screens" },
  { number: 26, title: "User and Role Management", subtitle: "Mission staff directory, account provisioning and 4-role permission matrix", href: "/admin", category: "Additional 10 Screens" },
];

const SEGMENT_LABELS: Record<string, string> = {
  landing: "Landing Page",
  login: "Authentication",
  crew: "Crew Monitoring",
  history: "Health History",
  twin: "Astronaut Digital Twin",
  intelligence: "AI Intelligence",
  explainability: "AI Explainability",
  predictions: "Prediction Comparison",
  models: "Model Evaluation",
  assistant: "AI Medical Assistant",
  space: "Space Environment",
  weather: "Space Weather",
  iss: "ISS Environment",
  explorer: "NASA Data Explorer",
  datasets: "Dataset Details",
  correlation: "Environmental-Health Correlation",
  radiation: "Radiation Intelligence",
  timeline: "Mission Timeline",
  emergency: "Emergency Simulator",
  analytics: "Analytics & Research",
  experiments: "Experiment Management",
  reports: "Reports & Incident Records",
  settings: "Settings",
  "system-overview": "System Overview",
  security: "Security & Audit Logs",
  system: "Deployment & System Health",
  notifications: "Notification Centre",
  admin: "User & Role Management",
  "self-check": "Crew Self-Check",
  alerts: "Alert Centre",
  simulation: "Mission Simulation Sandbox",
  demo: "Guided Demo",
  vitals: "Vitals Comparison",
  anomalies: "Anomalies & Scenario Console",
  sleep: "Sleep & Circadian",
  insights: "Rule Insights",
  overview: "Mission Health Overview",
  medical: "Medical Intelligence",
};

export function ScreenDirectoryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const pathname = usePathname() ?? "/";
  const [filter, setFilter] = useState("");
  const q = filter.trim().toLowerCase();
  const filtered = ALL_26_SCREENS.filter(
    (s) =>
      !q ||
      s.title.toLowerCase().includes(q) ||
      s.subtitle.toLowerCase().includes(q) ||
      String(s.number) === q ||
      s.href.toLowerCase().includes(q),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden border-bulkhead bg-hull p-0">
        <div className="border-b border-bulkhead px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <DialogTitle className="font-heading text-xl font-semibold text-foreground">
                ASTRA-MED 26-Screen Navigation Directory
              </DialogTitle>
              <DialogDescription className="text-xs text-ink-2">
                Jump directly to any of the 16 primary reference screens or 10 specialized operational screens.
              </DialogDescription>
            </div>
            <input
              type="search"
              placeholder="Filter 26 screens by name, # or route..."
              aria-label="Filter screens"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-8 w-64 rounded-md border border-input bg-abyss px-3 text-xs text-foreground outline-none focus-visible:border-telemetry"
            />
          </div>
        </div>
        <div className="scroll-quiet max-h-[68vh] space-y-5 overflow-y-auto p-5">
          {(["Primary 16 Screens", "Additional 10 Screens"] as const).map((cat) => {
            const list = filtered.filter((s) => s.category === cat);
            if (!list.length) return null;
            return (
              <section key={cat}>
                <h3 className="mb-2.5 flex items-center gap-2 text-xs font-semibold tracking-wider text-telemetry uppercase">
                  <Layers className="size-3.5" aria-hidden />
                  {cat} ({list.length})
                </h3>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {list.map((s) => {
                    const active = pathname === s.href;
                    return (
                      <Link
                        key={s.number}
                        href={s.href}
                        onClick={() => onOpenChange(false)}
                        className={cn(
                          "group flex items-start gap-2.5 rounded-lg border p-2.5 transition-colors",
                          active
                            ? "border-telemetry bg-telemetry/10 text-foreground"
                            : "border-bulkhead/70 bg-abyss/60 hover:border-telemetry/60 hover:bg-panel-2",
                        )}
                      >
                        <span
                          className={cn(
                            "readout flex size-6 shrink-0 items-center justify-center rounded text-xs font-bold",
                            active ? "bg-telemetry text-primary-foreground" : "bg-bulkhead/70 text-telemetry",
                          )}
                        >
                          {s.number}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground group-hover:text-telemetry">
                            {s.title}
                          </p>
                          <p className="line-clamp-1 text-[11px] text-ink-3">{s.subtitle}</p>
                          <code className="text-[10px] text-ink-3">{s.href}</code>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AppBreadcrumbs() {
  const pathname = usePathname() ?? "/";
  const [dirOpen, setDirOpen] = useState(false);

  const screen = ALL_26_SCREENS.find((s) => s.href === pathname);
  const parts = pathname.split("/").filter(Boolean);

  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-bulkhead/60 pb-2.5 text-xs">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1.5 text-ink-2">
        <Link
          href="/"
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-ink-2 transition-colors hover:bg-sidebar-accent hover:text-telemetry"
        >
          <Home className="size-3.5 text-telemetry" aria-hidden />
          <span>Mission Control</span>
        </Link>
        {parts.map((seg, i) => {
          const href = "/" + parts.slice(0, i + 1).join("/");
          const isLast = i === parts.length - 1;
          const label = SEGMENT_LABELS[seg] ?? decodeURIComponent(seg);
          return (
            <span key={href} className="inline-flex items-center gap-1.5">
              <ChevronRight className="size-3.5 text-ink-3" aria-hidden />
              {isLast ? (
                <span className="font-medium text-foreground" aria-current="page">
                  {label}
                </span>
              ) : (
                <Link href={href} className="rounded px-1.5 py-0.5 hover:bg-sidebar-accent hover:text-telemetry">
                  {label}
                </Link>
              )}
            </span>
          );
        })}
        {screen && (
          <span className="ml-1.5 rounded-full border border-telemetry/30 bg-telemetry/10 px-2 py-0.5 text-[11px] font-medium text-telemetry">
            Screen #{screen.number} of 26
          </span>
        )}
      </nav>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="xs"
          onClick={() => setDirOpen(true)}
          className="border-telemetry/35 bg-hull/80 text-telemetry hover:bg-telemetry/15"
        >
          <Compass className="size-3.5" aria-hidden />
          All 26 Screens
        </Button>
      </div>
      <ScreenDirectoryDialog open={dirOpen} onOpenChange={setDirOpen} />
    </div>
  );
}
