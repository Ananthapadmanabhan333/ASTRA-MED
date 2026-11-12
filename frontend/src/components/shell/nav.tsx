"use client";

import {
  Activity,
  Bot,
  ClipboardList,
  Fingerprint,
  HeartPulse,
  KeyRound,
  Siren,
  Stethoscope,
  BellRing,
  BrainCircuit,
  CalendarRange,
  ChartScatter,
  Database,
  FlaskConical,
  LayoutDashboard,
  Lightbulb,
  Moon,
  Radiation,
  Satellite,
  Sun,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

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

export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/", label: "Mission control", icon: LayoutDashboard },
      { href: "/intelligence", label: "AI intelligence", icon: BrainCircuit },
      { href: "/crew", label: "Crew health", icon: Users },
      { href: "/vitals", label: "Vitals compare", icon: Activity },
      { href: "/alerts", label: "Alerts", icon: BellRing },
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
      { href: "/space/timeline", label: "Mission timeline", icon: CalendarRange },
      { href: "/space/correlation", label: "Environment-health", icon: ChartScatter },
    ],
  },
  {
    label: "Administration",
    items: [{ href: "/admin", label: "Users & audit log", icon: KeyRound, perms: ["users:manage", "audit:read"] }],
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

function NavLink({ item, pathname, layout }: { item: NavItem; pathname: string | null; layout: "rail" | "bar" }) {
  const { href, label, icon: Icon } = item;
  const active = isActive(pathname, href);
  return (
    <li className="shrink-0">
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
}

function NavList({ pathname, layout }: { pathname: string | null; layout: "rail" | "bar" }) {
  const groups = useVisibleGroups();
  if (layout === "bar") {
    return (
      <ul className="flex gap-1">
        {groups.flatMap((g) => g.items).map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} layout="bar" />
        ))}
      </ul>
    );
  }
  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <div key={group.label ?? "main"}>
          {group.label && (
            <p className="mb-1 px-3 text-[11px] font-medium tracking-wide text-ink-3 uppercase">{group.label}</p>
          )}
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} layout="rail" />
            ))}
          </ul>
        </div>
      ))}
    </div>
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
