import type { Metadata } from "next";

import { PageHeader } from "@/components/data/panel";
import { SleepView } from "@/components/sleep/sleep-view";

export const metadata: Metadata = { title: "Sleep & circadian" };

export default function SleepPage() {
  return (
    <div className="space-y-5">
      <PageHeader
        title="Sleep and circadian rhythm"
        description="Seven nights per crew member: how long they slept, and how far sleep drifted from the schedule."
      />
      <SleepView />
    </div>
  );
}
