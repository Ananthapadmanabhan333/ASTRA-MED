"""Space-weather summary, radiation-related alerts and radiation intelligence.

Radiation information is kept in four separate categories that are never summed or converted
into one another:

A. measured   - absorbed dose measured on the ISS (EDA, historical missions; mGy, in water).
B. indicator  - DONKI space-weather events (flares, SEP, radiation belt, storms). No dose.
C. estimate   - a cruise dose-equivalent estimate for the fictional mission from a published
                measurement (MSL RAD, Zeitlin et al. 2013); mSv, excludes solar particle events.
D. simulated  - the ASTRA-MED simulator's crew doses and SPE test scenarios (mSv).

Units differ on purpose: absorbed dose (mGy) and dose equivalent (mSv) are different quantities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpaceWeatherEventRow
from app.space import classify, donki
from app.space import repository as repo
from app.space.provenance import DONKI

VANTAGE_NOTE = (
    "Observed from near Earth. For a spacecraft in Mars transit, an event's relevance depends on where the "
    "spacecraft is relative to the source region; this prototype does not model that geometry."
)
ESTIMATE_RATE_MSV_DAY = 1.84
ESTIMATE_SOURCE = (
    "Mars-cruise dose-equivalent rate measured inside the MSL spacecraft by the Radiation Assessment Detector "
    "(Zeitlin et al., Science 340, 2013). Applied to the fictional mission as an estimate; excludes solar "
    "particle events and does not model this spacecraft's shielding."
)


# --------------------------------------------------------------------------- alerts ----
def alert_for(e: SpaceWeatherEventRow) -> dict[str, Any] | None:
    """Prototype alert rules for radiation-relevant events. Returns None if no rule applies."""
    sev, rule = None, None
    if e.event_type == "SEP":
        sev = "advisory" if e.model_derived else "caution"
        rule = "Any solar energetic particle event (model-derived detections: advisory)"
    elif e.event_type == "FLR" and e.severity is not None and e.severity >= 1:
        sev = "caution" if e.severity >= 3 else "advisory"
        rule = "Flare at R1 or above (R3+, X-class: caution)"
    elif e.event_type == "RBE":
        sev, rule = "advisory", "Radiation belt electron enhancement"
    elif e.event_type == "GST" and e.severity is not None and e.severity >= 1:
        sev = "caution" if e.severity >= 4 else "advisory"
        rule = "Geomagnetic storm G1 or above (G4+: caution)"
    elif e.event_type == "CME" and e.severity is not None and e.severity >= 3:
        sev = "caution" if e.severity >= 4 else "advisory"
        rule = "CME of speed class O (>= 1000 km/s) or faster"
    if sev is None:
        return None
    label = donki.EVENT_TYPES[e.event_type]
    level = f" ({e.scale})" if e.scale else ""
    return {
        "id": f"swx-{e.id}",
        "event_id": e.id,
        "event_type": e.event_type,
        "severity": sev,
        "title": f"{label}{level}: {e.classification or ''}".strip().rstrip(":"),
        "event_time": e.peak_time or e.start_time,
        "rule": rule,
        "category": "indicator",
        "note": "Environmental indicator from DONKI. It is not a dose measurement for any person. " + VANTAGE_NOTE,
        "link": e.link,
    }


def alert_status(event_time: datetime, now: datetime) -> str:
    age = now - event_time
    return "active" if age <= timedelta(hours=24) else "recent" if age <= timedelta(days=3) else "past"


async def space_alerts(session: AsyncSession, now: datetime, days: int = 30) -> list[dict[str, Any]]:
    events = await repo.list_events(session, now - timedelta(days=days), now, donki.RADIATION_RELEVANT)
    out = []
    for e in events:
        a = alert_for(e)
        if a:
            a["status"] = alert_status(a["event_time"], now)
            out.append(a)
    rank = {"caution": 0, "advisory": 1}
    return sorted(out, key=lambda a: (a["status"] != "active", rank[a["severity"]], -a["event_time"].timestamp()))


# ---------------------------------------------------------------- space weather ----
async def weather_summary(session: AsyncSession, now: datetime, days: int = 30) -> dict[str, Any]:
    events = await repo.list_events(session, now - timedelta(days=days), now)
    by_type: dict[str, list[SpaceWeatherEventRow]] = defaultdict(list)
    for e in events:
        by_type[e.event_type].append(e)
    flares = [e for e in by_type["FLR"] if e.magnitude is not None]
    strongest = max(flares, key=lambda e: e.magnitude) if flares else None
    storms = [e for e in by_type["GST"] if e.magnitude is not None]
    peak_storm = max(storms, key=lambda e: e.magnitude) if storms else None
    cmes = [e for e in by_type["CME"] if e.magnitude is not None]
    fastest = max(cmes, key=lambda e: e.magnitude) if cmes else None
    flare_classes = Counter((e.raw.get("classType") or "?")[0].upper() for e in by_type["FLR"])
    return {
        "window_days": days,
        "counts": {t: len(by_type.get(t, [])) for t in donki.EVENT_TYPES},
        "flare_classes": {k: flare_classes.get(k, 0) for k in "ABCMX"},
        "strongest_flare": strongest,
        "max_storm": peak_storm,
        "fastest_cme": fastest,
        "latest": {t: (max(v, key=lambda e: e.start_time) if v else None) for t, v in by_type.items()},
        "caveats": list(DONKI.caveats),
    }


# ---------------------------------------------------------- radiation intelligence ----
async def measured_dose_summaries(session: AsyncSession) -> list[dict[str, Any]]:
    """Category A: one summary per EDA mission with dosimetry."""
    out = []
    for m in await repo.list_missions(session):
        rows = await repo.measurements(session, m.name, ("dose_gcr_mgy_day", "dose_saa_mgy_day", "dose_total_mgy_day"))
        if not rows:
            continue
        series: dict[str, list] = defaultdict(list)
        for r in rows:
            series[r.quantity].append(r)
        total = series.get("dose_total_mgy_day", [])
        if not total:
            continue
        measured_only = [r.value for r in total if not r.approximate]
        out.append({
            "mission": m.name,
            "title": m.title,
            "start": total[0].ts,
            "end": total[-1].ts,
            "days": len(total),
            "approximate_days": sum(1 for r in total if r.approximate),
            "mean_total_mgy_day": round(mean(measured_only), 4) if measured_only else None,
            "mean_gcr_mgy_day": round(mean(r.value for r in series["dose_gcr_mgy_day"] if not r.approximate), 4)
            if series.get("dose_gcr_mgy_day") and measured_only else None,
            "mean_saa_mgy_day": round(mean(r.value for r in series["dose_saa_mgy_day"] if not r.approximate), 4)
            if series.get("dose_saa_mgy_day") and measured_only else None,
            "cumulative_mgy": round(sum(r.value for r in total), 3),
        })
    return out


def _day(dt: datetime) -> date:
    return dt.astimezone(UTC).date()


async def indicator_summary(session: AsyncSession, now: datetime, days: int) -> dict[str, Any]:
    events = await repo.list_events(session, now - timedelta(days=days), now, donki.RADIATION_RELEVANT)
    counts = Counter(e.event_type for e in events)
    r1 = sum(1 for e in events if e.event_type == "FLR" and (e.severity or 0) >= 1)
    fast = sum(1 for e in events if e.event_type == "CME" and (e.severity or 0) >= 3)
    storms = sum(1 for e in events if e.event_type == "GST" and (e.severity or 0) >= 1)
    relevant = [e for e in events if alert_for(e)]
    return {
        "window_days": days,
        "sep_events": counts.get("SEP", 0),
        "flares_r1_plus": r1,
        "radiation_belt_enhancements": counts.get("RBE", 0),
        "storms_g1_plus": storms,
        "fast_cmes": fast,
        "events": relevant[:40],
    }


def exposure_timeline(days: list[date], simulated: list[dict[str, Any]],
                      events: list[SpaceWeatherEventRow]) -> list[dict[str, Any]]:
    """Daily rows on the mission axis. Each value keeps its category and unit."""
    sim_by_day: dict[date, list[float]] = defaultdict(list)
    spe_days: set[date] = set()
    for crew in simulated:
        for d in crew["daily"]:
            sim_by_day[d["day"]].append(d["dose_msv"])
            if d["solar_particle_event"]:
                spe_days.add(d["day"])
    ev_by_day: dict[date, Counter] = defaultdict(Counter)
    for e in events:
        if alert_for(e):
            ev_by_day[_day(e.peak_time or e.start_time)][e.event_type] += 1
    rows = []
    for d in days:
        sims = sim_by_day.get(d, [])
        rows.append({
            "day": d,
            "estimate_msv": ESTIMATE_RATE_MSV_DAY,
            "simulated_crew_mean_msv": round(mean(sims), 4) if sims else None,
            "simulated_spe": d in spe_days,
            "indicator_events": dict(ev_by_day.get(d, {})),
        })
    return rows


async def radiation_intelligence(session: AsyncSession, overview, now: datetime, days: int,
                                 mission_start: date) -> dict[str, Any]:
    """``overview`` is the existing phase 2 RadiationOverview (simulated crew doses)."""
    simulated = [c.model_dump() for c in overview.crew]
    indicators = await indicator_summary(session, now, days)
    mission_days = max(0, (now.date() - mission_start).days)
    events = await repo.list_events(session, now - timedelta(days=days), now, donki.RADIATION_RELEVANT)
    day_axis = [now.date() - timedelta(days=i) for i in range(days - 1, -1, -1)]
    return {
        "measured": {
            "label": "A. Measured radiation dose",
            "description": "Daily absorbed dose in water measured on the ISS during historical missions (NASA OSDR "
                           "Environmental Data App, preliminary SRAG analysis). Location dose at the experiment, not "
                           "any astronaut's dose, and not this fictional mission.",
            "unit": "mGy/day",
            "missions": await measured_dose_summaries(session),
        },
        "indicators": {
            "label": "B. Environmental radiation indicators",
            "description": "Space-weather events reported in NASA DONKI. They describe the environment near Earth and "
                           "carry no dose information.",
            **indicators,
        },
        "estimate": {
            "label": "C. Estimated exposure",
            "description": ESTIMATE_SOURCE,
            "unit": "mSv/day",
            "rate_msv_day": ESTIMATE_RATE_MSV_DAY,
            "mission_days": mission_days,
            "mission_to_date_msv": round(ESTIMATE_RATE_MSV_DAY * mission_days, 1),
        },
        "simulated": {
            "label": "D. Simulated exposure scenarios",
            "description": "Crew doses from the ASTRA-MED simulator, including simulated solar particle event "
                           "scenarios. Not measurements and not driven by DONKI events.",
            "unit": "mSv/day",
            "crew": simulated,
            "reference_career_limit_msv": overview.reference_career_limit_msv,
        },
        "timeline": exposure_timeline(day_axis, simulated, events),
        "alerts": await space_alerts(session, now, days),
        "rules": [
            "A flare, SEP or storm is never converted into a dose.",
            "Absorbed dose (mGy) and dose equivalent (mSv) are shown separately and never summed.",
            "Historical ISS measurements are never shown as current telemetry.",
        ],
    }


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0), tzinfo=UTC)
    return start, start + timedelta(days=1)


def describe_severity(e: SpaceWeatherEventRow) -> str:
    return classify.describe(e.event_type, e.severity)
