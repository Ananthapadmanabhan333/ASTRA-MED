"""Mission stages of the fictional Helios-7 Earth–Mars transit.

These are configuration of the simulated mission timeline (matching ``TRANSIT_DAYS`` in
``app/services/mission.py``), used only to group data. They are not physiological phases.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    first_day: int
    last_day: int | None  # inclusive; None = open-ended
    description: str

    def contains(self, mission_day: int) -> bool:
        return mission_day >= self.first_day and (self.last_day is None or mission_day <= self.last_day)


STAGES: tuple[Stage, ...] = (
    Stage("launch_adaptation", "Launch and early adaptation", 0, 14,
          "First two weeks after departure."),
    Stage("early_transit", "Early transit", 15, 60, "Days 15–60 of the transit."),
    Stage("mid_transit", "Mid transit", 61, 150, "Days 61–150 of the transit."),
    Stage("late_transit", "Late transit", 151, 239, "Days 151–239, approaching Mars."),
    Stage("arrival", "Mars arrival", 240, None, "From the planned arrival day onward."),
)


def stage_for(mission_day: int) -> Stage:
    for stage in STAGES:
        if stage.contains(mission_day):
            return stage
    return STAGES[0]
