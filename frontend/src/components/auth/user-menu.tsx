"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, ShieldCheck, ShieldOff } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

export function UserMenu({ compact = false }: { compact?: boolean }) {
  const session = useAuth((s) => s.session);
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!session) return null;
  const disabled = session.method === "disabled";

  async function signOut() {
    setBusy(true);
    try {
      await api.POST("/api/auth/logout");
    } finally {
      qc.clear();
      useAuth.getState().signedOut("signed_out");
      setBusy(false);
    }
  }

  return (
    <div className={cn("flex items-center gap-2", compact ? "" : "px-4 py-3")}>
      {disabled ? (
        <ShieldOff className="size-4 shrink-0 text-caution" aria-hidden />
      ) : (
        <ShieldCheck className="size-4 shrink-0 text-nominal" aria-hidden />
      )}
      <div className={cn("min-w-0 flex-1", compact && "hidden sm:block")}>
        <p className="truncate text-sm font-medium" title={session.user.display_name}>
          {session.user.display_name}
        </p>
        <p className="truncate text-xs text-ink-3">
          {disabled ? "Authentication disabled (development)" : session.user.role_label}
        </p>
      </div>
      {!disabled && (
        <Button size="icon-sm" variant="ghost" onClick={signOut} disabled={busy} aria-label="Sign out" title="Sign out">
          <LogOut aria-hidden />
        </Button>
      )}
    </div>
  );
}
