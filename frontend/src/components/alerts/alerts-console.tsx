"use client";

import { BellRing } from "lucide-react";
import { useMemo, useState } from "react";

import { AstronautSwitcher } from "@/components/crew/astronaut-switcher";
import { Panel } from "@/components/data/panel";
import { EmptyState, QueryView } from "@/components/data/states";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAlerts, useAstronauts, type AlertFilters } from "@/lib/api/hooks";
import type { AlertStatus, Severity } from "@/lib/api/types";

import { AlertList } from "./alert-list";

const STATUSES: { value: AlertStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
];
const SEVERITIES: { value: Severity; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "caution", label: "Caution" },
  { value: "advisory", label: "Advisory" },
];
const WINDOWS = [
  { value: "24", label: "Last 24 h" },
  { value: "72", label: "Last 3 days" },
  { value: "168", label: "Last 7 days" },
];

export function AlertsConsole() {
  const [statuses, setStatuses] = useState<AlertStatus[]>(["active", "acknowledged"]);
  const [severities, setSeverities] = useState<Severity[]>([]);
  const [astronaut, setAstronaut] = useState("all");
  const [hours, setHours] = useState("168");
  const crew = useAstronauts();

  const filters: AlertFilters = useMemo(
    () => ({
      status: statuses.length ? statuses : undefined,
      severity: severities.length ? severities : undefined,
      astronaut_id: astronaut === "all" ? undefined : astronaut,
      hours: Number(hours),
    }),
    [statuses, severities, astronaut, hours],
  );
  const alerts = useAlerts(filters);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3" role="group" aria-label="Alert filters">
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          value={statuses}
          onValueChange={(v) => setStatuses(v as AlertStatus[])}
          aria-label="Status"
        >
          {STATUSES.map((s) => (
            <ToggleGroupItem key={s.value} value={s.value} className="px-3 text-xs">
              {s.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <ToggleGroup
          type="multiple"
          variant="outline"
          size="sm"
          value={severities}
          onValueChange={(v) => setSeverities(v as Severity[])}
          aria-label="Severity"
        >
          {SEVERITIES.map((s) => (
            <ToggleGroupItem key={s.value} value={s.value} className="px-3 text-xs">
              {s.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {crew.data && (
          <AstronautSwitcher crew={crew.data} value={astronaut} onChange={setAstronaut} includeAll label="Filter by crew member" />
        )}
        <Select value={hours} onValueChange={setHours}>
          <SelectTrigger className="w-36" aria-label="Look-back window">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOWS.map((w) => (
              <SelectItem key={w.value} value={w.value}>
                {w.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Panel
        title={alerts.data ? `${alerts.data.length} alert${alerts.data.length === 1 ? "" : "s"}` : "Alerts"}
        description="Newest first. Acknowledge to show an operator has seen it; resolve to close it."
      >
        <QueryView
          query={alerts}
          isEmpty={(d) => d.length === 0}
          empty={
            <EmptyState title="No alerts match these filters" icon={<BellRing className="size-5" />}>
              Widen the filters, or start a test scenario to generate one.
            </EmptyState>
          }
        >
          {(data) => (
            <div className={alerts.isPlaceholderData ? "opacity-60" : undefined}>
              <AlertList alerts={data} crew={crew.data} />
            </div>
          )}
        </QueryView>
      </Panel>
    </div>
  );
}
