"use client";

import { Lightbulb } from "lucide-react";
import { useState } from "react";

import { ExplanationView } from "@/components/ai/explanation-view";
import { ErrorState, LoadingState } from "@/components/data/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAlertExplanation } from "@/lib/api/hooks";
import type { Alert } from "@/lib/api/types";

export function ExplainAlertButton({ alert }: { alert: Alert }) {
  const [open, setOpen] = useState(false);
  const q = useAlertExplanation(alert.id, open);
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <Lightbulb aria-hidden /> Explain
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Why this alert fired</DialogTitle>
            <DialogDescription>{alert.title}. Experimental explanation built on simulated data; not a diagnosis.</DialogDescription>
          </DialogHeader>
          {q.isPending ? (
            <LoadingState label="Building explanation" rows={4} />
          ) : q.error ? (
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          ) : (
            <div className="space-y-4">
              <p className="rounded-md bg-abyss/50 px-3 py-2 text-xs text-ink-2">{q.data.rule}</p>
              <ExplanationView explanation={q.data.explanation} />
              {q.data.anomaly_context.length > 0 && (
                <p className="text-xs text-ink-3">
                  Anomaly ensemble around the alert: peak {Math.max(...q.data.anomaly_context.map((p) => p.ensemble_score)).toFixed(2)}x
                  threshold; {q.data.anomaly_context.filter((p) => p.flagged).length} of {q.data.anomaly_context.length} windows flagged.
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
