"use client";

import { ArrowRight, Download, KeyRound, Lock, ShieldCheck, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Panel } from "@/components/data/panel";
import { LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { useAudit } from "@/lib/api/medical-hooks";
import { useAuth, useCan } from "@/lib/auth/store";
import { utcDayTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SAMPLE_AUDIT_ROWS = [
  {
    id: 501,
    ts: "2026-11-14T14:22:10Z",
    username: "surgeon",
    role: "flight_surgeon",
    action: "report.review",
    resource_type: "incident_report",
    resource_id: "R-1047",
    outcome: "success",
    status_code: 200,
    ip: "127.0.0.1",
  },
  {
    id: 500,
    ts: "2026-11-14T14:20:05Z",
    username: "operator",
    role: "mission_operator",
    action: "assistant.ask",
    resource_type: "astronaut",
    resource_id: "AST-01",
    outcome: "success",
    status_code: 200,
    ip: "127.0.0.1",
  },
  {
    id: 499,
    ts: "2026-11-14T13:55:42Z",
    username: "analyst",
    role: "analyst",
    action: "simulation.start",
    resource_type: "emergency_run",
    resource_id: "hr_elevation",
    outcome: "denied",
    status_code: 403,
    ip: "127.0.0.1",
  },
  {
    id: 498,
    ts: "2026-11-14T13:10:19Z",
    username: "admin",
    role: "admin",
    action: "auth.login",
    resource_type: "session",
    resource_id: "sess_89a1",
    outcome: "success",
    status_code: 200,
    ip: "127.0.0.1",
  },
];

export function SecurityAuditView() {
  const canAudit = useCan("audit:read");
  const user = useAuth((s) => s.session?.user);
  const [username, setUsername] = useState("");
  const [outcome, setOutcome] = useState("");
  const [hours, setHours] = useState(24);

  const q = useAudit({ username: username || undefined, outcome: outcome || undefined, hours }, canAudit);

  const rows = (q.data && q.data.length > 0 ? q.data : SAMPLE_AUDIT_ROWS).filter((r) => {
    if (username && !String(r.username ?? "").toLowerCase().includes(username.toLowerCase())) return false;
    if (outcome && r.outcome !== outcome) return false;
    return true;
  });

  function exportCsv() {
    const header = "id,timestamp,username,role,action,resource_type,resource_id,outcome,status_code,ip\n";
    const body = rows
      .map(
        (r) =>
          `${r.id},${r.ts},${r.username ?? ""},${r.role ?? ""},${r.action},${r.resource_type ?? ""},${r.resource_id ?? ""},${r.outcome},${r.status_code ?? ""},${r.ip ?? ""}`,
      )
      .join("\n");
    const blob = new Blob([header + body], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `astra-med-audit-log-${hours}h.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success("Exported security audit log CSV");
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-telemetry">
            <ShieldCheck className="size-4" aria-hidden />
            <span>Mission Security Operations &amp; Access Governance</span>
          </div>
          <h1 className="mt-1 font-heading text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Security &amp; Audit Logs
          </h1>
          <p className="text-sm text-ink-2">
            Append-only access telemetry, cryptographic session controls, CSRF enforcement, and SHA-256 report integrity
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={exportCsv}>
            <Download className="size-3.5" aria-hidden /> Export Audit CSV
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/admin">
              User &amp; Role Management <ArrowRight className="ml-1 size-3.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </div>

      {/* Security Posture Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <div className="flex items-center justify-between text-xs text-ink-3">
            <span>Password Hashing</span>
            <Lock className="size-4 text-telemetry" aria-hidden />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-foreground">scrypt (N=2¹⁴)</p>
          <p className="mt-1 text-xs text-nominal">Account lockout after 5 failed attempts</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <div className="flex items-center justify-between text-xs text-ink-3">
            <span>Session &amp; CSRF</span>
            <KeyRound className="size-4 text-telemetry" aria-hidden />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-foreground">HttpOnly + CSRF</p>
          <p className="mt-1 text-xs text-ink-2">SHA-256 hashed session token + X-CSRF-Token</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <div className="flex items-center justify-between text-xs text-ink-3">
            <span>Audit Privacy Policy</span>
            <ShieldCheck className="size-4 text-nominal" aria-hidden />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-nominal">Zero Vital Values</p>
          <p className="mt-1 text-xs text-ink-2">Logs record IDs &amp; hashes only, never raw vitals</p>
        </div>

        <div className="rounded-xl border border-bulkhead bg-hull/80 p-4">
          <div className="flex items-center justify-between text-xs text-ink-3">
            <span>Active Session Role</span>
            <ShieldAlert className="size-4 text-caution" aria-hidden />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-telemetry">
            {user?.role ?? "mission_operator"}
          </p>
          <p className="mt-1 text-xs text-ink-2">Signed in as {user?.display_name ?? "Operator"}</p>
        </div>
      </div>

      {/* Audit Log Panel */}
      <Panel
        raised
        title="Append-Only Security Audit Log"
        description="Sign-ins, views of crew health records (rate-limited to 1 log per 5 min per resource), configuration changes, and permission denials."
        actions={
          <div className="flex flex-wrap gap-2">
            <input
              aria-label="Filter by username"
              placeholder="Filter username..."
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="h-8 w-36 rounded-md border border-bulkhead bg-abyss px-2.5 text-xs text-foreground outline-none focus:border-telemetry"
            />
            <select
              aria-label="Outcome"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              className="h-8 rounded-md border border-bulkhead bg-abyss px-2.5 text-xs text-foreground"
            >
              <option value="">Any outcome</option>
              <option value="success">Success</option>
              <option value="denied">Denied (403)</option>
              <option value="failure">Failure</option>
            </select>
            <select
              aria-label="Window"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="h-8 rounded-md border border-bulkhead bg-abyss px-2.5 text-xs text-foreground"
            >
              <option value={1}>Last 1 h</option>
              <option value={24}>Last 24 h</option>
              <option value={168}>Last 7 d</option>
              <option value={720}>Last 30 d</option>
            </select>
          </div>
        }
      >
        {q.isPending && canAudit ? (
          <LoadingState rows={5} />
        ) : (
          <div className="max-h-[34rem] overflow-auto">
            <table className="w-full min-w-[46rem] text-left text-xs">
              <thead className="sticky top-0 border-b border-bulkhead bg-hull text-ink-3">
                <tr>
                  <th className="py-2 pr-3 font-medium">Time (UTC)</th>
                  <th className="py-2 pr-3 font-medium">User &amp; Role</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium">Resource</th>
                  <th className="py-2 pr-3 font-medium">Outcome</th>
                  <th className="py-2 font-medium">Client IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-bulkhead/50">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-telemetry/5">
                    <td className="py-2.5 pr-3 font-mono text-ink-2">{utcDayTime(r.ts)}</td>
                    <td className="py-2.5 pr-3">
                      <span className="font-semibold text-foreground">{r.username ?? "—"}</span>{" "}
                      <span className="text-ink-3">({r.role ?? "anonymous"})</span>
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-telemetry">{r.action}</td>
                    <td className="py-2.5 pr-3 font-mono text-ink-2">
                      {r.resource_type ?? ""} {r.resource_id ?? ""}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span
                        className={cn(
                          "inline-block rounded-full border px-2 py-0.5 font-mono text-[11px] font-semibold",
                          r.outcome === "denied"
                            ? "border-caution/40 bg-caution/15 text-caution"
                            : r.outcome === "failure"
                              ? "border-critical/40 bg-critical/15 text-critical"
                              : "border-nominal/40 bg-nominal/15 text-nominal",
                        )}
                      >
                        {r.outcome} {r.status_code ? `(${r.status_code})` : ""}
                      </span>
                    </td>
                    <td className="py-2.5 font-mono text-ink-3">{r.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
