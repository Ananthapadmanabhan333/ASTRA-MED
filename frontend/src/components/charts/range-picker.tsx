"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { RANGE_OPTIONS, type ChartRange } from "@/lib/metrics";

export function RangePicker({
  value,
  onChange,
  includeLive = true,
}: {
  value: ChartRange;
  onChange: (v: ChartRange) => void;
  includeLive?: boolean;
}) {
  const options = includeLive ? RANGE_OPTIONS : RANGE_OPTIONS.filter((o) => o.value !== "live");
  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      value={value}
      onValueChange={(v) => v && onChange(v as ChartRange)}
      aria-label="Time range"
    >
      {options.map((o) => (
        <ToggleGroupItem key={o.value} value={o.value} className="px-2.5 text-xs">
          {o.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
