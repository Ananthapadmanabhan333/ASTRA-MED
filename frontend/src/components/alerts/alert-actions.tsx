"use client";

import { Check, CheckCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAlertAction } from "@/lib/api/hooks";
import type { Alert } from "@/lib/api/types";

const COPY = {
  acknowledge: {
    button: "Acknowledge",
    title: "Acknowledge alert",
    body: "Acknowledging records that an operator has seen this alert. It stays open until resolved.",
    done: "Alert acknowledged",
  },
  resolve: {
    button: "Resolve",
    title: "Resolve alert",
    body: "Resolving closes the alert. If the condition continues, a new alert will open.",
    done: "Alert resolved",
  },
} as const;

export function AlertActions({ alert, size = "sm" }: { alert: Alert; size?: "sm" | "xs" }) {
  const [open, setOpen] = useState<null | "acknowledge" | "resolve">(null);
  const [note, setNote] = useState("");
  const ack = useAlertAction("acknowledge");
  const resolve = useAlertAction("resolve");
  if (alert.status === "resolved") return null;

  const mutation = open === "resolve" ? resolve : ack;
  const submit = () => {
    if (!open) return;
    const action = open;
    mutation.mutate(
      { id: alert.id, note: note.trim() || undefined },
      {
        onSuccess: () => {
          toast.success(COPY[action].done, { description: alert.title });
          setOpen(null);
          setNote("");
        },
        onError: (e) => toast.error(`Couldn't ${action} the alert`, { description: e.message }),
      },
    );
  };

  return (
    <>
      <div className="flex gap-1.5">
        {alert.status === "active" && (
          <Button size={size} variant="outline" onClick={() => setOpen("acknowledge")}>
            <Check aria-hidden /> {COPY.acknowledge.button}
          </Button>
        )}
        <Button size={size} variant="secondary" onClick={() => setOpen("resolve")}>
          <CheckCheck aria-hidden /> {COPY.resolve.button}
        </Button>
      </div>
      <Dialog open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          {open && (
            <>
              <DialogHeader>
                <DialogTitle>{COPY[open].title}</DialogTitle>
                <DialogDescription>
                  {alert.title}: {COPY[open].body}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-2">
                <Label htmlFor={`note-${alert.id}`}>Operator note (optional)</Label>
                <Textarea
                  id={`note-${alert.id}`}
                  value={note}
                  maxLength={500}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="What was checked or done"
                />
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(null)}>
                  Cancel
                </Button>
                <Button onClick={submit} disabled={mutation.isPending}>
                  {mutation.isPending ? "Saving…" : COPY[open].button}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
