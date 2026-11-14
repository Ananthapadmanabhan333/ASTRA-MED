"use client";

import { ArrowRight, Bell, CheckCircle2, KeyRound, Sliders, User, Users } from "lucide-react";
import Link from "next/link";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useSpaceSources } from "@/lib/api/hooks";
import { useRoles } from "@/lib/api/medical-hooks";
import { useAuth } from "@/lib/auth/store";
import { useDisplayZone, type ZoneValue } from "@/lib/timezone";
import { cn } from "@/lib/utils";

type SettingsSection = "profile" | "users" | "keys" | "simulation" | "notifications";

const SECTIONS: { id: SettingsSection; label: string; icon: typeof User }[] = [
  { id: "profile", label: "Profile", icon: User },
  { id: "users", label: "Users & Roles", icon: Users },
  { id: "keys", label: "Data & API Keys", icon: KeyRound },
  { id: "simulation", label: "Simulation", icon: Sliders },
  { id: "notifications", label: "Notifications", icon: Bell },
];

export function SettingsView() {
  const user = useAuth((s) => s.session?.user);
  const { zone, setZone } = useDisplayZone();
  const sources = useSpaceSources();
  const roles = useRoles();

  const [activeTab, setActiveTab] = useState<SettingsSection>("profile");
  const [name, setName] = useState(user?.display_name ?? "Dr. Alex Carter");
  const [email, setEmail] = useState("alex.carter@astramed.org");
  const [roleLabel, setRoleLabel] = useState("Mission Specialist");

  const [simSeed, setSimSeed] = useState(42);
  const [simCadence, setSimCadence] = useState("5s");
  const [autoConformal, setAutoConformal] = useState(true);

  const [p1Toast, setP1Toast] = useState(true);
  const [p2Toast, setP2Toast] = useState(true);
  const [spaceWeatherAlerts, setSpaceWeatherAlerts] = useState(true);
  const [escalationMinutes, setEscalationMinutes] = useState(10);

  function saveProfile(e: FormEvent) {
    e.preventDefault();
    toast.success(`Profile settings saved for ${name} (${zone})`);
  }

  return (
    <div className="space-y-5">
      {/* Header matching Screen 15 */}
      <div>
        <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Settings</h1>
        <p className="text-sm text-ink-2">Manage mission, users and system configuration</p>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Left Vertical Menu matching Screen 15 */}
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-3 lg:col-span-3">
          <nav aria-label="Settings sections" className="space-y-1.5">
            {SECTIONS.map((sec) => {
              const Icon = sec.icon;
              const active = activeTab === sec.id;
              return (
                <button
                  key={sec.id}
                  type="button"
                  onClick={() => setActiveTab(sec.id)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-lg border px-3.5 py-2.5 text-left text-xs font-semibold transition-all",
                    active
                      ? "border-telemetry/60 bg-telemetry/15 text-telemetry shadow-[0_0_15px_rgba(61,216,234,0.15)]"
                      : "border-transparent text-ink-2 hover:border-bulkhead hover:bg-abyss/60 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  <span>{sec.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right Workspace Card matching Screen 15 */}
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-6 lg:col-span-9">
          {activeTab === "profile" && (
            <form onSubmit={saveProfile} className="space-y-5">
              <div>
                <h2 className="text-lg font-bold text-foreground">Profile Settings</h2>
                <p className="text-xs text-ink-3">Configure operator identity, display role and mission clock zone</p>
              </div>

              <div className="grid max-w-xl gap-4">
                <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[8rem_1fr]">
                  <label htmlFor="prof-name" className="text-xs font-medium text-ink-2">
                    Name
                  </label>
                  <input
                    id="prof-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="h-10 rounded-lg border border-bulkhead bg-[#091526] px-3.5 text-sm text-foreground outline-none focus:border-telemetry"
                  />
                </div>

                <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[8rem_1fr]">
                  <label htmlFor="prof-email" className="text-xs font-medium text-ink-2">
                    Email
                  </label>
                  <input
                    id="prof-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="h-10 rounded-lg border border-bulkhead bg-[#091526] px-3.5 text-sm text-foreground outline-none focus:border-telemetry"
                  />
                </div>

                <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[8rem_1fr]">
                  <label htmlFor="prof-role" className="text-xs font-medium text-ink-2">
                    Role
                  </label>
                  <select
                    id="prof-role"
                    value={roleLabel}
                    onChange={(e) => setRoleLabel(e.target.value)}
                    className="h-10 rounded-lg border border-bulkhead bg-[#091526] px-3.5 text-sm text-foreground outline-none focus:border-telemetry"
                  >
                    <option value="Mission Specialist">Mission Specialist</option>
                    <option value="Flight Surgeon">Flight Surgeon</option>
                    <option value="Flight Director">Flight Director</option>
                    <option value="Research Analyst">Research Analyst</option>
                    <option value="System Administrator">System Administrator</option>
                  </select>
                </div>

                <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[8rem_1fr]">
                  <label htmlFor="prof-tz" className="text-xs font-medium text-ink-2">
                    Timezone
                  </label>
                  <select
                    id="prof-tz"
                    value={zone}
                    onChange={(e) => setZone(e.target.value as ZoneValue)}
                    className="h-10 rounded-lg border border-bulkhead bg-[#091526] px-3.5 text-sm text-foreground outline-none focus:border-telemetry"
                  >
                    <option value="UTC">UTC</option>
                    <option value="America/Chicago">America/Chicago (Houston MCC)</option>
                    <option value="local">Local Browser Time</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end pt-3">
                <button
                  type="submit"
                  className="rounded-lg bg-telemetry px-5 py-2.5 text-xs font-bold text-abyss shadow-[0_0_16px_rgba(61,216,234,0.3)] transition-all hover:brightness-110"
                >
                  Save Changes
                </button>
              </div>
            </form>
          )}

          {activeTab === "users" && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-foreground">Users &amp; Roles Configuration</h2>
                  <p className="text-xs text-ink-3">Role-based access control (RBAC) permissions and active mission staff</p>
                </div>
                <Button asChild size="sm" variant="outline">
                  <Link href="/admin">
                    Open Full User &amp; Role Management <ArrowRight className="ml-1 size-3.5" aria-hidden />
                  </Link>
                </Button>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(roles.data?.roles ?? [
                  { key: "mission_operator", label: "Mission Operator", description: "Mission command & simulation control", permissions: ["health:read", "alerts:write", "simulation:control"] },
                  { key: "flight_surgeon", label: "Flight Surgeon", description: "Clinical decision support & report sign-off", permissions: ["health:read", "reports:write", "reports:review"] },
                  { key: "analyst", label: "Research Analyst", description: "Read-only analytics, AI models & NASA datasets", permissions: ["health:read", "ai:read", "space:read"] },
                  { key: "admin", label: "Administrator", description: "Full user provisioning, audit logs & system repair", permissions: ["users:manage", "audit:read"] },
                ]).map((r) => (
                  <div key={r.key} className="rounded-lg border border-bulkhead/70 bg-abyss/50 p-4">
                    <p className="text-sm font-bold text-foreground">{r.label}</p>
                    <p className="mt-0.5 text-xs text-ink-2">{r.description}</p>
                    <p className="mt-2 font-mono text-[11px] text-telemetry">
                      {r.permissions.length} granted capabilities
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "keys" && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-bold text-foreground">Data &amp; API Keys</h2>
                <p className="text-xs text-ink-3">NASA Open API credentials and background collector synchronization</p>
              </div>

              <div className="rounded-lg border border-bulkhead bg-abyss/60 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">NASA Open Data API Key (DONKI / OSDR)</p>
                    <p className="text-xs text-ink-2">
                      {sources.data?.api_key_configured
                        ? "Personal NASA API key configured on backend server."
                        : "Using public NASA DEMO_KEY with automatic SQLite cache fallback."}
                    </p>
                  </div>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-nominal/40 bg-nominal/15 px-3 py-1 text-xs font-semibold text-nominal">
                    <CheckCircle2 className="size-3.5" aria-hidden /> Connected
                  </span>
                </div>
              </div>

              <div className="space-y-2">
                {(sources.data?.sources ?? []).map((s) => (
                  <div
                    key={s.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-bulkhead/60 bg-abyss/40 px-4 py-3 text-xs"
                  >
                    <div>
                      <p className="font-semibold text-foreground">{s.name}</p>
                      <p className="text-ink-3">
                        {s.records.toLocaleString()} stored records · {s.update_frequency}
                      </p>
                    </div>
                    <span className="font-mono text-nominal">{s.health.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "simulation" && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-bold text-foreground">Simulation Engine Parameters</h2>
                <p className="text-xs text-ink-3">Deterministic PRNG seed, telemetry cadence, and conformal calibration</p>
              </div>

              <div className="grid max-w-xl gap-4">
                <div className="flex items-center justify-between gap-4">
                  <label htmlFor="set-seed" className="text-xs font-medium text-ink-2">
                    Deterministic PRNG Seed
                  </label>
                  <input
                    id="set-seed"
                    type="number"
                    value={simSeed}
                    onChange={(e) => setSimSeed(Number(e.target.value))}
                    className="h-9 w-36 rounded-lg border border-bulkhead bg-[#091526] px-3 font-mono text-sm text-foreground"
                  />
                </div>

                <div className="flex items-center justify-between gap-4">
                  <label htmlFor="set-cadence" className="text-xs font-medium text-ink-2">
                    Live Telemetry Broadcast Cadence
                  </label>
                  <select
                    id="set-cadence"
                    value={simCadence}
                    onChange={(e) => setSimCadence(e.target.value)}
                    className="h-9 w-36 rounded-lg border border-bulkhead bg-[#091526] px-3 text-xs text-foreground"
                  >
                    <option value="1s">1 second</option>
                    <option value="5s">5 seconds</option>
                    <option value="15s">15 seconds</option>
                  </select>
                </div>

                <label className="flex items-center justify-between gap-4 text-xs text-ink-2">
                  <span>Split-Conformal 90% Prediction Interval Calibration</span>
                  <input
                    type="checkbox"
                    checked={autoConformal}
                    onChange={(e) => setAutoConformal(e.target.checked)}
                    className="size-4 accent-telemetry"
                  />
                </label>
              </div>

              <div className="pt-2">
                <Button
                  size="sm"
                  onClick={() => toast.success(`Simulation parameters updated (seed=${simSeed}, cadence=${simCadence})`)}
                >
                  Apply Simulation Defaults
                </Button>
              </div>
            </div>
          )}

          {activeTab === "notifications" && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-bold text-foreground">Notification &amp; Escalation Rules</h2>
                  <p className="text-xs text-ink-3">Configure alert banners, flight surgeon escalation timers, and space weather advisories</p>
                </div>
                <Button asChild size="sm" variant="outline">
                  <Link href="/notifications">Open Notification Centre</Link>
                </Button>
              </div>

              <div className="space-y-3 max-w-xl">
                <label className="flex items-center justify-between rounded-lg border border-bulkhead/60 bg-abyss/40 px-4 py-3 text-xs">
                  <span className="font-medium text-foreground">P1 Critical Physiological Alerts (Immediate Banner)</span>
                  <input
                    type="checkbox"
                    checked={p1Toast}
                    onChange={(e) => setP1Toast(e.target.checked)}
                    className="size-4 accent-telemetry"
                  />
                </label>

                <label className="flex items-center justify-between rounded-lg border border-bulkhead/60 bg-abyss/40 px-4 py-3 text-xs">
                  <span className="font-medium text-foreground">P2 Caution &amp; AI Early Warning Toasts</span>
                  <input
                    type="checkbox"
                    checked={p2Toast}
                    onChange={(e) => setP2Toast(e.target.checked)}
                    className="size-4 accent-telemetry"
                  />
                </label>

                <label className="flex items-center justify-between rounded-lg border border-bulkhead/60 bg-abyss/40 px-4 py-3 text-xs">
                  <span className="font-medium text-foreground">NASA DONKI Solar Flare &amp; SEP Notifications</span>
                  <input
                    type="checkbox"
                    checked={spaceWeatherAlerts}
                    onChange={(e) => setSpaceWeatherAlerts(e.target.checked)}
                    className="size-4 accent-telemetry"
                  />
                </label>

                <div className="flex items-center justify-between rounded-lg border border-bulkhead/60 bg-abyss/40 px-4 py-3 text-xs">
                  <span className="font-medium text-foreground">Unacknowledged Alert Auto-Escalation Window (minutes)</span>
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={escalationMinutes}
                    onChange={(e) => setEscalationMinutes(Number(e.target.value))}
                    className="h-8 w-20 rounded border border-bulkhead bg-[#091526] px-2 font-mono text-foreground"
                  />
                </div>
              </div>

              <Button
                size="sm"
                onClick={() => toast.success("Notification preferences saved")}
              >
                Save Notification Rules
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
