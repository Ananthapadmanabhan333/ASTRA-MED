"use client";

import { Orbit, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { useEffect, type ReactNode } from "react";

import { RouteAccess } from "@/components/auth/route-access";
import { ErrorBoundary } from "@/components/mc/error-boundary";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { MissionHeader } from "./mission-header";
import { Nav } from "./nav";
import { useShell } from "./shell-store";

function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2 rounded-md px-1 py-1" aria-label="ASTRA-MED mission control home">
      <Orbit className="size-6 shrink-0 text-telemetry" aria-hidden />
      {!compact && (
        <span className="font-heading text-xl font-bold tracking-tight">
          ASTRA<span className="font-medium text-ink-2">-MED</span>
        </span>
      )}
    </Link>
  );
}

function Sidebar() {
  const collapsed = useShell((s) => s.collapsed);
  const toggle = useShell((s) => s.toggleCollapsed);
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-bulkhead bg-sidebar transition-[width] duration-200 lg:flex",
        collapsed ? "w-[60px]" : "w-60",
      )}
      aria-label="Sidebar"
    >
      <div className={cn("pt-4 pb-4", collapsed ? "flex justify-center px-0" : "px-4")}>
        <Wordmark compact={collapsed} />
        {!collapsed && <p className="mt-1 px-1 text-xs text-ink-3">Crew health mission control</p>}
      </div>
      <div className={cn("scroll-quiet flex-1 overflow-y-auto pb-4", collapsed ? "px-1.5" : "px-3")}>
        <Nav collapsed={collapsed} />
      </div>
      <div className={cn("border-t border-bulkhead", collapsed ? "flex justify-center py-2" : "px-3 py-2")}>
        <Button
          variant="ghost"
          size={collapsed ? "icon-sm" : "sm"}
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className={cn("text-ink-2", !collapsed && "w-full justify-start")}
        >
          {collapsed ? <PanelLeftOpen aria-hidden /> : <PanelLeftClose aria-hidden />}
          {!collapsed && "Collapse"}
        </Button>
      </div>
      {!collapsed && (
        <p className="border-t border-bulkhead px-4 py-3 text-xs leading-relaxed text-ink-3">
          Research prototype for NASA Space Apps 2026. Not a medical device. Not clinically validated.
        </p>
      )}
    </aside>
  );
}

function MobileNav() {
  const open = useShell((s) => s.mobileOpen);
  const setOpen = useShell((s) => s.setMobileOpen);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="top-0 left-0 flex h-dvh max-h-dvh w-72 max-w-[85vw] translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-y-0 border-l-0 border-r border-bulkhead bg-sidebar p-0">
        <div className="px-4 pt-4 pb-3">
          <DialogTitle asChild>
            <div>
              <Wordmark />
            </div>
          </DialogTitle>
          <DialogDescription className="mt-1 px-1 text-xs text-ink-3">Crew health mission control</DialogDescription>
        </div>
        <div className="scroll-quiet flex-1 overflow-y-auto px-3 pb-4">
          <Nav onNavigate={() => setOpen(false)} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const hydrate = useShell((s) => s.hydrate);
  useEffect(() => hydrate(), [hydrate]);
  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <MobileNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <MissionHeader />
        <main id="main" className="mx-auto w-full max-w-[1680px] flex-1 px-3 py-4 sm:px-5 sm:py-5">
          <ErrorBoundary label="This page" className="mx-auto max-w-2xl">
            <RouteAccess>{children}</RouteAccess>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
