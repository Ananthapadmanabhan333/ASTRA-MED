"use client";

import {
  Activity,
  BarChart3,
  BellRing,
  Bot,
  BrainCircuit,
  CalendarRange,
  ChartScatter,
  ClipboardList,
  Database,
  Fingerprint,
  FlaskConical,
  GanttChart,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  Lightbulb,
  Moon,
  PlayCircle,
  Radiation,
  Satellite,
  ServerCog,
  Siren,
  Stethoscope,
  Sun,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth/store";
import { useLive } from "@/lib/live/store";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Any one of these permissions shows the item (default: health:read). */
  perms?: string[];
}

interface NavGroup {
  label: string | null;
  items: NavItem[];
}

/** Every role signs in with at least one of these, so the page is open to all signed-in users. */
const ANY_ROLE = ["health:read", "space:read", "audit:read", "users:manage"];

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Command",
    items: [
      { href: "/", label: "Mission control", icon: LayoutDashboard },
      { href: "/crew", label: "Crew monitoring", icon: Users },
      { href: "/alerts", label: "Alert centre", icon: BellRing },
      { href: "/timeline", label: "Situational awareness", icon: GanttChart },
      { href: "/simulation", label: "Mission simulation", icon: PlayCircle },
      { href: "/analytics", label: "Mission analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Health and AI",
    items: [
      { href: "/intelligence", label: "AI intelligence", icon: BrainCircuit },
      { href: "/vitals", label: "Vitals compare", icon: Activity },
      { href: "/anomalies", label: "Anomalies & tests", icon: FlaskConical },
      { href: "/sleep", label: "Sleep & circadian", icon: Moon },
      { href: "/insights", label: "Insights", icon: Lightbulb },
    ],
  },
  {
    label: "Medical decision support",
    items: [
      { href: "/overview", label: "Mission health overview", icon: HeartPulse },
      { href: "/twin", label: "Digital twin", icon: Fingerprint },
      { href: "/medical", label: "Medical intelligence", icon: Stethoscope },
      { href: "/assistant", label: "AI medical assistant", icon: Bot, perms: ["assistant:use"] },
      { href: "/emergency", label: "Emergency simulator", icon: Siren },
      { href: "/reports", label: "Incident reports", icon: ClipboardList, perms: ["reports:read"] },
    ],
  },
  {
    label: "Space environment",
    items: [
      { href: "/space/weather", label: "Space weather", icon: Sun, perms: ["space:read"] },
      { href: "/radiation", label: "Radiation intelligence", icon: Radiation },
      { href: "/space/iss", label: "ISS environment", icon: Satellite, perms: ["space:read"] },
      { href: "/space/explorer", label: "NASA data explorer", icon: Database, perms: ["space:read"] },
      { href: "/space/timeline", label: "Space timeline", icon: CalendarRange },
      { href: "/space/correlation", label: "Environment-health", icon: ChartScatter },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/system", label: "System status", icon: ServerCog, perms: ANY_ROLE },
      { href: "/admin", label: "Users & audit log", icon: KeyRound, perms: ["users:manage", "audit:read"] },
    ],
  },
];

function allowed(item: NavItem, permissions: string[] | undefined): boolean {
  return (item.perms ?? ["health:read"]).some((p) => permissions?.includes(p));
}

/** Permissions that open a route: from the longest matching nav entry, else crew health records. */
export function routePermissions(pathname: string): string[] {
  const match = NAV_GROUPS.flatMap((g) => g.items)
    .filter((i) => (i.href === "/" ? pathname === "/" : pathname === i.href || pathname.startsWith(`${i.href}/`)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match?.perms ?? ["health:read"];
}

function useVisibleGroups(): NavGroup[] {
  const permissions = useAuth((s) => s.session?.permissions);
  return NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => allowed(i, permissions)) })).filter(
    (g) => g.items.length > 0,
  );
}

export const NAV: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);

function isActive(pathname: string | null, href: string) {
  if (!pathname) return false;
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function AlertCount({ collapsed }: { collapsed: boolean }) {
  const count = useLive((s) => Object.keys(s.openAlerts).length);
  if (!count) return null;
  return (
    <span
      className={cn(
        "rounded-full bg-critical/15 px-1.5 text-[11px] font-semibold text-critical tabular-nums",
        collapsed ? "absolute -top-1 -right-1 bg-critical px-1 text-[10px] text-[#2a0606]" : "ml-auto",
      )}
    >
      {count}
      <span className="sr-only"> open alerts</span>
    </span>
  );
}

function SimDot({ collapsed }: { collapsed: boolean }) {
  const active = useLive((s) => s.sim?.active);
  if (!active) return null;
  return (
    <span
      className={cn("size-2 rounded-full bg-sandbox", collapsed ? "absolute -top-0.5 -right-0.5" : "ml-auto")}
      title="A sandbox mission is running"
    >
      <span className="sr-only">Sandbox mission running</span>
    </span>
  );
}

function NavLink({ item, pathname, collapsed, onNavigate }: {
  item: NavItem;
  pathname: string | null;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const { href, label, icon: Icon } = item;
  const active = isActive(pathname, href);
  const link = (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-md text-sm transition-colors",
        collapsed ? "mx-auto size-9 justify-center" : "px-2.5 py-[7px]",
        active ? "bg-sidebar-accent text-foreground" : "text-ink-2 hover:bg-sidebar-accent/60 hover:text-foreground",
      )}
    >
      {active && !collapsed && <span aria-hidden className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-telemetry" />}
      <Icon
        className={cn("size-4 shrink-0", active ? "text-telemetry" : "text-ink-3 group-hover:text-ink-2")}
        aria-hidden
      />
      {!collapsed && <span className="truncate">{label}</span>}
      {href === "/alerts" && <AlertCount collapsed={collapsed} />}
      {href === "/simulation" && <SimDot collapsed={collapsed} />}
    </Link>
  );
  return (
    <li>
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>{link}</TooltipTrigger>
          <TooltipContent side="right">{label}</TooltipContent>
        </Tooltip>
      ) : (
        link
      )}
    </li>
  );
}

function NavList({ pathname, collapsed, onNavigate }: {
  pathname: string | null;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const groups = useVisibleGroups();
  return (
    <div className={cn(collapsed ? "space-y-3" : "space-y-5")}>
      {groups.map((group) => (
        <div key={group.label ?? "main"}>
          {group.label &&
            (collapsed ? (
              <div className="mx-3 mb-2 border-t border-bulkhead/70" aria-hidden />
            ) : (
              <p className="mb-1 px-2.5 text-xs font-medium text-ink-3">{group.label}</p>
            ))}
          <ul className="space-y-0.5" aria-label={group.label ?? undefined}>
            {group.items.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} collapsed={collapsed} onNavigate={onNavigate} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ActiveNav(props: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return <NavList pathname={pathname} {...props} />;
}

export function Nav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Primary">
      <Suspense fallback={<NavList pathname={null} collapsed={collapsed} />}>
        <ActiveNav collapsed={collapsed} onNavigate={onNavigate} />
      </Suspense>
    </nav>
  );
}
