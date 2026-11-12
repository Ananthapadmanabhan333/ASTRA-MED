"""Mission timeline adapter: planned activity for future time steps.

Forecasts condition on what the crew member is *scheduled* to do (sleep, exercise, work). Here the
timeline comes from the simulator's schedule, where plan and reality coincide. A real deployment
would read the mission planning system instead; actual activity would then differ from plan.
"""

from __future__ import annotations

import pandas as pd

from app.simulator.profiles import CREW_BY_ID
from app.simulator.schedule import activity_at


def planned_steps(astronaut_id: str, index: pd.DatetimeIndex, seed: int, step_minutes: int = 30) -> pd.DataFrame:
    """Planned mean activity load, sleep fraction and dominant state for each step starting at ``index``."""
    profile = CREW_BY_ID[astronaut_id]
    rows = []
    offsets = [pd.Timedelta(minutes=2.5 + 5 * i) for i in range(step_minutes // 5)]
    for start in index:
        samples = [activity_at(profile, (start + off).to_pydatetime(), seed) for off in offsets]
        states = [s for s, _ in samples]
        rows.append({
            "activity_met": sum(m for _, m in samples) / len(samples),
            "sleep_frac": states.count("sleep") / len(states),
            "state": max(set(states), key=states.count),
        })
    return pd.DataFrame(rows, index=index)
