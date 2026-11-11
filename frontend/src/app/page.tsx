import { CrewBoard } from "@/components/crew/crew-board";
import { Panel } from "@/components/data/panel";
import {
  ActiveScenariosPanel,
  OpenAlertsPanel,
  RadiationBriefPanel,
  TopInsightsPanel,
} from "@/components/mission/overview-panels";

export default function MissionControlPage() {
  return (
    <div className="space-y-5">
      <h1 className="sr-only">Mission control</h1>
      <Panel
        raised
        title="Crew status"
        description="Live simulated telemetry for the fictional Helios-7 crew, updated every second."
        bodyClassName="pt-1"
      >
        <CrewBoard />
      </Panel>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <OpenAlertsPanel />
          <TopInsightsPanel />
        </div>
        <div className="space-y-5">
          <ActiveScenariosPanel />
          <RadiationBriefPanel />
        </div>
      </div>
    </div>
  );
}
