"use client";

import { BellRing, BrainCircuit, ChevronLeft, ChevronRight, Fingerprint, GanttChart, Stethoscope, Users } from "lucide-react";
import Link from "next/link";

import { useAstronauts } from "@/lib/api/hooks";
import { crewColor } from "@/lib/crew";

/** Moves between crew members and into every view of one crew member's digital health profile. */
export function CrewProfileNav({ id }: { id: string }) {
  const crew = useAstronauts();
  const list = crew.data ?? [];
  const i = list.findIndex((a) => a.id === id);
  const prev = i > 0 ? list[i - 1] : list[list.length - 1];
  const next = i >= 0 && i < list.length - 1 ? list[i + 1] : list[0];
  const links = [
    { href: `/twin?astronaut=${id}`, label: "Digital twin", icon: Fingerprint },
    { href: `/medical?astronaut=${id}`, label: "Medical intelligence", icon: Stethoscope },
    { href: `/intelligence?astronaut=${id}`, label: "AI intelligence", icon: BrainCircuit },
    { href: `/alerts?astronaut=${id}`, label: "Alerts", icon: BellRing },
    { href: `/timeline?astronaut=${id}`, label: "Timeline", icon: GanttChart },
  ];
  return (
    <nav aria-label="Crew member navigation" className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-bulkhead/70 bg-hull/60 px-3 py-2 text-sm">
      <Link href="/crew" className="inline-flex items-center gap-1.5 text-ink-2 hover:text-telemetry">
        <Users className="size-4" aria-hidden /> Crew monitoring
      </Link>
      {list.length > 1 && prev && next && (
        <span className="flex items-center gap-1">
          <Link href={`/crew/${prev.id}`} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-ink-2 hover:bg-sidebar-accent hover:text-foreground" aria-label={`Previous: ${prev.name}`}>
            <ChevronLeft className="size-4" aria-hidden />
            <span className="size-2 rounded-full" style={{ background: crewColor(prev.id) }} aria-hidden />
            <span className="hidden sm:inline">{prev.name}</span>
          </Link>
          <Link href={`/crew/${next.id}`} className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-ink-2 hover:bg-sidebar-accent hover:text-foreground" aria-label={`Next: ${next.name}`}>
            <span className="size-2 rounded-full" style={{ background: crewColor(next.id) }} aria-hidden />
            <span className="hidden sm:inline">{next.name}</span>
            <ChevronRight className="size-4" aria-hidden />
          </Link>
        </span>
      )}
      <span className="ml-auto flex flex-wrap gap-x-4 gap-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className="inline-flex items-center gap-1.5 text-ink-2 hover:text-telemetry">
            <Icon className="size-3.5" aria-hidden /> {label}
          </Link>
        ))}
      </span>
    </nav>
  );
}
