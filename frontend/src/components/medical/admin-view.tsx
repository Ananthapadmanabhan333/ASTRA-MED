"use client";

import { ArrowRight, ShieldCheck, Users as UsersIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { EmptyState, QueryView } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { useAudit, useCreateUser, useRoles, useUpdateUser, useUsers } from "@/lib/api/medical-hooks";
import type { RoleKey } from "@/lib/api/types";
import { useAuth, useCan } from "@/lib/auth/store";
import { utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const ROLES: { key: RoleKey; label: string }[] = [
  { key: "flight_surgeon", label: "Flight surgeon" },
  { key: "mission_operator", label: "Mission operator" },
  { key: "analyst", label: "Analyst" },
  { key: "admin", label: "Administrator" },
];

function Users() {
  const users = useUsers(true);
  const update = useUpdateUser();
  const create = useCreateUser();
  const me = useAuth((s) => s.session?.user.id);
  const [form, setForm] = useState({ username: "", display_name: "", role: "analyst" as RoleKey, password: "" });
  return (
    <Panel title="User accounts" description="Changing a role or deactivating an account signs that user out everywhere.">
      <QueryView query={users}>
        {(list) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-ink-2"><tr className="border-b border-bulkhead"><th className="py-2 font-medium">User</th><th className="py-2 font-medium">Role</th><th className="py-2 font-medium">Last sign-in</th><th className="py-2 font-medium">State</th><th className="py-2 font-medium" /></tr></thead>
              <tbody>
                {list.map((u) => (
                  <tr key={u.id} className="border-b border-bulkhead/50">
                    <td className="py-2">{u.display_name} <span className="block text-xs text-ink-3">{u.username}</span></td>
                    <td className="py-2">
                      <select aria-label={`Role of ${u.username}`} value={u.role} disabled={u.id === me || update.isPending}
                        onChange={(e) => update.mutate({ userId: u.id, role: e.target.value as RoleKey }, { onSuccess: () => toast.success("Role updated"), onError: (er) => toast.error(er.message) })}
                        className="h-8 rounded-md border border-input bg-abyss px-2 text-sm">
                        {ROLES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                      </select>
                    </td>
                    <td className="py-2 text-xs text-ink-2">{u.last_login_at ? `${utcDayTime(u.last_login_at)} UTC` : "never"}</td>
                    <td className="py-2 text-xs">{u.locked_until ? <span className="text-caution">locked</span> : u.active ? "active" : <span className="text-ink-3">inactive</span>}</td>
                    <td className="py-2 text-right">
                      {u.locked_until && <Button size="xs" variant="outline" onClick={() => update.mutate({ userId: u.id, unlock: true })}>Unlock</Button>}{" "}
                      {u.id !== me && <Button size="xs" variant="ghost" onClick={() => update.mutate({ userId: u.id, active: !u.active })}>{u.active ? "Deactivate" : "Activate"}</Button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
      <form className="mt-4 grid gap-2 sm:grid-cols-5" onSubmit={(e) => { e.preventDefault(); create.mutate(form, { onSuccess: () => { toast.success("User created"); setForm({ ...form, username: "", display_name: "", password: "" }); }, onError: (er) => toast.error(er.message) }); }}>
        <input aria-label="Username" required placeholder="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm" />
        <input aria-label="Display name" required placeholder="Display name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm" />
        <select aria-label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as RoleKey })} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm">
          {ROLES.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
        <input aria-label="Initial password" required type="password" autoComplete="new-password" placeholder="Password (12+ characters)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm" />
        <Button type="submit" size="sm" disabled={create.isPending}>Add user</Button>
      </form>
    </Panel>
  );
}

function Audit() {
  const [username, setUsername] = useState("");
  const [outcome, setOutcome] = useState("");
  const [hours, setHours] = useState(24);
  const q = useAudit({ username: username || undefined, outcome: outcome || undefined, hours }, true);
  return (
    <Panel title="Audit log" description="Sign-ins, views of health records (once per 5 minutes per resource), changes and denials. Identifiers only, never measurement values."
      actions={
        <div className="flex flex-wrap gap-2">
          <input aria-label="Filter by username" placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} className="h-8 w-32 rounded-md border border-input bg-abyss px-2 text-sm" />
          <select aria-label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm">
            <option value="">Any outcome</option><option value="success">Success</option><option value="denied">Denied</option><option value="failure">Failure</option>
          </select>
          <select aria-label="Window" value={hours} onChange={(e) => setHours(Number(e.target.value))} className="h-8 rounded-md border border-input bg-abyss px-2 text-sm">
            <option value={1}>1 h</option><option value={24}>24 h</option><option value={168}>7 d</option><option value={720}>30 d</option>
          </select>
        </div>
      }>
      <QueryView query={q} isEmpty={(d) => d.length === 0} empty={<EmptyState title="No entries" />}>
        {(rows) => (
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="sticky top-0 bg-hull text-ink-2"><tr className="border-b border-bulkhead"><th className="py-1.5 font-medium">Time (UTC)</th><th className="py-1.5 font-medium">User</th><th className="py-1.5 font-medium">Action</th><th className="py-1.5 font-medium">Resource</th><th className="py-1.5 font-medium">Outcome</th><th className="py-1.5 font-medium">Client</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-bulkhead/40">
                    <td className="py-1.5 tabular-nums">{utcDayTime(r.ts)}</td>
                    <td className="py-1.5">{r.username ?? "—"} <span className="text-ink-3">{r.role ?? ""}</span></td>
                    <td className="py-1.5 font-mono">{r.action}</td>
                    <td className="py-1.5">{r.resource_type ?? ""} {r.resource_id ?? ""}</td>
                    <td className={cn("py-1.5", r.outcome === "denied" ? "text-caution" : r.outcome === "failure" ? "text-critical" : "text-nominal")}>{r.outcome}{r.status_code ? ` ${r.status_code}` : ""}</td>
                    <td className="py-1.5 text-ink-3">{r.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

function Matrix() {
  const q = useRoles();
  return (
    <Panel title="Roles and permissions" description="Enforced by the API on every request.">
      <QueryView query={q}>
        {(m) => (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-xs">
              <thead className="text-ink-2"><tr className="border-b border-bulkhead"><th className="py-1.5 font-medium">Permission</th>{m.roles.map((r) => <th key={r.key} className="py-1.5 font-medium">{r.label}</th>)}</tr></thead>
              <tbody>
                {m.permissions.map((p) => (
                  <tr key={p.key} className="border-b border-bulkhead/40">
                    <td className="py-1.5"><span className="font-mono">{p.key}</span><span className="block text-ink-3">{p.description}</span></td>
                    {m.roles.map((r) => <td key={r.key} className="py-1.5">{r.permissions.includes(p.key) ? <span className="text-nominal">yes</span> : <span className="text-ink-3">no</span>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryView>
    </Panel>
  );
}

export function AdminView() {
  const canUsers = useCan("users:manage");
  const canAudit = useCan("audit:read");
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <UsersIcon className="size-4" aria-hidden />
            <span>Mission Staff Directory &amp; Role-Based Access Control</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            User &amp; Role Management
          </h1>
          <p className="text-sm text-ink-2">
            Provision mission staff accounts, assign Flight Surgeon / Operator / Analyst roles, and audit API permissions
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <Link href="/security">
              <ShieldCheck className="mr-1 size-3.5 text-telemetry" aria-hidden /> Security &amp; Audit Logs
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/settings">
              Settings <ArrowRight className="ml-1 size-3.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </div>

      {canUsers && <Users />}
      <Matrix />
      {canAudit && <Audit />}
      {!canUsers && !canAudit && <EmptyState title="Administrator access required for account mutation" />}
    </div>
  );
}
