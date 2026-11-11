"use client";

import { useRouter } from "next/navigation";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AstronautSummary } from "@/lib/api/types";
import { crewColor } from "@/lib/crew";

export function AstronautSwitcher({
  crew,
  value,
  onChange,
  includeAll = false,
  label = "Crew member",
}: {
  crew: AstronautSummary[];
  value: string;
  onChange?: (id: string) => void;
  includeAll?: boolean;
  label?: string;
}) {
  const router = useRouter();
  const handle = (id: string) => (onChange ? onChange(id) : router.push(`/crew/${id}`));
  return (
    <Select value={value} onValueChange={handle}>
      <SelectTrigger className="w-56" aria-label={label}>
        <SelectValue placeholder="Choose crew member" />
      </SelectTrigger>
      <SelectContent>
        {includeAll && <SelectItem value="all">Whole crew</SelectItem>}
        {crew.map((a) => (
          <SelectItem key={a.id} value={a.id}>
            <span className="inline-block size-2 rounded-full" style={{ background: crewColor(a.id) }} aria-hidden />
            {a.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
