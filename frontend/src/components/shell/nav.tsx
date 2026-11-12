"use client";

import {
  Activity,
  BellRing,
  BrainCircuit,
  FlaskConical,
  LayoutDashboard,
  Lightbulb,
  Moon,
  Radiation,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { useLive } from "@/lib/live/store";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Mission control", icon: LayoutDashboard },
  { href: "/intelligence", label: "AI intelligence", icon: BrainCircuit },
  { href: "/crew", label: "Crew health", icon: Users },
  { href: "/vitals", label: "Vitals compare", icon: Activity },
  { href: "/alerts", label: "Alerts", icon: BellRing },
  { href: "/anomalies", label: "Anomalies & tests", icon: FlaskConical },
  { href: "/radiation", label: "Radiation", icon: Radiation },
  { href: "/sleep", label: "Sleep & circadian", icon: Moon },
  { href: "/insights", label: "Insights", icon: Lightbulb },
];

function isActive(pathname: string | null, href: string) {
  if (!pathname) return false;
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function AlertCount() {
  const count = useLive((s) => Object.keys(s.openAlerts).length);
  if (!count) return null;
  return (
    <span className="ml-auto rounded-full bg-critical/15 px-1.5 text-[11px] font-semibold text-critical tabular-nums">
      {count}
      <span className="sr-only"> open alerts</span>
    </span>
  );
}

function NavList({ pathname, layout }: { pathname: string | null; layout: "rail" | "bar" }) {
  return (
    <ul className={cn(layout === "rail" ? "space-y-0.5" : "flex gap-1")}>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <li key={href} className="shrink-0">
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group flex items-center gap-2.5 rounded-md text-sm transition-colors",
                layout === "rail" ? "px-3 py-2" : "px-3 py-1.5 whitespace-nowrap",
                active
                  ? "bg-sidebar-accent text-foreground"
                  : "text-ink-2 hover:bg-sidebar-accent/60 hover:text-foreground",
              )}
            >
              <Icon
                className={cn("size-4 shrink-0", active ? "text-telemetry" : "text-ink-3 group-hover:text-ink-2")}
                aria-hidden
              />
              <span>{label}</span>
              {href === "/alerts" && <AlertCount />}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function ActiveNav({ layout }: { layout: "rail" | "bar" }) {
  const pathname = usePathname();
  return <NavList pathname={pathname} layout={layout} />;
}

export function Nav({ layout }: { layout: "rail" | "bar" }) {
  return (
    <nav aria-label="Primary">
      <Suspense fallback={<NavList pathname={null} layout={layout} />}>
        <ActiveNav layout={layout} />
      </Suspense>
    </nav>
  );
}
