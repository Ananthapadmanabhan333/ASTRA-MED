"use client";

import { FlaskConical, Play, Square } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AstronautSwitcher } from "@/components/crew/astronaut-switcher";
import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  useAstronauts,
  useCancelScenario,
  useScenarios,
  useSimulationEvents,
  useStartScenario,
} from "@/lib/api/hooks";
import type { ScenarioKey } from "@/lib/api/types";
import { duration } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

const DURATIONS = [
  { value: "default", label: "Scenario default" },
  { value: "60", label: "1 minute" },
  { value: "120", label: "2 minutes" },
  { value: "300", label: "5 minutes" },
  { value: "600", label: "10 minutes" },
];

export function ScenarioConsole() {
  const scenarios = useScenarios();
  const crew = useAstronauts();
  const events = useSimulationEvents();
  const start = useStartScenario();
  const cancel = useCancelScenario();
  const now = useNow(1000);

  const [astronaut, setAstronaut] = useState("AST-01");
  const [key, setKey] = useState<ScenarioKey>("tachycardia");
  const [intensity, setIntensity] = useState(1);
  const [length, setLength] = useState("default");

  const spec = scenarios.data?.find((s) => s.key === key);
  const names = new Map(crew.data?.map((a) => [a.id, a.name]));
  const running = events.data?.filter((e) => e.active && !e.cancelled_at) ?? [];

  const submit = () => {
    start.mutate(
      {
        scenario: key,
        astronaut_id: spec?.crew_wide ? null : astronaut,
        intensity,
        duration_seconds: length === "default" ? null : Number(length),
      },
      {
        onSuccess: (e) =>
          toast.success("Test scenario started", {
            description: `${e.label} for ${e.astronaut_id ? names.get(e.astronaut_id) : "the whole crew"}.`,
          }),
        onError: (err) => toast.error("Couldn't start the scenario", { description: err.message }),
      },
    );
  };

  return (
    <Panel
      raised
      title="Event simulation console"
      description="Inject a software test scenario into one crew member's simulated data, then watch detection, alerts and displays respond. Scenarios are test patterns, not diagnoses."
    >
      {scenarios.isPending ? (
        <LoadingState rows={4} />
      ) : scenarios.error ? (
        <ErrorState error={scenarios.error} onRetry={() => scenarios.refetch()} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Scenario</legend>
            <div role="radiogroup" className="grid gap-2 sm:grid-cols-2">
              {scenarios.data.map((s) => {
                const selected = s.key === key;
                return (
                  <button
                    key={s.key}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setKey(s.key)}
                    className={cn(
                      "rounded-md border px-3 py-2.5 text-left transition-colors",
                      selected
                        ? "border-telemetry bg-telemetry/8"
                        : "border-bulkhead hover:border-ink-3 hover:bg-accent/40",
                    )}
                  >
                    <span className="flex items-center justify-between gap-2 text-sm font-medium">
                      {s.label}
                      {s.crew_wide && <span className="text-xs font-normal text-ink-3">Whole crew</span>}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-2">{s.description}</span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="space-y-5">
            <div className="space-y-2">
              <Label>Crew member</Label>
              {crew.data && (
                <div className={spec?.crew_wide ? "pointer-events-none opacity-50" : undefined} aria-disabled={spec?.crew_wide}>
                  <AstronautSwitcher crew={crew.data} value={astronaut} onChange={setAstronaut} />
                </div>
              )}
              {spec?.crew_wide && <p className="text-xs text-ink-3">This scenario affects the whole crew.</p>}
            </div>
            <div className="space-y-3">
              <div className="flex items-baseline justify-between">
                <Label htmlFor="intensity">Intensity</Label>
                <span className="text-sm tabular-nums text-ink-2">{intensity.toFixed(2)}×</span>
              </div>
              <Slider
                id="intensity"
                min={0.5}
                max={1.5}
                step={0.05}
                value={[intensity]}
                onValueChange={([v]) => setIntensity(v)}
                aria-label="Scenario intensity"
              />
            </div>
            <div className="space-y-2">
              <Label>Duration</Label>
              <Select value={length} onValueChange={setLength}>
                <SelectTrigger className="w-full" aria-label="Scenario duration">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DURATIONS.map((d) => (
                    <SelectItem key={d.value} value={d.value}>
                      {d.value === "default" && spec ? `Default (${duration(spec.default_duration_s)})` : d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button className="w-full" onClick={submit} disabled={start.isPending}>
              <Play aria-hidden /> {start.isPending ? "Starting…" : "Start test scenario"}
            </Button>
          </div>
        </div>
      )}

      <div className="mt-6 border-t border-bulkhead/70 pt-4">
        <h3 className="mb-2 text-sm font-medium">Running now</h3>
        {running.length === 0 ? (
          <p className="text-sm text-ink-2">No test scenarios are running.</p>
        ) : (
          <ul className="space-y-2">
            {running.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-3 rounded-md bg-abyss/50 px-3 py-2">
                <FlaskConical className="size-4 text-caution" aria-hidden />
                <span className="text-sm">
                  {e.label}{" "}
                  <span className="text-ink-2">
                    for {e.astronaut_id ? names.get(e.astronaut_id) ?? e.astronaut_id : "the whole crew"}
                  </span>
                </span>
                <span className="text-xs text-ink-3">
                  {e.triggered_by === "random" ? "Started by simulator" : "Started by operator"}
                  {now && `, ${duration((Date.parse(e.ends_at) - now) / 1000)} left`}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={cancel.isPending}
                  onClick={() =>
                    cancel.mutate(e.id, {
                      onSuccess: () => toast.success("Test scenario stopped", { description: e.label }),
                      onError: (err) => toast.error("Couldn't stop the scenario", { description: err.message }),
                    })
                  }
                >
                  <Square aria-hidden /> Stop
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
