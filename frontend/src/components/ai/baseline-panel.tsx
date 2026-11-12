"use client";

import { Panel } from "@/components/data/panel";
import { ErrorState, LoadingState } from "@/components/data/states";
import { useAiBaseline } from "@/lib/api/hooks";
import { fmt, utcDayTime } from "@/lib/format";
import { ACTIVITY_LABEL } from "@/lib/metrics";
import { cn } from "@/lib/utils";

const LEVEL: Record<string, string> = {
  cell: "activity and time of day",
  state: "activity only",
  overall: "overall",
  none: "none yet for this activity",
};

function digits(signal: string) {
  return signal === "temperature_c" ? 2 : signal === "spo2" ? 1 : 0;
}

export function BaselinePanel({ astronautId, name }: { astronautId: string; name: string }) {
  const q = useAiBaseline(astronautId);
  return (
    <Panel
      title="Personal baselines"
      description={`What is normal for ${name}: learned from stored history by activity and time of day, updated as new data arrives.`}
    >
      {q.isPending ? (
        <LoadingState rows={6} />
      ) : q.error && !q.data ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.data ? (
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <caption className="sr-only">Latest values against personal baseline</caption>
              <thead className="text-xs text-ink-2">
                <tr>
                  {["Signal", "Latest", "Expected now", "z", "Percentile", "Last 24 h", "Last 7 d", "Baseline basis"].map((h) => (
                    <th key={h} scope="col" className="py-2 pr-4 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {q.data.signals.map((s) => {
                  const c = s.current;
                  const d = digits(s.signal);
                  return (
                    <tr key={s.signal} className="border-t border-bulkhead/60">
                      <td className="py-2 pr-4">{s.label}</td>
                      <td className={cn("py-2 pr-4", c?.assessment === "high" || c?.assessment === "low" ? "text-caution" : "")}>
                        {c ? `${fmt(c.value, d)} ${s.unit}` : "—"}
                      </td>
                      <td className="py-2 pr-4 text-ink-2">
                        {c
                          ? c.expected != null
                            ? `${fmt(c.expected, d)} (${ACTIVITY_LABEL[c.state].toLowerCase()})`
                            : `not learned yet (${ACTIVITY_LABEL[c.state].toLowerCase()})`
                          : "—"}
                      </td>
                      <td className="py-2 pr-4">{c?.z != null ? `${c.z > 0 ? "+" : ""}${fmt(c.z, 1)}` : "—"}</td>
                      <td className="py-2 pr-4">{c?.percentile != null ? `${fmt(c.percentile, 0)}th` : "—"}</td>
                      <td className="py-2 pr-4 text-ink-2">
                        {s.rolling_24h.mean != null ? `${fmt(s.rolling_24h.mean, d)} ± ${fmt(s.rolling_24h.std, d)}` : "—"}
                      </td>
                      <td className="py-2 pr-4 text-ink-2">
                        {s.rolling_7d.mean != null ? `${fmt(s.rolling_7d.mean, d)} ± ${fmt(s.rolling_7d.std, d)}` : "—"}
                      </td>
                      <td className="py-2 pr-4 text-xs text-ink-3">{c ? LEVEL[c.reference_level] : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-ink-3">
            Built from {q.data.windows_used.toLocaleString()} five-minute windows ({q.data.first_ts ? utcDayTime(q.data.first_ts) : "?"} to{" "}
            {q.data.last_ts ? utcDayTime(q.data.last_ts) : "?"} UTC); last updated {utcDayTime(q.data.updated_at)} UTC. z uses the robust
            personal centre and spread for the current activity and time of day. An activity with under an hour of history
            gets no z-score rather than being compared with other activities.
          </p>
        </div>
      ) : null}
    </Panel>
  );
}
